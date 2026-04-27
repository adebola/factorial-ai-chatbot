"""
Tool: structured contract analysis.

Retrieves relevant chunks from the workspace, then uses an inner OpenAI call
to produce a structured legal analysis (not the outer agent LLM).
"""
import asyncio
import os
import logging
from typing import Type, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import LegalToolConfig

logger = logging.getLogger(__name__)

ANALYSIS_PROMPTS = {
    "summarize": (
        "You are a Nigerian legal advisor. Summarise the following contract "
        "excerpts. Structure your summary as:\n"
        "1. Parties involved\n"
        "2. Purpose / subject matter\n"
        "3. Key commercial terms (price, payment, duration)\n"
        "4. Governing law and dispute resolution\n"
        "5. Any unusual or noteworthy provisions\n\n"
        "Cite the source document name and page number for every point."
    ),
    "obligations": (
        "You are a Nigerian legal advisor. Extract ALL obligations and "
        "responsibilities from the following contract excerpts. For each "
        "obligation list:\n"
        "- The obligated party\n"
        "- The obligation description\n"
        "- Timeline / deadline (if any)\n"
        "- Consequence of breach (if stated)\n"
        "- Source (document name, page number)\n\n"
        "Organise by party."
    ),
    "risk_flags": (
        "You are a Nigerian legal advisor performing a risk review. Identify "
        "ALL risk flags and potential issues in the following contract excerpts, "
        "including:\n"
        "- One-sided indemnity or limitation clauses\n"
        "- Uncapped liability exposure\n"
        "- Automatic renewal or evergreen clauses\n"
        "- Broad termination rights favouring one party\n"
        "- Non-compete or restrictive covenant scope issues\n"
        "- Deviation from standard Nigerian commercial practice\n"
        "- Missing regulatory compliance provisions (e.g. NDPC, SEC, CBN)\n\n"
        "Rate each flag as HIGH / MEDIUM / LOW risk. Cite source document and page."
    ),
    "missing_clauses": (
        "You are a Nigerian legal advisor. Review the following contract excerpts "
        "and identify clauses that are MISSING or inadequately addressed compared "
        "to standard Nigerian commercial practice, including:\n"
        "- Force majeure\n"
        "- Governing law and jurisdiction\n"
        "- Dispute resolution (arbitration under the Arbitration and Mediation Act 2023)\n"
        "- Data protection (NDPA 2023 / NDPC compliance)\n"
        "- Anti-corruption / compliance\n"
        "- Insurance requirements\n"
        "- Intellectual property ownership\n"
        "- Confidentiality and non-disclosure\n"
        "- Assignment and novation\n"
        "- Severability\n\n"
        "For each missing clause, explain why it matters under Nigerian law and "
        "recommend specific language."
    ),
}


class ContractAnalysisInput(BaseModel):
    """Input for the contract analysis tool."""
    analysis_type: Literal["summarize", "obligations", "risk_flags", "missing_clauses"] = Field(
        description=(
            "Type of analysis to perform: 'summarize' for executive summary, "
            "'obligations' for obligation extraction, 'risk_flags' for risk "
            "assessment, 'missing_clauses' for gap analysis."
        )
    )
    document_name: Optional[str] = Field(
        default=None,
        description=(
            "Optional filename to focus the analysis on a single document. "
            "If omitted, all workspace documents are analysed."
        ),
    )


class ContractAnalysisTool(BaseTool):
    """Perform structured contract analysis using a specialised LLM prompt."""

    name: str = "contract_analysis"
    description: str = (
        "Perform structured legal analysis on contracts in the workspace. "
        "Supported analysis types: summarize, obligations, risk_flags, "
        "missing_clauses. Optionally focus on a specific document by name."
    )
    args_schema: Type[BaseModel] = ContractAnalysisInput
    config: LegalToolConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(
        self,
        analysis_type: str = "summarize",
        document_name: Optional[str] = None,
    ) -> str:
        """Retrieve context and perform LLM analysis."""
        try:
            # Build search query based on analysis type
            search_queries = {
                "summarize": "contract summary parties terms conditions",
                "obligations": "obligations responsibilities duties shall must required",
                "risk_flags": "indemnity liability limitation termination penalty risk",
                "missing_clauses": "force majeure governing law dispute arbitration data protection confidentiality",
            }
            query = search_queries.get(analysis_type, analysis_type)

            if document_name:
                query = f"{document_name} {query}"

            # Retrieve relevant chunks
            from ..services.vector_service import search_workspace

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
                return f"No relevant content found for {analysis_type} analysis."

            # If filtering to a specific document, narrow results
            if document_name:
                filtered = [
                    c for c in chunks
                    if document_name.lower() in c.get("document_name", "").lower()
                ]
                if filtered:
                    chunks = filtered

            # Build context block
            context_parts = []
            for c in chunks:
                page_info = f"page {c['page_number']}" if c.get("page_number") else "page unknown"
                context_parts.append(
                    f"[Source: {c['document_name']}, {page_info}]\n{c['content']}"
                )
            context = "\n\n---\n\n".join(context_parts)

            # Inner LLM call
            system_prompt = ANALYSIS_PROMPTS.get(analysis_type, ANALYSIS_PROMPTS["summarize"])
            from openai import OpenAI

            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Contract excerpts:\n\n{context}"},
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"contract_analysis tool error: {e}")
            return f"Error performing {analysis_type} analysis: {str(e)}"
