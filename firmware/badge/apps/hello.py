"""Hello app: a minimal working example to copy from.

Shows a label when launched (one ~30 s e-paper refresh), then reacts to the
User A / User B buttons with the LED bar, which updates instantly.
"""

import lvgl

from apps.base_app import BaseApp
from lib.button import UserA, UserB
from lib.epd import display
from lib.led_bar import leds

_BLACK = lvgl.color_hex(0x000000)
_RED = lvgl.color_hex(0xFF0000)


class HelloApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        super().__init__("Hello")
        self.sleep_ms = 50
        self.presses = 0

    def run(self):
        if self.launched:
            # Start from white paper, then let LVGL draw only the label's area.
            # Redrawing the whole 960x672 screen through LVGL is slow in Python.
            display.clear()
            scr = lvgl.obj()
            scr.remove_style_all()
            label = lvgl.label(scr)
            label.set_text("Hello, Supercon!")
            label.set_style_text_font(lvgl.font_montserrat_48, 0)
            label.set_style_text_color(_RED, 0)
            label.center()
            lvgl.screen_load(scr)
            scr.update_layout()
            display.lv_display.inv_p = 0
            label.invalidate()
            lvgl.refr_now(display.lv_display)
            display.update()  # starts the panel refresh in the background
            print("hello: drawn, refreshing panel")
            return

        if UserA.pressed():
            self.presses += 1
            print(f"hello: A pressed ({self.presses})")
            leds.fill((0, 0, 8))
            leds.write()
        if UserB.pressed():
            print("hello: B pressed")
            leds.fill((0, 0, 0))
            leds.write()
