"""E-Paper Display Driver for Billboard Badge

Ported from Wiring in https://github.com/PervasiveDisplays/EPD_Driver_GU_large/blob/e408154652802a82e520cc25ba04adeb347d0528/src/EPD_Driver.cpp

--COPYRIGHT--
Brief The drivers and functions of development board
Copyright (c) 2012-2021 Pervasive Displays Inc. All rights reserved.
 Authors: Pervasive Displays Inc.
 Redistribution and use in source and binary forms, with or without
 modification, are permitted provided that the following conditions
 are met:
 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in
    the documentation and/or other materials provided with the
    distribution.
 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import asyncio as aio
import btree
import framebuf
import gc
import os
from machine import Pin, SPI, SoftSPI
import micropython
from micropython import const
import time

import lvgl

from lib.large_png import show_png
from lib.led_bar import leds, NUM_LEDS

EPD_CS1_PIN = Pin(13, mode=Pin.OUT)
EPD_CS2_PIN = Pin(3, mode=Pin.OUT)
EPD_BUSY1_PIN = Pin(12, mode=Pin.IN)
EPD_BUSY2_PIN = Pin(8, mode=Pin.IN)
EPD_DC_PIN = Pin(10, mode=Pin.OUT)  # Data High Command Low
EPD_RST_PIN = Pin(11, mode=Pin.OUT)
EPD_SCL_PIN = Pin(21, mode=Pin.OUT)
EPD_SDA_PIN = Pin(47, mode=Pin.OUT)
EPD_SPI_MISO_PIN = Pin(45, mode=Pin.IN)  # Not connected, signal not needed
EPD_PWR_EN_PIN = 48


pdi_cp = 0x9608
pdi_size = 0x96  # 9.69"
display_width = const(960)
half_width = const(display_width // 2)
display_height = const(672)
# Frame-buffer size = width * height / 8 * depth, uint32_t
# image_data_size is really only half the panel pixels, of one color
half_frame_one_color_size = const(display_height * display_width // (8 * 2))
# The width of rows in the full-frame and half-frame framebuffers
# Counting bytes, not pixels, since each byte is 8 packed pixels
display_width_bytes = const(display_width // 8)
display_half_width_bytes = const(display_width_bytes // 2)


# Two displays use different bit orders
def reverse_byte(byte: int) -> int:
    byte = (byte & 0xF0) >> 4 | (byte & 0x0F) << 4
    byte = (byte & 0xCC) >> 2 | (byte & 0x33) << 2
    byte = (byte & 0xAA) >> 1 | (byte & 0x55) << 1
    return byte


# Pre-computed 256-byte LUT for instant bit reversal
_REVERSE_LUT = bytearray(256)
for _i in range(256):
    _REVERSE_LUT[_i] = reverse_byte(_i)


@micropython.viper
def _viper_lv_flush(
    src: ptr8,
    fb_black: ptr8,
    fb_red: ptr8,
    x1: int,
    y1: int,
    w: int,
    h: int,
    stride: int,
):
    width = 960
    for row in range(h):
        base = (y1 + row) * width + x1
        row_off = row * stride
        for col in range(w):
            i = row_off + (col << 1)
            c = src[i] | (src[i + 1] << 8)  # RGB565, little-endian
            idx = base + col
            byte_idx = idx >> 3
            mask = 1 << (7 - (idx & 7))
            clear = mask ^ 0xFF
            bits = c & 0x8410
            if bits == 0x8000:
                fb_red[byte_idx] |= mask
                fb_black[byte_idx] &= clear
            elif bits == 0:
                fb_black[byte_idx] |= mask
                fb_red[byte_idx] &= clear
            else:
                fb_black[byte_idx] &= clear
                fb_red[byte_idx] &= clear


@micropython.viper
def _fast_split_and_reverse(src_fb: ptr8, dst_left: ptr8, dst_right: ptr8, lut: ptr8):
    for r in range(672):
        src_row = r * 120
        dst_row = r * 60
        for c in range(60):
            dst_left[dst_row + c] = lut[src_fb[src_row + c]]
            dst_right[dst_row + c] = lut[src_fb[src_row + 60 + c]]


@micropython.viper
def _fast_split_no_reverse(src_fb: ptr8, dst_left: ptr8, dst_right: ptr8):
    for r in range(672):
        src_row = r * 120
        dst_row = r * 60
        for c in range(60):
            dst_left[dst_row + c] = src_fb[src_row + c]
            dst_right[dst_row + c] = src_fb[src_row + 60 + c]


# ---- fast refresh (ported from upstream PR #3 by FacioErgoSum) ------------
# On driver B the panel runs each refresh for a fixed ~1 s, so a fast update
# re-triggers the latched short waveform this many times.
FAST_PULLS_B = 3
FAST_PULLS_8 = 1
# If this file exists on the badge, fast requests become normal refreshes.
NO_FAST_REFRESH_PATH = "/data/no_fast_refresh"


def _keep_red_lut(lut, group_size, groups):
    """Copy of a fast LUT with the red tables (2 and 3) replaced by idle
    groups, so red pixels get no drive. Table index is (red bit << 1) | bw bit;
    the idle group is the table's own last VCOM group (ground, one frame)."""
    b = bytearray(lut)
    idle_at = (4 * groups + groups - 1) * group_size
    idle = bytes(b[idle_at:idle_at + group_size])
    for t in (2, 3):
        for g in range(groups):
            o = (t * groups + g) * group_size
            b[o:o + group_size] = idle
    return bytes(b)


