"""
graphics_api.py — Hardware-Accelerated Sprite Graphics API
===========================================================

Provides a Python interface to the on-chip sprite compositor engine
implemented in hdmi_mux.v (PL side).  The compositor can overwrite a
configurable rectangular region of the HDMI output with custom pixel data
in real-time (sub-frame latency), without any GPU or CPU rendering on the
critical video path.

Key features
------------
  • show_banner(text, duration, ...)
        Renders text/icons using OpenCV, uploads pixels into FPGA BRAM,
        and arms the hardware compositor. Banner disappears automatically
        after `duration` seconds using a background thread.

  • show_authorized_screen(username, confidence, duration)
        Full "ACCESS GRANTED" branded banner with a green accent bar.

  • show_unauthorized_screen(duration)
        "ACCESS DENIED" red banner — typically shown while auth is failing.

  • show_custom(pixels, ...)
        Low-level: supply a raw NumPy array (H×W×3, uint8, RGB) and place it
        anywhere on screen.

  • update_alpha(alpha)
        Set blending weight (0=transparent … 15=opaque) at any time.

  • hide()
        Immediately disable the compositor (zero-latency hardware write).

  • set_position(x0, y0, x1, y1)
        Reposition the sprite rectangle without re-uploading pixels.

BRAM write protocol
-------------------
Each pixel is written sequentially via the AXI-Lite sprite register window:
  1. Write sprite_wr_addr (offset 0x1C) — pixel index (row * W + col)
  2. Write sprite_wr_data (offset 0x20) — RGB24 value
  3. Pulse sprite_wr_en  (offset 0x18) — one AXI write (value=1)

Transparent colour convention: RGB (1,1,1) → hardware passes background through.
Use (0,0,0) for solid black; the API remaps (0,0,0) → (1,1,1) automatically.

AXI-Lite sprite register map (base address: 0x43C10000 by default)
-------------------------------------------------------------------
  Offset  Name             Width   Notes
  0x00    sprite_visible   1 bit   1 = compositor active
  0x04    sprite_alpha     4 bit   0..15 blending weight
  0x08    sprite_x0        11 bit  left edge (0..1279)
  0x0C    sprite_y0        10 bit  top  edge (0..719)
  0x10    sprite_x1        11 bit  right edge exclusive
  0x14    sprite_y1        10 bit  bottom edge exclusive
  0x18    sprite_wr_en     1 bit   pulse to commit wr_addr/wr_data
  0x1C    sprite_wr_addr   17 bit  BRAM write address (max 65 535)
  0x20    sprite_wr_data   24 bit  RGB888 pixel value

Usage example
-------------
>>> from graphics_api import HardwareGraphicsAPI
>>> gfx = HardwareGraphicsAPI(fpga_interface)
>>> gfx.show_authorized_screen("Ramsey", confidence=0.94, duration=4.0)
>>> # ... banner appears on the live HDMI monitor for 4 seconds ...
"""

import cv2
import numpy as np
import threading
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# AXI-Lite register offsets (must match top.v / create_project.tcl)
# ─────────────────────────────────────────────────────────────────────────────
_REG_VISIBLE    = 0x00
_REG_ALPHA      = 0x04
_REG_X0         = 0x08
_REG_Y0         = 0x0C
_REG_X1         = 0x10
_REG_Y1         = 0x14
_REG_WR_EN      = 0x18
_REG_WR_ADDR    = 0x1C
_REG_WR_DATA    = 0x20

# Hardware BRAM canvas limits — must match `define in hdmi_mux.v
SPRITE_MAX_W    = 512
SPRITE_MAX_H    = 128

# Transparent "magic" colour remapped at the hardware level
_TRANSPARENT    = 0x010101   # RGB (1,1,1) = passthrough to background


def _rgb_to_hw(r: int, g: int, b: int) -> int:
    """Pack RGB bytes into a 24-bit hardware word, remapping pure-black → magic transparent."""
    if r == 0 and g == 0 and b == 0:
        return _TRANSPARENT   # treat (0,0,0) as solid black on the hardware
    return ((int(r) & 0xFF) << 16) | ((int(g) & 0xFF) << 8) | (int(b) & 0xFF)


