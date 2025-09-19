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
    """PostgreSQL-based vector store using pgvector extension"""
    
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
    
    def _sanitize_content(self, content: str) -> str:
        """Remove NUL characters and other problematic characters from content"""
        if not content:
            return ""
        # Remove NUL characters (0x00) that PostgreSQL doesn't allow
        sanitized = content.replace('\x00', '')
        # Also remove other control characters except tab, newline, carriage return
        import re
        sanitized = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized)
        return sanitized

    def _get_content_hash(self, content: str) -> str:
        """Generate a hash for content deduplication"""
        return hashlib.sha256(content.encode()).hexdigest()
    
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
    
    def add_documents(self, tenant_id: str, documents: List[Document], document_id: str = None, ingestion_id: str = None):
        """Add documents to the vector store"""
        if not documents:
            return
        
        session = self.SessionLocal()
        try:
            # Prepare data for batch processing
            texts = [doc.page_content for doc in documents]
            embeddings = self._generate_embeddings(texts)
            
            # Insert chunks in batches
            batch_size = 100
            total_inserted = 0
            
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                batch_embeddings = embeddings[i:i + batch_size]
                
                # Prepare batch insert data
                insert_data = []
                for j, (doc, embedding) in enumerate(zip(batch_docs, batch_embeddings)):
                    # Sanitize content to remove NUL characters
                    sanitized_content = self._sanitize_content(doc.page_content)
                    content_hash = self._get_content_hash(sanitized_content)

                    # Check if chunk already exists
                    existing = session.execute(
                        text("SELECT id FROM vectors.document_chunks WHERE tenant_id = :tenant_id AND content_hash = :hash"),
                        {"tenant_id": tenant_id, "hash": content_hash}
                    ).first()

                    if existing:
                        self.logger.debug(f"Skipping duplicate chunk for tenant {tenant_id}")
                        continue

                    # Extract metadata and sanitize text fields
                    metadata = doc.metadata or {}
                    source_type = metadata.get('source_type', 'document')
                    source_name = self._sanitize_content(metadata.get('source_name', ''))
                    page_number = metadata.get('page', None)
                    section_title = self._sanitize_content(metadata.get('section_title', '') if metadata.get('section_title') else None)

                    insert_data.append({
                        'tenant_id': tenant_id,
                        'document_id': document_id,
                        'ingestion_id': ingestion_id,
                        'content': sanitized_content,
                        'content_hash': content_hash,
                        'chunk_index': i + j,
                        'embedding': embedding,
                        'source_type': source_type,
                        'source_name': source_name,
                        'page_number': page_number,
                        'section_title': section_title
                    })
                
                if insert_data:
                    # Batch insert
                    session.execute(
                        text("""
                            INSERT INTO vectors.document_chunks
                            (id, tenant_id, document_id, ingestion_id, content, content_hash, chunk_index,
                             embedding, source_type, source_name, page_number, section_title,
                             category_ids, tag_ids, content_type)
                            VALUES (gen_random_uuid(), :tenant_id, :document_id, :ingestion_id, :content,
                                   :content_hash, :chunk_index, :embedding, :source_type, :source_name,
                                   :page_number, :section_title, '{}', '{}', NULL)
                        """),
                        insert_data
                    )
                    total_inserted += len(insert_data)
            
            # Update search index statistics
            session.execute(
                text("""
                    INSERT INTO vectors.vector_search_indexes (id, tenant_id, total_chunks, last_indexed_at)
                    VALUES (gen_random_uuid(), :tenant_id, :total_chunks, NOW())
                    ON CONFLICT (tenant_id) DO UPDATE SET
                        total_chunks = vectors.vector_search_indexes.total_chunks + :total_chunks,
                        last_indexed_at = NOW()
                """),
                {"tenant_id": tenant_id, "total_chunks": total_inserted}
            )
            
            session.commit()
            self.logger.info(f"Added {total_inserted} chunks to vector store for tenant {tenant_id}")
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to add documents for tenant {tenant_id}: {e}")
            raise
        finally:
            session.close()
    
    def search_similar(self, tenant_id: str, query: str, k: int = 4) -> List[Document]:
        """Search for similar documents using vector similarity"""
        try:
            # Generate embedding for query
            query_embeddings = self._generate_embeddings([query])
            query_embedding = query_embeddings[0]
            
            session = self.SessionLocal()
            try:
                # Perform vector similarity search
                results = session.execute(
                    text("""
                        SELECT content, source_type, source_name, page_number, section_title,
                               (embedding <=> :query_embedding) as distance
                        FROM vectors.document_chunks
                        WHERE tenant_id = :tenant_id
                        ORDER BY embedding <=> :query_embedding
                        LIMIT :k
                    """),
                    {
                        "tenant_id": tenant_id,
                        "query_embedding": str(query_embedding),
                        "k": k
                    }
                ).fetchall()
                
                # Convert to Document objects
                documents = []
                for row in results:
                    metadata = {
                        'source_type': row.source_type,
                        'source_name': row.source_name,
                        'page': row.page_number,
                        'section_title': row.section_title,
                        'distance': float(row.distance)
                    }
                    # Remove None values
                    metadata = {k: v for k, v in metadata.items() if v is not None}
                    
                    documents.append(Document(
                        page_content=row.content,
                        metadata=metadata
                    ))
                
                self.logger.info(f"Vector search returned {len(documents)} documents for tenant {tenant_id}")
                return documents
                
            finally:
                session.close()
                
        except Exception as e:
            self.logger.error(f"Vector search failed for tenant {tenant_id}: {e}")
            return []
    
    def search_with_score(self, tenant_id: str, query: str, k: int = 4) -> List[Tuple[Document, float]]:
        """Search with similarity scores"""
        try:
            query_embeddings = self._generate_embeddings([query])
            query_embedding = query_embeddings[0]
            
            session = self.SessionLocal()
            try:
                results = session.execute(
                    text("""
                        SELECT content, source_type, source_name, page_number, section_title,
                               (embedding <=> :query_embedding) as distance
                        FROM vectors.document_chunks
                        WHERE tenant_id = :tenant_id
                        ORDER BY embedding <=> :query_embedding
                        LIMIT :k
                    """),
                    {
                        "tenant_id": tenant_id,
                        "query_embedding": str(query_embedding),
                        "k": k
                    }
                ).fetchall()
                
                documents_with_scores = []
                for row in results:
                    metadata = {
                        'source_type': row.source_type,
                        'source_name': row.source_name,
                        'page': row.page_number,
                        'section_title': row.section_title
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
    
    def delete_tenant_store(self, tenant_id: str) -> bool:
        """Delete all vectors for a tenant"""
        session = self.SessionLocal()
        try:
            # Delete all chunks for the tenant
            chunks_deleted = session.execute(
                text("DELETE FROM vectors.document_chunks WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id}
            ).rowcount
            
            # Delete search index
            session.execute(
                text("DELETE FROM vectors.vector_search_indexes WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
            
            session.commit()
            self.logger.info(f"Deleted {chunks_deleted} chunks for tenant {tenant_id}")
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to delete tenant store {tenant_id}: {e}")
            return False
        finally:
            session.close()
    
    def delete_document_vectors(self, tenant_id: str, document_id: str) -> bool:
        """Delete vectors for a specific document"""
        session = self.SessionLocal()
        try:
            deleted_count = session.execute(
                text("DELETE FROM vectors.document_chunks WHERE tenant_id = :tenant_id AND document_id = :document_id"),
                {"tenant_id": tenant_id, "document_id": document_id}
            ).rowcount
            
            # Update search index statistics
            session.execute(
                text("""
                    UPDATE vectors.vector_search_indexes 
                    SET total_chunks = GREATEST(0, total_chunks - :deleted_count),
                        last_indexed_at = NOW()
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id, "deleted_count": deleted_count}
            )
            
            session.commit()
            self.logger.info(f"Deleted {deleted_count} chunks for document {document_id}")
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to delete document vectors: {e}")
            return False
        finally:
            session.close()
    
    def delete_ingestion_vectors(self, tenant_id: str, ingestion_id: str) -> bool:
        """Delete vectors for a specific website ingestion"""
        session = self.SessionLocal()
        try:
            deleted_count = session.execute(
                text("DELETE FROM vectors.document_chunks WHERE tenant_id = :tenant_id AND ingestion_id = :ingestion_id"),
                {"tenant_id": tenant_id, "ingestion_id": ingestion_id}
            ).rowcount
            
            # Update search index statistics
            session.execute(
                text("""
                    UPDATE vectors.vector_search_indexes 
                    SET total_chunks = GREATEST(0, total_chunks - :deleted_count),
                        last_indexed_at = NOW()
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id, "deleted_count": deleted_count}
            )
            
            session.commit()
            self.logger.info(f"Deleted {deleted_count} chunks for ingestion {ingestion_id}")
            return True
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to delete ingestion vectors: {e}")
            return False
        finally:
            session.close()
    
    def get_tenant_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get statistics for a tenant's vector store"""
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