class EPaperDisplay:
    width = display_width
    height = display_height

    def __init__(self) -> None:
        print("Initializing E-Paper Display (Fast Hardware SPI + Viper)")
        EPD_DC_PIN.value(True)
        EPD_RST_PIN.value(True)
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)
        try:
            self.spi = SPI(
                1,
                baudrate=20_000_000,
                sck=EPD_SCL_PIN,
                mosi=EPD_SDA_PIN,
                miso=EPD_SPI_MISO_PIN,
            )
        except Exception:
            self.spi = SoftSPI(
                baudrate=8_000_000,
                sck=EPD_SCL_PIN,
                mosi=EPD_SDA_PIN,
                miso=EPD_SPI_MISO_PIN,
            )
            self.spi.init()

        try:
            with open("/data/hwconf", "rb") as f:
                hwconf = btree.open(f)
                display_pn = hwconf.get(b"display_pn", b"B1")
                if display_pn == b"84":
                    self._reverse_fb_bits = False
                else:
                    self._reverse_fb_bits = True
        except OSError:
            self._reverse_fb_bits = True
        # E2969JS084 = "driver 8", E2969JS0B1 = "driver B" (see rendered_luts.py)
        self._driver_b = self._reverse_fb_bits
        self._fast_luts = None  # loaded on the first fast update
        self._request = (False, None, False)  # fast, passes, keep_red

        # The framebuffers are set and display should be updated.
        self._framebuffer_ready = aio.Event()

        """Each byte is a mini-row of 8 bits for pixels of one color (1 sets the color, 0 is white)
        Bytes are in rows across the screen, as seen on the badge
        0 ------------------------> 59 [60 bytes per row]
        60 ----------------------> 119
        ...                        ...
        [672 rows of 60 bytes per row]
        """
        self._framebuffer_black = bytearray(half_frame_one_color_size * 2)
        self._framebuffer_red = bytearray(half_frame_one_color_size * 2)
        # Framebuffers that can be drawn to directly
        self.black = framebuf.FrameBuffer(
            self._framebuffer_black, display_width, display_height, framebuf.MONO_HLSB
        )
        self.red = framebuf.FrameBuffer(
            self._framebuffer_red, display_width, display_height, framebuf.MONO_HLSB
        )

        # Is the display done updating? Start set since the display is not updating before boot.
        self._display_updated = aio.Event()
        self._display_updated.set()
        gc.collect()

        # Set up lvgl (deinit first if soft-rebooted so C pointers don't corrupt)
        if hasattr(lvgl, "is_initialized") and lvgl.is_initialized():
            if hasattr(lvgl, "deinit"):
                lvgl.deinit()
        lvgl.init()
        # Give LVGL a buffer 2-bytes-per-pixel for RGB565 format
        self._lv_draw_buf = bytearray(display_width * display_height * 2)

        self.lv_display = lvgl.display_create(display_width, display_height)
        self.lv_display.set_color_format(lvgl.COLOR_FORMAT.RGB565)
        self.lv_display.set_buffers(
            self._lv_draw_buf,
            None,
            len(self._lv_draw_buf),
            lvgl.DISPLAY_RENDER_MODE.PARTIAL,
        )
        self.lv_display.set_flush_cb(self._lv_flush)
        self.lv_screen = lvgl.screen_active()
        self.lv_screen.set_size(display_width, display_height)

    def _lv_flush(self, disp, area, color_p):
        print("Calling EPaperDisplay._lv_flush (Viper)")
        x1, y1 = area.x1, area.y1
        w = area.x2 - x1 + 1
        h = area.y2 - y1 + 1
        try:
            stride = lvgl.draw_buf_width_to_stride(w, lvgl.COLOR_FORMAT.RGB565)
        except AttributeError:
            stride = w * 2
        src = color_p.__dereference__(stride * h)
        _viper_lv_flush(
            src,
            self._framebuffer_black,
            self._framebuffer_red,
            x1,
            y1,
            w,
            h,
            stride,
        )
        disp.flush_ready()

    def update(self, fast=False, passes=None, keep_red=False):
        """Done updating the framebuffer, update the display with the contents.

        fast=True: short waveform (~4-6 s instead of ~35 s), black and white
        only — red comes up pale, and ghosting builds up, so do a normal
        update now and then and for anything with red. keep_red=True leaves
        red already on the panel undriven. passes overrides the pull count.
        Ported from upstream PR #3 (FacioErgoSum). Create /data/no_fast_refresh
        on the badge to turn every fast request into a normal refresh.
        """
        self._request = (fast, passes, keep_red)
        self._display_updated.clear()
        self._framebuffer_ready.set()

    @staticmethod
    def fast_refresh_allowed():
        try:
            os.stat(NO_FAST_REFRESH_PATH)
            return False
        except OSError:
            return True

    def clear(self):
        """Clear framebuffers to full white"""
        self.black.fill(0)
        self.red.fill(0)

    def is_done_updating(self):
        """Is the display done updating?"""
        return self._display_updated.is_set()

    def draw_image(self, image, height: int, width: int, row: int = 0, col: int = 0):
        for img_r in range(height):
            for img_c in range(width):
                color = image[img_r][img_c]
                red = color[0] > 127
                black = color[0] < 128 and color[1] < 128 and color[2] < 128
                self.black.pixel((col + img_c), (row + img_r), int(black))
                self.red.pixel((col + img_c), (row + img_r), int(red))

    def draw_png(self, filename: str, row: int = 0, col: int = 0):
        gc.collect()
        print(f"Loading {filename} This will take a while... {time.time()}")
        show_png(filename, self._framebuffer_black, self._framebuffer_red, row, col)
        print("Done loading png")
        gc.collect()

    async def run(self):
        black_left = bytearray(half_frame_one_color_size)
        black_right = bytearray(half_frame_one_color_size)
        red_left = bytearray(half_frame_one_color_size)
        red_right = bytearray(half_frame_one_color_size)
        while True:
            if self._framebuffer_ready.is_set():
                self._display_updated.clear()
                fast, passes, keep_red = self._request
                if fast and not self.fast_refresh_allowed():
                    print("EPD: fast refresh switched off (%s)" % NO_FAST_REFRESH_PATH)
                    fast = False
                if fast and self._fast_lut(keep_red) is None:
                    fast = False
                mode = "fast" if fast else "full"
                progress = aio.create_task(self._led_progress(self._refresh_ms[mode]))
                started = time.ticks_ms()
                t0 = time.ticks_ms()
                if self._reverse_fb_bits:
                    _fast_split_and_reverse(
                        self._framebuffer_black, black_left, black_right, _REVERSE_LUT
                    )
                    _fast_split_and_reverse(
                        self._framebuffer_red, red_left, red_right, _REVERSE_LUT
                    )
                else:
                    _fast_split_no_reverse(
                        self._framebuffer_black, black_left, black_right
                    )
                    _fast_split_no_reverse(
                        self._framebuffer_red, red_left, red_right
                    )
                print("Viper split & reverse ms:", time.ticks_diff(time.ticks_ms(), t0))

                # Don't flip _reverse_fb_bits around this call (as PR #4
                # did): if the refresh is interrupted the flag stays wrong
                # and later images go out bit-mirrored. _send_images no
                # longer reverses, so there is nothing to switch off.
                try:
                    await self.global_update(
                        black_left, red_left, black_right, red_right,
                        fast, passes, keep_red,
                    )
                finally:
                    progress.cancel()
                took = time.ticks_diff(time.ticks_ms(), started)
                # Learn how long each kind of refresh really takes, for the bar.
                self._refresh_ms[mode] = (self._refresh_ms[mode] + took) // 2
                print("Display refresh (%s) took %d ms" % (mode, took))
                self._framebuffer_ready.clear()
                gc.collect()
                self._display_updated.set()
                await self._led_done()
            await aio.sleep_ms(50)

    # ---- refresh progress on the LED bar (works for every app) ----------

    # First guesses; replaced by measured times.
    _refresh_ms = {"full": 36000, "fast": 6000}
    _PROGRESS_LIT = (3, 2, 0)   # amber: filled part of the bar
    _PROGRESS_HEAD = (6, 4, 0)  # brighter amber: the LED currently filling
    _PROGRESS_DONE = (0, 4, 0)  # green: refresh finished

    async def _led_progress(self, expected_ms):
        """Fill the LED bar left to right over the expected refresh time."""
        start = time.ticks_ms()
        blink = False
        while True:
            frac = time.ticks_diff(time.ticks_ms(), start) / expected_ms
            lit = min(int(frac * NUM_LEDS), NUM_LEDS - 1)  # never "done" early
            blink = not blink
            frame = [self._PROGRESS_LIT if i < lit else (0, 0, 0) for i in range(NUM_LEDS)]
            frame[lit] = self._PROGRESS_HEAD if blink else (0, 0, 0)
            leds.show_overlay(frame)
            await aio.sleep_ms(250)

    async def _led_done(self):
        """Flash the bar green, then give the LEDs back to the app."""
        leds.show_overlay([self._PROGRESS_DONE] * NUM_LEDS)
        await aio.sleep_ms(1500)
        leds.clear_overlay()

    async def global_update(
        self,
        black_left: bytearray | bytes | memoryview[int],
        red_left: bytearray | bytes | memoryview[int],
        black_right: bytearray | bytes | memoryview[int],
        red_right: bytearray | bytes | memoryview[int],
        fast=False,
        passes=None,
        keep_red=False,
    ):
        wave = self._fast_lut(keep_red) if fast else None
        if wave is None:
            passes = 1
        elif passes is None:
            passes = FAST_PULLS_B if self._driver_b else FAST_PULLS_8
        print("Updating display to new image (%s)" % ("fast x%d" % passes if wave else "full"))
        await self._reset()
        tick = time.ticks_ms()
        self._send_images(black_left, red_left, black_right, red_right)
        tock = time.ticks_ms()
        print(tock - tick)

        print("display working")
        tick = time.ticks_ms()
        await self.cog_initial()
        if wave is not None:
            # After the 0x44/0x45/0xA7 sequence (which loads the OTP waveform
            # into these registers) and before the DC/DC soft start.
            self._send_index_data(0xB0, wave)
        await self._dcdc_soft_start()
        for _ in range(max(1, passes)):
            # Later passes re-trigger the latched waveform; nothing is resent.
            await self._display_refresh()
        await self._dcdc_soft_shutdown()
        print("Done updating display")
        tock = time.ticks_ms()
        print(tock - tick)

    def _fast_lut(self, keep_red):
        """The short waveform for this panel, or None (then: full refresh)."""
        if self._fast_luts is None:
            try:
                import data.rendered_luts as L
                if self._driver_b:
                    base = bytes(L.lutb_base)
                    self._fast_luts = (base, _keep_red_lut(base, 8, 10))
                else:
                    base = bytes(L.lut8_nored_clear)
                    self._fast_luts = (base, _keep_red_lut(base, 4, 9))
                del L
                gc.collect()
            except Exception as ex:
                print(f"EPD: no fast waveform ({ex}), using a full refresh")
                self._fast_luts = ()
        if not self._fast_luts:
            return None
        return self._fast_luts[1 if keep_red else 0]

    async def cog_initial(self):
        self._send_index_data(0x05, [0x7D])
        await aio.sleep_ms(200)
        self._send_index_data(0x05, [0x00])
        await aio.sleep_ms(10)
        self._send_index_data(0xD8, [0x80])  # MS_SYNC)
        self._send_index_data(0xD6, [0x00])  # BVSS
        self._send_index_data(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data(0xA7, [0x00])
        await aio.sleep_ms(100)
        self._send_index_data(0x03, [0x00, 0x11])  # OSC

        # Display 1
        self._send_index_data_left(0x44, [0x00])
        self._send_index_data_left(0x45, [0x80])
        self._send_index_data_left(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_left(0xA7, [0x00])
        await aio.sleep_ms(100)
        self._send_index_data_left(0x44, [0x06])
        self._send_index_data_left(0x45, [0x82])  # Temperature 0x82@25C
        self._send_index_data_left(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_left(0xA7, [0x00])
        await aio.sleep_ms(100)

        # Display 2
        self._send_index_data_right(0x44, [0x00])
        self._send_index_data_right(0x45, [0x80])
        self._send_index_data_right(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_right(0xA7, [0x00])
        await aio.sleep_ms(100)
        self._send_index_data_right(0x44, [0x06])
        self._send_index_data_right(0x45, [0x82])  # Temperature 0x82@25C
        self._send_index_data_right(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_right(0xA7, [0x00])
        await aio.sleep_ms(100)

        self._send_index_data(0x60, [0x25])  # TCON
        self._send_index_data_left(0x61, [0x01])  # STV_DIR for Display 1
        self._send_index_data(0x02, [0x00])  # VCOM

    async def cog_poweroff(self):
        """CoG shutdown function
        Shuts down the CoG and DC/DC circuit after all update functions
        """
        self._send_index_data(0x09, [0x7F, 0x7D, 0x00])
        await aio.sleep_ms(200)
        while not EPD_BUSY1_PIN.value() or not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(1)
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        await aio.sleep_ms(150)
        EPD_RST_PIN.value(False)

    def _send_index_data(self, index: int, data: bytes | list):
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes([index]))
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)
        EPD_DC_PIN.value(True)
        EPD_CS1_PIN.value(False)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes(data))
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)

    def _send_index_data_left(self, index: int, data: bytes | list | memoryview[int]):
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        EPD_CS2_PIN.value(True)
        self.spi.write(bytes([index]))
        EPD_CS1_PIN.value(True)
        EPD_DC_PIN.value(True)
        EPD_CS1_PIN.value(False)
        self.spi.write(bytes(data))
        EPD_CS1_PIN.value(True)

    def _send_index_data_right(self, index: int, data: bytes | list | memoryview[int]):
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes([index]))
        EPD_CS2_PIN.value(True)
        EPD_DC_PIN.value(True)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes(data))
        EPD_CS2_PIN.value(True)

    async def _display_refresh(self):
        while not EPD_BUSY1_PIN.value() or not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(100)
        self._send_index_data(0x15, [0x3C])
        await aio.sleep_ms(5)

    async def _reset(self):
        """CoG driver power-on hard reset"""
        await aio.sleep_ms(200)
        EPD_RST_PIN.value(True)
        await aio.sleep_ms(20)
        EPD_RST_PIN.value(False)
        await aio.sleep_ms(200)
        EPD_RST_PIN.value(True)
        await aio.sleep_ms(200)
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)
        await aio.sleep_ms(5)

    def _send_images(
        self,
        black_left: bytearray | bytes | memoryview[int],
        red_left: bytearray | bytes | memoryview[int],
        black_right: bytearray | bytes | memoryview[int],
        red_right: bytearray | bytes | memoryview[int],
    ):
        assert len(black_left) == half_frame_one_color_size
        assert len(red_left) == half_frame_one_color_size
        assert len(black_right) == half_frame_one_color_size
        assert len(red_right) == half_frame_one_color_size

        # The halves arrive already bit-reversed where the panel needs it
        # (run() does that in one viper pass), so nothing to do here.

        # DUW for both left and right halves
        self._send_index_data(0x13, [0x00, 0x3B, 0x00, 0x00, 0x9F, 0x02])
        # DRFW for Both left and right halves
        self._send_index_data(0x90, [0x00, 0x3B, 0x00, 0xA9])
        ram_rw_data = [0x3B, 0x00, 0x14]
        self._send_index_data_left(0x12, ram_rw_data)  # RAM_RW for left half
        self._send_index_data_left(0x10, black_left)  # Black frame for left half
        self._send_index_data_left(0x12, ram_rw_data)  # RAM_RW for left half
        self._send_index_data_left(0x11, red_left)  # Red frame for left half
        self._send_index_data_right(0x12, ram_rw_data)  # RAM_RW for right half
        self._send_index_data_right(0x10, black_right)  # black frame for right half
        self._send_index_data_right(0x12, ram_rw_data)  # RAM_RW for right half
        self._send_index_data_right(0x11, red_right)  # Red frame for right half

    async def _dcdc_soft_start(self):
        """DC-DC soft-start command
        Implemented after image data are uploaded to CoG
        Specific to mid-sized EPDs only
        """
        self._send_index_data(0x51, [0x50, 0x01])

        for val in range(1, 5):
            self._send_index_data(0x09, [0x1F])
            self._send_index_data(0x51, [0x50, val])
            self._send_index_data(0x09, [0x9F])
            await aio.sleep_ms(2)

        for val in range(1, 11):
            self._send_index_data(0x09, [0x1F])
            self._send_index_data(0x51, [0x0A, val])
            self._send_index_data(0x09, [0x9F])
            await aio.sleep_ms(2)

        for val in range(3, 11):
            self._send_index_data(0x09, [0x7F])
            self._send_index_data(0x51, [0x0A, val])
            self._send_index_data(0x09, [0xFF])
            await aio.sleep_ms(2)

        for val in range(9, 1, -1):
            self._send_index_data(0x09, [0x7F])
            self._send_index_data(0x51, [val, 0x0A])
            self._send_index_data(0x09, [0xFF])
            await aio.sleep_ms(2)

        self._send_index_data(0x09, [0xFF])
        await aio.sleep_ms(10)

    async def _dcdc_soft_shutdown(self):
        """DC-DC soft-shutdown command
        Implemented after image data are uploaded to CoG
        Specific to mid-sized EPDs only
        """
        while not EPD_BUSY1_PIN.value() or not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(100)
        self._send_index_data(0x09, [0x7F])
        self._send_index_data(0x05, [0x7D])
        self._send_index_data(0x09, [0x00])
        await aio.sleep_ms(200)
        while not EPD_BUSY1_PIN.value() or not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(100)
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        EPD_RST_PIN.value(False)
        EPD_CS1_PIN.value(True)


display = EPaperDisplay()
