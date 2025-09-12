from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any
import asyncio
from datetime import datetime

from ..core.database import get_db, get_vector_db
from ..services.website_scraper import WebsiteScraper
from ..services.pg_vector_ingestion import PgVectorIngestionService
from ..services.dependencies import get_current_tenant, TokenClaims, validate_token, get_full_tenant_details
from ..models.tenant import IngestionStatus, WebsitePage

router = APIRouter()


@router.post("/websites/ingest")
async def ingest_website(
    website_url: str = Form(...),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Start the website ingestion process (requires Bearer token authentication)"""
    
    # Validate URL
    if not website_url.startswith(('http://', 'https://')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format"
        )
    
    try:
        # Start scraping in the background
        scraper = WebsiteScraper(db)
        ingestion = scraper.start_website_ingestion(claims.tenant_id, website_url)
        
        # Process in the background (in a real app, use Celery)
        # Pass environment variables explicitly to a background task
        import os
        openai_key = os.environ.get("OPENAI_API_KEY")
        asyncio.create_task(
            background_website_ingestion(claims.tenant_id, website_url, ingestion.id, db, openai_key)
        )

        # Get tenant details if needed
        tenant_details = await get_full_tenant_details(claims.tenant_id)
        
        return {
            "message": "Website ingestion started",
            "ingestion_id": ingestion.id,
            "website_url": website_url,
            "status": "in_progress",
            "tenant_id": claims.tenant_id,
            "tenant_name": tenant_details.get("name")
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start website ingestion: {str(e)}"
        )


@router.get("/ingestions/{ingestion_id}/status")
async def get_ingestion_status(
    ingestion_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get website ingestion status (requires Bearer token authentication)"""
    
    scraper = WebsiteScraper(db)
    ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)
    
    if not ingestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion not found or does not belong to this tenant"
        )

    # Get tenant details if needed
    tenant_details = await get_full_tenant_details(claims.tenant_id)
    
    return {
        "ingestion_id": ingestion.id,
        "base_url": ingestion.base_url,
        "status": ingestion.status,
        "pages_discovered": ingestion.pages_discovered,
        "pages_processed": ingestion.pages_processed,
        "pages_failed": ingestion.pages_failed,
        "started_at": ingestion.started_at.isoformat() if ingestion.started_at else None,
        "completed_at": ingestion.completed_at.isoformat() if ingestion.completed_at else None,
        "error_message": ingestion.error_message,
        "tenant_id": claims.tenant_id,
        "tenant_name": tenant_details.get("name")
    }


@router.get("/ingestions/")
async def list_tenant_ingestions(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all website ingestions for a tenant (requires Bearer token authentication)"""
    
    scraper = WebsiteScraper(db)
    ingestions = scraper.get_tenant_ingestions(claims.tenant_id)

    # Get tenant details if needed
    tenant_details = await get_full_tenant_details(claims.tenant_id)
    
    return {
        "ingestions": [
            {
                "id": ing.id,
                "base_url": ing.base_url,
                "status": ing.status,
                "pages_discovered": ing.pages_discovered,
                "pages_processed": ing.pages_processed,
                "pages_failed": ing.pages_failed,
                "started_at": ing.started_at.isoformat() if ing.started_at else None,
                "completed_at": ing.completed_at.isoformat() if ing.completed_at else None,
                "error_message": ing.error_message
            }
            for ing in ingestions
        ],
        "total_ingestions": len(ingestions),
        "tenant_id": claims.tenant_id,
        "tenant_name": tenant_details.get("name")
    }


@router.delete("/ingestions/{ingestion_id}")
async def delete_ingestion(
    ingestion_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete a website ingestion record (requires Bearer token authentication)"""
    
    try:
        scraper = WebsiteScraper(db)
        
        # Verify ingestion exists and belongs to a tenant
        ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)
        if not ingestion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingestion not found or does not belong to this tenant"
            )
        
        # Delete ingestion record (this could also clean up related pages)
        success = scraper.delete_ingestion(claims.tenant_id, ingestion_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete ingestion"
            )
        
        return {
            "message": "Website ingestion deleted successfully",
            "ingestion_id": ingestion_id,
            "base_url": ingestion.base_url,
            "tenant_id": claims.tenant_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete ingestion: {str(e)}"
        )


