from fastapi import APIRouter

router = APIRouter()

_MANIFEST = {
    "service_key": "legal",
    "name": "Legal & Professional Services",
    "version": "1.0.0",
    "category": "agentic",
    "description": "AI-powered legal intelligence for Nigerian legal practice — contract analysis, legal research, document drafting, due diligence, regulatory compliance, litigation support, and knowledge management.",
    "capabilities": {
        "contract_intelligence": True,
        "workspaces": True,
        "document_upload": True,
    },
    "triggers": [
        "contract", "legal", "clause", "nda", "agreement",
        "cama", "indemnity", "liability", "obligation",
        "termination", "governing law", "force majeure",
        "due diligence", "compliance", "litigation",
        "lawyer", "solicitor", "barrister", "court",
        "statute", "regulation", "circular", "gazette",
    ],
    "ui_extensions": [],
    "settings_schema": None,
}

@router.get("/manifest")
async def get_manifest():
    return _MANIFEST
