"""
Intent Embedding Service for semantic trigger detection.

Uses OpenAI embeddings + cosine similarity to match user messages
against workflow intent patterns. Pattern embeddings are pre-computed
at workflow create/update time; only the user message is embedded at
trigger-check time (~20-50ms per call).
"""
import os
import math
from typing import List, Dict, Optional

from openai import OpenAI

from ..core.logging_config import get_logger

logger = get_logger("intent_embedding")

EMBEDDING_MODEL = "text-embedding-ada-002"


class IntentEmbeddingService:
    _client: Optional[OpenAI] = None

    @classmethod
    def _get_client(cls) -> OpenAI:
        """Lazy singleton — avoids creating client when not needed."""
        if cls._client is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY environment variable is not set")
            cls._client = OpenAI(api_key=api_key, timeout=15, max_retries=2)
        return cls._client

    def generate_pattern_embeddings(self, intent_patterns: List[str]) -> List[Dict]:
        """
        Embed all intent patterns in a single batch API call.

        Called at workflow create/update time (not in chat critical path).

        Returns:
            List of {"text": str, "embedding": List[float]} dicts.
        """
        if not intent_patterns:
            return []

        client = self._get_client()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=intent_patterns,
        )

        results = []
        for i, item in enumerate(response.data):
            results.append({
                "text": intent_patterns[i],
                "embedding": item.embedding,
            })

        logger.info(
            f"Generated embeddings for {len(intent_patterns)} intent patterns",
            extra={"pattern_count": len(intent_patterns)},
        )
        return results

    def embed_message(self, message: str) -> List[float]:
        """
        Embed a single user message.

        Called at trigger-check time (~20-50ms).
        """
        client = self._get_client()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[message],
        )
        return response.data[0].embedding

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Pure Python cosine similarity — no numpy needed for small vectors."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
