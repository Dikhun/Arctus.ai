"""
Embedding Generator — Creates semantic embeddings for experience search.
"""

import hashlib
import json
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np


class EmbeddingGenerator:
    """
    Generates semantic embeddings for experiences to enable similarity search.
    Supports multiple embedding backends.
    """
    
    def __init__(self, config):
        self.config = config.embeddings if hasattr(config, 'embeddings') else config
        self.model = None
        self._cache: Dict[str, np.ndarray] = {}
        self._load_model()
    
    def _load_model(self):
        """Load the embedding model."""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.config.model_name, device=self.config.device)
        except ImportError:
            # Fallback to simple embedding
            self.model = None
    
    def _simple_embedding(self, text: str, dim: int = 384) -> np.ndarray:
        """Fallback simple embedding using character n-gram hashing."""
        # Simple but deterministic embedding for when transformers unavailable
        vec = np.zeros(dim, dtype=np.float32)
        text = text.lower()
        
        # Character trigrams
        for i in range(len(text) - 2):
            trigram = text[i:i+3]
            idx = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % dim
            vec[idx] += 1.0
        
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec
    
    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for a text string."""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if self.model is not None:
            embedding = self.model.encode(text, convert_to_numpy=True)
            if self.config.normalize_embeddings:
                embedding = embedding / np.linalg.norm(embedding)
        else:
            embedding = self._simple_embedding(text)
        
        self._cache[cache_key] = embedding
        return embedding
    
    def embed_experience(self, experience) -> np.ndarray:
        """
        Generate embeddi
        """
        pass # Cutoff in provided text - closed syntactically.
