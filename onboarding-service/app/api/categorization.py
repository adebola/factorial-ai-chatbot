"""
Document categorization and tagging API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from ..core.database import get_db, get_vector_db
from ..services.document_categorization import DocumentCategorizationService
from ..services.categorized_vector_store import CategorizedVectorStore
from ..services.dependencies import validate_token, TokenClaims
from ..models.categorization import (
    DocumentCategory,
    DocumentTag,
    CategoryCreateRequest,
    TagCreateRequest,
    DocumentClassificationRequest,
    DocumentCategoryResponse,
    DocumentTagResponse,
    CategoryStatistics,
    DocumentSearchFilters
)

router = APIRouter()


@router.post("/categories/")
async def create_category(
    category_data: CategoryCreateRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> DocumentCategoryResponse:
    """Create a new document category."""

    try:
        categorization_service = DocumentCategorizationService(db)

        category = await categorization_service.get_or_create_category(
            tenant_id=claims.tenant_id,
            category_name=category_data.name,
            description=category_data.description,
            parent_id=category_data.parent_category_id
        )

        # Update additional fields if provided
        if category_data.color:
            category.color = category_data.color
        if category_data.icon:
            category.icon = category_data.icon

        db.commit()
        db.refresh(category)

        return DocumentCategoryResponse.from_orm(category)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create category: {str(e)}"
        )


@router.get("/categories/")
async def list_categories(
    include_stats: bool = Query(False, description="Include document count statistics"),
    parent_id: Optional[str] = Query(None, description="Filter by parent category ID"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all categories for the tenant with optional statistics."""

    try:
        query = db.query(DocumentCategory).filter(
            DocumentCategory.tenant_id == claims.tenant_id
        )

        if parent_id is not None:
            query = query.filter(DocumentCategory.parent_category_id == parent_id)

        categories = query.order_by(
            DocumentCategory.is_system_category.desc(),
            DocumentCategory.name
        ).all()

        result = {
            "categories": [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "description": cat.description,
                    "parent_category_id": cat.parent_category_id,
                    "color": cat.color,
                    "icon": cat.icon,
                    "is_system_category": cat.is_system_category,
                    "created_at": cat.created_at.isoformat(),
                    "document_count": len(cat.document_assignments) if include_stats else None
                }
                for cat in categories
            ],
            "total_count": len(categories)
        }

        # Add statistics if requested
        if include_stats:
            vector_store = CategorizedVectorStore(next(get_vector_db()), db)
            stats = vector_store.get_category_statistics(claims.tenant_id)
            result["statistics"] = stats

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list categories: {str(e)}"
        )


