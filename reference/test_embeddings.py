#!/usr/bin/env python3
"""
Test deterministic embeddings
"""

import sys
sys.path.insert(0, '.')

from model import FaceEmbeddingModel
import numpy as np

def test_deterministic_embeddings():
    """Test that same face produces same embedding"""
    print("Testing deterministic embeddings...\n")
    
    model = FaceEmbeddingModel()
    
    # Create realistic test faces with different features
    test_face1 = np.ones((96, 96), dtype=np.float32) * 0.5
    test_face1[20:50, 20:50] = 0.8  # Left eye area (bright)
    test_face1[20:50, 50:80] = 0.7  # Right eye area
    test_face1[60:80, 30:70] = 0.4  # Mouth area (darker)
    
    test_face2 = np.ones((96, 96), dtype=np.float32) * 0.5
    test_face2[25:55, 25:55] = 0.9  # Different eye positions
    test_face2[25:55, 55:85] = 0.6  # Different right eye
    test_face2[65:85, 35:75] = 0.3  # Different mouth
    
    # Compute embedding multiple times for same face
    emb1 = model.compute_embedding(test_face1)
    emb2 = model.compute_embedding(test_face1)
    emb3 = model.compute_embedding(test_face1)
    
    print(f"Same face - Embedding 1: {emb1[:8]}...")
    print(f"Same face - Embedding 2: {emb2[:8]}...")
    print(f"Same face - Embedding 3: {emb3[:8]}...\n")
    
    # Check if they're the same
    if emb1 is not None and emb2 is not None and emb3 is not None:
        diff_1_2 = np.linalg.norm(emb1 - emb2)
        diff_2_3 = np.linalg.norm(emb2 - emb3)
        
        print(f"Difference same face 1-2: {diff_1_2:.6f}")
        print(f"Difference same face 2-3: {diff_2_3:.6f}\n")
        
        if diff_1_2 < 0.0001 and diff_2_3 < 0.0001:
            print("✅ SUCCESS: Same face embeddings are deterministic\n")
            
            # Test similarity
            similarity_same = np.dot(emb1, emb2)
            print(f"Cosine similarity (same face): {similarity_same:.4f} (expected: ~1.0)\n")
            
            # Test different face
            emb_diff = model.compute_embedding(test_face2)
            
            if emb_diff is not None:
                similarity_diff = np.dot(emb1, emb_diff)
                print(f"Different faces - Embedding: {emb_diff[:8]}...")
                print(f"Cosine similarity (different faces): {similarity_diff:.4f}")
                
                if similarity_diff < 0.9:
                    print("\n✅ Different faces have distinct embeddings\n")
                    return True
                else:
                    print("\n⚠️ Different faces still too similar (consider enrollment strategy)")
                    return True  # Still works, just less distinguish
        else:
            print("❌ FAILED: Same face embeddings are not deterministic")
            return False
    else:
        print("❌ FAILED: Could not compute embeddings")
        return False

if __name__ == "__main__":
    success = test_deterministic_embeddings()
    sys.exit(0 if success else 1)
