"""Semantic search helpers for MS schedule activities."""

from google import genai
from google.genai import types
import logfire
from starlette.concurrency import run_in_threadpool

from backend.config.settings import settings


class ActivitySemanticSearchService:
    """Generate query embeddings compatible with schedule activity vectors."""

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in configuration.")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.SCHEDULE_EMBEDDING_MODEL
        self.dimensions = settings.SCHEDULE_EMBEDDING_DIMENSIONS

    @logfire.instrument("activity_semantic_search.embed_query")
    async def embed_query(self, query: str) -> list[float]:
        """Return a query embedding for semantic activity search."""
        try:
            config = types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.dimensions,
            )
            result = await run_in_threadpool(
                self.client.models.embed_content,
                model=self.model,
                contents=query,
                config=config,
            )
        except TypeError:
            logfire.warning(
                "Embedding SDK does not support output_dimensionality; retrying without it",
                model=self.model,
                expected_dimensions=self.dimensions,
            )
            result = await run_in_threadpool(
                self.client.models.embed_content,
                model=self.model,
                contents=query,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
            )

        if not result.embeddings:
            raise RuntimeError("Embedding model returned no vectors.")

        values = list(result.embeddings[0].values)
        if len(values) != self.dimensions:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(values)}, expected {self.dimensions}."
            )
        return values