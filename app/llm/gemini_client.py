from __future__ import annotations

import time
from typing import List, Optional

from google import genai
from google.genai import types
from google.genai.errors import ClientError


class GeminiClient:
    """
    Lightweight wrapper for Gemini (free tier friendly).

    - Text generation: gemini-2.5-flash
    - Embeddings: gemini-embedding-001
    - Handles:
        * Batch limit for embeddings (<=100 items/request)
        * Free-tier 429 (RESOURCE_EXHAUSTED) with per-batch retry/backoff
        * Optional per-batch sleep to be extra gentle on quotas
    """

    def __init__(
        self,
        api_key: str,
        gen_model: str = "gemini-2.5-flash",
        emb_model: str = "gemini-embedding-001",
        emb_dim: int = 768,
        batch_size: int = 100,        # Gemini cap per embed request
        per_batch_sleep: float = 0.0, # optional delay between batches (seconds)
    ):
        # If api_key is set via environment, passing empty here is also fine.
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self.gen_model = gen_model
        self.emb_model = emb_model
        self.emb_dim = emb_dim
        self.batch_size = max(1, min(batch_size, 100))
        self.per_batch_sleep = max(0.0, per_batch_sleep)

    # -----------------
    # Embeddings
    # -----------------
    def embed(
        self,
        texts: List[str],
        task: str = "RETRIEVAL_DOCUMENT",  # or "RETRIEVAL_QUERY"
        dim: Optional[int] = None,
    ) -> list[list[float]]:
        """
        Embed a list of texts with batching and 429 backoff.
        Returns a list of vectors aligned with `texts`.
        """
        if not texts:
            return []

        output_dim = dim or self.emb_dim
        cfg = types.EmbedContentConfig(
            task_type=task,
            output_dimensionality=output_dim,
        )

        vectors: list[list[float]] = []

        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]

            # Retry loop for this batch only (handles free-tier 429s)
            while True:
                try:
                    # NOTE: google-genai supports batching by passing list[str] to `contents`
                    res = self.client.models.embed_content(
                        model=self.emb_model,
                        contents=chunk,
                        config=cfg,
                    )
                    vectors.extend([e.values for e in res.embeddings])

                    # Gentle throttle between batches if configured
                    if self.per_batch_sleep:
                        time.sleep(self.per_batch_sleep)
                    break

                except ClientError as e:
                    # Handle free-tier rate limit
                    is_429 = getattr(e, "status_code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)
                    if is_429:
                        # Sleep a little over a minute, then retry this same batch
                        time.sleep(65)
                        continue
                    # Other errors: bubble up
                    raise

        return vectors

    # -----------------
    # Generation
    # -----------------
    def generate(self, prompt: str) -> str:
        """
        Simple text generation call with the flash model.
        """
        res = self.client.models.generate_content(
            model=self.gen_model,
            contents=prompt,
        )
        return res.text or ""
