from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any, Optional
import io

from ..core.database import get_db, get_vector_db
from ..services.document_processor import DocumentProcessor
from ..services.pg_vector_ingestion import PgVectorIngestionService
from ..services.categorized_vector_store import CategorizedVectorStore
from ..services.dependencies import validate_token, get_full_tenant_details, TokenClaims
from ..services.billing_client import BillingClient

router = APIRouter()

@router.post("/documents/upload")
async def upload_document_with_categorization(
    file: UploadFile = File(...),
    categories: Optional[List[str]] = Form(None, description="User-specified categories"),
    tags: Optional[List[str]] = Form(None, description="User-specified tags"),
    auto_categorize: bool = Form(True, description="Enable AI categorization"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Upload and process a document with enhanced categorization (requires Bearer token authentication)"""

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

    # Check document upload limit via Billing Service API
    # This happens BEFORE processing to avoid wasted resources
    billing_client = BillingClient(claims.access_token)
    limit_check = await billing_client.check_usage_limit("documents")

    if not limit_check.get("allowed", False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=limit_check.get(
                "reason",
                "Document upload limit exceeded. Please upgrade your plan to upload more documents."
            )
        )

    try:
        # Process document with categorization
        doc_processor = DocumentProcessor(db)
        documents, document_id, classification = await doc_processor.process_document(
            tenant_id=claims.tenant_id,
            file_data=file.file,
            filename=file.filename,
            content_type=file.content_type,
            user_categories=categories,
            user_tags=tags,
            auto_categorize=auto_categorize
        )

        # Ingest into vector store (metadata is already in documents)
        vector_service = PgVectorIngestionService(vector_db)
        vector_service.ingest_documents(claims.tenant_id, documents, document_id)

        # Get tenant details
        tenant_details = await get_full_tenant_details(claims.tenant_id, claims.access_token)

        # Note: Usage tracking events are now published by the Billing Service
        # The billing service monitors document creation through its own mechanisms

        return {
            "message": "Document uploaded and categorized successfully",
            "document_id": document_id,
            "filename": file.filename,
            "chunks_created": len(documents),
            "classification": {
                "categories": classification.categories if classification else [],
                "tags": classification.tags if classification else [],
                "content_type": classification.content_type if classification else "document",
                "language": classification.language if classification else "en",
                "confidence": max([c["confidence"] for c in classification.categories]) if classification and classification.categories else 0
            },
            "user_specified": {
                "categories": categories or [],
                "tags": tags or []
            },
            "tenant_id": claims.tenant_id,
            "tenant_name": tenant_details.get("name")
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )

@router.get("/documents/")
async def list_tenant_documents(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all documents for a tenant (requires Bearer token authentication)"""
    
    doc_processor = DocumentProcessor(db)
    documents = doc_processor.get_tenant_documents(claims.tenant_id)
    
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
    claims: TokenClaims = Depends(validate_token),
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
        existing_documents = doc_processor.get_tenant_documents(claims.tenant_id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )
        
        # Delete the old document (this will also clean up storage)
        doc_processor.delete_document(claims.tenant_id, document_id)
        
        # Process the new document with the same metadata where possible
        new_documents, x_id = doc_processor.process_document(
            tenant_id=claims.tenant_id,
            file_data=file.file,
            filename=file.filename,
            content_type=file.content_type
        )
        
        # Update the new document record to use the original document ID
        if new_documents:
            # Get the newly created document
            updated_documents = doc_processor.get_tenant_documents(claims.tenant_id)
            newest_doc = max(updated_documents, key=lambda x: x.created_at)
            
            # Update the ID to match the original document
            db.execute (
                "UPDATE documents SET id = :old_id WHERE id = :new_id",
                {"old_id": document_id, "new_id": newest_doc.id}
            )
            db.commit()
        
        # Ingest into vector store (this will create new embeddings)
        vector_service = PgVectorIngestionService(vector_db)
        vector_service.ingest_documents(claims.tenant_id, new_documents, document_id)
        
        # Get tenant details if needed
        tenant_details = await get_full_tenant_details(claims.tenant_id, claims.access_token)
        
        return {
            "message": "Document replaced successfully",
            "document_id": document_id,
            "original_filename": existing_doc.original_filename,
            "new_filename": file.filename,
            "chunks_created": len(new_documents),
            "tenant_id": claims.tenant_id,
            "tenant_name": tenant_details.get("name")
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
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete a single document (requires Bearer token authentication)"""
    
    try:
        doc_processor = DocumentProcessor(db)
        
        # Verify the document exists and belongs to tenant
        existing_documents = doc_processor.get_tenant_documents(claims.tenant_id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)
        
        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )
        
        # Delete document (this also removes from storage)
        success = doc_processor.delete_document(claims.tenant_id, document_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document"
            )

        # Publish usage event for document deletion (fire-and-forget)
        try:
            usage_publisher.connect()
            usage_publisher.publish_document_deleted(
                tenant_id=claims.tenant_id,
                document_id=document_id
            )
        except Exception as e:
            # Log but don't fail the request
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to publish document deleted event: {e}")

        return {
            "message": "Document deleted successfully",
            "document_id": document_id,
            "filename": existing_doc.original_filename,
            "tenant_id": claims.tenant_id
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
    claims: TokenClaims = Depends(validate_token),
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
        existing_documents = doc_processor.get_tenant_documents(claims.tenant_id)
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
        successfully_deleted_ids = []

        for document_id in document_ids:
            success = doc_processor.delete_document(claims.tenant_id, document_id)
            if success:
                deleted_count += 1
                successfully_deleted_ids.append(document_id)
            else:
                failed_ids.append(document_id)

        # Publish usage events for all successfully deleted documents (fire-and-forget)
        try:
            usage_publisher.connect()
            for document_id in successfully_deleted_ids:
                usage_publisher.publish_document_deleted(
                    tenant_id=claims.tenant_id,
                    document_id=document_id
                )
        except Exception as e:
            # Log but don't fail the request
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to publish document deleted events: {e}")
        
        result = {
            "message": f"Deleted {deleted_count} of {len(document_ids)} documents",
            "deleted_count": deleted_count,
            "total_requested": len(document_ids),
            "tenant_id": claims.tenant_id
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
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> StreamingResponse:
    """Download a document file (requires Bearer token authentication)"""
    
    try:
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(claims.tenant_id)
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
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """View document metadata and content preview (requires Bearer token authentication)"""
    
    try:
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(claims.tenant_id)
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
        
        # Get tenant details if needed
        tenant_details = await get_full_tenant_details(claims.tenant_id, claims.access_token)
        
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
            "tenant_id": claims.tenant_id,
            "tenant_name": tenant_details.get("name")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to view document: {str(e)}"
        )


@router.get("/documents/{document_id}/metadata")
async def get_document_metadata(
    document_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Get comprehensive document metadata including categories, tags, and file information (requires Bearer token authentication)"""

    try:
        doc_processor = DocumentProcessor(db)
        existing_documents = doc_processor.get_tenant_documents(claims.tenant_id)
        existing_doc = next((doc for doc in existing_documents if doc.id == document_id), None)

        if not existing_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or does not belong to this tenant"
            )

        # Get document categories
        categories = db.execute(
            text("""
                SELECT c.id, c.name, c.description, c.color, c.icon, c.is_system_category,
                       dca.confidence_score, dca.assigned_by, dca.assigned_at
                FROM document_categories c
                JOIN document_category_assignments dca ON c.id = dca.category_id
                WHERE dca.document_id = :document_id
                ORDER BY dca.confidence_score DESC
            """),
            {"document_id": document_id}
        ).fetchall()

        # Get document tags
        tags = db.execute(
            text("""
                SELECT t.id, t.name, t.tag_type, t.usage_count,
                       dta.confidence_score, dta.assigned_by, dta.assigned_at
                FROM document_tags t
                JOIN document_tag_assignments dta ON t.id = dta.tag_id
                WHERE dta.document_id = :document_id
                ORDER BY dta.confidence_score DESC
            """),
            {"document_id": document_id}
        ).fetchall()

        # Format file size in human-readable format
        def format_file_size(size_bytes):
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"

        # Get processing statistics from vector database
        processing_stats = vector_db.execute(
            text("""
                SELECT COUNT(*) as chunk_count
                FROM vectors.document_chunks
                WHERE document_id = :document_id
            """),
            {"document_id": document_id}
        ).fetchone()

        return {
            "document_id": existing_doc.id,
            "filename": existing_doc.original_filename,
            "file_size": existing_doc.file_size,
            "file_size_formatted": format_file_size(existing_doc.file_size or 0),
            "mime_type": existing_doc.mime_type,
            "status": existing_doc.status,
            "file_path": existing_doc.file_path,
            "created_at": existing_doc.created_at.isoformat(),
            "processed_at": existing_doc.processed_at.isoformat() if existing_doc.processed_at else None,
            "error_message": existing_doc.error_message,
            "tenant_id": claims.tenant_id,
            "categories": [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "description": cat.description,
                    "color": cat.color,
                    "icon": cat.icon,
                    "is_system_category": cat.is_system_category,
                    "confidence_score": float(cat.confidence_score or 0),
                    "assigned_by": cat.assigned_by,
                    "assigned_at": cat.assigned_at.isoformat() if cat.assigned_at else None
                }
                for cat in categories
            ],
            "tags": [
                {
                    "id": tag.id,
                    "name": tag.name,
                    "tag_type": tag.tag_type,
                    "usage_count": tag.usage_count,
                    "confidence_score": float(tag.confidence_score or 0),
                    "assigned_by": tag.assigned_by,
                    "assigned_at": tag.assigned_at.isoformat() if tag.assigned_at else None
                }
                for tag in tags
            ],
            "processing_stats": {
                "chunk_count": processing_stats.chunk_count if processing_stats else 0,
                "has_vector_data": bool(processing_stats and processing_stats.chunk_count > 0)
            },
            "categorization_summary": {
                "total_categories": len(categories),
                "total_tags": len(tags),
                "ai_assigned_categories": len([c for c in categories if c.assigned_by == "ai"]),
                "user_assigned_categories": len([c for c in categories if c.assigned_by == "user"]),
                "auto_tags": len([t for t in tags if t.tag_type == "auto"]),
                "custom_tags": len([t for t in tags if t.tag_type == "custom"])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get document metadata: {str(e)}"
        )