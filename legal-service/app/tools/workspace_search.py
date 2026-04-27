"""
Tool: RAG similarity search scoped to the active workspace.

Uses the vector_service to find relevant document chunks, then formats
results with document attribution for the LLM.
"""
import asyncio
import logging
from typing import Type

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import LegalToolConfig

logger = logging.getLogger(__name__)


class WorkspaceSearchInput(BaseModel):
    """Input for workspace similarity search."""
    query: str = Field(
        description="The search query — a natural-language question or topic."
    )


class WorkspaceSearchTool(BaseTool):
    """Perform RAG similarity search across all documents in the workspace."""

    name: str = "workspace_search"
    description: str = (
        "Search across all documents in the current workspace using semantic "
        "similarity. Returns the most relevant passages with source document "
        "attribution (filename and page number). Use this for general legal "
        "questions or when you need to find specific clauses, terms, or provisions."
    )
    args_schema: Type[BaseModel] = WorkspaceSearchInput
    config: LegalToolConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, query: str) -> str:
        """Search workspace vectors and return formatted results."""
        try:
            from ..services.vector_service import search_workspace

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        results = pool.submit(
                            asyncio.run,
                            search_workspace(
                                tenant_id=self.config.tenant_id,
                                workspace_id=self.config.workspace_id,
                                query=query,
                                k=10,
                            ),
                        ).result()
                else:
                    results = loop.run_until_complete(
                        search_workspace(
                            tenant_id=self.config.tenant_id,
                            workspace_id=self.config.workspace_id,
                            query=query,
                            k=10,
                        )
                    )
            except RuntimeError:
                results = asyncio.run(
                    search_workspace(
                        tenant_id=self.config.tenant_id,
                        workspace_id=self.config.workspace_id,
                        query=query,
                        k=10,
                    )
                )

            if not results:
                return f"No relevant results found for query: {query}"

            lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                page_info = f"page {r['page_number']}" if r.get("page_number") else "page unknown"
                lines.append(
                    f"[{i}] Source: {r['document_name']} ({page_info})\n"
                    f"{r['content']}\n"
                )
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"workspace_search tool error: {e}")
            return f"Error searching workspace: {str(e)}"
