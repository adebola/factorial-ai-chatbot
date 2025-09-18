"""
Advanced document categorization service using hybrid AI + rule-based approach.
"""
import os
import json
import re
import asyncio
from typing import List, Dict, Tuple, Optional
from datetime import datetime

import openai
from langchain.docstore.document import Document
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..models.categorization import (
    DocumentCategory,
    DocumentTag,
    DocumentCategoryAssignment,
    DocumentTagAssignment,
    DocumentClassification
)
from ..core.logging_config import get_logger

logger = get_logger("document_categorization")


class DocumentCategorizationService:
    """
    Hybrid document categorization service that combines:
    1. Fast rule-based classification using keywords and patterns
    2. AI-powered classification using GPT-4 for accuracy
    3. Entity extraction and sentiment analysis
    """

    def __init__(self, db: Session):
        self.db = db
        self.openai_client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.system_categories = self._load_system_categories()

    def _load_system_categories(self) -> Dict[str, Dict]:
        """Load predefined system categories with keywords and patterns."""
        return {
            "Legal": {
                "keywords": [
                    "contract", "agreement", "terms", "liability", "clause", "legal",
                    "whereas", "therefore", "party", "parties", "jurisdiction",
                    "confidentiality", "non-disclosure", "nda", "license", "copyright",
                    "trademark", "patent", "compliance", "regulation", "statute",
                    "amendment", "addendum", "exhibit", "schedule", "appendix"
                ],
                "patterns": [
                    r"\b(whereas|therefore|party|parties|agreement)\b",
                    r"\b(section|clause|subsection)\s+\d+",
                    r"\b(effective date|execution date|termination)\b",
                    r"\bhereby\s+(agree|acknowledge|represent)\b"
                ],
                "subcategories": ["Contracts", "Compliance", "Policies", "Legal Notices"]
            },
            "Financial": {
                "keywords": [
                    "invoice", "payment", "financial", "budget", "revenue", "cost",
                    "expense", "profit", "loss", "balance", "statement", "report",
                    "tax", "accounting", "audit", "fiscal", "quarterly", "annual",
                    "accounts", "payable", "receivable", "cash", "flow", "forecast"
                ],
                "patterns": [
                    r"\$[\d,]+\.?\d*",
                    r"\b(payment|invoice|receipt)\b",
                    r"\b(quarterly|annual)\s+(report|statement)\b",
                    r"\b(net|gross)\s+(income|profit)\b"
                ],
                "subcategories": ["Invoices", "Reports", "Budgets", "Tax Documents"]
            },
            "HR": {
                "keywords": [
                    "employee", "hiring", "policy", "benefits", "payroll", "recruitment",
                    "performance", "review", "evaluation", "training", "development",
                    "onboarding", "termination", "resignation", "vacation", "leave",
                    "handbook", "manual", "personnel", "staff", "team", "manager"
                ],
                "patterns": [
                    r"\b(employee|staff|hr|human resources)\b",
                    r"\b(job description|position)\b",
                    r"\b(annual review|performance evaluation)\b"
                ],
                "subcategories": ["Policies", "Onboarding", "Performance", "Benefits"]
            },
            "Technical": {
                "keywords": [
                    "specification", "manual", "documentation", "technical", "api",
                    "software", "hardware", "system", "architecture", "design",
                    "implementation", "configuration", "installation", "setup",
                    "troubleshooting", "maintenance", "upgrade", "migration"
                ],
                "patterns": [
                    r"\b(api|endpoint|function|method|class)\b",
                    r"\b(version|release)\s+\d+\.\d+",
                    r"\b(install|configure|setup)\b"
                ],
                "subcategories": ["Manuals", "Specifications", "Documentation", "APIs"]
            },
            "Marketing": {
                "keywords": [
                    "marketing", "campaign", "brand", "content", "social", "media",
                    "advertising", "promotion", "strategy", "analysis", "metrics",
                    "conversion", "engagement", "reach", "impression", "click",
                    "email", "newsletter", "blog", "seo", "sem", "ppc"
                ],
                "patterns": [
                    r"\b(campaign|marketing|brand|content)\b",
                    r"\b(click.through|conversion) rate\b",
                    r"\b(social media|email marketing)\b"
                ],
                "subcategories": ["Campaigns", "Content", "Analysis", "Social Media"]
            }
        }

    async def classify_document(
        self,
        document: Document,
        tenant_id: str,
        enable_ai: bool = True
    ) -> DocumentClassification:
        """
        Classify document using hybrid AI + rule-based approach.

        Args:
            document: LangChain document to classify
            tenant_id: Tenant ID for custom categories
            enable_ai: Whether to use AI classification (can be disabled for speed)

        Returns:
            DocumentClassification with categories, tags, and metadata
        """
        logger.info(
            "Starting document classification",
            tenant_id=tenant_id,
            content_length=len(document.page_content),
            enable_ai=enable_ai
        )

        # Extract text content
        content = document.page_content
        content_preview = content[:2000]  # First 2K chars for AI analysis

        try:
            # Step 1: Rule-based classification (fast)
            rule_based_results = self._rule_based_classification(content)
            logger.info(
                "Rule-based classification completed",
                categories_found=len(rule_based_results["categories"]),
                tags_found=len(rule_based_results["tags"])
            )

            # Step 2: AI-powered classification (if enabled)
            ai_results = {}
            if enable_ai and os.environ.get("OPENAI_API_KEY"):
                ai_results = await self._ai_classification(content_preview, tenant_id)
                logger.info(
                    "AI classification completed",
                    ai_categories=len(ai_results.get("categories", [])),
                    content_type=ai_results.get("content_type", "unknown")
                )
            else:
                # Fallback values when AI is disabled
                ai_results = {
                    "categories": [],
                    "tags": [],
                    "content_type": "document",
                    "language": "en",
                    "sentiment": "neutral"
                }

            # Step 3: Combine results
            combined_categories = self._combine_category_results(rule_based_results, ai_results)

            # Step 4: Extract entities (if AI is enabled)
            entities = []
            if enable_ai and os.environ.get("OPENAI_API_KEY"):
                entities = await self._extract_entities(content_preview)

            classification = DocumentClassification(
                categories=combined_categories["categories"],
                tags=combined_categories["tags"],
                content_type=ai_results.get("content_type", "document"),
                language=ai_results.get("language", "en"),
                sentiment=ai_results.get("sentiment", "neutral"),
                key_entities=entities
            )

            logger.info(
                "Document classification completed",
                final_categories=len(classification.categories),
                final_tags=len(classification.tags),
                content_type=classification.content_type
            )

            return classification

        except Exception as e:
            logger.error(
                "Document classification failed",
                error=str(e),
                tenant_id=tenant_id
            )
            # Return basic classification on error
            return DocumentClassification(
                categories=[],
                tags=[],
                content_type="document",
                language="en",
                sentiment="neutral",
                key_entities=[]
            )

    def _rule_based_classification(self, content: str) -> Dict:
        """Fast rule-based classification using keywords and patterns."""
        content_lower = content.lower()
        results = {"categories": [], "tags": []}

        for category_name, category_data in self.system_categories.items():
            score = 0.0
            matches = 0

            # Keyword matching with frequency weighting
            for keyword in category_data["keywords"]:
                if keyword in content_lower:
                    score += 0.1
                    matches += content_lower.count(keyword)

            # Pattern matching with regex
            for pattern in category_data["patterns"]:
                try:
                    pattern_matches = len(re.findall(pattern, content_lower))
                    if pattern_matches > 0:
                        score += 0.2 * min(pattern_matches, 3)  # Cap pattern boost
                except re.error:
                    continue  # Skip invalid patterns

            # Normalize score based on content length and keyword density
            if matches > 0:
                # Adjust score based on keyword density
                keyword_density = matches / len(content_lower.split())
                confidence = min(score * (1 + keyword_density * 10), 1.0)

                if confidence > 0.3:  # Threshold for relevance
                    results["categories"].append({
                        "name": category_name,
                        "confidence": confidence
                    })

                    # Generate tags from matched keywords
                    matched_keywords = [
                        kw for kw in category_data["keywords"]
                        if kw in content_lower
                    ][:3]  # Top 3 matched keywords as tags

                    for keyword in matched_keywords:
                        results["tags"].append({
                            "name": keyword,
                            "confidence": confidence * 0.8  # Tags have slightly lower confidence
                        })

        # Sort by confidence
        results["categories"].sort(key=lambda x: x["confidence"], reverse=True)
        results["tags"].sort(key=lambda x: x["confidence"], reverse=True)

        return results

    async def _ai_classification(self, content: str, tenant_id: str) -> Dict:
        """AI-powered classification using GPT-4."""

        # Get tenant's custom categories
        custom_categories = await self._get_tenant_categories(tenant_id)

        classification_prompt = f"""
        Analyze the following document content and classify it comprehensively:

        Custom Categories Available: {json.dumps(custom_categories)}
        System Categories: {list(self.system_categories.keys())}

        Document Content:
        {content}

        Please provide a JSON response with:
        {{
            "primary_category": "most likely category from the lists above",
            "categories": [
                {{"name": "category_name", "confidence": 0.95}}
            ],
            "tags": [
                {{"name": "tag_name", "confidence": 0.89}}
            ],
            "content_type": "contract|invoice|report|email|presentation|manual|policy|specification|other",
            "language": "en|es|fr|de|pt|other",
            "sentiment": "positive|negative|neutral",
            "summary": "brief summary of document purpose and key topics"
        }}

        Guidelines:
        - confidence should be between 0.0 and 1.0
        - include 1-3 most relevant categories
        - include 3-5 relevant tags that describe key topics
        - be specific about content_type
        - detect document language accurately
        """

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Use gpt-4o-mini which supports JSON mode and is cost-effective
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document classification expert. Analyze documents and provide structured categorization data in JSON format. Be accurate and specific."
                    },
                    {
                        "role": "user",
                        "content": classification_prompt
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=1000,
                temperature=0.1  # Low temperature for consistency
            )

            result = json.loads(response.choices[0].message.content)

            # Validate and clean the response
            return self._validate_ai_response(result)

        except Exception as e:
            logger.error(f"AI classification failed: {e}")
            return {
                "categories": [],
                "tags": [],
                "content_type": "document",
                "language": "en",
                "sentiment": "neutral"
            }

    async def _extract_entities(self, content: str) -> List[str]:
        """Extract key entities using NER."""
        entity_prompt = f"""
        Extract key entities from this document content. Focus on:
        - Company names and organizations
        - Person names and roles
        - Monetary amounts and financial figures
        - Important dates and deadlines
        - Product or service names
        - Location names
        - Technical terms or specifications

        Content: {content}

        Return a JSON object with an "entities" array containing the most important entities:
        {{"entities": ["entity1", "entity2", "entity3"]}}

        Limit to maximum 10 most important entities.
        """

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Use gpt-4o-mini which supports JSON mode
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting key entities from documents. Return only the most important and relevant entities."
                    },
                    {
                        "role": "user",
                        "content": entity_prompt
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
                temperature=0.1
            )

            result = json.loads(response.choices[0].message.content)
            return result.get("entities", [])[:10]  # Limit to 10 entities

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []

    def _combine_category_results(self, rule_based: Dict, ai_results: Dict) -> Dict:
        """Combine rule-based and AI classification results with weighted scoring."""
        combined = {"categories": [], "tags": []}

        # Merge categories with weighted scoring
        category_scores = {}

        # Add rule-based categories (40% weight)
        for cat in rule_based.get("categories", []):
            category_scores[cat["name"]] = cat["confidence"] * 0.4

        # Add AI categories (60% weight)
        for cat in ai_results.get("categories", []):
            existing_score = category_scores.get(cat["name"], 0)
            category_scores[cat["name"]] = existing_score + (cat["confidence"] * 0.6)

        # Convert back to list and filter by minimum threshold
        combined["categories"] = [
            {"name": name, "confidence": min(score, 1.0)}
            for name, score in sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
            if score > 0.4  # Minimum threshold for inclusion
        ][:3]  # Limit to top 3 categories

        # Merge tags similarly
        tag_scores = {}

        # Add rule-based tags (30% weight)
        for tag in rule_based.get("tags", []):
            tag_scores[tag["name"]] = tag["confidence"] * 0.3

        # Add AI tags (70% weight)
        for tag in ai_results.get("tags", []):
            existing_score = tag_scores.get(tag["name"], 0)
            tag_scores[tag["name"]] = existing_score + (tag["confidence"] * 0.7)

        # Convert and filter tags
        combined["tags"] = [
            {"name": name, "confidence": min(score, 1.0)}
            for name, score in sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
            if score > 0.3  # Lower threshold for tags
        ][:5]  # Limit to top 5 tags

        return combined

    async def _get_tenant_categories(self, tenant_id: str) -> List[Dict]:
        """Get custom categories for a tenant."""
        try:
            categories = self.db.execute(
                text("""
                    SELECT name, description
                    FROM document_categories
                    WHERE tenant_id = :tenant_id OR tenant_id = ''
                    ORDER BY is_system_category DESC, name
                """),
                {"tenant_id": tenant_id}
            ).fetchall()

            return [
                {"name": cat.name, "description": cat.description or ""}
                for cat in categories
            ]
        except Exception as e:
            logger.error(f"Failed to get tenant categories: {e}")
            return []

    def _validate_ai_response(self, response: Dict) -> Dict:
        """Validate and clean AI response."""
        # Ensure required fields exist
        validated = {
            "categories": response.get("categories", []),
            "tags": response.get("tags", []),
            "content_type": response.get("content_type", "document"),
            "language": response.get("language", "en"),
            "sentiment": response.get("sentiment", "neutral")
        }

        # Validate confidence scores
        for category in validated["categories"]:
            if "confidence" not in category or not isinstance(category["confidence"], (int, float)):
                category["confidence"] = 0.5
            else:
                category["confidence"] = max(0.0, min(1.0, float(category["confidence"])))

        for tag in validated["tags"]:
            if "confidence" not in tag or not isinstance(tag["confidence"], (int, float)):
                tag["confidence"] = 0.5
            else:
                tag["confidence"] = max(0.0, min(1.0, float(tag["confidence"])))

        return validated

    async def get_or_create_category(
        self,
        tenant_id: str,
        category_name: str,
        description: str = None,
        parent_id: str = None
    ) -> DocumentCategory:
        """Get existing category or create new one."""

        # Try to find existing category
        existing = self.db.query(DocumentCategory).filter(
            DocumentCategory.tenant_id == tenant_id,
            DocumentCategory.name == category_name,
            DocumentCategory.parent_category_id == parent_id
        ).first()

        if existing:
            return existing

        # Create new category
        new_category = DocumentCategory(
            tenant_id=tenant_id,
            name=category_name,
            description=description,
            parent_category_id=parent_id,
            is_system_category=False
        )

        self.db.add(new_category)
        self.db.commit()
        self.db.refresh(new_category)

        logger.info(
            "Created new category",
            tenant_id=tenant_id,
            category_name=category_name,
            category_id=new_category.id
        )

        return new_category

    async def get_or_create_tag(
        self,
        tenant_id: str,
        tag_name: str,
        tag_type: str = "auto"
    ) -> DocumentTag:
        """Get existing tag or create new one."""

        # Try to find existing tag
        existing = self.db.query(DocumentTag).filter(
            DocumentTag.tenant_id == tenant_id,
            DocumentTag.name == tag_name
        ).first()

        if existing:
            # Update usage count
            existing.usage_count += 1
            self.db.commit()
            return existing

        # Create new tag
        new_tag = DocumentTag(
            tenant_id=tenant_id,
            name=tag_name,
            tag_type=tag_type,
            usage_count=1
        )

        self.db.add(new_tag)
        self.db.commit()
        self.db.refresh(new_tag)

        logger.info(
            "Created new tag",
            tenant_id=tenant_id,
            tag_name=tag_name,
            tag_id=new_tag.id
        )

        return new_tag

    async def save_document_classification(
        self,
        document_id: str,
        classification: DocumentClassification,
        tenant_id: str
    ) -> None:
        """Save classification results to database."""

        try:
            # Save categories
            for cat_data in classification.categories:
                category = await self.get_or_create_category(
                    tenant_id,
                    cat_data["name"]
                )

                # Create assignment
                assignment = DocumentCategoryAssignment(
                    document_id=document_id,
                    category_id=category.id,
                    confidence_score=cat_data["confidence"],
                    assigned_by="ai"
                )
                self.db.add(assignment)

            # Save tags
            for tag_data in classification.tags:
                tag = await self.get_or_create_tag(
                    tenant_id,
                    tag_data["name"],
                    "auto"
                )

                assignment = DocumentTagAssignment(
                    document_id=document_id,
                    tag_id=tag.id,
                    confidence_score=tag_data["confidence"],
                    assigned_by="ai"
                )
                self.db.add(assignment)

            self.db.commit()

            logger.info(
                "Saved document classification",
                document_id=document_id,
                categories_saved=len(classification.categories),
                tags_saved=len(classification.tags)
            )

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to save document classification",
                document_id=document_id,
                error=str(e)
            )
            raise

    async def initialize_system_categories(self, tenant_id: str) -> None:
        """Initialize default system categories for a tenant."""

        for category_name, category_data in self.system_categories.items():
            # Check if category already exists
            existing = self.db.query(DocumentCategory).filter(
                DocumentCategory.tenant_id == tenant_id,
                DocumentCategory.name == category_name,
                DocumentCategory.is_system_category == True
            ).first()

            if not existing:
                # Create system category
                system_category = DocumentCategory(
                    tenant_id=tenant_id,
                    name=category_name,
                    description=f"System category for {category_name.lower()} documents",
                    is_system_category=True,
                    color=self._get_category_color(category_name),
                    icon=self._get_category_icon(category_name)
                )
                self.db.add(system_category)

                # Create subcategories
                for subcat_name in category_data["subcategories"]:
                    subcategory = DocumentCategory(
                        tenant_id=tenant_id,
                        name=subcat_name,
                        description=f"{category_name} - {subcat_name}",
                        parent_category_id=system_category.id,
                        is_system_category=True
                    )
                    self.db.add(subcategory)

        self.db.commit()

        logger.info(
            "Initialized system categories",
            tenant_id=tenant_id,
            categories_count=len(self.system_categories)
        )

    def _get_category_color(self, category_name: str) -> str:
        """Get color for system categories."""
        colors = {
            "Legal": "#1E40AF",
            "Financial": "#059669",
            "HR": "#DC2626",
            "Technical": "#7C3AED",
            "Marketing": "#EA580C"
        }
        return colors.get(category_name, "#6B7280")

    def _get_category_icon(self, category_name: str) -> str:
        """Get icon for system categories."""
        icons = {
            "Legal": "legal",
            "Financial": "financial",
            "HR": "users",
            "Technical": "code",
            "Marketing": "megaphone"
        }
        return icons.get(category_name, "document")