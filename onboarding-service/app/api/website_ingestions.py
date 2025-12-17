from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime

from ..core.database import get_db, get_vector_db
from ..core.config import settings
from ..services.website_scraper import WebsiteScraper, ScrapingStrategy
from ..services.pg_vector_ingestion import PgVectorIngestionService
from ..services.document_categorization import DocumentCategorizationService
from ..services.dependencies import get_current_tenant, TokenClaims, validate_token, get_full_tenant_details
from ..models.tenant import IngestionStatus, WebsitePage, WebsiteIngestion
from ..core.logging_config import get_logger
from ..services.billing_client import BillingClient
from ..services.usage_publisher import usage_publisher

router = APIRouter()
logger = get_logger("website_ingestions")


@router.post("/websites/ingest")
async def ingest_website(
    website_url: str = Form(...),
    categories: Optional[List[str]] = Form(None, description="User-specified categories"),
    tags: Optional[List[str]] = Form(None, description="User-specified tags"),
    auto_categorize: bool = Form(True, description="Enable AI categorization"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Start the website ingestion process with categorization (requires Bearer token authentication)"""

    # Validate URL
    if not website_url.startswith(('http://', 'https://')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format"
        )

    # Check website ingestion limit via Billing Service API
    # This happens BEFORE starting the expensive scraping process
    billing_client = BillingClient(claims.access_token)

    # Use new restrictions API endpoint for comprehensive subscription + limit check
    limit_check = await billing_client.check_can_ingest_website(claims.tenant_id)

    if not limit_check.get("allowed", False):
        reason = limit_check.get("reason", "Website ingestion not allowed")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason
        )

    try:
        # Start scraping in the background
        # Don't pass use_javascript parameter - let it use the default AUTO strategy
        scraper = WebsiteScraper(db)
        ingestion = scraper.start_website_ingestion(claims.tenant_id, website_url)
        
        # Process in the background (in a real app, use Celery)
        # Pass environment variables and categorization parameters to background task
        import os
        openai_key = os.environ.get("OPENAI_API_KEY")
        asyncio.create_task(
            background_website_ingestion(
                tenant_id=claims.tenant_id,
                website_url=website_url,
                ingestion_id=ingestion.id,
                openai_api_key=openai_key,
                user_categories=categories,
                user_tags=tags,
                auto_categorize=auto_categorize,
                scraping_strategy=scraper.strategy
            )
        )

        # Get tenant details if needed
        tenant_details = await get_full_tenant_details(claims.tenant_id, claims.access_token)

        return {
            "message": "Website ingestion started with categorization",
            "ingestion_id": ingestion.id,
            "website_url": website_url,
            "status": "in_progress",
            "categorization": {
                "auto_categorize": auto_categorize,
                "user_categories": categories or [],
                "user_tags": tags or []
            },
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
    db: Session = Depends(get_db),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Get website ingestion status with categorization statistics (requires Bearer token authentication)"""

    scraper = WebsiteScraper(db)
    ingestion = scraper.get_ingestion_status(claims.tenant_id, ingestion_id)

    if not ingestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion not found or does not belong to this tenant"
        )

    # Get categorization statistics from vector database
    categorization_stats = None
    try:
        from sqlalchemy import text

        # Query for categorization statistics for this ingestion
        stats_query = text("""
            SELECT
                COUNT(*) as total_chunks,
                COUNT(*) FILTER (WHERE array_length(category_ids, 1) > 0) as chunks_with_categories,
                COUNT(*) FILTER (WHERE array_length(tag_ids, 1) > 0) as chunks_with_tags,
                COUNT(DISTINCT content_type) FILTER (WHERE content_type IS NOT NULL) as content_types_count
            FROM vectors.document_chunks
            WHERE tenant_id = :tenant_id AND ingestion_id = :ingestion_id
        """)

        result = vector_db.execute(stats_query, {
            "tenant_id": claims.tenant_id,
            "ingestion_id": ingestion_id
        }).first()

        if result and result.total_chunks > 0:
            # Get distinct content types
            content_types_query = text("""
                SELECT content_type, COUNT(*) as count
                FROM vectors.document_chunks
                WHERE tenant_id = :tenant_id AND ingestion_id = :ingestion_id
                    AND content_type IS NOT NULL
                GROUP BY content_type
                ORDER BY count DESC
            """)

            content_types_result = vector_db.execute(content_types_query, {
                "tenant_id": claims.tenant_id,
                "ingestion_id": ingestion_id
            }).fetchall()

            # Get unique category IDs used in this ingestion
            categories_query = text("""
                SELECT DISTINCT unnest(category_ids) as category_id
                FROM vectors.document_chunks
                WHERE tenant_id = :tenant_id AND ingestion_id = :ingestion_id
                    AND array_length(category_ids, 1) > 0
            """)

            category_ids_result = vector_db.execute(categories_query, {
                "tenant_id": claims.tenant_id,
                "ingestion_id": ingestion_id
            }).fetchall()

            # Get category names from main database
            categories_list = []
            if category_ids_result:
                from ..models.categorization import DocumentCategory
                category_ids = [row.category_id for row in category_ids_result]
                categories = db.query(DocumentCategory).filter(
                    DocumentCategory.id.in_(category_ids)
                ).all()
                categories_list = [{"id": cat.id, "name": cat.name} for cat in categories]

            # Get unique tag IDs used in this ingestion
            tags_query = text("""
                SELECT DISTINCT unnest(tag_ids) as tag_id
                FROM vectors.document_chunks
                WHERE tenant_id = :tenant_id AND ingestion_id = :ingestion_id
                    AND array_length(tag_ids, 1) > 0
            """)

            tag_ids_result = vector_db.execute(tags_query, {
                "tenant_id": claims.tenant_id,
                "ingestion_id": ingestion_id
            }).fetchall()

            # Get tag names from main database
            tags_list = []
            if tag_ids_result:
                from ..models.categorization import DocumentTag
                tag_ids = [row.tag_id for row in tag_ids_result]
                tags = db.query(DocumentTag).filter(
                    DocumentTag.id.in_(tag_ids)
                ).all()
                tags_list = [{"id": tag.id, "name": tag.name} for tag in tags]

            categorization_stats = {
                "total_chunks": result.total_chunks,
                "chunks_with_categories": result.chunks_with_categories,
                "chunks_with_tags": result.chunks_with_tags,
                "categories": categories_list,
                "tags": tags_list,
                "content_types": {row.content_type: row.count for row in content_types_result}
            }
    except Exception as e:
        logger.warning(f"Failed to get categorization stats: {e}")
        categorization_stats = None

    # Get tenant details if needed
    tenant_details = await get_full_tenant_details(claims.tenant_id, claims.access_token)

    response = {
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

    # Add categorization stats if available
    if categorization_stats:
        response["categorization"] = categorization_stats

    return response


@router.get("/ingestions/")
async def list_tenant_ingestions(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """List all website ingestions for a tenant with categorization summaries (requires Bearer token authentication)"""

    scraper = WebsiteScraper(db)
    ingestions = scraper.get_tenant_ingestions(claims.tenant_id)

    # Get categorization summaries for all ingestions in batch
    categorization_summaries = {}
    if ingestions:
        try:
            from sqlalchemy import text

            ingestion_ids = [ing.id for ing in ingestions]

            # Single batch query to get categorization stats for all ingestions
            batch_query = text("""
                SELECT
                    ingestion_id,
                    COUNT(*) as total_chunks,
                    COUNT(*) FILTER (WHERE array_length(category_ids, 1) > 0) as chunks_with_categories,
                    COUNT(*) FILTER (WHERE array_length(tag_ids, 1) > 0) as chunks_with_tags,
                    (
                        SELECT COUNT(DISTINCT category_id)
                        FROM (
                            SELECT unnest(category_ids) as category_id
                            FROM vectors.document_chunks
                            WHERE tenant_id = :tenant_id AND ingestion_id = dc.ingestion_id
                        ) cat_ids
                    ) as unique_categories,
                    (
                        SELECT COUNT(DISTINCT tag_id)
                        FROM (
                            SELECT unnest(tag_ids) as tag_id
                            FROM vectors.document_chunks
                            WHERE tenant_id = :tenant_id AND ingestion_id = dc.ingestion_id
                        ) tag_ids
                    ) as unique_tags,
                    (
                        SELECT content_type
                        FROM vectors.document_chunks
                        WHERE tenant_id = :tenant_id
                            AND ingestion_id = dc.ingestion_id
                            AND content_type IS NOT NULL
                        GROUP BY content_type
                        ORDER BY COUNT(*) DESC
                        LIMIT 1
                    ) as primary_content_type
                FROM vectors.document_chunks dc
                WHERE tenant_id = :tenant_id
                    AND ingestion_id = ANY(:ingestion_ids)
                GROUP BY ingestion_id
            """)

            results = vector_db.execute(batch_query, {
                "tenant_id": claims.tenant_id,
                "ingestion_ids": ingestion_ids
            }).fetchall()

            # Build summary dict
            for row in results:
                categorization_summaries[row.ingestion_id] = {
                    "category_count": row.unique_categories or 0,
                    "tag_count": row.unique_tags or 0,
                    "primary_content_type": row.primary_content_type,
                    "has_categorization": (row.chunks_with_categories or 0) > 0,
                    "chunks_with_categories": row.chunks_with_categories or 0,
                    "total_chunks": row.total_chunks or 0
                }
        except Exception as e:
            logger.warning(f"Failed to get categorization summaries: {e}")
            # Continue without categorization summaries

    # Get tenant details if needed
    tenant_details = await get_full_tenant_details(claims.tenant_id, claims.access_token)

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
                "error_message": ing.error_message,
                "categorization_summary": categorization_summaries.get(ing.id)
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

        # Publish usage event to billing service
        try:
            usage_publisher.publish_website_removed(
                tenant_id=claims.tenant_id,
                website_id=ingestion_id,
                url=ingestion.base_url
            )
        except Exception as e:
            # Log error but don't fail the request
            logger.error(f"Failed to publish website removal usage event: {e}", tenant_id=claims.tenant_id)

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

        # Determine strategy based on ingestion status
        if ingestion.status == "failed":
            # Failed ingestion: use AUTO to try to determine best method
            strategy = ScrapingStrategy.AUTO
            logger.info(
                "Using AUTO strategy for failed ingestion retry",
                ingestion_id=ingestion_id,
                tenant_id=claims.tenant_id
            )
        else:
            # Completed ingestion: use the strategy that worked before
            # Fallback to AUTO if not set (for old records)
            strategy = ScrapingStrategy(ingestion.scraping_strategy or "auto")
            logger.info(
                "Using preserved strategy for completed ingestion retry",
                ingestion_id=ingestion_id,
                tenant_id=claims.tenant_id,
                strategy=strategy.value
            )

        # Create scraper with the determined strategy
        scraper_with_strategy = WebsiteScraper(db, strategy=strategy)

        # Reset ingestion status and restart
        scraper_with_strategy.reset_ingestion_for_retry(ingestion_id)

        # Start processing in the background
        import os
        openai_key = os.environ.get("OPENAI_API_KEY")
        asyncio.create_task(
            background_website_ingestion(
                tenant_id=claims.tenant_id,
                website_url=ingestion.base_url,
                ingestion_id=ingestion_id,
                openai_api_key=openai_key,
                scraping_strategy=strategy
            )
        )

        return {
            "message": "Website ingestion retry started",
            "ingestion_id": ingestion_id,
            "base_url": ingestion.base_url,
            "status": "in_progress",
            "strategy": strategy.value,
            "tenant_id": claims.tenant_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry ingestion: {str(e)}"
        )


async def background_website_ingestion(
    tenant_id: str,
    website_url: str,
    ingestion_id: str,
    openai_api_key: str = None,
    user_categories: Optional[List[str]] = None,
    user_tags: Optional[List[str]] = None,
    auto_categorize: bool = True,
    scraping_strategy: ScrapingStrategy = None
):
    """Background task for website ingestion with categorization - creates its own database session"""
    logger.info(
        "Background ingestion task started",
        tenant_id=tenant_id,
        ingestion_id=ingestion_id,
        website_url=website_url,
        scraping_strategy=scraping_strategy.value if scraping_strategy else "auto"
    )

    # Create FRESH database session for this background task
    # This prevents session staleness during long-running operations (hours)
    db = next(get_db())

    try:
        # Ensure environment variables are loaded
        import os
        from dotenv import load_dotenv
        load_dotenv()

        # Set the OPENAI_API_KEY explicitly in the background task environment
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
            logger.debug(
                "OPENAI_API_KEY set in background task",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                key_length=len(openai_api_key)
            )

        # Check if OPENAI_API_KEY is available
        current_key = os.environ.get("OPENAI_API_KEY")
        if not current_key:
            error_msg = "OPENAI_API_KEY environment variable not found in background task"
            logger.error(
                "Background ingestion failed - Missing OPENAI_API_KEY",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                error=error_msg
            )

            # Update ingestion status to failed
            from ..core.config import settings
            scraper = WebsiteScraper(db)
            ingestion = scraper.get_ingestion_status(tenant_id, ingestion_id)
            if ingestion:
                ingestion.status = IngestionStatus.FAILED
                ingestion.error_message = error_msg
                ingestion.completed_at = datetime.now()
                db.commit()
            return

        logger.debug(
            "OPENAI_API_KEY confirmed available",
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            key_length=len(current_key)
        )

        from ..core.config import settings
        scraper = WebsiteScraper(db, strategy=scraping_strategy)

        # Get the existing ingestion record instead of creating a new one
        ingestion = scraper.get_ingestion_status(tenant_id, ingestion_id)
        if not ingestion:
            logger.error(
                "Ingestion record not found",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id
            )
            return

        logger.info(
            "Starting website scraping process",
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            website_url=website_url
        )

        documents = await scraper.process_existing_ingestion(ingestion)

        # Define pages_scraped for usage tracking and logging
        pages_scraped = len(documents) if documents else 0

        # Categorize documents before vector ingestion
        if documents:
            logger.info(
                "Starting categorization for scraped pages",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                document_count=len(documents),
                auto_categorize=auto_categorize
            )

            # Initialize categorization service
            categorization_service = DocumentCategorizationService(db)

            # Track categorization statistics
            categorized_count = 0
            categories_discovered = set()
            tags_discovered = set()
            content_types_found = {}

            # Categorize each scraped page
            for doc in documents:
                try:
                    # Perform categorization using classify_document method
                    classification = await categorization_service.classify_document(
                        document=doc,
                        tenant_id=tenant_id,
                        enable_ai=auto_categorize
                    )

                    if classification:
                        # Get or create category and tag records, collect their IDs
                        category_ids = []
                        tag_ids = []

                        # Process categories
                        for cat_data in classification.categories:
                            try:
                                category = await categorization_service.get_or_create_category(
                                    tenant_id=tenant_id,
                                    category_name=cat_data["name"],
                                    description=f"Auto-categorized as {cat_data['name']}"
                                )
                                category_ids.append(category.id)
                                categories_discovered.add(cat_data["name"])
                            except Exception as cat_err:
                                logger.warning(f"Failed to create category {cat_data['name']}: {cat_err}")

                        # Process tags
                        for tag_data in classification.tags:
                            try:
                                tag = await categorization_service.get_or_create_tag(
                                    tenant_id=tenant_id,
                                    tag_name=tag_data["name"],
                                    tag_type="auto"
                                )
                                tag_ids.append(tag.id)
                                tags_discovered.add(tag_data["name"])
                            except Exception as tag_err:
                                logger.warning(f"Failed to create tag {tag_data['name']}: {tag_err}")

                        # Update document metadata with IDs for vector database
                        doc.metadata['category_ids'] = category_ids
                        doc.metadata['tag_ids'] = tag_ids
                        doc.metadata['content_type'] = classification.content_type
                        doc.metadata['language'] = classification.language
                        doc.metadata['sentiment'] = classification.sentiment

                        # Track statistics
                        categorized_count += 1
                        content_type = classification.content_type
                        content_types_found[content_type] = content_types_found.get(content_type, 0) + 1

                        logger.debug(
                            "Page categorized",
                            page_url=doc.metadata.get('source_name'),
                            categories=len(category_ids),
                            tags=len(tag_ids),
                            content_type=content_type
                        )

                except Exception as e:
                    logger.warning(
                        "Failed to categorize page",
                        page_url=doc.metadata.get('source_name'),
                        error=str(e)
                    )
                    # Continue with other pages even if one fails

            logger.info(
                "Categorization completed",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                categorized_count=categorized_count,
                total_pages=len(documents),
                categories_discovered=len(categories_discovered),
                tags_discovered=len(tags_discovered),
                content_types=content_types_found
            )

        # Ingest into vector store
        if documents:
            logger.info(
                "Ingesting documents into vector store",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                document_count=len(documents)
            )

            # Get a fresh vector database session for the background task
            from ..core.database import get_vector_db
            vector_db = next(get_vector_db())
            vector_service = PgVectorIngestionService(vector_db)
            vector_service.ingest_documents(tenant_id, documents, ingestion_id=ingestion_id)
            vector_db.close()

            # Publish usage event to billing service
            try:
                usage_publisher.publish_website_added(
                    tenant_id=tenant_id,
                    website_id=ingestion_id,
                    url=website_url,
                    pages_scraped=pages_scraped
                )
            except Exception as e:
                # Log error but don't fail the ingestion
                logger.error(f"Failed to publish website usage event: {e}", tenant_id=tenant_id)

            logger.info(
                "✅ Background ingestion completed successfully",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                document_count=len(documents),
                pages_scraped=pages_scraped
            )
        else:
            logger.warning(
                "No documents extracted from website",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id
            )

        # Mark ingestion as completed after ALL processing (scraping + categorization + vector ingestion)
        # This ensures the status is only set to COMPLETED when everything is truly done
        from ..core.database import get_db as get_main_db
        main_db = next(get_main_db())
        try:
            ingestion_record = main_db.query(WebsiteIngestion).filter(
                WebsiteIngestion.id == ingestion_id
            ).first()
            if ingestion_record:
                ingestion_record.status = IngestionStatus.COMPLETED
                ingestion_record.completed_at = datetime.now()
                main_db.commit()
                logger.info(
                    "Ingestion status updated to COMPLETED",
                    tenant_id=tenant_id,
                    ingestion_id=ingestion_id
                )
        finally:
            main_db.close()

    except Exception as e:
        logger.error(
            "❌ Background ingestion failed with exception",
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            website_url=website_url,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )

        # Update ingestion status to failed
        try:
            from ..core.config import settings
            scraper = WebsiteScraper(db)
            ingestion = scraper.get_ingestion_status(tenant_id, ingestion_id)
            if ingestion:
                ingestion.status = IngestionStatus.FAILED
                ingestion.error_message = str(e)
                ingestion.completed_at = datetime.now()
                db.commit()

                logger.info(
                    "Updated ingestion status to FAILED",
                    tenant_id=tenant_id,
                    ingestion_id=ingestion_id
                )
        except Exception as update_error:
            logger.error(
                "Failed to update ingestion status after failure",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                error=str(update_error),
                error_type=type(update_error).__name__,
                exc_info=True
            )
    finally:
        # Always close the database session to prevent connection leaks
        db.close()
        logger.debug(
            "Database session closed",
            tenant_id=tenant_id,
            ingestion_id=ingestion_id
        )


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
