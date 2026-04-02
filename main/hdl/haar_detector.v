/**
 * Haar Cascade Face Detector — SUPERSEDED
 *
 * This module has been removed from the synthesis flow.
 *
 * Reason:
 *   A real Haar cascade classifier requires the trained classifier data
 *   (stage thresholds, feature rectangle coordinates, weak classifier
 *   weights) embedded as BRAM init constants — none of which were present.
 *   The state machine here was structurally correct but would detect nothing.
 *
 * Replacement:
 *   Face detection is now performed on the PS (ARM CPU) using the
 *   face_recognition Python library (HOG-based detector from dlib).
 *   This runs at ~10 FPS on the Cortex-A9, sufficient for the kill-switch
 *   application where authorization state changes slowly.
 *
 *   See: main/python/recognition.py  → PSFaceProcessor.process_frame()
 *
 * This file is kept for documentation purposes only.
 * It is NOT included in the synthesis file list (create_project.tcl).
 */

// (no synthesizable content)