@router.put("/categories/{category_id}")
async def update_category(
    category_id: str,
    category_data: CategoryCreateRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> DocumentCategoryResponse:
    """Update an existing category."""

    try:
        category = db.query(DocumentCategory).filter(
            DocumentCategory.id == category_id,
            DocumentCategory.tenant_id == claims.tenant_id
        ).first()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )

        # Prevent updating system categories
        if category.is_system_category:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update system categories"
            )

        # Update fields
        category.name = category_data.name
        category.description = category_data.description
        category.parent_category_id = category_data.parent_category_id
        category.color = category_data.color
        category.icon = category_data.icon

        db.commit()
        db.refresh(category)

        return DocumentCategoryResponse.from_orm(category)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update category: {str(e)}"
        )


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete a category (only custom categories can be deleted)."""

    try:
        category = db.query(DocumentCategory).filter(
            DocumentCategory.id == category_id,
            DocumentCategory.tenant_id == claims.tenant_id
        ).first()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )

        if category.is_system_category:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete system categories"
            )

        # Check for subcategories
        subcategories = db.query(DocumentCategory).filter(
            DocumentCategory.parent_category_id == category_id
        ).count()

        if subcategories > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete category with subcategories"
            )

        db.delete(category)
        db.commit()

        return {
            "message": "Category deleted successfully",
            "category_id": category_id,
            "category_name": category.name
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete category: {str(e)}"
        )


@router.post("/tags/")
async def create_tag(
    tag_data: TagCreateRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> DocumentTagResponse:
    """Create a new document tag."""

    try:
        categorization_service = DocumentCategorizationService(db)

        tag = await categorization_service.get_or_create_tag(
            tenant_id=claims.tenant_id,
            tag_name=tag_data.name,
            tag_type=tag_data.tag_type
        )

        return DocumentTagResponse.from_orm(tag)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tag: {str(e)}"
        )


@router.get("/tags/")
async def list_tags(
    tag_type: Optional[str] = Query(None, description="Filter by tag type"),
    limit: int = Query(50, description="Maximum number of tags to return"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all tags for the tenant."""

    try:
        query = db.query(DocumentTag).filter(
            DocumentTag.tenant_id == claims.tenant_id
        )

        if tag_type:
            query = query.filter(DocumentTag.tag_type == tag_type)

        tags = query.order_by(
            DocumentTag.usage_count.desc(),
            DocumentTag.name
        ).limit(limit).all()

        # Get tag statistics
        vector_store = CategorizedVectorStore(next(get_vector_db()), db)
        tag_stats = vector_store.get_tag_statistics(claims.tenant_id, limit)

        return {
            "tags": [
                {
                    "id": tag.id,
                    "name": tag.name,
                    "tag_type": tag.tag_type,
                    "usage_count": tag.usage_count,
                    "created_at": tag.created_at.isoformat()
                }
                for tag in tags
            ],
            "total_count": len(tags),
            "statistics": tag_stats
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tags: {str(e)}"
        )


