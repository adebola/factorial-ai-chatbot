import os
import json
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from langchain_core.documents import Document
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, Session
from openai import OpenAI
import redis

from ..core.config import settings
from ..core.database import engine_vector
from ..core.logging_config import get_logger


class PgVectorStore:
    """
    PostgreSQL-based vector store for similarity search using pgvector extension.

    This service is READ-ONLY for the chat service - it only performs similarity searches.
    All write operations (add_documents, delete_documents) are handled by the onboarding service.
    """

    # Maximum cosine distance for results to be considered relevant
    MAX_DISTANCE = 1.5

    # Embedding cache TTL in seconds (1 hour)
    EMBEDDING_CACHE_TTL = 3600

    def __init__(self):
        self.logger = get_logger("pg_vector_store")

        # Get OpenAI API key
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")

        self.openai_client = OpenAI(api_key=openai_api_key, timeout=60.0, max_retries=2)

        # Reuse shared vector database engine from database.py (with connection pooling)
        self.engine = engine_vector
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Redis client for embedding cache
        try:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
        except Exception as e:
            self.logger.warning(f"Redis unavailable for embedding cache, caching disabled: {e}")
            self._redis = None

        self.logger.info("PgVectorStore initialized successfully")

    def _embedding_cache_key(self, text: str) -> str:
        """Generate Redis cache key for an embedding"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"emb:{text_hash}"

    def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """Try to get a cached embedding from Redis"""
        if not self._redis:
            return None
        try:
            cached = self._redis.get(self._embedding_cache_key(text))
            if cached:
                return json.loads(cached)
        except Exception as e:
            self.logger.warning(f"Redis embedding cache read error: {e}")
        return None

    def _cache_embedding(self, text: str, embedding: List[float]) -> None:
        """Cache an embedding in Redis"""
        if not self._redis:
            return
        try:
            self._redis.setex(
                self._embedding_cache_key(text),
                self.EMBEDDING_CACHE_TTL,
                json.dumps(embedding)
            )
        except Exception as e:
            self.logger.warning(f"Redis embedding cache write error: {e}")

    def _generate_embeddings(self, texts: List[str], tenant_id: str = None, session_id: str = None) -> List[List[float]]:
        """Generate embeddings using OpenAI API with Redis caching"""
        results = [None] * len(texts)
        uncached_texts = []
        uncached_indices = []

        # Check cache for each text
        for i, text in enumerate(texts):
            cached = self._get_cached_embedding(text)
            if cached:
                results[i] = cached
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        if uncached_texts:
            try:
                response = self.openai_client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=uncached_texts,
                    timeout=15.0
                )
                for j, item in enumerate(response.data):
                    idx = uncached_indices[j]
                    results[idx] = item.embedding
                    self._cache_embedding(uncached_texts[j], item.embedding)

                # Record embedding token usage
                if tenant_id and response.usage:
                    try:
                        from .token_usage_service import token_usage_service
                        token_usage_service.record_usage(
                            tenant_id=tenant_id,
                            model="text-embedding-ada-002",
                            usage_type="embedding",
                            prompt_tokens=response.usage.prompt_tokens,
                            completion_tokens=0,
                            total_tokens=response.usage.total_tokens,
                            session_id=session_id,
                        )
                    except Exception as rec_err:
                        self.logger.warning(f"Failed to record embedding token usage: {rec_err}")
            except Exception as e:
                self.logger.error(f"Failed to generate embeddings: {e}")
                raise

        if uncached_texts:
            self.logger.debug(
                f"Embedding cache: {len(texts) - len(uncached_texts)} hits, {len(uncached_texts)} misses"
            )

        return results

    def search_similar(
        self,
        tenant_id: str,
        query: str,
        k: int = 4,
        category_ids: List[str] = None,
        tag_ids: List[str] = None,
        content_types: List[str] = None
    ) -> List[Document]:
        """
        Search for similar documents using vector similarity with optional filtering.

        Args:
            tenant_id: The tenant ID to search within
            query: The search query text
            k: Number of similar documents to return (default: 4)
            category_ids: Optional list of category IDs to filter by
            tag_ids: Optional list of tag IDs to filter by
            content_types: Optional list of content types to filter by

        Returns:
            List of similar documents with metadata including categorization
        """
        try:
            # Generate embedding for query
            query_embeddings = self._generate_embeddings([query], tenant_id=tenant_id)
            query_embedding = query_embeddings[0]

            session = self.SessionLocal()
            try:
                # Build dynamic WHERE clause for filters (includes distance threshold)
                where_clauses = [
                    "tenant_id = :tenant_id",
                    "(embedding <=> :query_embedding) < :max_distance"
                ]
                params = {
                    "tenant_id": tenant_id,
                    "query_embedding": str(query_embedding),
                    "k": k,
                    "max_distance": self.MAX_DISTANCE
                }

                # Add category filter if provided
                if category_ids:
                    where_clauses.append("category_ids && :category_ids")
                    # Convert Python list to PostgreSQL array format
                    params["category_ids"] = '{' + ','.join(category_ids) + '}'

                # Add tag filter if provided
                if tag_ids:
                    where_clauses.append("tag_ids && :tag_ids")
                    params["tag_ids"] = '{' + ','.join(tag_ids) + '}'

                # Add content_type filter if provided
                if content_types:
                    where_clauses.append("content_type = ANY(:content_types)")
                    params["content_types"] = content_types

                where_clause = " AND ".join(where_clauses)

                # Perform vector similarity search with filters
                query_sql = f"""
                    SELECT content, source_type, source_name, page_number, section_title,
                           category_ids, tag_ids, content_type,
                           (embedding <=> :query_embedding) as distance
                    FROM vectors.document_chunks
                    WHERE {where_clause}
                    ORDER BY embedding <=> :query_embedding
                    LIMIT :k
                """

                results = session.execute(text(query_sql), params).fetchall()

                # Convert to Document objects
                documents = []
                for row in results:
                    metadata = {
                        'source_type': row.source_type,
                        'source_name': row.source_name,
                        'page': row.page_number,
                        'section_title': row.section_title,
                        'category_ids': list(row.category_ids) if row.category_ids else [],
                        'tag_ids': list(row.tag_ids) if row.tag_ids else [],
                        'content_type': row.content_type,
                        'distance': float(row.distance)
                    }
                    # Remove None values
                    metadata = {k: v for k, v in metadata.items() if v is not None}

                    documents.append(Document(
                        page_content=row.content,
                        metadata=metadata
                    ))

                filter_info = []
                if category_ids:
                    filter_info.append(f"categories={len(category_ids)}")
                if tag_ids:
                    filter_info.append(f"tags={len(tag_ids)}")
                if content_types:
                    filter_info.append(f"types={','.join(content_types)}")

                filter_str = f" with filters: {', '.join(filter_info)}" if filter_info else ""
                self.logger.info(f"Vector search returned {len(documents)} documents for tenant {tenant_id}{filter_str}")
                return documents

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Vector search failed for tenant {tenant_id}: {e}")
            return []

    def search_with_score(
        self,
        tenant_id: str,
        query: str,
        k: int = 4,
        category_ids: List[str] = None,
        tag_ids: List[str] = None,
        content_types: List[str] = None
    ) -> List[Tuple[Document, float]]:
        """
        Search with similarity scores and optional filtering.

        Args:
            tenant_id: The tenant ID to search within
            query: The search query text
            k: Number of similar documents to return (default: 4)
            category_ids: Optional list of category IDs to filter by
            tag_ids: Optional list of tag IDs to filter by
            content_types: Optional list of content types to filter by

        Returns:
            List of tuples containing (Document, similarity_score)
        """
        try:
            query_embeddings = self._generate_embeddings([query], tenant_id=tenant_id)
            query_embedding = query_embeddings[0]

            session = self.SessionLocal()
            try:
                # Build dynamic WHERE clause for filters
                where_clauses = ["tenant_id = :tenant_id"]
                params = {
                    "tenant_id": tenant_id,
                    "query_embedding": str(query_embedding),
                    "k": k
                }

                # Add category filter if provided
                if category_ids:
                    where_clauses.append("category_ids && :category_ids")
                    params["category_ids"] = '{' + ','.join(category_ids) + '}'

                # Add tag filter if provided
                if tag_ids:
                    where_clauses.append("tag_ids && :tag_ids")
                    params["tag_ids"] = '{' + ','.join(tag_ids) + '}'

                # Add content_type filter if provided
                if content_types:
                    where_clauses.append("content_type = ANY(:content_types)")
                    params["content_types"] = content_types

                where_clause = " AND ".join(where_clauses)

                query_sql = f"""
                    SELECT content, source_type, source_name, page_number, section_title,
                           category_ids, tag_ids, content_type,
                           (embedding <=> :query_embedding) as distance
                    FROM vectors.document_chunks
                    WHERE {where_clause}
                    ORDER BY embedding <=> :query_embedding
                    LIMIT :k
                """

                results = session.execute(text(query_sql), params).fetchall()

                documents_with_scores = []
                for row in results:
                    metadata = {
                        'source_type': row.source_type,
                        'source_name': row.source_name,
                        'page': row.page_number,
                        'section_title': row.section_title,
                        'category_ids': list(row.category_ids) if row.category_ids else [],
                        'tag_ids': list(row.tag_ids) if row.tag_ids else [],
                        'content_type': row.content_type
                    }
                    metadata = {k: v for k, v in metadata.items() if v is not None}

                    document = Document(page_content=row.content, metadata=metadata)
                    # Convert distance to similarity score (1 - distance for cosine)
                    similarity_score = 1.0 - float(row.distance)
                    documents_with_scores.append((document, similarity_score))

                return documents_with_scores

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Vector search with score failed for tenant {tenant_id}: {e}")
            return []

    def get_tenant_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get statistics for a tenant's vector store.

        Args:
            tenant_id: The tenant ID to get stats for

        Returns:
            Dictionary containing chunk_count, document_count, ingestion_count,
            last_indexed_at, and avg_query_time_ms
        """
        session = self.SessionLocal()
        try:
            # Get chunk count and search index info
            result = session.execute(
                text("""
                    SELECT
                        COUNT(*) as chunk_count,
                        COUNT(DISTINCT document_id) as document_count,
                        COUNT(DISTINCT ingestion_id) as ingestion_count
                    FROM vectors.document_chunks
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id}
            ).first()

            search_index = session.execute(
                text("SELECT * FROM vectors.vector_search_indexes WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id}
            ).first()

            return {
                'tenant_id': tenant_id,
                'chunk_count': result.chunk_count if result else 0,
                'document_count': result.document_count if result else 0,
                'ingestion_count': result.ingestion_count if result else 0,
                'last_indexed_at': search_index.last_indexed_at if search_index else None,
                'avg_query_time_ms': search_index.avg_query_time_ms if search_index else 0
            }

        except Exception as e:
            self.logger.error(f"Failed to get tenant stats: {e}")
            return {}
        finally:
            session.close()
