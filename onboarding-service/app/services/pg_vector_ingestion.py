import httpx
import hashlib
from langchain.docstore.document import Document
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import os
from openai import OpenAI
from ..core.logging_config import get_logger, log_vector_operation, log_document_processing


class PgVectorIngestionService:
    """PostgresSQL-based vector ingestion service using pgvector"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("pg_vector_ingestion")
        
        # Debug: Log which database this service is connected to
        database_url = str(self.db.bind.url)
        self.logger.debug(f"PgVectorIngestionService initialized with database: {database_url}")
        
        # Get OpenAI API key with proper validation
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        
        self.openai_client = OpenAI(api_key=openai_api_key)
    
    def _get_content_hash(self, content: str) -> str:
        """Generate a hash for content deduplication"""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API"""
        try:
            self.logger.info(f"Generating embeddings for {len(texts)} text chunks")
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=texts
            )
            embeddings = [item.embedding for item in response.data]
            self.logger.info(f"Successfully generated {len(embeddings)} embeddings")
            return embeddings
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def ingest_documents(self, tenant_id: str, documents: List[Document], document_id: str = None, ingestion_id: str = None):
        """Ingest documents into the PostgresSQL vector store"""
        
        if not documents:
            self.logger.warning("No documents provided for ingestion")
            return

        if not document_id and not ingestion_id:
            self.logger.warning("No document id or ingestion id provided for this ingestion")
            return
        
        log_vector_operation(
            operation="pg_ingest_start",
            tenant_id=tenant_id,
            document_count=len(documents)
        )
        
        self.logger.info(
            "Starting PostgreSQL vector ingestion",
            tenant_id=tenant_id,
            document_count=len(documents),
            document_id=document_id,
            ingestion_id=ingestion_id
        )
        
        try:
            # Process documents in batches
            batch_size = 10  # Smaller batches for OpenAI API rate limits
            total_inserted = 0
            
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                
                # Generate embeddings for this batch
                texts = [doc.page_content for doc in batch]
                embeddings = self._generate_embeddings(texts)
                
                # Prepare batch insert data
                insert_data = []
                for j, (doc, embedding) in enumerate(zip(batch, embeddings)):
                    content_hash = self._get_content_hash(doc.page_content)
                    
                    # Check for duplicates
                    existing = self.db.execute(
                        text("SELECT id FROM document_chunks WHERE tenant_id = :tenant_id AND content_hash = :hash"),
                        {"tenant_id": tenant_id, "hash": content_hash}
                    ).first()
                        
                    if existing:
                        self.logger.debug(f"Skipping duplicate chunk for tenant {tenant_id}")
                        continue
                    
                    # Extract metadata
                    metadata = doc.metadata or {}
                    source_type = metadata.get('source_type', 'document')
                    source_name = metadata.get('source_name', '')
                    page_number = metadata.get('page', None)
                    section_title = metadata.get('section_title', None)
                    
                    insert_data.append({
                        'tenant_id': tenant_id,
                        'document_id': document_id,
                        'ingestion_id': ingestion_id,
                        'content': doc.page_content,
                        'content_hash': content_hash,
                        'chunk_index': i + j,
                        'embedding': embedding,  # Keep as list for proper conversion
                        'source_type': source_type,
                        'source_name': source_name,
                        'page_number': page_number,
                        'section_title': section_title
                    })
                
                if insert_data:
                    # Batch insert chunks with proper vector handling
                    for item in insert_data:
                        self.db.execute(
                            text("""
                                INSERT INTO document_chunks 
                                (id, tenant_id, document_id, ingestion_id, content, content_hash, chunk_index, 
                                 embedding, source_type, source_name, page_number, section_title)
                                VALUES (gen_random_uuid(), :tenant_id, :document_id, :ingestion_id, :content, 
                                       :content_hash, :chunk_index, :embedding, :source_type, :source_name, 
                                       :page_number, :section_title)
                            """),
                            {
                                **item,
                                'embedding': str(item['embedding'])  # Convert list to string representation
                            }
                        )
                    total_inserted += len(insert_data)
                    
                    self.logger.info(
                        f"Inserted batch of {len(insert_data)} chunks",
                        batch_start=i,
                        total_processed=i + len(batch),
                        total_documents=len(documents)
                    )
            
            # Update search index statistics
            self.db.execute(
                text("""
                    INSERT INTO vector_search_indexes (id, tenant_id, total_chunks, last_indexed_at)
                    VALUES (gen_random_uuid(), :tenant_id, :total_chunks, NOW())
                    ON CONFLICT (tenant_id) DO UPDATE SET
                        total_chunks = vector_search_indexes.total_chunks + :total_chunks,
                        last_indexed_at = NOW()
                """),
                {"tenant_id": tenant_id, "total_chunks": total_inserted}
            )
            
            self.db.commit()
            
            self.logger.info(
                "PostgreSQL vector ingestion completed successfully",
                tenant_id=tenant_id,
                document_count=len(documents),
                chunks_inserted=total_inserted,
                document_id=document_id,
                ingestion_id=ingestion_id
            )
            
            log_vector_operation(
                operation="pg_ingest_complete",
                tenant_id=tenant_id,
                document_count=len(documents),
                chunks_inserted=total_inserted
            )
            
        except Exception as e:
            error_msg = f"Failed to ingest documents into PostgreSQL vector store for tenant {tenant_id}: {str(e)}"
            self.logger.error(
                "PostgreSQL vector ingestion failed",
                tenant_id=tenant_id,
                error=str(e),
                document_id=document_id,
                ingestion_id=ingestion_id
            )
            raise RuntimeError(error_msg)
    
    def delete_document_vectors(self, tenant_id: str, document_id: str) -> bool:
        """Delete all vectors for a specific document"""
        try:
            result = self.db.execute(
                text("DELETE FROM document_chunks WHERE tenant_id = :tenant_id AND document_id = :document_id"),
                {"tenant_id": tenant_id, "document_id": document_id}
            )
            deleted_count = result.rowcount

            # Update search index statistics
            self.db.execute(
                text("""
                    UPDATE vector_search_indexes 
                    SET total_chunks = GREATEST(0, total_chunks - :deleted_count),
                        last_indexed_at = NOW()
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id, "deleted_count": deleted_count}
            )
            
            self.db.commit()
            
            self.logger.info(f"Deleted {deleted_count} vector chunks for document {document_id}")

            return deleted_count != 0

        except Exception as e:
            self.logger.error(f"Failed to delete document vectors: {e}")
            raise
    
    def delete_ingestion_vectors(self, tenant_id: str, ingestion_id: str) -> bool:
        """Delete all vectors for a specific website ingestion"""
        try:
            result = self.db.execute(
                text("DELETE FROM document_chunks WHERE tenant_id = :tenant_id AND ingestion_id = :ingestion_id"),
                {"tenant_id": tenant_id, "ingestion_id": ingestion_id}
            )
            deleted_count = result.rowcount
            
            # Update search index statistics
            self.db.execute(
                text("""
                    UPDATE vector_search_indexes 
                    SET total_chunks = GREATEST(0, total_chunks - :deleted_count),
                        last_indexed_at = NOW()
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id, "deleted_count": deleted_count}
            )
            
            self.db.commit()
            
            self.logger.info(f"Deleted {deleted_count} vector chunks for ingestion {ingestion_id}")
            return deleted_count != 0
                
        except Exception as e:
            self.logger.error(f"Failed to delete ingestion vectors: {e}")
            raise
    
    def delete_tenant_vectors(self, tenant_id: str) -> bool:
        """Delete all vectors for a tenant (documents and website ingestions)"""
        try:
            # Delete all chunks for the tenant
            result = self.db.execute(
                text("DELETE FROM document_chunks WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
            deleted_count = result.rowcount
            
            # Delete search index statistics for the tenant
            self.db.execute(
                text("DELETE FROM vector_search_indexes WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
            
            self.db.commit()
            
            self.logger.info(f"Deleted {deleted_count} vector chunks for tenant {tenant_id}")
            
            return deleted_count > 0
            
        except Exception as e:
            self.logger.error(f"Failed to delete tenant vectors: {e}")
            raise
