import cv2
import numpy as np
import threading
import time
import logging
import os, glob, urllib.request
from pathlib import Path
from pynq import Overlay
from cosine_driver import CosineSimilarity

# --- Configuration -----------------------------------------------------------
BITSTREAM_PATH            = "hc_graphics3.bit"
VIDEO_PATH                = "http://192.168.0.114:4747/video"
# VIDEO_PATH = "test.mp4"
AUTHORIZED_EMBEDDINGS_DIR = "authorized_embeddings"
WIDTH, HEIGHT             = 1280, 720
HDMI_FPS                  = 20.0
HDMI_INTERVAL             = 1 / 12        # ~12 FPS processing budget

DETECTION_SCALE  = 0.25                   # Haar runs on a downscaled frame
DETECTION_EVERY  = 2
MAX_FACES        = 1
MATCH_THRESHOLD  = 0.70                   # cosine; OpenFace is more permissive than dlib

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("HDMI_Face_Detect")

# --- Bitstream + cosine accelerator ------------------------------------------
ol = Overlay(BITSTREAM_PATH)
cs = CosineSimilarity(bitfile=None, base_addr=0x4000_0000)

# --- Haar cascade (PS detection) ---------------------------------------------
def find_cascade():
    cands = []
    cands += glob.glob("/usr/share/opencv*/haarcascades/haarcascade_frontalface_default.xml")
    cands += glob.glob("/usr/local/share/opencv*/haarcascades/haarcascade_frontalface_default.xml")
    cands += glob.glob("/usr/share/OpenCV/haarcascades/haarcascade_frontalface_default.xml")
    cv2_dir = os.path.dirname(cv2.__file__)
    cands += glob.glob(os.path.join(cv2_dir, "data", "haarcascade_frontalface_default.xml"))
    for p in cands:
        if os.path.exists(p):
            return p
    local = "haarcascade_frontalface_default.xml"
    if not os.path.exists(local):
        url = ("https://raw.githubusercontent.com/opencv/opencv/4.x/"
               "data/haarcascades/haarcascade_frontalface_default.xml")
        log.info("Downloading Haar cascade XML ...")
        urllib.request.urlretrieve(url, local)
    return local

CASCADE_PATH = find_cascade()
log.info(f"Cascade: {CASCADE_PATH}")
detector = cv2.CascadeClassifier(CASCADE_PATH)
if detector.empty():
    raise RuntimeError("Failed to load Haar cascade")

# --- OpenFace embedder (PS, 128-D, L2-normalized) ----------------------------
EMBED_FILE = "openface.nn4.small2.v1.t7"
EMBED_URLS = [
    "https://github.com/pyannote/pyannote-data/raw/master/openface.nn4.small2.v1.t7",
    "https://storage.cmusatyalab.org/openface-models/nn4.small2.v1.t7",
]
if not os.path.exists(EMBED_FILE):
    for url in EMBED_URLS:
        try:
            log.info(f"Downloading OpenFace model from {url}")
            urllib.request.urlretrieve(url, EMBED_FILE)
            break
        except Exception as e:
            log.warning(f"  failed: {e}")
    if not os.path.exists(EMBED_FILE):
        raise RuntimeError("Could not download nn4.small2.v1.t7 — fetch it manually.")

embedder = cv2.dnn.readNetFromTorch(EMBED_FILE)


def compute_embedding(face_bgr):
    """face_bgr: HxWx3 BGR uint8 -> 128-D L2-normalized float32 vector."""
    blob = cv2.dnn.blobFromImage(
        face_bgr, scalefactor=1.0 / 255,
        size=(96, 96), mean=(0, 0, 0),
        swapRB=True, crop=False)
    embedder.setInput(blob)
    v = embedder.forward().flatten().astype(np.float32)
    n = float(np.linalg.norm(v)) + 1e-8
    return v / n


