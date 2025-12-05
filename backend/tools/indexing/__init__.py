"""Indexing tools package - tools for vector indexing operations.

These tools manage the vector search index for semantic activity search.

All tool names follow the convention: {action}_{entity}
"""

from backend.tools.indexing.operations import (
    index_project,
)

__all__ = [
    "index_project",
]
