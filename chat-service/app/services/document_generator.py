"""Generate PDF, PPTX, or DOCX documents from agent conversation blocks.

Takes structured content blocks stored in AgentMessage.structured_blocks
and renders them into downloadable documents. Falls back to plain text
content when structured_blocks is not available.
"""
import io
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.agent_models import AgentSession, AgentMessage

logger = logging.getLogger(__name__)


class DocumentGenerator:
    """Generate documents from agent conversation sessions."""

    def export_session(
        self,
        db: Session,
        session_id: str,
        format: str,
        message_ids: Optional[List[str]] = None,
    ) -> bytes:
        """
        Export a session (or selected messages) to a document format.

        Args:
            db: Database session
            session_id: Agent session ID
            format: "pdf", "pptx", or "docx"
            message_ids: Optional list of specific message IDs to export.
                         If None, exports all messages in the session.

        Returns:
            Document content as bytes
        """
        session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        query = db.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).order_by(AgentMessage.created_at)

        if message_ids:
            query = query.filter(AgentMessage.id.in_(message_ids))

        messages = query.all()

        if format == "pdf":
            return self._generate_pdf(session, messages)
        elif format == "pptx":
            return self._generate_pptx(session, messages)
        elif format == "docx":
            return self._generate_docx(session, messages)
        else:
            raise ValueError(f"Unsupported format: {format}")

    # ── PDF Generation (ReportLab) ──

    def _generate_pdf(self, session: AgentSession, messages: List[AgentMessage]) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            Preformatted, HRFlowable
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        code_style = ParagraphStyle(
            "CodeBlock", parent=styles["Code"],
            fontSize=8, leading=10,
            backColor=HexColor("#f5f5f5"),
            borderPadding=6,
            spaceBefore=6, spaceAfter=6,
        )
        alert_style = ParagraphStyle(
            "Alert", parent=styles["Normal"],
            fontSize=10, backColor=HexColor("#fff3cd"),
            borderPadding=8,
            spaceBefore=6, spaceAfter=6,
        )
        user_style = ParagraphStyle(
            "UserMessage", parent=styles["Normal"],
            fontSize=10, textColor=HexColor("#1a1a1a"),
            spaceBefore=12, spaceAfter=4,
        )
        assistant_style = ParagraphStyle(
            "AssistantMessage", parent=styles["Normal"],
            fontSize=10, textColor=HexColor("#333333"),
            spaceBefore=4, spaceAfter=12,
        )

        # Title
        story.append(Paragraph(
            f"Agent Session: {session.service_key}",
            styles["Title"]
        ))
        story.append(Paragraph(
            f"Date: {session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else 'N/A'} | "
            f"Tokens used: {session.total_tokens_used or 0}",
            styles["Normal"]
        ))
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%"))
        story.append(Spacer(1, 12))

        for msg in messages:
            # Role header
            role_label = "You" if msg.role == "user" else "Agent"
            role_style = user_style if msg.role == "user" else assistant_style
            story.append(Paragraph(f"<b>{role_label}</b>", role_style))

            blocks = msg.structured_blocks if msg.structured_blocks else None

            if blocks and isinstance(blocks, list):
                for block in blocks:
                    block_type = block.get("type", "text")

                    if block_type == "text":
                        content = self._escape_xml(block.get("content", ""))
                        story.append(Paragraph(content, assistant_style))

                    elif block_type == "table":
                        table_data = block.get("data", {})
                        headers = table_data.get("headers", [])
                        rows = table_data.get("rows", [])
                        if headers and rows:
                            pdf_table = self._build_pdf_table(headers, rows, styles)
                            story.append(pdf_table)

                    elif block_type == "code":
                        code_content = block.get("content", "")
                        lang = block.get("language", "")
                        if lang:
                            story.append(Paragraph(f"<i>{lang}</i>", styles["Italic"]))
                        story.append(Preformatted(code_content[:2000], code_style))

                    elif block_type == "alert":
                        severity = block.get("severity", "info")
                        content = self._escape_xml(block.get("content", ""))
                        prefix = {"error": "ERROR", "warning": "WARNING", "info": "INFO", "success": "OK"}.get(severity, "NOTE")
                        story.append(Paragraph(f"<b>[{prefix}]</b> {content}", alert_style))

                    elif block_type == "chart":
                        story.append(Paragraph("<i>[Chart data — see application for interactive view]</i>", styles["Italic"]))

                    elif block_type == "diagram":
                        story.append(Paragraph("<i>[Diagram — see application for rendered view]</i>", styles["Italic"]))

                    elif block_type == "image":
                        url = block.get("url", "")
                        alt = block.get("alt", "Image")
                        story.append(Paragraph(f"<i>[Image: {self._escape_xml(alt)}]</i>", styles["Italic"]))

                    story.append(Spacer(1, 4))
            else:
                # Plain text fallback
                content = self._escape_xml(msg.content or "")
                story.append(Paragraph(content, role_style))

            story.append(Spacer(1, 8))

        doc.build(story)
        return buffer.getvalue()

    def _build_pdf_table(self, headers, rows, styles):
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib.colors import HexColor
        from reportlab.lib.units import inch

        # Truncate wide tables
        max_cols = 8
        if len(headers) > max_cols:
            headers = headers[:max_cols]
            rows = [r[:max_cols] for r in rows]

        # Truncate long cell values
        def truncate_cell(val):
            s = str(val) if val is not None else ""
            return s[:80] + "..." if len(s) > 80 else s

        table_data = [[truncate_cell(h) for h in headers]]
        for row in rows[:30]:  # Cap at 30 rows
            table_data.append([truncate_cell(v) for v in row])

        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2B55FF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F8F8F8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    # ── DOCX Generation (python-docx) ──

    def _generate_docx(self, session: AgentSession, messages: List[AgentMessage]) -> bytes:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # Title
        title = doc.add_heading(f"Agent Session: {session.service_key}", level=1)
        doc.add_paragraph(
            f"Date: {session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else 'N/A'} | "
            f"Tokens used: {session.total_tokens_used or 0}"
        )
        doc.add_paragraph("")  # spacer

        for msg in messages:
            role_label = "You" if msg.role == "user" else "Agent"
            p = doc.add_paragraph()
            run = p.add_run(f"{role_label}: ")
            run.bold = True
            if msg.role == "user":
                run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
            else:
                run.font.color.rgb = RGBColor(0x2B, 0x55, 0xFF)

            blocks = msg.structured_blocks if msg.structured_blocks else None

            if blocks and isinstance(blocks, list):
                for block in blocks:
                    block_type = block.get("type", "text")

                    if block_type == "text":
                        doc.add_paragraph(block.get("content", ""))

                    elif block_type == "table":
                        table_data = block.get("data", {})
                        headers = table_data.get("headers", [])
                        rows = table_data.get("rows", [])
                        if headers and rows:
                            self._add_docx_table(doc, headers, rows)

                    elif block_type == "code":
                        lang = block.get("language", "")
                        code_content = block.get("content", "")[:2000]
                        if lang:
                            doc.add_paragraph(f"[{lang}]", style="Caption")
                        p = doc.add_paragraph()
                        run = p.add_run(code_content)
                        run.font.name = "Courier New"
                        run.font.size = Pt(8)

                    elif block_type == "alert":
                        severity = block.get("severity", "info")
                        content = block.get("content", "")
                        prefix = {"error": "ERROR", "warning": "WARNING", "info": "INFO"}.get(severity, "NOTE")
                        p = doc.add_paragraph()
                        run = p.add_run(f"[{prefix}] {content}")
                        run.bold = True
                        if severity == "error":
                            run.font.color.rgb = RGBColor(0xDC, 0x35, 0x45)
                        elif severity == "warning":
                            run.font.color.rgb = RGBColor(0xFF, 0xA5, 0x00)

                    elif block_type in ("chart", "diagram", "image"):
                        alt = block.get("alt", block_type.capitalize())
                        doc.add_paragraph(f"[{alt} — see application for rendered view]", style="Caption")
            else:
                doc.add_paragraph(msg.content or "")

        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    def _add_docx_table(self, doc, headers, rows):
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        max_cols = 8
        if len(headers) > max_cols:
            headers = headers[:max_cols]
            rows = [r[:max_cols] for r in rows]

        table = doc.add_table(rows=1 + min(len(rows), 30), cols=len(headers))
        table.style = "Table Grid"

        # Header row
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = str(header)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(9)

        # Data rows
        for row_idx, row in enumerate(rows[:30]):
            for col_idx, val in enumerate(row[:len(headers)]):
                cell = table.rows[row_idx + 1].cells[col_idx]
                cell.text = str(val)[:80] if val is not None else ""
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(8)

    # ── PPTX Generation (python-pptx) ──

    def _generate_pptx(self, session: AgentSession, messages: List[AgentMessage]) -> bytes:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Title slide
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = f"Agent Session: {session.service_key}"
        slide.placeholders[1].text = (
            f"Date: {session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else 'N/A'}\n"
            f"Tokens used: {session.total_tokens_used or 0}"
        )

        # Generate content slides from messages
        for msg in messages:
            if msg.role == "system":
                continue

            blocks = msg.structured_blocks if msg.structured_blocks else None
            role_label = "You" if msg.role == "user" else "Agent"

            if blocks and isinstance(blocks, list):
                for block in blocks:
                    block_type = block.get("type", "text")

                    if block_type == "text":
                        content = block.get("content", "")
                        if not content.strip():
                            continue
                        slide = prs.slides.add_slide(prs.slide_layouts[1])
                        slide.shapes.title.text = role_label
                        slide.placeholders[1].text = content[:1500]

                    elif block_type == "table":
                        table_data = block.get("data", {})
                        headers = table_data.get("headers", [])
                        rows = table_data.get("rows", [])
                        if headers and rows:
                            self._add_pptx_table_slide(prs, role_label, headers, rows)

                    elif block_type == "code":
                        code = block.get("content", "")[:1500]
                        lang = block.get("language", "")
                        slide = prs.slides.add_slide(prs.slide_layouts[1])
                        slide.shapes.title.text = f"{role_label} — {lang}" if lang else role_label
                        tf = slide.placeholders[1].text_frame
                        tf.text = code
                        for paragraph in tf.paragraphs:
                            for run in paragraph.runs:
                                run.font.name = "Courier New"
                                run.font.size = Pt(10)

                    elif block_type == "alert":
                        content = block.get("content", "")
                        severity = block.get("severity", "info")
                        slide = prs.slides.add_slide(prs.slide_layouts[1])
                        slide.shapes.title.text = f"Alert ({severity.upper()})"
                        slide.placeholders[1].text = content

                    elif block_type in ("chart", "diagram", "image"):
                        slide = prs.slides.add_slide(prs.slide_layouts[1])
                        slide.shapes.title.text = role_label
                        slide.placeholders[1].text = f"[{block_type.capitalize()} — see application for interactive view]"
            else:
                # Plain text message → single slide
                content = msg.content or ""
                if not content.strip():
                    continue
                slide = prs.slides.add_slide(prs.slide_layouts[1])
                slide.shapes.title.text = role_label
                slide.placeholders[1].text = content[:1500]

        buffer = io.BytesIO()
        prs.save(buffer)
        return buffer.getvalue()

    def _add_pptx_table_slide(self, prs, title, headers, rows):
        from pptx.util import Inches, Pt

        max_cols = 6
        if len(headers) > max_cols:
            headers = headers[:max_cols]
            rows = [r[:max_cols] for r in rows]
        max_rows = 15
        rows = rows[:max_rows]

        slide = prs.slides.add_slide(prs.slide_layouts[5])  # Blank layout
        # Add title manually
        from pptx.util import Emu
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.6))
        tf = txBox.text_frame
        tf.text = title
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True

        # Add table
        num_rows = len(rows) + 1
        num_cols = len(headers)
        left = Inches(0.5)
        top = Inches(1.2)
        width = Inches(12)
        height = Inches(0.4 * num_rows)
        table = slide.shapes.add_table(num_rows, num_cols, left, top, width, height).table

        # Header
        for i, h in enumerate(headers):
            table.cell(0, i).text = str(h)

        # Data
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row[:num_cols]):
                cell_text = str(val)[:60] if val is not None else ""
                table.cell(r_idx + 1, c_idx).text = cell_text

    # ── Utilities ──

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters for ReportLab Paragraphs."""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


# Module-level singleton
document_generator = DocumentGenerator()
