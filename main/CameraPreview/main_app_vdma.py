"""
PYNQ-Z2 face recognition with HDMI output via VDMA.

Pipeline:
  Camera (IP) -> grabber thread (drains buffer) -> main loop @ 12 FPS:
    A. Haar detect + OpenFace embed (every DETECTION_EVERY frames)
    B. PL cosine match against authorized_embeddings/*.npy
    C. Push the latest frame to HDMI via VDMA
"""
import os, glob, time, threading, logging, urllib.request
from pathlib import Path

import cv2
import numpy as np

from pynq import Overlay, allocate, MMIO
from pynq.lib.video import VideoMode
from cosine_driver import CosineSimilarity

# --- Configuration -----------------------------------------------------------
BITSTREAM_PATH            = "hvc1.bit"
VIDEO_PATH                = "http://192.168.0.202:4747/video"
AUTHORIZED_EMBEDDINGS_DIR = "authorized_embeddings"

WIDTH, HEIGHT             = 1280, 720
HDMI_FPS                  = 12.0
HDMI_INTERVAL             = 1.0 / HDMI_FPS

DETECTION_SCALE           = 0.25
DETECTION_EVERY           = 5
MAX_FACES                 = 1
MATCH_THRESHOLD           = 0.70

EMBED_FILE = "openface.nn4.small2.v1.t7"
EMBED_URLS = [
    "https://github.com/pyannote/pyannote-data/raw/master/openface.nn4.small2.v1.t7",
    "https://storage.cmusatyalab.org/openface-models/nn4.small2.v1.t7",
]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("HDMI_Face_Detect")


# --- Bitstream + cosine accelerator ------------------------------------------
ol = Overlay(BITSTREAM_PATH)
cs = CosineSimilarity(bitfile=None, base_addr=0x4000_0000)


# --- Video Timing Controller (720p60) ----------------------------------------
def setup_vtc(overlay):
    VTC_CTL, VTC_ACTIVE_SIZE   = 0x0000, 0x0060
    VTC_ENCODING, VTC_POLARITY = 0x0068, 0x006C
    VTC_HSIZE, VTC_VSIZE       = 0x0070, 0x0074
    VTC_HSYNC, VTC_VSYNC0      = 0x0078, 0x0080

    base = overlay.ip_dict["v_tc_0"]["phys_addr"]
    size = overlay.ip_dict["v_tc_0"]["addr_range"]
    vtc  = MMIO(base, size)

    ACTIVE_SIZE_720P = (720 << 16) | 1280
    HSIZE_720P, VSIZE_720P = 1650, 750
    HSYNC_720P  = (1430 << 16) | 1390
    VSYNC0_720P = (730  << 16) | 725

    vtc.write(VTC_CTL, 0x80000000)            # reset
    time.sleep(0.1)
    vtc.write(VTC_ACTIVE_SIZE, ACTIVE_SIZE_720P)
    vtc.write(VTC_ENCODING,    0)
    vtc.write(VTC_POLARITY,    0x3F)
    vtc.write(VTC_HSIZE,       HSIZE_720P)
    vtc.write(VTC_VSIZE,       VSIZE_720P)
    vtc.write(VTC_HSYNC,       HSYNC_720P)
    vtc.write(VTC_VSYNC0,      VSYNC0_720P)
    vtc.write(VTC_CTL, 0x01FFFF07)            # enable
    log.info("VTC configured for 720p60")


setup_vtc(ol)


# --- VDMA + HDMI buffer ------------------------------------------------------
vdma = ol.axi_vdma_0
vdma.writechannel.mode = VideoMode(WIDTH, HEIGHT, 24)
vdma.writechannel.start()
hdmi_buffer = allocate(shape=(HEIGHT, WIDTH, 3), dtype=np.uint8)
log.info(f"VDMA Status: {hex(int(vdma.register_map.MM2S_VDMASR))}")


# --- Haar cascade ------------------------------------------------------------
def find_cascade():
    cands = []
    cands += glob.glob("/usr/share/opencv*/haarcascades/haarcascade_frontalface_default.xml")
    cands += glob.glob("/usr/local/share/opencv*/haarcascades/haarcascade_frontalface_default.xml")
    cands += glob.glob("/usr/share/OpenCV/haarcascades/haarcascade_frontalface_default.xml")
    cands += glob.glob(os.path.join(os.path.dirname(cv2.__file__), "data",
                                    "haarcascade_frontalface_default.xml"))
    for p in cands:
        if os.path.exists(p):
            return p
    local = "haarcascade_frontalface_default.xml"
    if not os.path.exists(local):
        log.info("Downloading Haar cascade XML ...")
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/opencv/opencv/4.x/"
            "data/haarcascades/haarcascade_frontalface_default.xml", local)
    return local


CASCADE_PATH = find_cascade()
log.info(f"Cascade: {CASCADE_PATH}")
detector = cv2.CascadeClassifier(CASCADE_PATH)
if detector.empty():
    raise RuntimeError("Failed to load Haar cascade")


# --- OpenFace embedder (128-D, L2-normalized) --------------------------------
if not os.path.exists(EMBED_FILE):
    for url in EMBED_URLS:
        try:
            log.info(f"Downloading OpenFace model from {url}")
            urllib.request.urlretrieve(url, EMBED_FILE)
            break
        except Exception as e:
            log.warning(f"  failed: {e}")
    if not os.path.exists(EMBED_FILE):
        raise RuntimeError("Could not download nn4.small2.v1.t7 — fetch manually.")

embedder = cv2.dnn.readNetFromTorch(EMBED_FILE)