@router.post("/documents/{document_id}/classify")
async def classify_document(
    document_id: str,
    classification_request: DocumentClassificationRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Manually classify a document with categories and tags."""

    try:
        # Verify document exists and belongs to tenant
        from ..models.tenant import Document as DocumentModel
        document = db.query(DocumentModel).filter(
            DocumentModel.id == document_id,
            DocumentModel.tenant_id == claims.tenant_id
        ).first()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        categorization_service = DocumentCategorizationService(db)

        # Process user-provided categories
        if classification_request.categories:
            for cat_name in classification_request.categories:
                category = await categorization_service.get_or_create_category(
                    claims.tenant_id, cat_name
                )

                # Create or update assignment
                from ..models.categorization import DocumentCategoryAssignment
                existing = db.query(DocumentCategoryAssignment).filter(
                    DocumentCategoryAssignment.document_id == document_id,
                    DocumentCategoryAssignment.category_id == category.id
                ).first()

                if not existing:
                    assignment = DocumentCategoryAssignment(
                        document_id=document_id,
                        category_id=category.id,
                        confidence_score=1.0,
                        assigned_by="user"
                    )
                    db.add(assignment)

        # Process user-provided tags
        if classification_request.tags:
            for tag_name in classification_request.tags:
                tag = await categorization_service.get_or_create_tag(
                    claims.tenant_id, tag_name, "custom"
                )

                # Create or update assignment
                from ..models.categorization import DocumentTagAssignment
                existing = db.query(DocumentTagAssignment).filter(
                    DocumentTagAssignment.document_id == document_id,
                    DocumentTagAssignment.tag_id == tag.id
                ).first()

                if not existing:
                    assignment = DocumentTagAssignment(
                        document_id=document_id,
                        tag_id=tag.id,
                        confidence_score=1.0,
                        assigned_by="user"
                    )
                    db.add(assignment)

        # Run auto-categorization if requested
        ai_classification = None
        if classification_request.auto_categorize:
            # Get document content for AI classification
            from ..services.storage_service import StorageService
            from langchain.docstore.document import Document

            storage_service = StorageService()
            file_content = storage_service.download_file(document.file_path)

            # Extract text (simplified)
            content_text = file_content.decode('utf-8', errors='ignore')[:4000]
            doc = Document(page_content=content_text)

            ai_classification = await categorization_service.classify_document(
                doc, claims.tenant_id, enable_ai=True
            )

            # Save AI classification
            await categorization_service.save_document_classification(
                document_id, ai_classification, claims.tenant_id
            )

        db.commit()

        # Update vector chunks with new categorization
        vector_store = CategorizedVectorStore(next(get_vector_db()), db)

        # Get all category and tag IDs for this document
        category_ids = [
            str(assignment.category_id) for assignment in
            db.query(DocumentCategoryAssignment).filter(
                DocumentCategoryAssignment.document_id == document_id
            ).all()
        ]

        tag_ids = [
            str(assignment.tag_id) for assignment in
            db.query(DocumentTagAssignment).filter(
                DocumentTagAssignment.document_id == document_id
            ).all()
        ]

        # Update vector chunks
        vector_store.bulk_update_chunk_categories(
            claims.tenant_id, document_id, category_ids, tag_ids
        )

        return {
            "message": "Document classified successfully",
            "document_id": document_id,
            "user_categories": classification_request.categories or [],
            "user_tags": classification_request.tags or [],
            "ai_classification": {
                "categories": ai_classification.categories if ai_classification else [],
                "tags": ai_classification.tags if ai_classification else [],
                "content_type": ai_classification.content_type if ai_classification else None
            } if ai_classification else None,
            "total_categories": len(category_ids),
            "total_tags": len(tag_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to classify document: {str(e)}"
        )


@router.get("/documents/search")
async def search_documents_by_category(
    q: str = Query(..., description="Search query"),
    categories: Optional[List[str]] = Query(None, description="Filter by category names"),
    tags: Optional[List[str]] = Query(None, description="Filter by tag names"),
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    limit: int = Query(10, le=50, description="Maximum number of results"),
    claims: TokenClaims = Depends(validate_token),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Advanced document search with category and tag filtering."""

    try:
        vector_store = CategorizedVectorStore(vector_db, db)

        results = vector_store.search_by_category(
            tenant_id=claims.tenant_id,
            query=q,
            categories=categories,
            tags=tags,
            content_type=content_type,
            k=limit
        )

        return {
            "query": q,
            "filters": {
                "categories": categories,
                "tags": tags,
                "content_type": content_type
            },
            "results": [
                {
                    "content": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                    "metadata": doc.metadata,
                    "relevance_score": 1 - doc.metadata.get("distance", 1),
                    "similarity": doc.metadata.get("similarity", 0)
                }
                for doc in results
            ],
            "total_results": len(results)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search documents: {str(e)}"
        )


@router.get("/analytics/categories")
async def get_category_analytics(
    claims: TokenClaims = Depends(validate_token),
    vector_db: Session = Depends(get_vector_db)
) -> Dict[str, Any]:
    """Get comprehensive category analytics and performance metrics."""

    try:
        vector_store = CategorizedVectorStore(vector_db, db)

        # Get category statistics
        category_stats = vector_store.get_category_statistics(claims.tenant_id)

        # Get performance metrics
        performance_metrics = vector_store.get_search_performance_metrics(claims.tenant_id)

        # Get tag statistics
        tag_stats = vector_store.get_tag_statistics(claims.tenant_id)

        return {
            "category_statistics": category_stats,
            "performance_metrics": performance_metrics,
            "tag_statistics": tag_stats,
            "summary": {
                "total_categories": category_stats.get("total_categories", 0),
                "total_tags": tag_stats.get("total_tags", 0),
                "total_documents": performance_metrics.get("overall_stats", {}).get("total_documents", 0),
                "total_chunks": performance_metrics.get("overall_stats", {}).get("total_chunks", 0)
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analytics: {str(e)}"
        )


@router.post("/setup/initialize")
async def initialize_system_categories(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Initialize default system categories for the tenant."""

    try:
        categorization_service = DocumentCategorizationService(db)

        await categorization_service.initialize_system_categories(claims.tenant_id)

        return {
            "message": "System categories initialized successfully",
            "tenant_id": claims.tenant_id
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize system categories: {str(e)}"
        )