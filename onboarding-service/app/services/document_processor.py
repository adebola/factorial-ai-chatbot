from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from sqlalchemy.orm import Session
from typing import List, BinaryIO, Tuple, Optional, Dict
import tempfile
import os
from datetime import datetime

from ..models.tenant import Document as DocumentModel, DocumentStatus
from ..models.categorization import DocumentClassification
from .storage_service import StorageService
from .pg_vector_ingestion import PgVectorIngestionService
from .document_categorization import DocumentCategorizationService
from .categorized_vector_store import CategorizedVectorStore
from ..core.database import get_vector_db
from ..core.logging_config import get_logger

logger = get_logger("document_processor")


class DocumentProcessor:
    """Enhanced service for processing, categorizing, and chunking documents"""

    def __init__(self, db: Session):
        self.db = db
        self.storage_service = StorageService()

        # Get vector database session for vector ingestion service
        self.vector_db = next(get_vector_db())
        self.vector_ingestion_service = PgVectorIngestionService(db=self.vector_db)

        # Initialize categorization services
        self.categorization_service = DocumentCategorizationService(db)
        self.categorized_vector_store = CategorizedVectorStore(self.vector_db, db)

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
        )
    
    async def process_document(
        self,
        tenant_id: str,
        file_data: BinaryIO,
        filename: str,
        content_type: str,
        user_categories: Optional[List[str]] = None,
        user_tags: Optional[List[str]] = None,
        auto_categorize: bool = True
    ) -> Tuple[List[Document], str, Optional[DocumentClassification]]:
        """
        Enhanced document processing with AI-powered categorization.

        Args:
            tenant_id: Tenant identifier
            file_data: File data stream
            filename: Original filename
            content_type: MIME type
            user_categories: User-specified categories
            user_tags: User-specified tags
            auto_categorize: Enable AI categorization

        Returns:
            Tuple of (documents, document_id, classification_results)
        """
        logger.info(
            "Starting document processing",
            tenant_id=tenant_id,
            filename=filename,
            content_type=content_type,
            auto_categorize=auto_categorize
        )

        # Store document in database
        doc_record = DocumentModel(
            tenant_id=tenant_id,
            filename=filename,
            original_filename=filename,
            file_path="",  # Will be updated after upload
            mime_type=content_type,
            status=DocumentStatus.PROCESSING
        )
        self.db.add(doc_record)
        self.db.commit()
        self.db.refresh(doc_record)

        classification = None

        try:
            # Upload to storage
            object_name = self.storage_service.upload_file(
                tenant_id=tenant_id,
                file_data=file_data,
                filename=filename,
                content_type=content_type
            )

            # Update document record with file path
            doc_record.file_path = object_name
            self.db.commit()

            # Download file for processing
            file_content = self.storage_service.download_file(object_name)

            # Process based on file type
            documents = self._extract_text_from_file(file_content, filename, content_type)

            # Step 1: AI-powered categorization (if enabled and documents exist)
            if auto_categorize and documents:
                logger.info("Starting AI categorization", document_id=doc_record.id)

                # Use first few chunks for classification to get representative content
                combined_content = " ".join([
                    doc.page_content for doc in documents[:3]
                ])[:4000]  # Limit to 4K chars for classification

                sample_doc = Document(page_content=combined_content)
                classification = await self.categorization_service.classify_document(
                    sample_doc, tenant_id, enable_ai=True
                )

                # Save classification results to database
                await self.categorization_service.save_document_classification(
                    doc_record.id, classification, tenant_id
                )

                logger.info(
                    "AI categorization completed",
                    document_id=doc_record.id,
                    categories_found=len(classification.categories),
                    tags_found=len(classification.tags),
                    content_type=classification.content_type
                )

            # Step 2: Process user-provided categories and tags
            user_classification = await self._process_user_classifications(
                doc_record.id, tenant_id, user_categories, user_tags
            )

            # Step 3: Enhance document metadata with categorization results
            category_ids = []
            tag_ids = []

            if classification:
                # Get category and tag IDs for chunks
                category_ids = await self._get_category_ids_from_classification(
                    tenant_id, classification.categories
                )
                tag_ids = await self._get_tag_ids_from_classification(
                    tenant_id, classification.tags
                )

            # Add user-specified categories/tags if provided
            if user_classification:
                category_ids.extend(user_classification.get("category_ids", []))
                tag_ids.extend(user_classification.get("tag_ids", []))

            # Remove duplicates
            category_ids = list(set(category_ids))
            tag_ids = list(set(tag_ids))

            # Step 4: Enhance document chunks with categorization metadata
            for doc in documents:
                doc.metadata.update({
                    "tenant_id": tenant_id,
                    "source": filename,
                    "document_id": doc_record.id,
                    "upload_date": datetime.now().isoformat(),
                    "categories": [cat["name"] for cat in (classification.categories if classification else [])],
                    "tags": [tag["name"] for tag in (classification.tags if classification else [])],
                    "content_type": classification.content_type if classification else "document",
                    "language": classification.language if classification else "en",
                    "key_entities": classification.key_entities if classification else [],
                    "category_ids": category_ids,
                    "tag_ids": tag_ids
                })

            # Mark as completed
            doc_record.status = DocumentStatus.COMPLETED
            doc_record.processed_at = datetime.now()
            self.db.commit()

            logger.info(
                "Document processing completed successfully",
                document_id=doc_record.id,
                chunks_created=len(documents),
                categories_assigned=len(category_ids),
                tags_assigned=len(tag_ids)
            )

            return documents, doc_record.id, classification

        except Exception as e:
            # Mark as failed
            doc_record.status = DocumentStatus.FAILED
            doc_record.error_message = str(e)
            self.db.commit()
            logger.error(
                "Document processing failed",
                document_id=doc_record.id,
                error=str(e)
            )
            raise

    async def _process_user_classifications(
        self,
        document_id: str,
        tenant_id: str,
        user_categories: Optional[List[str]],
        user_tags: Optional[List[str]]
    ) -> Optional[Dict]:
        """Process user-provided categories and tags."""
        if not user_categories and not user_tags:
            return None

        result = {"category_ids": [], "tag_ids": []}

        try:
            # Process user categories
            if user_categories:
                for cat_name in user_categories:
                    category = await self.categorization_service.get_or_create_category(
                        tenant_id, cat_name
                    )
                    result["category_ids"].append(category.id)

                    # Create assignment with user confidence
                    from ..models.categorization import DocumentCategoryAssignment
                    assignment = DocumentCategoryAssignment(
                        document_id=document_id,
                        category_id=category.id,
                        confidence_score=1.0,  # User assignments have full confidence
                        assigned_by="user"
                    )
                    self.db.add(assignment)

            # Process user tags
            if user_tags:
                for tag_name in user_tags:
                    tag = await self.categorization_service.get_or_create_tag(
                        tenant_id, tag_name, "custom"
                    )
                    result["tag_ids"].append(tag.id)

                    # Create assignment with user confidence
                    from ..models.categorization import DocumentTagAssignment
                    assignment = DocumentTagAssignment(
                        document_id=document_id,
                        tag_id=tag.id,
                        confidence_score=1.0,
                        assigned_by="user"
                    )
                    self.db.add(assignment)

            self.db.commit()

            logger.info(
                "Processed user classifications",
                document_id=document_id,
                user_categories=len(user_categories or []),
                user_tags=len(user_tags or [])
            )

            return result

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to process user classifications: {e}")
            return None

    async def _get_category_ids_from_classification(
        self,
        tenant_id: str,
        categories: List[Dict]
    ) -> List[str]:
        """Get category IDs from classification results."""
        category_ids = []

        for cat_data in categories:
            try:
                category = await self.categorization_service.get_or_create_category(
                    tenant_id, cat_data["name"]
                )
                category_ids.append(category.id)
            except Exception as e:
                logger.error(f"Failed to get category ID for {cat_data['name']}: {e}")

        return category_ids

    async def _get_tag_ids_from_classification(
        self,
        tenant_id: str,
        tags: List[Dict]
    ) -> List[str]:
        """Get tag IDs from classification results."""
        tag_ids = []

        for tag_data in tags:
            try:
                tag = await self.categorization_service.get_or_create_tag(
                    tenant_id, tag_data["name"], "auto"
                )
                tag_ids.append(tag.id)
            except Exception as e:
                logger.error(f"Failed to get tag ID for {tag_data['name']}: {e}")

        return tag_ids
    
    def _extract_text_from_file(
        self, 
        file_content: bytes, 
        filename: str, 
        content_type: str
    ) -> List[Document]:
        """Extract text from file based on type"""
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        try:
            documents = []
            
            if content_type == "application/pdf" or filename.lower().endswith('.pdf'):
                loader = PyPDFLoader(tmp_file_path)
                documents = loader.load()
            
            elif content_type == "text/plain" or filename.lower().endswith('.txt'):
                loader = TextLoader(tmp_file_path, encoding='utf-8')
                documents = loader.load()
            
            elif (content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" 
                  or filename.lower().endswith('.docx')):
                loader = Docx2txtLoader(tmp_file_path)
                documents = loader.load()
            
            else:
                # Try to treat as text
                try:
                    with open(tmp_file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    documents = [Document(page_content=content)]
                except:
                    raise ValueError(f"Unsupported file type: {content_type}")
            
            # Split documents into chunks
            if documents:
                chunked_docs = []
                for doc in documents:
                    chunks = self.text_splitter.split_documents([doc])
                    chunked_docs.extend(chunks)
                return chunked_docs
            
            return documents
            
        finally:
            # Clean up temporary file
            os.unlink(tmp_file_path)
    
    def get_tenant_documents(self, tenant_id: str) -> List[DocumentModel]:
        """Get all documents for a tenant"""
        return self.db.query(DocumentModel).filter(
            DocumentModel.tenant_id == tenant_id
        ).all()
    
    def delete_document(self, tenant_id: str, document_id: str) -> bool:
        """Delete a document and its associated vectors"""
        doc = self.db.query(DocumentModel).filter(
            DocumentModel.id == document_id,
            DocumentModel.tenant_id == tenant_id
        ).first()
        
        if not doc:
            return False
        
        try:
            cleanup_results = {
                "storage_deleted": False,
                "vectors_deleted": False,
            }
            
            # Delete from storage (MinIO)
            if doc.file_path:
                storage_deleted = self.storage_service.delete_file(doc.file_path)
                cleanup_results["storage_deleted"] = storage_deleted
                if storage_deleted:
                    print(f"✅ Deleted file from MinIO: {doc.file_path}")
                else:
                    print(f"⚠️ Failed to delete file from MinIO: {doc.file_path}")
            else:
                print(f"ℹ️ No file path found for document {document_id}")
                cleanup_results["storage_deleted"] = True  # No file to delete
            
            # Delete vectors from PgVector
            vector_deleted = self.vector_ingestion_service.delete_document_vectors(tenant_id, document_id)
            cleanup_results["vectors_deleted"] = vector_deleted
            if vector_deleted:
                print(f"✅ Deleted vectors from PgVector for document {document_id}")
            else:
                print(f"⚠️ Failed to delete vectors for document {document_id}")

            # Delete categorization assignments (cascading deletes will handle this automatically)
            # But we can also explicitly clean them up for better logging
            try:
                from ..models.categorization import DocumentCategoryAssignment, DocumentTagAssignment

                # Count assignments before deletion
                category_assignments = self.db.query(DocumentCategoryAssignment).filter(
                    DocumentCategoryAssignment.document_id == document_id
                ).count()

                tag_assignments = self.db.query(DocumentTagAssignment).filter(
                    DocumentTagAssignment.document_id == document_id
                ).count()

                # Delete assignments
                self.db.query(DocumentCategoryAssignment).filter(
                    DocumentCategoryAssignment.document_id == document_id
                ).delete()

                self.db.query(DocumentTagAssignment).filter(
                    DocumentTagAssignment.document_id == document_id
                ).delete()

                print(f"✅ Deleted categorization data: {category_assignments} categories, {tag_assignments} tags")
                cleanup_results["categorization_deleted"] = True

            except Exception as e:
                print(f"⚠️ Failed to delete categorization data: {e}")
                cleanup_results["categorization_deleted"] = False

            # Delete from database
            self.db.delete(doc)
            self.db.commit()
            
            # Log cleanup summary
            print(f"📋 Document {document_id} deletion summary:")
            print(f"   - Storage (MinIO): {'✅' if cleanup_results['storage_deleted'] else '❌'}")
            print(f"   - Vectors (PgVector): {'✅' if cleanup_results['vectors_deleted'] else '❌'}")
            print(f"   - Categorization: {'✅' if cleanup_results.get('categorization_deleted', False) else '❌'}")
            print(f"   - Database: ✅")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error deleting document {document_id}: {e}")
            return False
