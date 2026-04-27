"""
Tool: list documents in the active workspace.

The LLM should call this first to discover available documents before
performing analysis or search.
"""
import logging
from typing import Type

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import LegalToolConfig
from ..core.database import SessionLocal
from ..models.document import Document
from ..models.workspace import WorkspaceDocument

logger = logging.getLogger(__name__)


class DocumentListInput(BaseModel):
    """No additional parameters required — lists all active workspace documents."""
    pass


class DocumentListTool(BaseTool):
    """List all documents currently in the active workspace."""

    name: str = "document_list"
    description: str = (
        "Lists every document in the current workspace with filename, type, "
        "page count, processing status, and upload date. Call this FIRST to "
        "discover what documents are available before analysing or searching."
    )
    args_schema: Type[BaseModel] = DocumentListInput
    config: LegalToolConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, **kwargs) -> str:
        """Return a formatted list of workspace documents."""
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(Document)
                    .join(
                        WorkspaceDocument,
                        WorkspaceDocument.document_id == Document.id,
                    )
                    .filter(
                        WorkspaceDocument.workspace_id == self.config.workspace_id,
                        WorkspaceDocument.removed_at.is_(None),
                        Document.is_deleted == False,
                    )
                    .all()
                )

                if not rows:
                    return "No documents found in this workspace."

                lines = [f"Documents in workspace ({len(rows)} total):"]
                for doc in rows:
                    uploaded = (
                        doc.uploaded_at.strftime("%Y-%m-%d")
                        if doc.uploaded_at
                        else "unknown"
                    )
                    pages = doc.page_count if doc.page_count else "?"
                    lines.append(
                        f"- {doc.original_filename} "
                        f"(type={doc.file_type}, pages={pages}, "
                        f"status={doc.processing_status}, uploaded={uploaded})"
                    )
                return "\n".join(lines)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"document_list tool error: {e}")
            return f"Error listing documents: {str(e)}"
