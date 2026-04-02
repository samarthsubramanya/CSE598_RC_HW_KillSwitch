/**
 * CNN Embedding Engine — SUPERSEDED
 *
 * This module has been removed from the synthesis flow.
 *
 * Reason:
 *   Implementing a quantized ResNet-34 in raw Verilog requires pre-trained
 *   weight files (BRAM init data) and a complete datapath — this was a
 *   structural skeleton with no actual computation. Attempting to synthesize
 *   it would produce a bitstream that generates only zeros.
 *
 * Replacement:
 *   Face embedding is now computed on the PS (ARM CPU) using the
 *   face_recognition Python library (dlib + ResNet-34 model).
 *   The 128-D embeddings produced are identical in format to what this
 *   module was intended to output, so the Python recognition pipeline
 *   (recognition.py) is unchanged.
 *
 *   See: main/python/recognition.py  → PSFaceProcessor.process_frame()
 *
 * This file is kept for documentation purposes only.
 * It is NOT included in the synthesis file list (create_project.tcl).
 */

// (no synthesizable content)
