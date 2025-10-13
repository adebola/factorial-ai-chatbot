from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services.dependencies import TokenClaims, validate_token, validate_token_or_api_key
from ..services.trigger_detector import TriggerDetector
from ..schemas.workflow_schema import TriggerCheckRequest, TriggerCheckResponse

router = APIRouter()


@router.post("/check", response_model=TriggerCheckResponse)
async def check_triggers(
    request: TriggerCheckRequest,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token_or_api_key)
):
    """Check if a message should trigger any workflows

    This endpoint is called by the chat service to determine
    if a user message should start a workflow.

    Authentication: Accepts either JWT Bearer token OR X-API-Key header
    """
    try:
        detector = TriggerDetector(db)
        return await detector.check_triggers(
            tenant_id=claims.tenant_id,
            message=request.message,
            session_id=request.session_id,
            user_context=request.user_context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}/test", response_model=TriggerCheckResponse)
async def test_workflow_trigger(
    workflow_id: str,
    message: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Test if a specific workflow would be triggered by a message"""
    try:
        detector = TriggerDetector(db)
        return await detector.test_workflow_trigger(
            workflow_id=workflow_id,
            tenant_id=claims.tenant_id,
            message=message
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def get_trigger_analytics(
    days: int = 30,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Get trigger analytics for the tenant"""
    try:
        detector = TriggerDetector(db)
        return detector.get_trigger_analytics(claims.tenant_id, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-check")
async def bulk_check_triggers(
    messages: list[str],
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Bulk check multiple messages for trigger detection"""
    try:
        detector = TriggerDetector(db)
        results = []

        for i, message in enumerate(messages):
            session_id = f"bulk_test_{i}"
            result = await detector.check_triggers(
                tenant_id=claims.tenant_id,
                message=message,
                session_id=session_id
            )
            results.append({
                "message": message,
                "triggered": result.triggered,
                "workflow_id": result.workflow_id,
                "workflow_name": result.workflow_name,
                "confidence": result.confidence
            })

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))