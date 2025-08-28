from langchain.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from sqlalchemy.orm import Session
from typing import List, BinaryIO, Tuple
import tempfile
import os
from datetime import datetime

from ..models.tenant import Document as DocumentModel, DocumentStatus
from .storage_service import StorageService
from .pg_vector_ingestion import PgVectorIngestionService
from ..core.database import get_vector_db


class DocumentProcessor:
    """Service for processing and chunking documents"""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_service = StorageService()

        # Get vector database session for vector ingestion service
        self.vector_db = next(get_vector_db())
        self.vector_ingestion_service = PgVectorIngestionService(db=self.vector_db)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
        )
    
    def process_document(
        self, 
        tenant_id: str, 
        file_data: BinaryIO,
        filename: str,
        content_type: str
    ) -> Tuple[List[Document], str]:
        """Process uploaded document and return chunks"""
        
        # Store document in a database
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
        
        try:
            # Upload to storage
            object_name = self.storage_service.upload_file(
                tenant_id=tenant_id,
                file_data=file_data,
                filename=filename,
                content_type=content_type
            )
            
            # Update document record with a file path
            doc_record.file_path = object_name
            self.db.commit()
            
            # Download file for processing
            file_content = self.storage_service.download_file(object_name)
            
            # Process based on a file type
            documents = self._extract_text_from_file(file_content, filename, content_type)
            
            # Add metadata to documents
            for doc in documents:
                doc.metadata.update({
                    "tenant_id": tenant_id,
                    "source": filename,
                    "document_id": doc_record.id,
                    "upload_date": datetime.now().isoformat()
                })
            
            # Mark as completed
            doc_record.status = DocumentStatus.COMPLETED
            doc_record.processed_at = datetime.now()
            self.db.commit()
            
            return documents, doc_record.id
            
        except Exception as e:
            # Mark as failed
            doc_record.status = DocumentStatus.FAILED
            doc_record.error_message = str(e)
            self.db.commit()
            raise
    
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
            
            # Delete from database
            self.db.delete(doc)
            self.db.commit()
            
            # Log cleanup summary
            print(f"📋 Document {document_id} deletion summary:")
            print(f"   - Storage (MinIO): {'✅' if cleanup_results['storage_deleted'] else '❌'}")
            print(f"   - Vectors (PgVector): {'✅' if cleanup_results['vectors_deleted'] else '❌'}")
            print(f"   - Database: ✅")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error deleting document {document_id}: {e}")
            return False