# ─────────────────────────────────────────────────────────────────────────────
# HardwareGraphicsAPI
# ─────────────────────────────────────────────────────────────────────────────

class HardwareGraphicsAPI:
    """
    High-level Python driver for the FPGA sprite compositor in hdmi_mux.v.

    Parameters
    ----------
    fpga_interface : FPGAInterface
        The initialized FPGAInterface object from fpga_interface.py.
        The object must have a ``sprite_ctrl`` AXI-Lite register accessor
        that emulates ``.write(offset, value)`` and ``.read(offset)``.
    screen_w, screen_h : int
        Physical HDMI output resolution (default 1280×720).
    default_alpha : int
        Default blending weight (15 = fully opaque).
    default_duration : float
        Default banner display time in seconds (used when ``duration`` is
        not passed to a show_* method).
    """

    def __init__(
        self,
        fpga_interface,
        screen_w: int = 1280,
        screen_h: int = 720,
        default_alpha: int = 14,
        default_duration: float = 5.0,
    ):
        self._fpga           = fpga_interface
        self.screen_w        = screen_w
        self.screen_h        = screen_h
        self.default_alpha   = default_alpha
        self.default_duration = default_duration

        # Current compositor state (Python-side shadow of HW registers)
        self._visible = False
        self._alpha   = default_alpha
        self._x0 = 0; self._y0 = 0
        self._x1 = 0; self._y1 = 0

        # Auto-hide timer
        self._timer: Optional[threading.Timer] = None
        self._lock  = threading.Lock()

        # Ensure compositor is off at startup
        self.hide()
        logger.info("HardwareGraphicsAPI ready (screen %dx%d)", screen_w, screen_h)

    # ──────────────────────────────────────────────────────────────────────
    # High-level "show" methods
    # ──────────────────────────────────────────────────────────────────────

    def show_authorized_screen(
        self,
        username: str,
        confidence: float = 0.0,
        duration: Optional[float] = None,
        position: str = "top",          # "top", "bottom", "center"
        alpha: Optional[int] = None,
    ):
        """
        Display a branded "ACCESS GRANTED — Welcome, <username>" banner.

        The banner is rendered entirely in Python with OpenCV and uploaded
        to the FPGA BRAM. It appears on the HDMI monitor within one video
        frame (~16 ms at 60 Hz) and disappears after *duration* seconds.

        Parameters
        ----------
        username    : Human-readable name of the authenticated user.
        confidence  : Cosine-similarity score (shown as a percentage).
        duration    : Seconds to display before auto-hide (None → default).
        position    : Where on screen to place the banner.
        alpha       : Blending weight override (0–15, None → default).
        """
        banner = self._render_status_banner(
            status_text="ACCESS GRANTED",
            detail_text=f"Welcome, {username}",
            confidence=confidence,
            accent_color=(0, 220, 80),       # green
            bg_color=(10, 30, 10),
            icon_char="✓",
        )
        self.show_custom(
            pixels=banner,
            position=position,
            duration=duration,
            alpha=alpha,
        )

    def show_unauthorized_screen(
        self,
        duration: Optional[float] = None,
        position: str = "top",
        alpha: Optional[int] = None,
    ):
        """
        Display an "ACCESS DENIED" banner for *duration* seconds.
        """
        banner = self._render_status_banner(
            status_text="ACCESS DENIED",
            detail_text="Face not recognised",
            confidence=0.0,
            accent_color=(220, 40, 40),      # red
            bg_color=(30, 8, 8),
            icon_char="✗",
            show_confidence=False,
        )
        self.show_custom(
            pixels=banner,
            position=position,
            duration=duration,
            alpha=alpha,
        )

    def show_banner(
        self,
        text: str,
        color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (20, 20, 20),
        duration: Optional[float] = None,
        position: str = "top",
        alpha: Optional[int] = None,
        font_scale: float = 1.4,
    ):
        """
        General-purpose text banner.

        Parameters
        ----------
        text       : The string to display.
        color      : RGB text colour.
        bg_color   : RGB background colour of the banner.
        duration   : Seconds to display (None → self.default_duration).
        position   : "top", "bottom", or "center".
        alpha      : Hardware alpha (0–15).
        font_scale : OpenCV font scale factor.
        """
        w = min(SPRITE_MAX_W, self.screen_w)
        h = min(SPRITE_MAX_H, 64)

        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        # Background fill (avoid pure black which maps to transparent)
        canvas[:] = np.clip(bg_color, 1, 255)

        # Text
        font      = cv2.FONT_HERSHEY_DUPLEX
        thickness = 2
        text_sz   = cv2.getTextSize(text, font, font_scale, thickness)[0]
        tx = max(0, (w - text_sz[0]) // 2)
        ty = (h + text_sz[1]) // 2
        cv2.putText(canvas, text, (tx, ty), font, font_scale,
                    color, thickness, cv2.LINE_AA)

        self.show_custom(pixels=canvas, position=position,
                         duration=duration, alpha=alpha)

    def show_custom(
        self,
        pixels: np.ndarray,
        position: str = "top",
        x0: Optional[int] = None,
        y0: Optional[int] = None,
        duration: Optional[float] = None,
        alpha: Optional[int] = None,
    ):
        """
        Upload a raw pixel array (H×W×3, uint8, RGB) to the FPGA BRAM
        and arm the compositor.

        Parameters
        ----------
        pixels   : NumPy image array. Height ≤ SPRITE_MAX_H, Width ≤ SPRITE_MAX_W.
                   Values are interpreted as RGB (NOT BGR).
        position : Predefined anchor: "top", "bottom", "center", "top-right",
                   "bottom-right". Ignored if x0/y0 are given explicitly.
        x0, y0   : Explicit top-left corner on screen (overrides position).
        duration : Seconds before auto-hide. None → self.default_duration.
        alpha    : Hardware blending weight (0–15). None → self.default_alpha.
        """
        h, w = pixels.shape[:2]
        if h > SPRITE_MAX_H or w > SPRITE_MAX_W:
            logger.warning(
                "Sprite %dx%d exceeds hardware BRAM limit %dx%d — clipping",
                w, h, SPRITE_MAX_W, SPRITE_MAX_H
            )
            pixels = pixels[:SPRITE_MAX_H, :SPRITE_MAX_W]
            h, w = pixels.shape[:2]

        # Resolve position
        sx0, sy0 = self._resolve_position(position, w, h, x0, y0)
        sx1, sy1 = sx0 + w, sy0 + h

        _alpha   = alpha if alpha is not None else self.default_alpha
        _dur     = duration if duration is not None else self.default_duration

        with self._lock:
            self._cancel_timer()

            # 1. Upload pixels to BRAM
            self._upload_pixels(pixels, w, h)

            # 2. Set compositor geometry + enable
            self._set_geometry(sx0, sy0, sx1, sy1)
            self._set_alpha(_alpha)
            self._set_visible(True)

            # 3. Arm auto-hide timer
            if _dur > 0:
                self._timer = threading.Timer(_dur, self._auto_hide)
                self._timer.daemon = True
                self._timer.start()
                logger.debug("Sprite armed for %.1fs at (%d,%d)-(%d,%d) alpha=%d",
                             _dur, sx0, sy0, sx1, sy1, _alpha)

    # ──────────────────────────────────────────────────────────────────────
    # Low-level control
    # ──────────────────────────────────────────────────────────────────────

    def hide(self):
        """Immediately disable the hardware sprite compositor."""
        with self._lock:
            self._cancel_timer()
            self._set_visible(False)

    def update_alpha(self, alpha: int):
        """Change blending weight in real-time without re-uploading pixels."""
        alpha = max(0, min(15, alpha))
        self._set_alpha(alpha)

    def update_duration(self, remaining: float):
        """Reset the auto-hide timer to a new duration (from now)."""
        with self._lock:
            self._cancel_timer()
            if self._visible and remaining > 0:
                self._timer = threading.Timer(remaining, self._auto_hide)
                self._timer.daemon = True
                self._timer.start()

    def set_position(self, x0: int, y0: int, x1: int, y1: int):
        """
        Reposition the sprite rectangle on screen without re-uploading pixels.
        Takes effect on the next HDMI frame.
        """
        self._set_geometry(x0, y0, x1, y1)

    def fade_out(self, steps: int = 8, step_delay: float = 0.05):
        """
        Gradually decrease alpha from current value to 0, then hide.

        Runs in the calling thread — call in a background thread if needed.
        """
        start_alpha = self._alpha
        for i in range(steps, -1, -1):
            a = int(start_alpha * i / steps)
            self._set_alpha(a)
            time.sleep(step_delay)
        self.hide()

    def fade_in(self, target_alpha: Optional[int] = None,
                steps: int = 8, step_delay: float = 0.04):
        """
        Gradually increase alpha from 0 to target_alpha.
        The sprite must already be visible (pixels uploaded).
        """
        end_alpha = target_alpha if target_alpha is not None else self.default_alpha
        for i in range(steps + 1):
            a = int(end_alpha * i / steps)
            self._set_alpha(a)
            time.sleep(step_delay)

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers — register writes
    # ──────────────────────────────────────────────────────────────────────

    def _hw_write(self, offset: int, value: int):
        """Write to sprite AXI-Lite register. Delegates to FPGAInterface."""
        try:
            self._fpga.sprite_ctrl_write(offset, value)
        except Exception as e:
            logger.error("sprite_ctrl_write(0x%02X, 0x%X) failed: %s", offset, value, e)

    def _set_visible(self, on: bool):
        self._visible = on
        self._hw_write(_REG_VISIBLE, int(on))

    def _set_alpha(self, alpha: int):
        self._alpha = alpha
        self._hw_write(_REG_ALPHA, alpha & 0xF)

    def _set_geometry(self, x0: int, y0: int, x1: int, y1: int):
        self._x0 = x0; self._y0 = y0
        self._x1 = x1; self._y1 = y1
        self._hw_write(_REG_X0, x0 & 0x7FF)
        self._hw_write(_REG_Y0, y0 & 0x3FF)
        self._hw_write(_REG_X1, x1 & 0x7FF)
        self._hw_write(_REG_Y1, y1 & 0x3FF)

    def _upload_pixels(self, pixels: np.ndarray, w: int, h: int):
        """
        Burst-write a pixel array to the FPGA BRAM via the sprite write registers.

        For each pixel:
          - Write sprite_wr_addr
          - Write sprite_wr_data (RGB24)
          - Pulse sprite_wr_en
        """
        # Ensure array is contiguous uint8 RGB
        if pixels.dtype != np.uint8:
            pixels = pixels.astype(np.uint8)

        # Temporarily disable (so we don't display garbage mid-upload)
        was_visible = self._visible
        if was_visible:
            self._set_visible(False)

        addr = 0
        for row in range(h):
            for col in range(w):
                r, g, b = int(pixels[row, col, 0]), int(pixels[row, col, 1]), int(pixels[row, col, 2])
                hw_px = _rgb_to_hw(r, g, b)
                self._hw_write(_REG_WR_ADDR, addr)
                self._hw_write(_REG_WR_DATA, hw_px)
                self._hw_write(_REG_WR_EN, 1)   # commit (HW uses this as a write-strobe)
                addr += 1

        # Disable write-enable after upload
        self._hw_write(_REG_WR_EN, 0)

        if was_visible:
            self._set_visible(True)

        logger.debug("Uploaded %d pixels to BRAM", addr)

    def _upload_pixels_fast(self, pixels: np.ndarray, w: int, h: int):
        """
        Faster bulk upload that uses FPGAInterface.batch_sprite_write() if available.
        Falls back to _upload_pixels() on older firmware.
        """
        if hasattr(self._fpga, 'batch_sprite_write'):
            was_visible = self._visible
            if was_visible:
                self._set_visible(False)
            self._fpga.batch_sprite_write(pixels)
            self._hw_write(_REG_WR_EN, 0)
            if was_visible:
                self._set_visible(True)
        else:
            self._upload_pixels(pixels, w, h)

    def _auto_hide(self):
        """Timer callback — fade out then hide."""
        logger.debug("Auto-hide sprite triggered")
        # Run a short fade in a daemon thread so the timer thread returns fast
        t = threading.Thread(target=self.fade_out, kwargs={"steps": 6, "step_delay": 0.04})
        t.daemon = True
        t.start()

    def _cancel_timer(self):
        """Cancel any pending auto-hide timer. Must be called under self._lock."""
        if self._timer is not None and self._timer.is_alive():
            self._timer.cancel()
        self._timer = None

    # ──────────────────────────────────────────────────────────────────────
    # Rendering helpers — purely CPU-side OpenCV
    # ──────────────────────────────────────────────────────────────────────

    def _render_status_banner(
        self,
        status_text: str,
        detail_text: str,
        confidence: float,
        accent_color: Tuple[int, int, int],
        bg_color: Tuple[int, int, int],
        icon_char: str,
        show_confidence: bool = True,
    ) -> np.ndarray:
        """
        Render a 512×128 "status" banner with:
          - A 6-pixel left accent bar in accent_color
          - Large status text (e.g. "ACCESS GRANTED")
          - Smaller detail text (e.g. "Welcome, Ramsey")
          - An optional confidence score bar

        Returns an H×W×3 uint8 NumPy array in RGB order.
        """
        w, h = SPRITE_MAX_W, SPRITE_MAX_H  # 512×128
        canvas = np.zeros((h, w, 3), dtype=np.uint8)

        # Clamp bg_color so it's never pure black (avoid transparent-magic clash)
        bg = tuple(max(v, 1) for v in bg_color)
        canvas[:] = bg

        # Left accent bar (6 px wide)
        canvas[:, :6] = accent_color

        # Semi-transparent dark overlay on the right part for depth
        overlay = canvas.copy()
        cv2.rectangle(overlay, (6, 0), (w - 1, h - 1), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0, canvas)

        # Status text — large, bold, accent-coloured
        font  = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(canvas, status_text, (22, 52),
                    font, 1.4, accent_color, 2, cv2.LINE_AA)

        # Detail text — smaller, white
        cv2.putText(canvas, detail_text, (22, 82),
                    font, 0.75, (220, 220, 220), 1, cv2.LINE_AA)

        # Confidence score bar
        if show_confidence and confidence > 0:
            bar_x0, bar_y0 = 22, 100
            bar_w, bar_h   = 300, 10
            # Background
            cv2.rectangle(canvas,
                          (bar_x0, bar_y0),
                          (bar_x0 + bar_w, bar_y0 + bar_h),
                          (50, 50, 50), -1)
            # Fill
            fill_w = int(bar_w * min(confidence, 1.0))
            cv2.rectangle(canvas,
                          (bar_x0, bar_y0),
                          (bar_x0 + fill_w, bar_y0 + bar_h),
                          accent_color, -1)
            # Score label
            pct_text = f"{confidence * 100:.1f}%"
            cv2.putText(canvas, pct_text,
                        (bar_x0 + bar_w + 8, bar_y0 + bar_h),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (200, 200, 200), 1, cv2.LINE_AA)

        # Subtle bottom border line
        canvas[h - 1, :] = accent_color

        return canvas  # RGB uint8

    def _resolve_position(
        self,
        position: str,
        sprite_w: int,
        sprite_h: int,
        x0: Optional[int],
        y0: Optional[int],
    ) -> Tuple[int, int]:
        """
        Map a position string to (x0, y0) screen coordinates.
        Explicit x0/y0 always take priority.
        """
        if x0 is not None and y0 is not None:
            return x0, y0

        margin = 20
        pos = position.lower()

        if pos == "top":
            return margin, margin
        elif pos == "bottom":
            return margin, self.screen_h - sprite_h - margin
        elif pos == "center":
            return (self.screen_w - sprite_w) // 2, (self.screen_h - sprite_h) // 2
        elif pos == "top-right":
            return self.screen_w - sprite_w - margin, margin
        elif pos == "bottom-right":
            return self.screen_w - sprite_w - margin, self.screen_h - sprite_h - margin
        else:
            return margin, margin
