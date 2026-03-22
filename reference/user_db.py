"""
User database and enrollment management
Stores user embeddings and allows registration/lookup
"""

import json
import numpy as np
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE = "data/users.json"


class UserDatabase:
    """Manages user enrollment and storage"""

    def __init__(self, db_file=DB_FILE):
        """
        Initialize user database

        Args:
            db_file: Path to JSON file storing user data
        """
        self.db_file = db_file
        self.users = {}
        self.load_database()

    def load_database(self):
        """Load user database from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r") as f:
                    data = json.load(f)
                    # Convert lists back to numpy arrays
                    for username, user_data in data.items():
                        user_data["embedding"] = np.array(user_data["embedding"])
                    self.users = data
                logger.info(f"Loaded {len(self.users)} users from database")
            except Exception as e:
                logger.error(f"Failed to load database: {e}")
                self.users = {}
        else:
            logger.info("New database, no existing users")
            self.users = {}

    def save_database(self):
        """Save database to file"""
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        try:
            # Convert numpy arrays to lists for JSON serialization
            data_to_save = {}
            for username, user_data in self.users.items():
                data_to_save[username] = {
                    "embedding": user_data["embedding"].tolist(),
                    "registered_at": user_data.get("registered_at", ""),
                    "enrollment_samples": user_data.get("enrollment_samples", 0),
                }

            with open(self.db_file, "w") as f:
                json.dump(data_to_save, f, indent=2)
            logger.info(f"Database saved with {len(self.users)} users")
        except Exception as e:
            logger.error(f"Failed to save database: {e}")

    def enroll_user(self, username, embedding):
        """
        Enroll a new user with averaged embedding

        Args:
            username (str): User identifier
            embedding (numpy.ndarray): 64-D embedding vector

        Returns:
            bool: True if successful
        """
        if embedding is None or len(embedding) == 0:
            logger.error("Invalid embedding")
            return False

        if username in self.users:
            logger.warning(f"User {username} already exists, updating...")

        try:
            self.users[username] = {
                "embedding": np.array(embedding),
                "registered_at": str(np.datetime64("today")),
                "enrollment_samples": 1,
            }
            self.save_database()
            logger.info(f"Enrolled user: {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to enroll user: {e}")
            return False

    def update_user_embedding(self, username, new_embedding, alpha=0.7):
        """
        Update user embedding (incremental enrollment)

        Args:
            username (str): User identifier
            new_embedding (numpy.ndarray): New embedding
            alpha (float): Weight for existing embedding (0.7 = 70% old, 30% new)

        Returns:
            bool: True if successful
        """
        if username not in self.users:
            logger.warning(f"User {username} not found")
            return self.enroll_user(username, new_embedding)

        try:
            old_embedding = self.users[username]["embedding"]
            # Weighted average
            updated = alpha * old_embedding + (1 - alpha) * new_embedding
            # Normalize
            updated = updated / (np.linalg.norm(updated) + 1e-8)

            self.users[username]["embedding"] = updated
            self.users[username]["enrollment_samples"] += 1
            self.save_database()
            logger.info(f"Updated embedding for user: {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to update user embedding: {e}")
            return False

    def get_user_embedding(self, username):
        """
        Get stored embedding for a user

        Args:
            username (str): User identifier

        Returns:
            numpy.ndarray: Embedding vector or None
        """
        if username in self.users:
            return self.users[username]["embedding"]
        return None

    def delete_user(self, username):
        """
        Delete a user from database

        Args:
            username (str): User identifier

        Returns:
            bool: True if successful
        """
        if username in self.users:
            del self.users[username]
            self.save_database()
            logger.info(f"Deleted user: {username}")
            return True
        logger.warning(f"User {username} not found")
        return False

    def list_users(self):
        """
        Get list of enrolled users

        Returns:
            list: Usernames of all enrolled users
        """
        return list(self.users.keys())

    def clear_all(self):
        """Clear all users from database"""
        self.users = {}
        self.save_database()
        logger.info("Database cleared")
