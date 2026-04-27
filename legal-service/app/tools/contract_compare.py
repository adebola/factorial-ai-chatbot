"""
Tool: compare two documents and highlight material differences.
"""
import asyncio
import os
import logging
from typing import Type

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import LegalToolConfig

logger = logging.getLogger(__name__)

COMPARISON_PROMPT = (
    "You are a Nigerian legal advisor. Compare the following excerpts from "
    "two different documents and produce a structured comparison covering:\n\n"
    "1. **Parties** — are the parties the same or different?\n"
    "2. **Subject matter** — what does each document cover?\n"
    "3. **Key commercial terms** — price, payment terms, duration, renewal\n"
    "4. **Obligations** — material differences in obligations\n"
    "5. **Liability & indemnity** — differences in risk allocation\n"
    "6. **Termination** — different termination rights or notice periods\n"
    "7. **Governing law & dispute resolution** — any divergence\n"
    "8. **Other material differences** — any clauses present in one but "
    "absent from the other\n\n"
    "For every difference, cite the source document name and page number. "
    "Highlight which differences are legally significant under Nigerian law."
)


class ContractCompareInput(BaseModel):
    """Input for the contract comparison tool."""
    document_name_a: str = Field(
        description="Filename of the first document to compare."
    )
    document_name_b: str = Field(
        description="Filename of the second document to compare."
    )


class ContractCompareTool(BaseTool):
    """Compare two documents and surface material differences."""

    name: str = "contract_compare"
    description: str = (
        "Compare two documents side-by-side and identify material differences "
        "in terms, obligations, risk allocation, and other provisions. "
        "Provide the exact filenames of both documents."
    )
    args_schema: Type[BaseModel] = ContractCompareInput
    config: LegalToolConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, document_name_a: str, document_name_b: str) -> str:
        """Retrieve chunks for both documents and compare via LLM."""
        try:
            from ..services.vector_service import search_workspace

            def _search(query: str):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            return pool.submit(
                                asyncio.run,
                                search_workspace(
                                    tenant_id=self.config.tenant_id,
                                    workspace_id=self.config.workspace_id,
                                    query=query,
                                    k=15,
                                ),
                            ).result()
                    else:
                        return loop.run_until_complete(
                            search_workspace(
                                tenant_id=self.config.tenant_id,
                                workspace_id=self.config.workspace_id,
                                query=query,
                                k=15,
                            )
                        )
                except RuntimeError:
                    return asyncio.run(
                        search_workspace(
                            tenant_id=self.config.tenant_id,
                            workspace_id=self.config.workspace_id,
                            query=query,
                            k=15,
                        )
                    )

            # Retrieve chunks for both documents
            chunks_a = _search(f"{document_name_a} terms obligations parties")
            chunks_b = _search(f"{document_name_b} terms obligations parties")

            # Filter to target documents
            filtered_a = [
                c for c in (chunks_a or [])
                if document_name_a.lower() in c.get("document_name", "").lower()
            ]
            filtered_b = [
                c for c in (chunks_b or [])
                if document_name_b.lower() in c.get("document_name", "").lower()
            ]

            if not filtered_a and not filtered_b:
                return (
                    f"Could not find content for either document. "
                    f"Searched for '{document_name_a}' and '{document_name_b}'."
                )
            if not filtered_a:
                return f"No content found for document: {document_name_a}"
            if not filtered_b:
                return f"No content found for document: {document_name_b}"

            # Build context for each document
            def _format_chunks(chunks, label):
                parts = []
                for c in chunks:
                    page_info = f"page {c['page_number']}" if c.get("page_number") else "page unknown"
                    parts.append(
                        f"[Source: {c['document_name']}, {page_info}]\n{c['content']}"
                    )
                return f"=== {label} ===\n\n" + "\n\n---\n\n".join(parts)

            context_a = _format_chunks(filtered_a, document_name_a)
            context_b = _format_chunks(filtered_b, document_name_b)
            full_context = f"{context_a}\n\n{'=' * 60}\n\n{context_b}"

            # Inner LLM call
            from openai import OpenAI

            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": COMPARISON_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Compare these two documents:\n\n{full_context}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"contract_compare tool error: {e}")
            return f"Error comparing documents: {str(e)}"
