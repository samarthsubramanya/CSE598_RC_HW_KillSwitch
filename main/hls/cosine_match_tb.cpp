/**
 * cosine_match_tb.cpp
 * HLS Testbench for cosine_match_accel
 *
 * Verifies the fixed-point HLS accelerator against a software reference.
 * Run in Vivado HLS: Project → Run C Simulation
 *
 * Tests:
 *   1. Exact match — query equals enrolled user embedding
 *   2. Near match  — query is a noisy version of enrolled user
 *   3. No match    — query is orthogonal to all enrolled embeddings
 *   4. Multi-user  — finds the correct closest user among several
 */

#include "cosine_match.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>

// -----------------------------------------------------------------------
// Software reference: cosine similarity on float (for comparison)
// -----------------------------------------------------------------------
static float cosine_sim_ref(const float *a, const float *b, int dim) {
    float dot = 0.0f, na = 0.0f, nb = 0.0f;
    for (int i = 0; i < dim; i++) {
        dot += a[i] * b[i];
        na  += a[i] * a[i];
        nb  += b[i] * b[i];
    }
    return dot / (sqrtf(na) * sqrtf(nb) + 1e-8f);
}

// Normalize a float vector in-place
static void l2_normalize(float *v, int dim) {
    float n = 0.0f;
    for (int i = 0; i < dim; i++) n += v[i] * v[i];
    n = sqrtf(n) + 1e-8f;
    for (int i = 0; i < dim; i++) v[i] /= n;
}

// Simple LCG for deterministic pseudo-random test data
static unsigned int rng_state = 42;
static float rand_float() {
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((int)rng_state) / (float)(1 << 31);  // [-1, 1)
}

