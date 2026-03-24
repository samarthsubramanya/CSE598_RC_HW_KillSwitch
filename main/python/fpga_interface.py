"""
FPGA Interface Layer
Handles AXI communication between ARM CPU and FPGA hardware

Memory Map (24-bit address space):
- 0x000000: Control register (RW)
- 0x000004: Status register (RO)
- 0x000100: Input image buffer (W) - 1280x720 RGB (1.2MB)
- 0x200000: Output image buffer (R) - 1.2MB
- 0x400000: Face detection results (R) - up to 16 faces (1KB)
- 0x404000: CNN embeddings (R) - 16 faces * 128 * 4 bytes (8KB)
"""

import numpy as np
import logging
from typing import Tuple, Optional
import time

try:
    from pynq import allocate, MMIO
    PYNQ_AVAILABLE = True
except ImportError:
    PYNQ_AVAILABLE = False

logger = logging.getLogger(__name__)


class FPGAInterface:
    """Interface to FPGA accelerator via AXI"""
    
    def __init__(self, overlay, verbose=False):
        """
        Initialize FPGA interface
        
        Args:
            overlay: PYNQ Overlay object (from loaded bitstream)
            verbose: Enable debug logging
        """
        self.overlay = overlay
        self.verbose = verbose
        
        # AXI parameters (must match hardware)
        self.BASE_ADDR = 0x40000000  # AXI4 slave base address
        self.INPUT_IMG_ADDR = 0x000100
        self.OUTPUT_IMG_ADDR = 0x200000
        self.FACES_ADDR = 0x400000
        self.EMBEDDINGS_ADDR = 0x404000
        
        self.CTRL_REG = 0x000000
        self.STATUS_REG = 0x000004
        
        # Image dimensions
        self.IMAGE_WIDTH = 1280
        self.IMAGE_HEIGHT = 720
        self.IMAGE_SIZE = self.IMAGE_WIDTH * self.IMAGE_HEIGHT
        
        # Embedding parameters
        self.EMBEDDING_DIM = 128
        self.MAX_FACES = 16
        
        # Initialize AXI memory interface
        self._init_axi()
        
        logger.info("FPGA interface initialized")
    
    def _init_axi(self):
        """Initialize AXI memory interface"""
        if PYNQ_AVAILABLE:
            try:
                # Create MMIO interface to FPGA registers and memory
                self.mmio = MMIO(self.BASE_ADDR, 0x500000)  # 5MB address space
                logger.info(f"AXI memory interface created at 0x{self.BASE_ADDR:08X}")
            except Exception as e:
                logger.error(f"Failed to initialize AXI interface: {e}")
                raise
        else:
            logger.warning("PYNQ not available - MMIO disabled")
            self.mmio = None
    
    def process_frame(self, frame: np.ndarray) -> Optional[Tuple]:
        """
        Send frame to FPGA for processing
        
        Args:
            frame (np.ndarray): Input frame (BGR, 1280x720, uint8)
        
        Returns:
            Tuple[faces, embeddings] or None if processing failed
            - faces: List of (x1, y1, x2, y2) bounding boxes
            - embeddings: List of 128-D embeddings (normalized unit vectors)
        """
        if frame.shape != (self.IMAGE_HEIGHT, self.IMAGE_WIDTH, 3):
            logger.warning(f"Unexpected frame shape: {frame.shape}")
            return None
        
        try:
            # 1. Convert BGR to RGB and write to input buffer
            self._write_image_to_fpga(frame)
            
            # 2. Trigger detection and embedding computation
            self._start_processing()
            
            # 3. Wait for completion
            if not self._wait_for_completion(timeout=1.0):
                logger.warning("FPGA processing timeout")
                return None
            
            # 4. Read results
            faces, embeddings = self._read_results()
            
            if self.verbose:
                logger.debug(f"Detected {len(faces)} faces")
            
            return faces, embeddings
        
        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            return None
    
    def _write_image_to_fpga(self, frame: np.ndarray):
        """Write image frame to FPGA input buffer via AXI"""
        if not PYNQ_AVAILABLE or not self.mmio:
            return
        
        try:
            # Convert BGR to RGB (flip channels)
            rgb_frame = frame[:, :, ::-1]  # BGR -> RGB
            
            # Flatten image data
            flat_pixels = rgb_frame.reshape(-1)
            
            # Pack RGB pixels (3 bytes per pixel) into 32-bit words
            # FPGA expects pixels as: [B,G,R,X] in 32-bit words
            pixel_words = np.zeros(self.IMAGE_SIZE, dtype=np.uint32)
            
            for i in range(self.IMAGE_SIZE):
                idx = i * 3
                r = flat_pixels[idx] if idx < len(flat_pixels) else 0
                g = flat_pixels[idx+1] if idx+1 < len(flat_pixels) else 0
                b = flat_pixels[idx+2] if idx+2 < len(flat_pixels) else 0
                pixel_words[i] = (r << 16) | (g << 8) | b
            
            # Write to FPGA memory
            addr = self.BASE_ADDR + self.INPUT_IMG_ADDR
            self.mmio.write_region(addr, pixel_words.tobytes())
            
            if self.verbose:
                logger.debug(f"Image written to FPGA (0x{addr:X})")
        
        except Exception as e:
            logger.error(f"Failed to write image: {e}")
            raise
    
    def _start_processing(self):
        """Trigger FPGA face detection and CNN embedding computation"""
        if not PYNQ_AVAILABLE or not self.mmio:
            return
        
        try:
            # Write control register: bit[0]=detect_enable, bit[1]=cnn_enable
            ctrl = 0x03  # Enable both detection and CNN
            self.mmio.write(self.BASE_ADDR + self.CTRL_REG, ctrl)
            
            if self.verbose:
                logger.debug("FPGA processing started")
        
        except Exception as e:
            logger.error(f"Failed to start processing: {e}")
            raise
    
    def _wait_for_completion(self, timeout: float = 1.0) -> bool:
        """
        Wait for FPGA to complete processing
        
        Args:
            timeout: Timeout in seconds
        
        Returns:
            True if completed within timeout, False otherwise
        """
        if not PYNQ_AVAILABLE or not self.mmio:
            # Mock: simulate processing
            time.sleep(0.03)  # ~30ms for one frame
            return True
        
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            # Read status register
            status = self.mmio.read(self.BASE_ADDR + self.STATUS_REG)
            
            # Bit 8 = detection_complete, Bit 9 = embedding_complete
            detection_done = (status >> 8) & 0x1
            embedding_done = (status >> 9) & 0x1
            
            if detection_done and embedding_done:
                if self.verbose:
                    logger.debug("FPGA processing completed")
                return True
            
            time.sleep(0.001)  # Poll every 1ms
        
        logger.warning(f"FPGA processing timeout (status: 0x{status:08X})")
        return False
    
    def _read_results(self) -> Tuple:
        """
        Read face detection and embedding results from FPGA
        
        Returns:
            (faces, embeddings) tuple
            - faces: List of (x1, y1, x2, y2) tuples
            - embeddings: List of 128-D numpy arrays
        """
        faces = []
        embeddings = []
        
        if not PYNQ_AVAILABLE or not self.mmio:
            # Return mock results for testing
            faces.append((400, 200, 500, 300))  # Dummy face
            embeddings.append(np.random.randn(self.EMBEDDING_DIM).astype(np.float32))
            return faces, embeddings
        
        try:
            # Read status to get number of faces
            status = self.mmio.read(self.BASE_ADDR + self.STATUS_REG)
            num_faces = status & 0xFF
            
            if self.verbose:
                logger.debug(f"Reading {num_faces} faces from FPGA")
            
            # Read face bounding boxes
            addr_faces = self.BASE_ADDR + self.FACES_ADDR
            face_data = self.mmio.read_region(addr_faces, num_faces * 8)
            
            for i in range(num_faces):
                offset = i * 8
                x1 = int.from_bytes(face_data[offset:offset+2], 'little')
                y1 = int.from_bytes(face_data[offset+2:offset+4], 'little')
                x2 = int.from_bytes(face_data[offset+4:offset+6], 'little')
                y2 = int.from_bytes(face_data[offset+6:offset+8], 'little')
                
                faces.append((x1, y1, x2, y2))
            
            # Read CNN embeddings (INT8 quantized, 128-D per face)
            addr_emb = self.BASE_ADDR + self.EMBEDDINGS_ADDR
            emb_data = self.mmio.read_region(addr_emb, num_faces * self.EMBEDDING_DIM)
            
            for i in range(num_faces):
                offset = i * self.EMBEDDING_DIM
                # Read as INT8, convert to float, normalize
                emb_int8 = np.frombuffer(
                    emb_data[offset:offset+self.EMBEDDING_DIM],
                    dtype=np.int8
                )
                
                # Dequantize: INT8 -> Float
                emb_float = emb_int8.astype(np.float32) / 127.0
                
                # Normalize to unit length
                norm = np.linalg.norm(emb_float) + 1e-8
                emb_normalized = emb_float / norm
                
                embeddings.append(emb_normalized)
            
            return faces, embeddings
        
        except Exception as e:
            logger.error(f"Failed to read results: {e}")
            return [], []
    
    def set_authorization_status(self, is_authorized: bool):
        """
        Send authorization status to FPGA kill switch
        
        Args:
            is_authorized (bool): True = pass through computer HDMI, 
                                   False = show camera feed
        """
        try:
            if not PYNQ_AVAILABLE or not self.mmio:
                if is_authorized:
                    logger.info("[Mock] Authorization status set to AUTHORIZED")
                else:
                    logger.info("[Mock] Authorization status set to UNAUTHORIZED")
                return
            
            # Write authorization bit to control register (bit 2)
            # bit[0] = detect_enable
            # bit[1] = cnn_enable  
            # bit[2] = is_authorized (kill switch control)
            
            ctrl_value = 0x07 if is_authorized else 0x03  # bits 0,1 always on, bit 2 for auth
            self.mmio.write(self.BASE_ADDR + self.CTRL_REG, ctrl_value)
            
            status_str = "AUTHORIZED ✓" if is_authorized else "UNAUTHORIZED ✗"
            logger.debug(f"FPGA kill switch set to: {status_str} (ctrl=0x{ctrl_value:02X})")
            
        except Exception as e:
            logger.error(f"Failed to set authorization status: {e}")
    
    def shutdown(self):
        """Shutdown FPGA interface"""
        try:
            if PYNQ_AVAILABLE and self.mmio:
                # Clear control register
                self.mmio.write(self.BASE_ADDR + self.CTRL_REG, 0x00)
                logger.info("FPGA interface shutdown")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
