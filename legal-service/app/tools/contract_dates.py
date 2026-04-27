"""
Tool: extract dates, deadlines, and notice periods from a document.
"""
import asyncio
import os
import logging
from typing import Type

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import LegalToolConfig

logger = logging.getLogger(__name__)

DATE_EXTRACTION_PROMPT = (
    "You are a Nigerian legal advisor. Extract ALL dates, deadlines, notice "
    "periods, renewal dates, expiry dates, and time-bound obligations from "
    "the following contract excerpts.\n\n"
    "For each item provide:\n"
    "- Date or period (exact date if stated, or relative period e.g. '30 days after execution')\n"
    "- Event or obligation it relates to\n"
    "- Consequence of missing the date (if stated)\n"
    "- Source (document name, page number)\n\n"
    "Present the results as a chronological timeline where possible. "
    "Flag any dates that have already passed or are approaching within 30 days."
)


class ContractDatesInput(BaseModel):
    """Input for the contract dates extraction tool."""
    document_name: str = Field(
        description="Filename of the document to extract dates from."
    )


class ContractDatesTool(BaseTool):
    """Extract all dates, deadlines, and notice periods from a specific document."""

    name: str = "contract_dates"
    description: str = (
        "Extract a structured timeline of all dates, deadlines, renewal dates, "
        "notice periods, and time-bound obligations from a specific document. "
        "Provide the exact document filename."
    )
    args_schema: Type[BaseModel] = ContractDatesInput
    config: LegalToolConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, document_name: str) -> str:
        """Retrieve document chunks and extract dates via LLM."""
        try:
            from ..services.vector_service import search_workspace

            query = f"{document_name} date deadline expiry renewal notice period commencement termination"

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        chunks = pool.submit(
                            asyncio.run,
                            search_workspace(
                                tenant_id=self.config.tenant_id,
                                workspace_id=self.config.workspace_id,
                                query=query,
                                k=15,
                            ),
                        ).result()
                else:
                    chunks = loop.run_until_complete(
                        search_workspace(
                            tenant_id=self.config.tenant_id,
                            workspace_id=self.config.workspace_id,
                            query=query,
                            k=15,
                        )
                    )
            except RuntimeError:
                chunks = asyncio.run(
                    search_workspace(
                        tenant_id=self.config.tenant_id,
                        workspace_id=self.config.workspace_id,
                        query=query,
                        k=15,
                    )
                )

            if not chunks:
                return f"No content found for document: {document_name}"

            # Filter to the target document
            filtered = [
                c for c in chunks
                if document_name.lower() in c.get("document_name", "").lower()
            ]
            if not filtered:
                return (
                    f"No chunks matched document '{document_name}'. "
                    f"Available documents in results: "
                    f"{', '.join(set(c.get('document_name', '?') for c in chunks))}"
                )

            # Build context
            context_parts = []
            for c in filtered:
                page_info = f"page {c['page_number']}" if c.get("page_number") else "page unknown"
                context_parts.append(
                    f"[Source: {c['document_name']}, {page_info}]\n{c['content']}"
                )
            context = "\n\n---\n\n".join(context_parts)

            # Inner LLM call
            from openai import OpenAI

            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": DATE_EXTRACTION_PROMPT},
                    {
                        "role": "user",
                        "content": f"Extract all dates and deadlines from this document:\n\n{context}",
                    },
                ],
                temperature=0.1,
                max_tokens=3000,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"contract_dates tool error: {e}")
            return f"Error extracting dates from '{document_name}': {str(e)}"
