"""
Face Recognition Module
Performs embedding matching and manages authorization state
"""

import numpy as np
import logging
from typing import Optional
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class AuthStatus(Enum):
    """Authorization status"""
    AUTHORIZED = "AUTHORIZED"
    UNAUTHORIZED = "UNAUTHORIZED"
    UNKNOWN = "UNKNOWN"


class FaceRecognizer:
    """Recognizes faces by matching embeddings against stored database"""
    
    def __init__(self, user_db, similarity_threshold: float = 0.6):
        """
        Initialize recognizer
        
        Args:
            user_db: UserDatabase instance
            similarity_threshold: Cosine similarity threshold (0-1)
        """
        self.user_db = user_db
        self.similarity_threshold = similarity_threshold
        
        # Hysteresis state machine
        self.current_status = AuthStatus.UNKNOWN
        self.bad_frame_count = 0
        self.good_frame_count = 0
        self.lock_threshold = 3      # Bad frames to trigger lock
        self.unlock_threshold = 8    # Good frames to trigger unlock
        
        logger.info(f"Recognizer initialized (threshold={similarity_threshold})")
    
    def recognize(self, embedding: np.ndarray) -> dict:
        """
        Recognize a face from its embedding
        
        Args:
            embedding: 128-D embedding vector (normalized)
        
        Returns:
            Dict with:
            - 'status': AuthStatus
            - 'user': Username if recognized
            - 'confidence': Similarity score (0-1)
            - 'is_authorized': Boolean
        """
        if embedding is None or len(embedding) == 0:
            return {
                'status': AuthStatus.UNKNOWN,
                'user': None,
                'confidence': 0.0,
                'is_authorized': False
            }
        
        # Get all users from database
        users = self.user_db.get_all_users()
        
        if not users:
            return {
                'status': AuthStatus.UNKNOWN,
                'user': None,
                'confidence': 0.0,
                'is_authorized': False
            }
        
        # Find best match
        best_user = None
        best_similarity = -1.0
        
        for username, stored_embedding in users.items():
            # Compute cosine similarity
            similarity = self._cosine_similarity(embedding, stored_embedding)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_user = username
        
        # Determine authorization with hysteresis
        if best_similarity >= self.similarity_threshold:
            self.good_frame_count += 1
            self.bad_frame_count = 0
            
            if self.good_frame_count >= self.unlock_threshold:
                self.current_status = AuthStatus.AUTHORIZED
        else:
            self.bad_frame_count += 1
            self.good_frame_count = 0
            
            if self.bad_frame_count >= self.lock_threshold:
                self.current_status = AuthStatus.UNAUTHORIZED
        
        return {
            'status': self.current_status,
            'user': best_user if self.current_status == AuthStatus.AUTHORIZED else None,
            'confidence': best_similarity,
            'is_authorized': self.current_status == AuthStatus.AUTHORIZED
        }
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors
        
        Args:
            vec1: First vector
            vec2: Second vector
        
        Returns:
            Similarity score (0-1)
        """
        # Ensure normalized
        norm1 = np.linalg.norm(vec1) + 1e-8
        norm2 = np.linalg.norm(vec2) + 1e-8
        
        vec1_norm = vec1 / norm1
        vec2_norm = vec2 / norm2
        
        similarity = np.dot(vec1_norm, vec2_norm)
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, similarity))


# =====================================================================
# User Database
# =====================================================================

import json
from pathlib import Path


class UserDatabase:
    """Persistent user enrollment database"""
    
    def __init__(self, db_path: str = "data/users.json"):
        """
        Initialize database
        
        Args:
            db_path: Path to JSON database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {}
        
        self._load()
    
    def _load(self):
        """Load database from file"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                
                # Convert embeddings back to numpy arrays
                for username, embedding_list in data.items():
                    self.data[username] = np.array(embedding_list, dtype=np.float32)
                
                logger.info(f"Loaded {len(self.data)} users from database")
            except Exception as e:
                logger.error(f"Failed to load database: {e}")
                self.data = {}
        else:
            logger.info("Creating new database")
    
    def _save(self):
        """Save database to file"""
        try:
            # Convert embeddings to lists for JSON
            save_data = {}
            for username, embedding in self.data.items():
                save_data[username] = embedding.tolist()
            
            with open(self.db_path, 'w') as f:
                json.dump(save_data, f, indent=2)
            
            logger.info(f"Database saved with {len(self.data)} users")
        except Exception as e:
            logger.error(f"Failed to save database: {e}")
    
    def add_user(self, username: str, embedding: np.ndarray):
        """
        Add or update user with embedding
        
        Args:
            username (str): User identifier
            embedding (np.ndarray): 128-D embedding vector
        """
        if embedding is None or len(embedding) != 128:
            raise ValueError("Embedding must be 128-D")
        
        # Normalize embedding
        embedding = embedding.astype(np.float32)
        embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
        
        self.data[username] = embedding
        self._save()
        logger.info(f"User '{username}' added")
    
    def get_user(self, username: str) -> Optional[np.ndarray]:
        """
        Get user embedding
        
        Args:
            username (str): User identifier
        
        Returns:
            Embedding array or None if not found
        """
        return self.data.get(username)
    
    def get_all_users(self) -> dict:
        """
        Get all users
        
        Returns:
            Dict of {username: embedding}
        """
        return self.data.copy()
    
    def remove_user(self, username: str):
        """Remove user from database"""
        if username in self.data:
            del self.data[username]
            self._save()
            logger.info(f"User '{username}' removed")
    
    def clear_all(self):
        """Clear all users (use with caution!)"""
        self.data.clear()
        self._save()
        logger.info("Database cleared")
