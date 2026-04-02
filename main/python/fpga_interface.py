"""
FPGA Interface Layer
Handles communication between the PS (ARM CPU) and PL (FPGA logic).

Responsibilities:
  - Load the bitstream and configure the HDMI IN/OUT video pipeline
  - Write the 1-bit authorization flag to AXI GPIO → PL kill-switch mux
  - Feed camera frames to the VDMA so they appear on HDMI OUT when unauthorized

PL Block Design components accessed here:
  - axi_gpio_0  : AXI GPIO IP, 1-bit output, GPIO_DATA[0] = auth_flag
  - axi_vdma_0  : AXI VDMA, MM2S channel streams frames from DDR → PL
  - video_in    : PYNQ VideoIn  (dvi2rgb + HDMI RX)  — HDMI IN capture
  - video_out   : PYNQ VideoOut (rgb2dvi + HDMI TX)  — HDMI OUT display

Note: the Vivado block design exports an .hwh hardware description file that
PYNQ parses to automatically name the IP instances.  The attribute names used
below (overlay.axi_gpio_0, overlay.axi_vdma_0) must match the block-design
instance names set in create_project.tcl.
"""

import numpy as np
import logging
import time
from typing import Optional

try:
    from pynq import Overlay, allocate
    from pynq.lib.video import VideoIn, VideoOut, PIXEL_RGB
    PYNQ_AVAILABLE = True
except ImportError:
    PYNQ_AVAILABLE = False

logger = logging.getLogger(__name__)


# AXI GPIO register offsets (Xilinx AXI GPIO v2 IP)
_GPIO_DATA_OFFSET = 0x000   # Channel 1 data register


class FPGAInterface:
    """
    Thin PS↔PL interface.

    After init the HDMI pipeline is running continuously in hardware:
      - Unauthorized: VDMA camera frames → HDMI OUT
      - Authorized:   HDMI IN passthrough → HDMI OUT
    The PS only needs to update the 1-bit GPIO flag each recognition cycle.
    """

    def __init__(self, overlay, verbose: bool = False):
        """
        Args:
            overlay: Loaded pynq.Overlay object
            verbose: Enable debug logging
        """
        self.overlay = overlay
        self.verbose = verbose
        self._authorized = False

        self._init_gpio()
        self._init_video()

        # Start in unauthorized state (safe default: block PC signal)
        self.set_authorization_status(False)
        logger.info("FPGA interface ready — HDMI pipeline active")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_gpio(self):
        """Bind to the AXI GPIO IP that drives the kill-switch auth_flag."""
        if not PYNQ_AVAILABLE:
            self._gpio = None
            return
        try:
            # PYNQ auto-discovers IP instances from the .hwh file.
            # The GPIO IP is configured as 1-bit output-only in the block design.
            self._gpio = self.overlay.axi_gpio_0
            logger.info("AXI GPIO bound (auth_flag control)")
        except AttributeError:
            logger.error(
                "axi_gpio_0 not found in overlay — check block design instance name"
            )
            raise

    def _init_video(self):
        """Configure HDMI IN capture and HDMI OUT display via PYNQ video API."""
        if not PYNQ_AVAILABLE:
            self._hdmi_in = None
            self._hdmi_out = None
            return
        try:
            # VideoIn wraps the dvi2rgb IP + video timing controller
            self._hdmi_in = self.overlay.video.hdmi_in
            self._hdmi_in.configure(PIXEL_RGB)
            self._hdmi_in.start()

            # VideoOut wraps the rgb2dvi IP + video timing controller
            # Match the input mode (resolution + pixel format) automatically
            self._hdmi_out = self.overlay.video.hdmi_out
            self._hdmi_out.configure(self._hdmi_in.mode, PIXEL_RGB)
            self._hdmi_out.start()

            logger.info(
                f"HDMI IN/OUT configured: {self._hdmi_in.mode.width}x"
                f"{self._hdmi_in.mode.height} @ {self._hdmi_in.mode.fps} fps"
            )
        except AttributeError as e:
            logger.error(f"HDMI video init failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Kill-switch control
    # ------------------------------------------------------------------

    def set_authorization_status(self, is_authorized: bool):
        """
        Set the kill-switch state.

        Writes a single bit to AXI GPIO DATA register.  The PL hdmi_stream_mux
        samples this flag at the next frame boundary and routes accordingly.

        Args:
            is_authorized: True  → pass HDMI IN to HDMI OUT (PC signal visible)
                           False → show camera feed on HDMI OUT (PC signal blocked)
        """
        self._authorized = is_authorized

        if not PYNQ_AVAILABLE or self._gpio is None:
            status = "AUTHORIZED" if is_authorized else "UNAUTHORIZED"
            logger.info(f"[Mock] Kill-switch → {status}")
            return

        try:
            # AXI GPIO channel-1 data register: write 1 or 0 to bit[0]
            self._gpio.write(_GPIO_DATA_OFFSET, int(is_authorized))

            if self.verbose:
                logger.debug(
                    f"GPIO auth_flag = {int(is_authorized)} "
                    f"({'AUTHORIZED' if is_authorized else 'UNAUTHORIZED'})"
                )
        except Exception as e:
            logger.error(f"Failed to set authorization status: {e}")

    # ------------------------------------------------------------------
    # Camera frame injection (for VDMA path)
    # ------------------------------------------------------------------

    def write_camera_frame(self, frame: np.ndarray):
        """
        Write a camera frame into the VDMA frame buffer so it appears on
        HDMI OUT while the system is in the unauthorized state.

        The VDMA continuously re-reads the last written frame, so this only
        needs to be called when a new camera frame is available.

        Args:
            frame: BGR frame from OpenCV (H×W×3, uint8).
                   Will be converted to RGB before writing.
        """
        if not PYNQ_AVAILABLE or self._hdmi_out is None:
            return
        try:
            out_frame = self._hdmi_out.newframe()
            # Convert BGR (OpenCV) → RGB (HDMI), copy into PYNQ contiguous buffer
            out_frame[:] = frame[:, :, ::-1]
            self._hdmi_out.writeframe(out_frame)
        except Exception as e:
            logger.error(f"Failed to write camera frame: {e}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self):
        """Stop HDMI pipeline and set kill-switch to unauthorized (safe state)."""
        try:
            self.set_authorization_status(False)
            if PYNQ_AVAILABLE:
                if self._hdmi_in:
                    self._hdmi_in.stop()
                if self._hdmi_out:
                    self._hdmi_out.stop()
            logger.info("FPGA interface shutdown")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
