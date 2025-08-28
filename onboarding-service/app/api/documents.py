from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import io

from ..core.database import get_db, get_vector_db
from ..services.document_processor import DocumentProcessor
from ..services.pg_vector_ingestion import PgVectorIngestionService
from ..services.dependencies import get_current_tenant
from ..models.tenant import Tenant

router = APIRouter()



@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Upload and process a document (requires Bearer token authentication)"""
    
    # Validate file type
    allowed_types = {
        "application/pdf",
        "text/plain", 
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}"
        )
    
    try:
        # Process document
        doc_processor = DocumentProcessor(db)
        documents, document_id  = doc_processor.process_document(
            tenant_id=current_tenant.id,
            file_data=file.file,
            filename=file.filename,
            content_type=file.content_type
        )
        
        # Ingest into vector store
        vector_service = PgVectorIngestionService(vector_db)
        vector_service.ingest_documents(current_tenant.id, documents, document_id)
        
        return {
            "message": "Document uploaded and processed successfully",
            "filename": file.filename,
            "chunks_created": len(documents),
            "tenant_id": current_tenant.id,
            "tenant_name": current_tenant.name
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )

@router.get("/documents/")
async def list_tenant_documents(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all documents for a tenant (requires Bearer token authentication)"""
    
    doc_processor = DocumentProcessor(db)
    documents = doc_processor.get_tenant_documents(current_tenant.id)
    
    return {
        "documents": [
            {
                "id": doc.id,
                "filename": doc.original_filename,
                "status": doc.status,
                "created_at": doc.created_at.isoformat(),
                "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
                "error_message": doc.error_message
            }
            for doc in documents
        ]
    }




@router.put("/documents/{document_id}/replace")
async def replace_document(
    document_id: str,
    file: UploadFile = File(...),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Replace an existing document with a new file (requires Bearer token authentication)"""
    
    # Validate file type
    allowed_types = {
        "application/pdf",
        "text/plain", 
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}"
        )
    
    try:
        # Get an existing document to ensure it belongs to the tenant
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(current_tenant.id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )
        
        # Delete the old document (this will also clean up storage)
        doc_processor.delete_document(current_tenant.id, document_id)
        
        # Process the new document with the same metadata where possible
        new_documents, x_id = doc_processor.process_document(
            tenant_id=current_tenant.id,
            file_data=file.file,
            filename=file.filename,
            content_type=file.content_type
        )
        
        # Update the new document record to use the original document ID
        if new_documents:
            # Get the newly created document
            updated_documents = doc_processor.get_tenant_documents(current_tenant.id)
            newest_doc = max(updated_documents, key=lambda x: x.created_at)
            
            # Update the ID to match the original document
            db.execute(
                "UPDATE documents SET id = :old_id WHERE id = :new_id",
                {"old_id": document_id, "new_id": newest_doc.id}
            )
            db.commit()
        
        # Ingest into vector store (this will create new embeddings)
        vector_service = PgVectorIngestionService(vector_db)
        vector_service.ingest_documents(current_tenant.id, new_documents, document_id)
        
        return {
            "message": "Document replaced successfully",
            "document_id": document_id,
            "original_filename": existing_doc.original_filename,
            "new_filename": file.filename,
            "chunks_created": len(new_documents),
            "tenant_id": current_tenant.id,
            "tenant_name": current_tenant.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to replace document: {str(e)}"
        )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete a single document (requires Bearer token authentication)"""
    
    try:
        doc_processor = DocumentProcessor(db)
        
        # Verify the document exists and belongs to tenant
        existing_documents = doc_processor.get_tenant_documents(current_tenant.id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )
        
        # Delete document (this also removes from storage)
        success = doc_processor.delete_document(current_tenant.id, document_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document"
            )
        
        return {
            "message": "Document deleted successfully",
            "document_id": document_id,
            "filename": existing_doc.original_filename,
            "tenant_id": current_tenant.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )


@router.delete("/documents/")
async def delete_multiple_documents(
    document_ids: List[str],
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete multiple documents (requires Bearer token authentication)"""
    
    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No document IDs provided"
        )
    
    try:
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(current_tenant.id)
        existing_doc_ids = {doc.id for doc in existing_documents}
        
        # Validate all documents belong to tenant
        invalid_ids = [doc_id for doc_id in document_ids if doc_id not in existing_doc_ids]
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Documents not found or do not belong to tenant: {invalid_ids}"
            )
        
        # Delete all documents
        deleted_count = 0
        failed_ids = []
        
        for document_id in document_ids:
            success = doc_processor.delete_document(current_tenant.id, document_id)
            if success:
                deleted_count += 1
            else:
                failed_ids.append(document_id)
        
        result = {
            "message": f"Deleted {deleted_count} of {len(document_ids)} documents",
            "deleted_count": deleted_count,
            "total_requested": len(document_ids),
            "tenant_id": current_tenant.id
        }
        
        if failed_ids:
            result["failed_deletions"] = failed_ids
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete documents: {str(e)}"
        )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> StreamingResponse:
    """Download a document file (requires Bearer token authentication)"""
    
    try:
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(current_tenant.id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )
        
        # Get file from storage
        from ..services.storage_service import StorageService
        storage_service = StorageService()
        
        try:
            file_data = storage_service.download_file(existing_doc.file_path)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document file not found in storage"
            )
        
        # Create streaming response
        file_stream = io.BytesIO(file_data)
        
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=existing_doc.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=\"{existing_doc.original_filename}\""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {str(e)}"
        )


@router.get("/documents/{document_id}/view")
async def view_document(
    document_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """View document metadata and content preview (requires Bearer token authentication)"""
    
    try:
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(current_tenant.id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )
        
        # Get file content for preview (first 1000 characters for text files)
        content_preview = None
        if existing_doc.mime_type == "text/plain":
            try:
                from ..services.storage_service import StorageService
                storage_service = StorageService()
                file_data = storage_service.download_file(existing_doc.file_path)
                content_text = file_data.decode('utf-8', errors='ignore')
                content_preview = content_text[:1000] + ("..." if len(content_text) > 1000 else "")
            except Exception:
                content_preview = "Preview not available"
        
        return {
            "document_id": existing_doc.id,
            "filename": existing_doc.original_filename,
            "file_size": existing_doc.file_size,
            "mime_type": existing_doc.mime_type,
            "status": existing_doc.status,
            "created_at": existing_doc.created_at.isoformat(),
            "processed_at": existing_doc.processed_at.isoformat() if existing_doc.processed_at else None,
            "error_message": existing_doc.error_message,
            "content_preview": content_preview,
            "tenant_id": current_tenant.id,
            "tenant_name": current_tenant.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to view document: {str(e)}"
        )