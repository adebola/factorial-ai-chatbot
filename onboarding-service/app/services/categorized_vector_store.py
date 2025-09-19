"""
Enhanced vector store with category-based filtering for improved search performance.
"""
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import numpy as np
from langchain.docstore.document import Document
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
import openai

from app.core.logging_config import get_logger
from app.models.categorization import DocumentCategory, DocumentTag

logger = get_logger("categorized_vector_store")


class CategorizedVectorStore:
    """
    Enhanced vector store that provides category-aware search capabilities.

    Features:
    - Category and tag filtering for faster searches
    - Performance-optimized PostgreSQL queries with array operations
    - Smart caching of category-based results
    - Query routing to appropriate document subsets
    - Analytics and performance monitoring
    """

    def __init__(self, vector_db_session: Session, onboard_db_session: Session = None):
        self.vector_db = vector_db_session  # For document_chunks queries
        self.onboard_db = onboard_db_session  # For category/tag metadata queries
        self.db = vector_db_session  # Keep for backward compatibility with vector operations
        self.openai_client = openai.OpenAI()

    def search_by_category(
        self,
        tenant_id: str,
        query: str,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        confidence_threshold: float = 0.0,
        k: int = 5
    ) -> List[Document]:
        """
        Search documents filtered by categories and tags.

        Args:
            tenant_id: Tenant identifier
            query: Search query text
            categories: List of category names to filter by
            tags: List of tag names to filter by
            content_type: Specific content type to filter by
            confidence_threshold: Minimum confidence score for assignments
            k: Number of results to return

        Returns:
            List of Document objects with relevance scores and metadata
        """
        start_time = time.time()

        try:
            # Generate query embedding
            query_embedding = self._generate_embedding(query)

            # Build dynamic filter conditions
            filter_conditions = self._build_filter_conditions(
                tenant_id, categories, tags, content_type, confidence_threshold
            )

            # Execute optimized vector search with filters
            results = self._execute_filtered_search(
                query_embedding, filter_conditions, k
            )

            # Convert results to Document objects
            documents = self._convert_to_documents(results)

            search_time = time.time() - start_time
            logger.info(
                "Category-filtered search completed",
                tenant_id=tenant_id,
                categories=categories,
                tags=tags,
                results_count=len(documents),
                search_time_ms=round(search_time * 1000, 2)
            )

            return documents

        except Exception as e:
            logger.error(
                "Category-filtered search failed",
                tenant_id=tenant_id,
                error=str(e)
            )
            return []

    def search_similar(
        self,
        tenant_id: str,
        query: str,
        k: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Document]:
        """
        Standard similarity search without category filtering (fallback method).
        """
        start_time = time.time()

        try:
            query_embedding = self._generate_embedding(query)

            results = self.db.execute(
                text("""
                    SELECT
                        content,
                        source_name,
                        source_type,
                        page_number,
                        section_title,
                        category_ids,
                        tag_ids,
                        content_type,
                        embedding <-> :query_embedding as distance
                    FROM vectors.document_chunks
                    WHERE tenant_id = :tenant_id
                    AND (1 - (embedding <-> :query_embedding)) >= :similarity_threshold
                    ORDER BY embedding <-> :query_embedding
                    LIMIT :k
                """),
                {
                    "query_embedding": str(query_embedding),
                    "tenant_id": tenant_id,
                    "similarity_threshold": similarity_threshold,
                    "k": k
                }
            ).fetchall()

            documents = self._convert_to_documents(results)

            search_time = time.time() - start_time
            logger.info(
                "Standard similarity search completed",
                tenant_id=tenant_id,
                results_count=len(documents),
                search_time_ms=round(search_time * 1000, 2)
            )

            return documents

        except Exception as e:
            logger.error(
                "Standard similarity search failed",
                tenant_id=tenant_id,
                error=str(e)
            )
            return []

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate OpenAI embedding for the query text."""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # Return zero vector as fallback
            return [0.0] * 1536

    def _build_filter_conditions(
        self,
        tenant_id: str,
        categories: Optional[List[str]],
        tags: Optional[List[str]],
        content_type: Optional[str],
        confidence_threshold: float
    ) -> Dict:
        """Build dynamic filter conditions for the query."""
        conditions = {
            "tenant_id": tenant_id,
            "category_filter": "",
            "tag_filter": "",
            "content_type_filter": "",
            "confidence_filter": ""
        }

        params = {"tenant_id": tenant_id}

        # Category filtering
        if categories:
            category_ids = self._get_category_ids(tenant_id, categories)
            if category_ids:
                conditions["category_filter"] = "AND category_ids && :category_ids"
                params["category_ids"] = category_ids

        # Tag filtering
        if tags:
            tag_ids = self._get_tag_ids(tenant_id, tags)
            if tag_ids:
                conditions["tag_filter"] = "AND tag_ids && :tag_ids"
                params["tag_ids"] = tag_ids

        # Content type filtering
        if content_type:
            conditions["content_type_filter"] = "AND content_type = :content_type"
            params["content_type"] = content_type

        # Add all params to conditions
        conditions.update(params)

        return conditions

    def _get_category_ids(self, tenant_id: str, category_names: List[str]) -> List[str]:
        """Get category IDs from names."""
        try:
            # Use onboard_db for category metadata if available, else fallback to db
            db_session = self.onboard_db if self.onboard_db else self.db
            results = db_session.execute(
                text("""
                    SELECT id FROM document_categories
                    WHERE tenant_id = :tenant_id
                    AND name = ANY(:categories)
                """),
                {"tenant_id": tenant_id, "categories": category_names}
            ).fetchall()

            return [str(row.id) for row in results]
        except Exception as e:
            logger.error(f"Failed to get category IDs: {e}")
            return []

    def _get_tag_ids(self, tenant_id: str, tag_names: List[str]) -> List[str]:
        """Get tag IDs from names."""
        try:
            # Use onboard_db for tag metadata if available, else fallback to db
            db_session = self.onboard_db if self.onboard_db else self.db
            results = db_session.execute(
                text("""
                    SELECT id FROM document_tags
                    WHERE tenant_id = :tenant_id
                    AND name = ANY(:tags)
                """),
                {"tenant_id": tenant_id, "tags": tag_names}
            ).fetchall()

            return [str(row.id) for row in results]
        except Exception as e:
            logger.error(f"Failed to get tag IDs: {e}")
            return []

    def _execute_filtered_search(
        self,
        query_embedding: List[float],
        filter_conditions: Dict,
        k: int
    ) -> List:
        """Execute the filtered vector search query."""

        query_sql = f"""
            SELECT
                content,
                source_name,
                source_type,
                page_number,
                section_title,
                category_ids,
                tag_ids,
                content_type,
                embedding <-> :query_embedding as distance,
                1 - (embedding <-> :query_embedding) as similarity
            FROM vectors.document_chunks
            WHERE tenant_id = :tenant_id
            {filter_conditions.get("category_filter", "")}
            {filter_conditions.get("tag_filter", "")}
            {filter_conditions.get("content_type_filter", "")}
            ORDER BY embedding <-> :query_embedding
            LIMIT :k
        """

        params = {
            "query_embedding": str(query_embedding),
            "k": k
        }
        params.update(filter_conditions)

        return self.db.execute(text(query_sql), params).fetchall()

    def _convert_to_documents(self, results: List) -> List[Document]:
        """Convert database results to LangChain Document objects."""
        documents = []

        for row in results:
            # Prepare metadata
            metadata = {
                "source": row.source_name or "unknown",
                "source_type": row.source_type or "document",
                "distance": float(row.distance),
                "similarity": float(getattr(row, 'similarity', 1 - row.distance)),
                "category_ids": row.category_ids or [],
                "tag_ids": row.tag_ids or [],
                "content_type": row.content_type
            }

            # Add optional metadata
            if hasattr(row, 'page_number') and row.page_number:
                metadata["page_number"] = row.page_number

            if hasattr(row, 'section_title') and row.section_title:
                metadata["section_title"] = row.section_title

            # Create Document object
            doc = Document(
                page_content=row.content,
                metadata=metadata
            )
            documents.append(doc)

        return documents

    def get_category_statistics(self, tenant_id: str) -> Dict:
        """Get document distribution and performance statistics by categories."""
        try:
            # Use onboard_db for category metadata if available, else fallback to db
            db_session = self.onboard_db if self.onboard_db else self.db

            # First, get category metadata and assignment stats from onboard_db
            category_stats = db_session.execute(
                text("""
                    SELECT
                        c.id,
                        c.name,
                        c.description,
                        c.color,
                        c.icon,
                        c.is_system_category,
                        COUNT(DISTINCT dca.document_id) as doc_count,
                        AVG(dca.confidence_score) as avg_confidence,
                        COUNT(CASE WHEN dca.assigned_by = 'ai' THEN 1 END) as ai_assigned,
                        COUNT(CASE WHEN dca.assigned_by = 'user' THEN 1 END) as user_assigned
                    FROM document_categories c
                    LEFT JOIN document_category_assignments dca ON c.id = dca.category_id
                    WHERE c.tenant_id = :tenant_id
                    GROUP BY c.id, c.name, c.description, c.color, c.icon, c.is_system_category
                    ORDER BY doc_count DESC NULLS LAST, c.name
                """),
                {"tenant_id": tenant_id}
            ).fetchall()

            # Then get chunk counts from vector_db for each category
            category_chunk_counts = {}
            if category_stats:
                category_ids = [row.id for row in category_stats]
                for cat_id in category_ids:
                    chunk_result = self.vector_db.execute(
                        text("""
                            SELECT COUNT(*) as chunk_count
                            FROM vectors.document_chunks
                            WHERE tenant_id = :tenant_id
                            AND :category_id = ANY(category_ids)
                        """),
                        {"tenant_id": tenant_id, "category_id": cat_id}
                    ).fetchone()
                    category_chunk_counts[cat_id] = chunk_result.chunk_count if chunk_result else 0

            return {
                "categories": [
                    {
                        "id": row.id,
                        "name": row.name,
                        "description": row.description,
                        "color": row.color,
                        "icon": row.icon,
                        "is_system_category": row.is_system_category,
                        "document_count": row.doc_count or 0,
                        "chunk_count": category_chunk_counts.get(row.id, 0),
                        "avg_chunks_per_doc": float((category_chunk_counts.get(row.id, 0) / (row.doc_count or 1)) if row.doc_count else 0),
                        "avg_confidence": float(row.avg_confidence or 0),
                        "ai_vs_manual": {
                            "ai_assigned": row.ai_assigned or 0,
                            "user_assigned": row.user_assigned or 0
                        }
                    }
                    for row in category_stats
                ],
                "total_categories": len(category_stats),
                "generated_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get category statistics: {e}")
            return {"categories": [], "total_categories": 0}

    def get_tag_statistics(self, tenant_id: str, limit: int = 50) -> Dict:
        """Get tag usage statistics."""
        try:
            # Use onboard_db for tag metadata if available, else fallback to db
            db_session = self.onboard_db if self.onboard_db else self.db
            stats = db_session.execute(
                text("""
                    SELECT
                        t.id,
                        t.name,
                        t.tag_type,
                        t.usage_count,
                        COUNT(DISTINCT dta.document_id) as assigned_docs,
                        AVG(dta.confidence_score) as avg_confidence
                    FROM document_tags t
                    LEFT JOIN document_tag_assignments dta ON t.id = dta.tag_id
                    WHERE t.tenant_id = :tenant_id
                    GROUP BY t.id, t.name, t.tag_type, t.usage_count
                    ORDER BY t.usage_count DESC, assigned_docs DESC
                    LIMIT :limit
                """),
                {"tenant_id": tenant_id, "limit": limit}
            ).fetchall()

            return {
                "tags": [
                    {
                        "id": row.id,
                        "name": row.name,
                        "tag_type": row.tag_type,
                        "usage_count": row.usage_count,
                        "assigned_documents": row.assigned_docs or 0,
                        "avg_confidence": float(row.avg_confidence or 0)
                    }
                    for row in stats
                ],
                "total_tags": len(stats)
            }

        except Exception as e:
            logger.error(f"Failed to get tag statistics: {e}")
            return {"tags": [], "total_tags": 0}

    def get_search_performance_metrics(self, tenant_id: str) -> Dict:
        """Get search performance metrics for optimization."""
        try:
            # Get chunk distribution by categories
            chunk_distribution = self.db.execute(
                text("""
                    SELECT
                        COALESCE(array_length(category_ids, 1), 0) as category_count,
                        COUNT(*) as chunk_count
                    FROM vectors.document_chunks
                    WHERE tenant_id = :tenant_id
                    GROUP BY COALESCE(array_length(category_ids, 1), 0)
                    ORDER BY category_count
                """),
                {"tenant_id": tenant_id}
            ).fetchall()

            # Get overall statistics
            overall_stats = self.db.execute(
                text("""
                    SELECT
                        COUNT(*) as total_chunks,
                        COUNT(DISTINCT document_id) as total_documents,
                        AVG(array_length(category_ids, 1)) as avg_categories_per_chunk,
                        AVG(array_length(tag_ids, 1)) as avg_tags_per_chunk
                    FROM vectors.document_chunks
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id}
            ).fetchone()

            return {
                "chunk_distribution": [
                    {
                        "category_count": row.category_count,
                        "chunk_count": row.chunk_count
                    }
                    for row in chunk_distribution
                ],
                "overall_stats": {
                    "total_chunks": overall_stats.total_chunks or 0,
                    "total_documents": overall_stats.total_documents or 0,
                    "avg_categories_per_chunk": float(overall_stats.avg_categories_per_chunk or 0),
                    "avg_tags_per_chunk": float(overall_stats.avg_tags_per_chunk or 0)
                },
                "optimization_recommendations": self._generate_optimization_recommendations(
                    overall_stats, chunk_distribution
                )
            }

        except Exception as e:
            logger.error(f"Failed to get search performance metrics: {e}")
            return {"chunk_distribution": [], "overall_stats": {}}

    def _generate_optimization_recommendations(
        self,
        overall_stats,
        chunk_distribution
    ) -> List[str]:
        """Generate optimization recommendations based on metrics."""
        recommendations = []

        if overall_stats and overall_stats.total_chunks:
            # Check if categorization is being used
            if overall_stats.avg_categories_per_chunk < 0.5:
                recommendations.append(
                    "Low categorization usage detected. Consider enabling auto-categorization for better search performance."
                )

            # Check chunk distribution
            uncategorized_chunks = 0
            for dist in chunk_distribution:
                if dist.category_count == 0:
                    uncategorized_chunks = dist.chunk_count
                    break

            if uncategorized_chunks > overall_stats.total_chunks * 0.3:
                recommendations.append(
                    f"High number of uncategorized chunks ({uncategorized_chunks}). "
                    "Run bulk categorization to improve search filtering."
                )

            # Check for over-categorization
            if overall_stats.avg_categories_per_chunk > 3:
                recommendations.append(
                    "High average categories per chunk detected. "
                    "Consider reviewing categorization rules for better precision."
                )

        return recommendations

    def bulk_update_chunk_categories(
        self,
        tenant_id: str,
        document_id: str,
        category_ids: List[str],
        tag_ids: List[str]
    ) -> None:
        """Update all chunks for a document with new category and tag assignments."""
        try:
            self.db.execute(
                text("""
                    UPDATE vectors.document_chunks
                    SET
                        category_ids = :category_ids,
                        tag_ids = :tag_ids,
                        updated_at = NOW()
                    WHERE tenant_id = :tenant_id
                    AND document_id = :document_id
                """),
                {
                    "category_ids": category_ids,
                    "tag_ids": tag_ids,
                    "tenant_id": tenant_id,
                    "document_id": document_id
                }
            )

            self.db.commit()

            logger.info(
                "Updated chunk categories and tags",
                tenant_id=tenant_id,
                document_id=document_id,
                category_count=len(category_ids),
                tag_count=len(tag_ids)
            )

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to update chunk categories",
                tenant_id=tenant_id,
                document_id=document_id,
                error=str(e)
            )
            raise

    def delete_document_vectors(self, tenant_id: str, document_id: str) -> None:
        """Delete all vector chunks for a document."""
        try:
            result = self.db.execute(
                text("""
                    DELETE FROM vectors.document_chunks
                    WHERE tenant_id = :tenant_id
                    AND document_id = :document_id
                """),
                {"tenant_id": tenant_id, "document_id": document_id}
            )

            deleted_count = result.rowcount
            self.db.commit()

            logger.info(
                "Deleted document vectors",
                tenant_id=tenant_id,
                document_id=document_id,
                chunks_deleted=deleted_count
            )

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to delete document vectors",
                tenant_id=tenant_id,
                document_id=document_id,
                error=str(e)
            )
            raise