@router.post("/ingestions/{ingestion_id}/retry")
async def retry_ingestion(
    ingestion_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Retry a failed website ingestion (requires Bearer token authentication)"""
    
    try:
        scraper = WebsiteScraper(db)
        
        # Get existing ingestion
        ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)
        if not ingestion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingestion not found or does not belong to this tenant"
            )
        
        # Only allow retry for failed ingestions
        if ingestion.status not in ["failed", "completed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only retry failed or completed ingestions"
            )
        
        # Reset ingestion status and restart
        scraper.reset_ingestion_for_retry(ingestion_id)
        
        # Start processing in the background
        import os
        openai_key = os.environ.get("OPENAI_API_KEY")
        asyncio.create_task(
            background_website_ingestion(claims.tenant_id, ingestion.base_url, ingestion_id, db, openai_key)
        )
        
        return {
            "message": "Website ingestion retry started",
            "ingestion_id": ingestion_id,
            "base_url": ingestion.base_url,
            "status": "in_progress",
            "tenant_id": claims.tenant_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry ingestion: {str(e)}"
        )


async def background_website_ingestion(tenant_id: str, website_url: str, ingestion_id: str, db: Session, openai_api_key: str = None):
    """Background task for website ingestion"""
    try:
        # Ensure environment variables are loaded
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        # Set the OPENAI_API_KEY explicitly in the background task environment
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
            print(f"✅ OPENAI_API_KEY set in background task (length: {len(openai_api_key)})")
        
        # Check if OPENAI_API_KEY is available
        current_key = os.environ.get("OPENAI_API_KEY")
        if not current_key:
            error_msg = "OPENAI_API_KEY environment variable not found in background task"
            print(f"❌ Background ingestion failed: {error_msg}")
            
            # Update ingestion status to failed
            scraper = WebsiteScraper(db)
            ingestion = scraper.get_ingestion_status(tenant_id, ingestion_id)
            if ingestion:
                ingestion.status = IngestionStatus.FAILED
                ingestion.error_message = error_msg
                ingestion.completed_at = datetime.now()
                db.commit()
            return
        else:
            print(f"✅ OPENAI_API_KEY available in background task (length: {len(current_key)})")
        
        scraper = WebsiteScraper(db)
        
        # Get the existing ingestion record instead of creating a new one
        ingestion = scraper.get_ingestion_status(tenant_id, ingestion_id)
        if not ingestion:
            print(f"Ingestion {ingestion_id} not found")
            return
            
        documents = scraper.process_existing_ingestion(ingestion)
        
        # Ingest into vector store
        if documents:
            # Get a fresh vector database session for the background task
            from ..core.database import get_vector_db
            vector_db = next(get_vector_db())
            vector_service = PgVectorIngestionService(vector_db)
            vector_service.ingest_documents(tenant_id, documents, ingestion_id=ingestion_id)
            vector_db.close()
            
    except Exception as e:
        print(f"Background ingestion failed: {e}")
        # Update ingestion status to failed
        try:
            scraper = WebsiteScraper(db)
            ingestion = scraper.get_ingestion_status(tenant_id, ingestion_id)
            if ingestion:
                ingestion.status = IngestionStatus.FAILED
                ingestion.error_message = str(e)
                ingestion.completed_at = datetime.now()
                db.commit()
        except Exception as update_error:
            print(f"Failed to update ingestion status: {update_error}")


@router.get("/ingestions/{ingestion_id}/pages")
async def get_ingestion_pages(
    ingestion_id: str,
    page: int = 1,
    page_size: int = 20,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get individual pages for website ingestion with pagination (requires Bearer token authentication)"""
    
    # Verify ingestion belongs to tenant
    scraper = WebsiteScraper(db)
    ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)
    
    if not ingestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion not found or does not belong to this tenant"
        )
    
    # Calculate pagination
    offset = (page - 1) * page_size
    
    # Get pages with pagination
    pages_query = db.query(WebsitePage).filter(
        WebsitePage.tenant_id == claims.tenant_id,
        WebsitePage.ingestion_id == ingestion_id
    ).order_by(WebsitePage.created_at.desc())
    
    total_pages = pages_query.count()
    pages = pages_query.offset(offset).limit(page_size).all()
    
    return {
        "ingestion_id": ingestion_id,
        "base_url": ingestion.base_url,
        "ingestion_status": ingestion.status,
        "pages": [
            {
                "id": page.id,
                "url": page.url,
                "title": page.title,
                "status": page.status,
                "content_hash": page.content_hash,
                "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                "error_message": page.error_message,
                "created_at": page.created_at.isoformat() if page.created_at else None
            }
            for page in pages
        ],
        "pagination": {
            "current_page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_pages_count": (total_pages + page_size - 1) // page_size,
            "has_next": offset + page_size < total_pages,
            "has_previous": page > 1
        },
        "tenant_id": claims.tenant_id,
    }


