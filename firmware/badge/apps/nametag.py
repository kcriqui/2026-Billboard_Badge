"""Nametag app: the "Hello I am" tag, plus any photos in /data/photos.

User A: next picture, User B: previous. The list starts with the name tag:
data/graphics/hello_i_am_<name>.png if one exists (tools/make_nametag.py),
else the blank tag with LVGL text. Photos come from tools/make_photo.py.
Presses during a panel refresh (~35 s) are ignored.
"""

import os

import lvgl

from apps.base_app import BaseApp
from lib.button import UserA, UserB
from lib.epd import display, display_height
from lib.led_bar import leds


_WHITE = lvgl.color_hex(0xFFFFFF)
_RED = lvgl.color_hex(0xFF0000)
_BLACK = lvgl.color_hex(0x000000)
_FONT = lvgl.font_montserrat_48
# White name band on hello_i_am_blank.png. Center the plate there.
_NAME_TOP = 221
_NAME_BOTTOM = 557
_NAME_DY = (_NAME_TOP + _NAME_BOTTOM) // 2 - display_height // 2
_BLANK = "/data/graphics/hello_i_am_blank.png"
_PHOTO_DIR = "/data/photos"


def _named_tag():
    for name in sorted(os.listdir("/data/graphics")):
        if name.startswith("hello_i_am_") and name.endswith(".png") and name != "hello_i_am_blank.png":
            return "/data/graphics/" + name
    return None


def _pages():
    """Name tag first, then the photos."""
    pages = [_named_tag() or _BLANK]
    try:
        pages += sorted(_PHOTO_DIR + "/" + f for f in os.listdir(_PHOTO_DIR) if f.endswith(".png"))
    except OSError:
        pass
    return pages


class NametagApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        self.name = "Nametag"
        self.sleep_ms = 100
        self.launched = False
        self.index = 0

    def run(self):
        if self.launched:
            self._show()
            return
        step = 0
        if UserA.pressed():
            step = 1
        if UserB.pressed():
            step = -1
        if step and display.is_done_updating():
            self.index += step
            self._show()

    def _show(self):
        pages = _pages()
        self.index %= len(pages)
        page = pages[self.index]
        print("nametag: showing", page)
        leds.fill((0, 1, 1))
        display.clear()
        display.draw_png(page)
        if page == _BLANK:
            self._blank_text()
        display.update()
        leds.fill((0, 1, 0))

    def _blank_text(self):
        """Overlay LVGL text on the blank tag (only used without a named tag)."""
        scr = lvgl.obj()
        scr.remove_style_all()
        scr.set_size(lvgl.pct(100), lvgl.pct(100))
        scr.set_style_bg_opa(lvgl.OPA.TRANSP, 0)

        plate = lvgl.obj(scr)
        plate.remove_style_all()
        plate.set_size(lvgl.SIZE_CONTENT, lvgl.SIZE_CONTENT)
        plate.align(lvgl.ALIGN.CENTER, 0, _NAME_DY)
        plate.set_flex_flow(lvgl.FLEX_FLOW.COLUMN)
        plate.set_flex_align(
            lvgl.FLEX_ALIGN.CENTER,
            lvgl.FLEX_ALIGN.CENTER,
            lvgl.FLEX_ALIGN.CENTER,
        )
        plate.set_style_bg_color(_WHITE, 0)
        plate.set_style_bg_opa(lvgl.OPA.COVER, 0)
        plate.set_style_pad_all(8, 0)

        for _ in range(2):
            label = lvgl.label(plate)
            label.set_text("")
            label.set_style_text_color(_BLACK, 0)
            label.set_style_text_font(_FONT, 0)

        lvgl.screen_load(scr)
        scr.update_layout()
        # screen_load dirties the whole panel. Keep the PNG everywhere else.
        display.lv_display.inv_p = 0
        plate.invalidate()
        lvgl.refr_now(display.lv_display)
