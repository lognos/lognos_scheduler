import sqlite3
import numpy as np
from google import genai
from google.genai import types
import hashlib
import struct
from typing import List, Dict, Tuple
from backend.repositories.p6_repository import P6Repository
from backend.config.settings import settings
from backend.utils.db import get_db_connection
from backend.utils.safe_db import SafeP6Transaction

class VectorService:
    def __init__(self):
        self.repo = P6Repository()
        # Configure Gemini
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in configuration.")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = 'models/embedding-001'
        self._cache: Dict[int, Dict[int, np.ndarray]] = {} # proj_id -> {task_id: vector}

    def _compute_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _serialize_vector(self, vector: List[float]) -> bytes:
        """Packs a list of floats into bytes."""
        return struct.pack(f'{len(vector)}f', *vector)

    def _deserialize_vector(self, data: bytes) -> np.ndarray:
        """Unpacks bytes into a numpy array."""
        count = len(data) // 4
        return np.array(struct.unpack(f'{count}f', data), dtype=np.float32)

    def ensure_schema(self, conn: sqlite3.Connection):
        self.repo.ensure_embeddings_table(conn)

    def index_project(self, proj_id: int, conn: sqlite3.Connection = None):
        """
        Generates embeddings for all activities in a project if they are missing or outdated.
        """
        # Use provided connection or create a safe transaction
        if conn:
            self._index_project_impl(conn, proj_id)
        else:
            with SafeP6Transaction() as txn:
                self._index_project_impl(txn.conn, proj_id)
                txn.mark_modified()

    def _index_project_impl(self, conn: sqlite3.Connection, proj_id: int):
        self.ensure_schema(conn)
        
        # 1. Fetch all tasks and their text data
        tasks = self.repo.get_task_text_data(conn, proj_id)
        
        # 2. Fetch existing embeddings metadata (to check hashes)
        # We can just fetch all and check in memory, or optimize.
        # For simplicity, let's fetch all existing IDs and Hashes.
        cursor = conn.cursor()
        cursor.execute("SELECT TASK_ID, SOURCE_TEXT_HASH FROM TASK_EMBEDDINGS WHERE PROJ_ID = ?", (proj_id,))
        existing = {row[0]: row[1] for row in cursor.fetchall()}
        
        to_embed = []
        
        for task_id, code, name, memo, wbs_path in tasks:
            # Construct rich context: "Project > Phase 1 > A100: Excavation. Notes..."
            # Format: {WBS_PATH} > {TASK_CODE}: {TASK_NAME}. {MEMO}
            base = f"{code}: {name}"
            if wbs_path:
                base = f"{wbs_path} > {base}"
            
            if memo:
                base = f"{base}. {memo}"
                
            description = base.strip()
            current_hash = self._compute_hash(description)
            
            if task_id not in existing or existing[task_id] != current_hash:
                to_embed.append((task_id, description, current_hash))
        
        if not to_embed:
            return # Nothing to update

        # 3. Generate Embeddings in Batches
        batch_size = 100
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i:i+batch_size]
            texts = [item[1] for item in batch]
            
            try:
                # Gemini API call
                result = self.client.models.embed_content(
                    model=self.model,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                    )
                )
                
                embeddings = [e.values for e in result.embeddings]
                
                # 4. Save to DB
                for j, (task_id, _, source_hash) in enumerate(batch):
                    vector_bytes = self._serialize_vector(embeddings[j])
                    self.repo.upsert_task_embedding(conn, task_id, proj_id, vector_bytes, source_hash)
                    
            except Exception as e:
                print(f"Error embedding batch {i}: {e}")
                # Continue to next batch or raise?
                # For now, log and continue
                continue

    def search_activities(self, query: str, proj_id: int, limit: int = 3, threshold: float = 0.7, conn: sqlite3.Connection = None) -> List[Tuple[int, float]]:
        """
        Searches for activities matching the query.
        Returns list of (task_id, score).
        """
        if conn:
            return self._search_impl(conn, query, proj_id, limit, threshold)
        else:
            # Read-only, can use direct connection if we trust cache, 
            # but better to use SafeP6Transaction to ensure we see latest data if called within a transaction context
            # However, for pure read, get_db_connection is faster.
            # But if we need to index first (auto-index), we need write.
            # Let's assume indexing is done or triggered separately.
            with get_db_connection() as direct_conn:
                return self._search_impl(direct_conn, query, proj_id, limit, threshold)

    def _search_impl(self, conn: sqlite3.Connection, query: str, proj_id: int, limit: int, threshold: float) -> List[Tuple[int, float]]:
        # 1. Ensure Cache is populated
        if proj_id not in self._cache:
            self.ensure_schema(conn)
            rows = self.repo.get_project_embeddings(conn, proj_id)
            if not rows:
                # Try indexing if empty?
                # For now, just return empty
                return []
            
            self._cache[proj_id] = {}
            for task_id, blob in rows:
                self._cache[proj_id][task_id] = self._deserialize_vector(blob)
        
        project_vectors = self._cache[proj_id]
        if not project_vectors:
            return []

        # 2. Embed Query
        result = self.client.models.embed_content(
            model=self.model,
            contents=query,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
            )
        )
        query_embedding = result.embeddings[0].values
        query_vec = np.array(query_embedding, dtype=np.float32)

        # 3. Compute Cosine Similarity
        # Matrix multiplication for speed
        task_ids = list(project_vectors.keys())
        matrix = np.stack(list(project_vectors.values()))
        
        # Normalize query
        norm_query = np.linalg.norm(query_vec)
        if norm_query == 0:
            return []
        
        # Normalize matrix (pre-calculating this in cache would be better, but this is fast enough)
        norm_matrix = np.linalg.norm(matrix, axis=1)
        
        dot_products = np.dot(matrix, query_vec)
        similarities = dot_products / (norm_matrix * norm_query)
        
        # 4. Rank and Filter
        results = []
        for idx, score in enumerate(similarities):
            if score >= threshold:
                results.append((task_ids[idx], float(score)))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
