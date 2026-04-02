/**
 * cosine_match.h
 * HLS Cosine Similarity Accelerator — Face Recognition Kill Switch
 *
 * Computes cosine similarity between a query face embedding and every
 * enrolled user embedding stored in on-chip BRAM, returning the best
 * match index and score.
 *
 * Since all embeddings are L2-normalized unit vectors:
 *   cosine_similarity(a, b) = dot(a, b)     (no division needed)
 *
 * Fixed-point format — Q2.14  (ap_fixed<16,2>):
 *   Range : [-2.0, 2.0)
 *   LSB   : 2^-14 ≈ 6.1e-5
 *   Sufficient for unit-norm embeddings whose components lie in [-1, 1].
 *
 * Hardware resources (Zynq-7020 @ 100 MHz, UNROLL factor=8):
 *   DSP48E1 : ~8  (one per parallel MAC lane)
 *   BRAM    : ~1  (8 KB for 32 users × 128 dims × 2 bytes)
 *   LUT     : ~200
 *   Latency : 128/8 × num_users cycles  ≈  512 cycles @ 32 users → 5 µs
 */

#ifndef COSINE_MATCH_H
#define COSINE_MATCH_H

#include <ap_fixed.h>

// -----------------------------------------------------------------------
// Compile-time parameters — must match Python side (fpga_interface.py)
// -----------------------------------------------------------------------
#define EMB_DIM   128    // embedding dimensionality
#define MAX_USERS  32    // maximum enrolled users (BRAM-limited)

// Fixed-point types
typedef ap_fixed<16, 2, AP_RND, AP_SAT>  emb_t;   // Q2.14  single component
typedef ap_fixed<32, 4, AP_RND, AP_SAT>  acc_t;   // Q4.28  dot-product accumulator

// -----------------------------------------------------------------------
// Top-level function declaration
// -----------------------------------------------------------------------
void cosine_match_accel(
    emb_t  query[EMB_DIM],              // query embedding (from PS via AXI-Lite)
    emb_t  db_mem[MAX_USERS * EMB_DIM], // enrolled embeddings (AXI4 BRAM port)
    int    num_users,                    // number of enrolled users (1..MAX_USERS)
    int   *best_idx,                     // output: index of best match
    acc_t *best_score                    // output: similarity score (Q4.28)
);

#endif // COSINE_MATCH_H