def compute_embedding(face_bgr):
    blob = cv2.dnn.blobFromImage(
        face_bgr, scalefactor=1.0 / 255,
        size=(96, 96), mean=(0, 0, 0),
        swapRB=True, crop=False)
    embedder.setInput(blob)
    v = embedder.forward().flatten().astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-8)


def detect_and_embed(frame_bgr):
    """Detect on a downscaled frame; embed each face from the full-res crop."""
    small = cv2.resize(frame_bgr, (0, 0),
                       fx=DETECTION_SCALE, fy=DETECTION_SCALE,
                       interpolation=cv2.INTER_NEAREST)
    gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    faces = detector.detectMultiScale(
        gray, scaleFactor=1.2, minNeighbors=5,
        minSize=(20, 20), flags=cv2.CASCADE_SCALE_IMAGE)

    out, inv = [], 1.0 / DETECTION_SCALE
    H, W = frame_bgr.shape[:2]
    for (x, y, w, h) in faces[:MAX_FACES]:
        xf, yf = max(0, int(x * inv)), max(0, int(y * inv))
        xf2 = min(W, xf + int(w * inv))
        yf2 = min(H, yf + int(h * inv))
        crop = frame_bgr[yf:yf2, xf:xf2]
        if crop.size == 0:
            continue
        out.append(((xf, yf, xf2 - xf, yf2 - yf), compute_embedding(crop)))
    return out


# --- Authorized embeddings ---------------------------------------------------
def load_authorized_embeddings(directory):
    embeddings = []
    emb_dir = Path(directory)
    if not emb_dir.exists():
        return []
    for path in sorted(emb_dir.glob("*.npy")):
        embeddings.append(np.load(str(path)).astype(np.float32))
    log.info(f"Loaded {len(embeddings)} identities.")
    return embeddings


# --- Threaded camera grabber (drains buffer, no self-throttle) ---------------
class VideoFrameGrabber(threading.Thread):
    def __init__(self, path, fallback_img_path="ASUS.png"):
        super().__init__(daemon=True)
        self.cap = cv2.VideoCapture(path)
        # Keep only the newest frame in the FFmpeg/V4L2 backend buffer; without
        # this, IP-camera streams accumulate latency when the consumer pauses.
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        self.fallback_path = fallback_img_path
        self._frame = None
        self._lock  = threading.Lock()
        self.running = True
        log.info("VFG Init")

    def run(self):
        # cap.read() blocks until the next frame arrives, so this loop paces
        # itself to camera framerate without an explicit sleep — and crucially,
        # never stalls long enough for upstream buffers to fill with stale
        # frames.
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                log.info("Video ended. Switching to fallback image.")
                fallback = cv2.imread(self.fallback_path)
                if fallback is not None:
                    with self._lock:
                        self._frame = fallback
                else:
                    log.error(f"Could not find {self.fallback_path}")
                self.running = False
                break
            with self._lock:
                self._frame = frame
        self.cap.release()

    def latest(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None


# =============================================================================
auth_embs = load_authorized_embeddings(AUTHORIZED_EMBEDDINGS_DIR)
grabber   = VideoFrameGrabber(VIDEO_PATH)
grabber.start()

log.info("Starting detection + HDMI streaming ...")

frame_count    = 0
last_loop_time = 0.0
last_encodings = []

try:
    while True:
        # Pace the whole loop to HDMI_INTERVAL — the grabber runs free, so
        # we always pull a fresh frame, never a buffered one.
        now = time.time()
        elapsed = now - last_loop_time
        if elapsed < HDMI_INTERVAL:
            time.sleep(HDMI_INTERVAL - elapsed)
        last_loop_time = time.time()

        frame = grabber.latest()
        if frame is None:
            time.sleep(0.01)
            continue

        frame_count += 1

        # ---- A. Detection + embedding (every DETECTION_EVERY frames) -------
        if frame_count % DETECTION_EVERY == 0:
            detections = detect_and_embed(frame)
            last_encodings = [emb for _, emb in detections]

            if not last_encodings:
                # keep the PL cosine pipeline exercised + log no-user state
                a = np.random.randn(128).astype(np.float32)
                b = np.random.randn(128).astype(np.float32)
                cs.compare(a, b, threshold=MATCH_THRESHOLD)
                log.info("No User Found!")

        # ---- B. PL cosine matching -----------------------------------------
        for cam_emb in last_encodings:
            cam_emb = cam_emb.astype(np.float32)
            for auth_emb in auth_embs:
                match, score = cs.compare(cam_emb, auth_emb,
                                          threshold=MATCH_THRESHOLD)
                if match:
                    log.info(f"MATCH FOUND! Score: {score:.4f}")
                    break
                else:
                    log.info(f"MATCH NOT FOUND! Score: {score:.4f}")

        # ---- C. HDMI output (every iteration; loop is already paced) -------
        src_h, src_w = frame.shape[:2]
        if src_h == HEIGHT and src_w == WIDTH:
            hdmi_frame = frame                              # zero-copy
        else:
            hdmi_frame = cv2.resize(frame, (WIDTH, HEIGHT),
                                    interpolation=cv2.INTER_NEAREST)
        hdmi_buffer[:] = hdmi_frame[:, :, [2, 1, 0]]        # BGR -> RGB swap
        vdma.writechannel.writeframe(hdmi_buffer)

except KeyboardInterrupt:
    log.info("Shutting down...")
except Exception as e:
    log.exception(e)
finally:
    grabber.running = False
    try:
        vdma.writechannel.stop()
    except Exception:
        pass
    log.info("Cleanup complete.")