def detect_and_embed(frame_bgr):
    """Detect on a downscaled frame, embed each face from the full-res crop.
    Returns list of (bbox_full_res, embedding)."""
    small = cv2.resize(frame_bgr, (0, 0),
                       fx=DETECTION_SCALE, fy=DETECTION_SCALE,
                       interpolation=cv2.INTER_LINEAR)
    gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))

    faces = detector.detectMultiScale(
        gray, scaleFactor=1.2, minNeighbors=5,
        minSize=(20, 20), flags=cv2.CASCADE_SCALE_IMAGE)

    out, inv = [], 1.0 / DETECTION_SCALE
    H, W = frame_bgr.shape[:2]
    for (x, y, w, h) in faces[:MAX_FACES]:
        # scale bbox back up; embed from full-res crop for quality
        xf, yf = int(x * inv), int(y * inv)
        wf, hf = int(w * inv), int(h * inv)
        xf, yf = max(0, xf), max(0, yf)
        xf2, yf2 = min(W, xf + wf), min(H, yf + hf)
        crop = frame_bgr[yf:yf2, xf:xf2]
        if crop.size == 0:
            continue
        out.append(((xf, yf, xf2 - xf, yf2 - yf), compute_embedding(crop)))
    return out


# --- Authorized embeddings ---------------------------------------------------
def load_authorized_embeddings(directory: str):
    embeddings = []
    emb_dir = Path(directory)
    if not emb_dir.exists():
        return []
    for path in sorted(emb_dir.glob("*.npy")):
        embeddings.append(np.load(str(path)).astype(np.float32))
    log.info(f"Loaded {len(embeddings)} identities.")
    return embeddings


# --- Threaded camera grabber -------------------------------------------------
class VideoFrameGrabber(threading.Thread):
    def __init__(self, path, fallback_img_path="ASUS.png"):
        super().__init__(daemon=True)
        self.cap = cv2.VideoCapture(path)
        # Keep only the newest frame in the backend buffer (FFmpeg/V4L2);
        # without this, IP-camera streams build up latency when the
        # consumer is slower than the producer.
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        self.fallback_path = fallback_img_path
        self._frame = None
        self._lock = threading.Lock()
        self.running = True
        log.info("VFG Init")

    def run(self):
        # Drain frames at the camera's native rate — cap.read() blocks until
        # the next frame arrives, so this naturally paces itself without any
        # explicit sleep. The processing loop downstream still throttles to
        # HDMI_INTERVAL via the latest()-grab pattern.
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

log.info("Starting optimized detection + HDMI streaming...")

frame_count    = 0
last_hdmi_time = time.time()
last_encodings = []

try:
    last_loop_time = 0.0

    while True:
        current_time = time.time()
        if (current_time - last_loop_time) < HDMI_INTERVAL:
            time.sleep(HDMI_INTERVAL - (current_time - last_loop_time))
            continue
        last_loop_time = time.time()

        frame = grabber.latest()
        if frame is None:
            time.sleep(0.01)
            continue
        frame_count += 1

        # ---- A. Detection + embedding (throttled) ----------------------------
        if frame_count % DETECTION_EVERY == 0:
            detections = detect_and_embed(frame)
            last_encodings = [emb for _, emb in detections]

            if not last_encodings:
                # keep the PL cosine pipeline exercised + log no-user state
                a = np.random.randn(128).astype(np.float32)
                b = np.random.randn(128).astype(np.float32)
                match, cos_ref = cs.compare(a, b, threshold=1.0)
                log.info("No User Found!")

        # ---- B. PL cosine matching ------------------------------------------
        for cam_emb in last_encodings:
            cam_emb = cam_emb.astype(np.float32)
            for auth_emb in auth_embs:
                match, score = cs.compare(cam_emb, auth_emb,
                                          threshold=MATCH_THRESHOLD)
                if match:
                    log.info(f"MATCH FOUND! Score: {score:.4f}")
                    break
                else:
                    log.info(f"MATCH NOT FOUND! Score: {score: .4f}")

except KeyboardInterrupt:
    log.info("Shutting down...")
except Exception as e:
    log.exception(e)
finally:
    grabber.running = False
    log.info("Cleanup complete.")
