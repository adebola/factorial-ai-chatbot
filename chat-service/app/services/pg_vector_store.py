import os
import hashlib
from typing import List, Dict, Any, Tuple
from langchain.docstore.document import Document
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from openai import OpenAI

from ..core.config import settings
from ..core.logging_config import get_logger


class PgVectorStore:
    """
    PostgreSQL-based vector store for similarity search using pgvector extension.

    This service is READ-ONLY for the chat service - it only performs similarity searches.
    All write operations (add_documents, delete_documents) are handled by the onboarding service.
    """

    def __init__(self):
        self.logger = get_logger("pg_vector_store")

        # Get OpenAI API key
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")

        self.openai_client = OpenAI(api_key=openai_api_key)

        # Database connection
        self.engine = create_engine(os.environ['VECTOR_DATABASE_URL'])
        self.SessionLocal = sessionmaker(bind=self.engine)

        self.logger.info("PgVectorStore initialized successfully")

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API"""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {e}")
            raise

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
            query_embeddings = self._generate_embeddings([query])
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
            query_embeddings = self._generate_embeddings([query])
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