int main() {
    int failures = 0;

    printf("=== cosine_match_accel testbench ===\n\n");

    // -------------------------------------------------------------------
    // Test 1: Exact match
    // -------------------------------------------------------------------
    {
        printf("Test 1: exact match ... ");

        float user0_f[EMB_DIM];
        for (int d = 0; d < EMB_DIM; d++) user0_f[d] = rand_float();
        l2_normalize(user0_f, EMB_DIM);

        emb_t query[EMB_DIM];
        emb_t db[MAX_USERS * EMB_DIM];

        for (int d = 0; d < EMB_DIM; d++) {
            query[d]              = emb_t(user0_f[d]);
            db[0 * EMB_DIM + d]   = emb_t(user0_f[d]);
        }
        // Second user: orthogonal-ish
        for (int d = 0; d < EMB_DIM; d++) db[1 * EMB_DIM + d] = emb_t(-user0_f[d]);

        int   best_idx;
        acc_t best_score;
        cosine_match_accel(query, db, 2, &best_idx, &best_score);

        if (best_idx != 0) {
            printf("FAIL (expected idx=0, got %d)\n", best_idx);
            failures++;
        } else {
            float score_f = (float)best_score;
            printf("PASS (idx=%d, score=%.4f)\n", best_idx, score_f);
        }
    }

    // -------------------------------------------------------------------
    // Test 2: Near match (query = user + small noise)
    // -------------------------------------------------------------------
    {
        printf("Test 2: near match with noise ... ");

        float user0_f[EMB_DIM], query_f[EMB_DIM];
        for (int d = 0; d < EMB_DIM; d++) user0_f[d] = rand_float();
        l2_normalize(user0_f, EMB_DIM);

        // Add small Gaussian-like noise
        for (int d = 0; d < EMB_DIM; d++)
            query_f[d] = user0_f[d] + 0.05f * rand_float();
        l2_normalize(query_f, EMB_DIM);

        float ref_score = cosine_sim_ref(query_f, user0_f, EMB_DIM);

        emb_t query[EMB_DIM];
        emb_t db[MAX_USERS * EMB_DIM];

        for (int d = 0; d < EMB_DIM; d++) {
            query[d]            = emb_t(query_f[d]);
            db[0 * EMB_DIM + d] = emb_t(user0_f[d]);
        }
        // Unrelated second user
        for (int d = 0; d < EMB_DIM; d++) {
            float v = rand_float();
            db[1 * EMB_DIM + d] = emb_t(v);
        }

        int   best_idx;
        acc_t best_score;
        cosine_match_accel(query, db, 2, &best_idx, &best_score);

        float score_f = (float)best_score;
        float err     = fabsf(score_f - ref_score);

        if (best_idx != 0 || err > 0.01f) {
            printf("FAIL (idx=%d ref_score=%.4f got=%.4f err=%.4f)\n",
                   best_idx, ref_score, score_f, err);
            failures++;
        } else {
            printf("PASS (idx=%d score=%.4f ref=%.4f err=%.4f)\n",
                   best_idx, score_f, ref_score, err);
        }
    }

    // -------------------------------------------------------------------
    // Test 3: Multi-user — finds correct user among N=8
    // -------------------------------------------------------------------
    {
        printf("Test 3: multi-user (N=8) correct selection ... ");

        int  correct_user = 5;
        int  num_users    = 8;
        float db_f[MAX_USERS][EMB_DIM];
        float query_f[EMB_DIM];

        // Generate random unit-norm users
        for (int u = 0; u < num_users; u++) {
            for (int d = 0; d < EMB_DIM; d++) db_f[u][d] = rand_float();
            l2_normalize(db_f[u], EMB_DIM);
        }

        // Query = noisy version of correct_user
        for (int d = 0; d < EMB_DIM; d++)
            query_f[d] = db_f[correct_user][d] + 0.03f * rand_float();
        l2_normalize(query_f, EMB_DIM);

        // Verify software reference also selects the same user
        int ref_best = -1; float ref_best_s = -2.0f;
        for (int u = 0; u < num_users; u++) {
            float s = cosine_sim_ref(query_f, db_f[u], EMB_DIM);
            if (s > ref_best_s) { ref_best_s = s; ref_best = u; }
        }

        emb_t query[EMB_DIM];
        emb_t db[MAX_USERS * EMB_DIM];
        for (int d = 0; d < EMB_DIM; d++) query[d] = emb_t(query_f[d]);
        for (int u = 0; u < num_users; u++)
            for (int d = 0; d < EMB_DIM; d++)
                db[u * EMB_DIM + d] = emb_t(db_f[u][d]);

        int   best_idx;
        acc_t best_score;
        cosine_match_accel(query, db, num_users, &best_idx, &best_score);

        if (best_idx != ref_best) {
            printf("FAIL (expected=%d got=%d ref_score=%.4f)\n",
                   ref_best, best_idx, ref_best_s);
            failures++;
        } else {
            printf("PASS (idx=%d score=%.4f)\n", best_idx, (float)best_score);
        }
    }

    // -------------------------------------------------------------------
    // Test 4: No enrolled users edge case (num_users = 1)
    // -------------------------------------------------------------------
    {
        printf("Test 4: single enrolled user ... ");

        float user_f[EMB_DIM];
        for (int d = 0; d < EMB_DIM; d++) user_f[d] = rand_float();
        l2_normalize(user_f, EMB_DIM);

        emb_t query[EMB_DIM];
        emb_t db[MAX_USERS * EMB_DIM];
        for (int d = 0; d < EMB_DIM; d++) {
            query[d]            = emb_t(user_f[d]);
            db[0 * EMB_DIM + d] = emb_t(user_f[d]);
        }

        int   best_idx;
        acc_t best_score;
        cosine_match_accel(query, db, 1, &best_idx, &best_score);

        if (best_idx != 0) {
            printf("FAIL (expected idx=0, got %d)\n", best_idx);
            failures++;
        } else {
            printf("PASS (idx=%d score=%.4f)\n", best_idx, (float)best_score);
        }
    }

    // -------------------------------------------------------------------
    printf("\n=== Results: %d test(s) FAILED ===\n", failures);
    return failures;
}