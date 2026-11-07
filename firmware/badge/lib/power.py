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

Every LOG_EVERY_S it appends input voltage and sleep stats to /data/power.log
(capped), to estimate battery life.
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
LOG_EVERY_S = 600
LOG_MAX_BYTES = 8192
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


def forced():
    try:
        os.stat(FORCE_PATH)
        return True
    except OSError:
        return False


def on_battery():
    return forced() or input_volts() < USB_VOLTS


def _log(line):
    try:
        try:
            if os.stat(LOG_PATH)[6] > LOG_MAX_BYTES:
                os.remove(LOG_PATH)
        except OSError:
            pass
        with open(LOG_PATH, "a") as f:
            f.write("%d %s\n" % (time.time(), line))
    except OSError:
        pass


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

    def _sleep_chunk(self):
        """Light-sleep up to CHUNK_MS; True if a button press woke us."""
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < CHUNK_MS:
            machine.lightsleep(POLL_MS)
            if _pressed_raw():
                self.slept_ms += time.ticks_diff(time.ticks_ms(), start)
                return True
        self.slept_ms += time.ticks_diff(time.ticks_ms(), start)
        return False

    async def run(self, display):
        last_log = time.time()
        _log("start, input %.2f V, %s" % (input_volts(), "battery" if on_battery() else "USB"))
        wait_ms = 1000
        while True:
            await aio.sleep_ms(wait_ms)
            wait_ms = 1000
            now = time.ticks_ms()
            if time.time() - last_log >= LOG_EVERY_S:
                last_log = time.time()
                _log("input %.2f V, %d sleeps, %d s asleep" % (
                    input_volts(), self.sleeps, self.slept_ms // 1000))
            busy = not display.is_done_updating() or _any_button()
            if busy:
                self.last_active = now
            if busy or not on_battery() or time.ticks_diff(now, self.last_active) < IDLE_S * 1000:
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