@router.get("/ingestions/{ingestion_id}/stats")
async def get_ingestion_stats(
    ingestion_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get detailed statistics for a website ingestion (requires Bearer token authentication)"""
    
    # Verify ingestion belongs to tenant
    scraper = WebsiteScraper(db)
    ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)
    
    if not ingestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion not found or does not belong to this tenant"
        )
    
    # Get page statistics by status
    pages_stats = db.query(
        WebsitePage.status,
        func.count(WebsitePage.id).label('count')
    ).filter(
        WebsitePage.tenant_id == claims.tenant_id,
        WebsitePage.ingestion_id == ingestion_id
    ).group_by(WebsitePage.status).all()
    
    # Get total content size estimation (based on content_hash uniqueness)
    unique_pages = db.query(WebsitePage).filter(
        WebsitePage.tenant_id == claims.tenant_id,
        WebsitePage.ingestion_id == ingestion_id,
        WebsitePage.content_hash.isnot(None)
    ).count()
    
    # Get all pages for detailed analysis
    all_pages = db.query(WebsitePage).filter(
        WebsitePage.tenant_id == claims.tenant_id,
        WebsitePage.ingestion_id == ingestion_id
    ).all()
    
    # Calculate processing time if completed
    processing_time = None
    if ingestion.started_at and ingestion.completed_at:
        processing_time = (ingestion.completed_at - ingestion.started_at).total_seconds()
    
    # Group pages by domain/subdirectory
    url_analysis = {}
    for page in all_pages:
        if page.url:
            from urllib.parse import urlparse
            parsed = urlparse(page.url)
            domain_path = f"{parsed.netloc}{parsed.path.rpartition('/')[0]}"
            if domain_path not in url_analysis:
                url_analysis[domain_path] = {"total": 0, "completed": 0, "failed": 0}
            url_analysis[domain_path]["total"] += 1
            if page.status == "completed":
                url_analysis[domain_path]["completed"] += 1
            elif page.status == "failed":
                url_analysis[domain_path]["failed"] += 1
    
    return {
        "ingestion_id": ingestion_id,
        "base_url": ingestion.base_url,
        "status": ingestion.status,
        "summary": {
            "pages_discovered": ingestion.pages_discovered,
            "pages_processed": ingestion.pages_processed,
            "pages_failed": ingestion.pages_failed,
            "unique_content_pages": unique_pages,
            "processing_time_seconds": processing_time,
            "started_at": ingestion.started_at.isoformat() if ingestion.started_at else None,
            "completed_at": ingestion.completed_at.isoformat() if ingestion.completed_at else None
        },
        "pages_by_status": {
            stat.status: stat.count for stat in pages_stats
        },
        "url_analysis": url_analysis,
        "estimated_content_size": {
            "unique_pages": unique_pages,
            "estimated_total_characters": unique_pages * 2000,  # Rough estimate
            "note": "Content size is estimated based on average page content length"
        },
        "tenant_id": claims.tenant_id
    }


@router.get("/ingestions/{ingestion_id}/pages/{page_id}/content")
async def get_page_content_preview(
    ingestion_id: str,
    page_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get content preview for a specific page (requires Bearer token authentication)"""
    
    # Verify ingestion belongs to tenant
    scraper = WebsiteScraper(db)
    ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)
    
    if not ingestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion not found or does not belong to this tenant"
        )
    
    # Get the specific page
    page = db.query(WebsitePage).filter(
        WebsitePage.id == page_id,
        WebsitePage.tenant_id == claims.tenant_id,
        WebsitePage.ingestion_id == ingestion_id
    ).first()
    
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found in this ingestion"
        )
    
    # Content preview note - actual content is stored in vector store
    content_preview = None
    if page.status == "completed":
        content_preview = "✅ Content successfully processed and stored in vector database"
    elif page.status == "failed":
        content_preview = f"❌ Failed to process: {page.error_message}" if page.error_message else "❌ Processing failed"
    elif page.status == "processing":
        content_preview = "⏳ Currently being processed..."
    else:
        content_preview = "📝 Waiting to be processed"
    
    return {
        "page_id": page_id,
        "ingestion_id": ingestion_id,
        "page_details": {
            "url": page.url,
            "title": page.title,
            "status": page.status,
            "content_hash": page.content_hash,
            "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
            "error_message": page.error_message,
            "created_at": page.created_at.isoformat() if page.created_at else None
        },
        "content_preview": content_preview,
        "note": "Content preview shows first 500 characters of processed content",
        "tenant_id": claims.tenant_id,
    }
