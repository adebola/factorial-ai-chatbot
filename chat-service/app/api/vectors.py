from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional

from ..core.database import get_db
from ..services.vector_store import TenantVectorStore

router = APIRouter()

# Global vector store instance
vector_store = TenantVectorStore()


@router.delete("/document/{document_id}")
async def delete_document_vectors(
    document_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db)
):
    """Delete vectors associated with a specific document"""
    try:
        success = vector_store.delete_document_vectors(tenant_id, document_id)
        
        if success:
            return {
                "message": "Document vectors deleted successfully",
                "document_id": document_id,
                "tenant_id": tenant_id
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete document vectors"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error deleting document vectors: {str(e)}"
        )


@router.delete("/ingestion/{ingestion_id}")
async def delete_ingestion_vectors(
    ingestion_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    db: Session = Depends(get_db)
):
    """Delete vectors associated with a specific website ingestion"""
    try:
        success = vector_store.delete_ingestion_vectors(tenant_id, ingestion_id)
        
        if success:
            return {
                "message": "Ingestion vectors deleted successfully",
                "ingestion_id": ingestion_id,
                "tenant_id": tenant_id
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete ingestion vectors"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error deleting ingestion vectors: {str(e)}"
        )


@router.delete("/tenant/{tenant_id}")
async def delete_tenant_vectors(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """Delete all vectors for a tenant"""
    try:
        success = vector_store.delete_tenant_store(tenant_id)
        
        if success:
            return {
                "message": "Tenant vectors deleted successfully",
                "tenant_id": tenant_id
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete tenant vectors"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error deleting tenant vectors: {str(e)}"
        )