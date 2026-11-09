"""Battery mode: sleep between display updates, for any app.

Runs as a background task (started in main.py). When the badge is on
battery, the screen has finished refreshing and no button has been touched
for IDLE_S seconds, it turns WiFi off, blanks the LEDs and light-sleeps.

How it wakes: in POLL_MS light sleeps, reading all four buttons in between,
so any press longer than ~POLL_MS wakes it and then acts normally (User A in
XKCD fetches a comic). Every CHUNK_MS it stays awake for AWAKE_MS so apps
that update on a timer (XKCD, Gallery) run, at most CHUNK_MS late; they need
no changes, and XKCD reconnects WiFi at each update anyway.

Why polling: this firmware only allows pin wake on RTC pins (User A and
Menu - are on GPIO 39/40), the button pull-ups drop out in light sleep (so
armed pins woke it at once), and holding the pins through sleep hung the
chip. Timer-only light sleep works.

On battery = input voltage below USB_VOLTS (USB reads ~4.6-4.7 V on this
badge, a LiPo at most 4.2 V). Create /data/battery_mode to force it on over
USB for testing; the USB serial link is unusable while it sleeps (press a
button, then connect within IDLE_S).

Create /data/no_sleep to keep it awake on battery, to compare battery life
with and without this mode.

Battery log: on battery, every LOG_EVERY_S a CSV line goes to /data/power.log
(one older file kept as power.log.old):
    uptime_s,volts,mode,sleeps,asleep_s,oled
mode is "sleep" or "awake" (/data/no_sleep); oled is 1 if one is attached.
A "# boot" line starts each run. Uptime survives light sleep.
"""

import asyncio as aio
import os
import time

import machine

from lib import wifi
from lib.board import reg_in_v_sns
from lib.button import (Boot, MenuMinus, MenuPlus, UserA, UserB, MENU_MINUS_PIN,
                        MENU_PLUS_PIN, USER_A_PIN, USER_B_PIN)
from lib.led_bar import NUM_LEDS, leds

USB_VOLTS = 4.45
FORCE_PATH = "/data/battery_mode"
IDLE_S = 15
POLL_MS = 150     # light-sleep step; presses shorter than this may be missed
CHUNK_MS = 20000  # asleep this long between short awake windows
AWAKE_MS = 300    # awake window for apps' timers (they poll every ~100 ms)
LOG_PATH = "/data/power.log"
NO_SLEEP_PATH = "/data/no_sleep"
LOG_OLD_PATH = "/data/power.log.old"
LOG_EVERY_S = 300
LOG_MAX_BYTES = 32768
LIFE_TICK_POLLS = 3    # OLED idle animation: ~2 steps/s while asleep (Kevin)
_BUTTONS = (MenuMinus, MenuPlus, UserA, UserB)
_ALIVE = (0, 0, 1)  # dim blue blink on LED 0 at each awake window
_OFF = [(0, 0, 0)] * NUM_LEDS

# Raw button pins (already set up as pulled-up inputs by lib.button);
# the button scanner doesn't run while we sleep, so read these directly.
_PINS = [machine.Pin(n) for n in (MENU_MINUS_PIN, MENU_PLUS_PIN, USER_A_PIN, USER_B_PIN)]


def input_volts():
    """Regulator input voltage (USB or battery); the ADC sees half of it."""
    total = 0
    for _ in range(8):
        total += reg_in_v_sns.read_uv()
    return 2 * total / 8 / 1_000_000


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def forced():
    return _exists(FORCE_PATH)


def no_sleep():
    return _exists(NO_SLEEP_PATH)


def on_battery():
    return forced() or input_volts() < USB_VOLTS


def _log(line):
    try:
        try:
            if os.stat(LOG_PATH)[6] > LOG_MAX_BYTES:
                try:
                    os.remove(LOG_OLD_PATH)
                except OSError:
                    pass
                os.rename(LOG_PATH, LOG_OLD_PATH)
        except OSError:
            pass
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _oled_attached():
    try:
        from lib.oled import oled
        return 1 if oled.i2c is not None else 0
    except Exception:
        return 0


def _any_button():
    return any(b.value for b in _BUTTONS) or Boot.value


def _pressed_raw():
    return any(p.value() == 0 for p in _PINS)


class Power:
    def __init__(self):
        self.last_active = time.ticks_ms()
        self.sleeping = False
        self.sleeps = 0
        self.slept_ms = 0
        self.idle_tick = None   # called now and then while asleep (OLED)

    def _sleep_chunk(self):
        """Light-sleep up to CHUNK_MS; True if a button press woke us."""
        start = time.ticks_ms()
        polls = 0
        while time.ticks_diff(time.ticks_ms(), start) < CHUNK_MS:
            machine.lightsleep(POLL_MS)
            if _pressed_raw():
                self.slept_ms += time.ticks_diff(time.ticks_ms(), start)
                return True
            polls += 1
            if polls >= LIFE_TICK_POLLS and self.idle_tick:
                polls = 0
                self.idle_tick()
        self.slept_ms += time.ticks_diff(time.ticks_ms(), start)
        return False

    async def run(self, display):
        last_log = time.ticks_ms()
        stay_awake = no_sleep()
        v = input_volts()
        _log("# boot,%.2f,%s,%s" % (v, "battery" if v < USB_VOLTS else "usb",
                                    "awake" if stay_awake else "sleep"))
        wait_ms = 1000
        while True:
            await aio.sleep_ms(wait_ms)
            wait_ms = 1000
            now = time.ticks_ms()
            if time.ticks_diff(now, last_log) >= LOG_EVERY_S * 1000:
                last_log = now
                v = input_volts()
                if v < USB_VOLTS:  # USB readings say nothing about the battery
                    _log("%d,%.2f,%s,%d,%d,%d" % (
                        now // 1000, v, "awake" if stay_awake else "sleep",
                        self.sleeps, self.slept_ms // 1000, _oled_attached()))
            busy = not display.is_done_updating() or _any_button()
            if busy:
                self.last_active = now
            if busy or stay_awake or not on_battery() or time.ticks_diff(now, self.last_active) < IDLE_S * 1000:
                if self.sleeping:  # back to normal: give the LEDs back
                    self.sleeping = False
                    leds.clear_overlay()
                continue

            if not self.sleeping:
                self.sleeping = True
                wifi.off()
            leds.show_overlay(_OFF)
            woke = self._sleep_chunk()
            self.sleeps += 1
            if woke:
                # Let the button scanner see the press; it acts as normal.
                self.last_active = time.ticks_ms()
                self.sleeping = False
                leds.clear_overlay()
                wait_ms = 10
            else:
                # Short awake window so timer-driven apps can run, with a
                # brief sign of life on LED 0.
                leds.show_overlay([_ALIVE] + _OFF[1:])
                await aio.sleep_ms(40)
                leds.show_overlay(_OFF)
                wait_ms = AWAKE_MS


power = Power()
