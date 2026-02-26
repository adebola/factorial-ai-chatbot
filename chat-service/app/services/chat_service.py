import asyncio
import time
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional
import redis
import json
import os
from openai import OpenAI

from ..core.config import settings
from ..models.chat_models import ChatMessage
from .vector_store import TenantVectorStore
from .tenant_client import TenantClient
from ..core.logging_config import (
    get_logger,
    log_chat_message,
    log_ai_generation,
    log_vector_search,
    log_tenant_operation
)
from .event_publisher import event_publisher


class ChatService:
    """Handles AI chat responses with RAG and memory using a direct OpenAI client"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("chat_service")
        
        # Get OpenAI API key with validation
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        
        self.openai_client = OpenAI(api_key=openai_api_key, timeout=60.0, max_retries=2)
        self.vector_store = TenantVectorStore()
        self.redis_client = redis.from_url(os.environ["REDIS_URL"])
        self.tenant_client = TenantClient()
        
        # System prompt template
        self.system_prompt = """You are a helpful AI assistant for {company_name}.
        You have access to the company's documents and website content to answer questions accurately.

        Use the following context information to answer the user's question:
        {context}

        Guidelines:
        - Answer based on the provided context when possible
        - When the context contains specific items (job listings, services, products, events, etc.), enumerate and list them with their details rather than giving a generic summary
        - Always cite specific details, names, requirements, and facts found in the context
        - If you truly cannot find relevant information in the context, say so politely
        - Be conversational and helpful
        - Never say information is unavailable if the context contains relevant details, even if partial
        """

        # Intent-based content type mappings for smart filtering
        self.intent_patterns = {
            'contract': {
                'keywords': ['contract', 'agreement', 'terms', 'legal', 'clause', 'sign', 'binding'],
                'content_types': ['contract', 'policy']
            },
            'invoice': {
                'keywords': ['invoice', 'payment', 'bill', 'receipt', 'charge', 'cost', 'price', 'pay'],
                'content_types': ['invoice', 'contract']
            },
            'policy': {
                'keywords': ['policy', 'rule', 'guideline', 'procedure', 'regulation', 'compliance'],
                'content_types': ['policy', 'manual']
            },
            'technical': {
                'keywords': ['specification', 'technical', 'api', 'architecture', 'implementation', 'configure'],
                'content_types': ['specification', 'manual']
            },
            'report': {
                'keywords': ['report', 'analysis', 'summary', 'findings', 'results', 'metrics', 'data'],
                'content_types': ['report', 'presentation']
            },
            'email': {
                'keywords': ['email', 'message', 'correspondence', 'communication', 'sent', 'received'],
                'content_types': ['email']
            }
        }

    def _detect_content_type_intent(self, query: str) -> Optional[List[str]]:
        """
        Detect query intent and suggest relevant content types for filtering.

        DISABLED: Intent-based filtering was causing accuracy issues by excluding
        relevant content (e.g., website pages about board of directors, branch locations).
        The filtering was too aggressive and would exclude content with generic content_types
        like "webpage" even when they contained the answer.

        Can be re-enabled in future with:
        - Higher confidence threshold (require 3+ keyword matches)
        - Smart fallback (retry without filter if <3 results)
        - Multi-intent support (combine multiple content_types)

        Args:
            query: The user's query text

        Returns:
            None - No filtering applied, search all content
        """
        # DISABLED: Return None to disable intent-based filtering
        return None

        # Original implementation preserved below for future reference:
        # query_lower = query.lower()
        # intent_scores = {}
        # for intent, config in self.intent_patterns.items():
        #     matches = sum(1 for keyword in config['keywords'] if keyword in query_lower)
        #     if matches > 0:
        #         intent_scores[intent] = matches
        # if intent_scores:
        #     top_intent = max(intent_scores, key=intent_scores.get)
        #     return self.intent_patterns[top_intent]['content_types']
        # return None

    async def pre_search(
        self,
        tenant_id: str,
        user_message: str,
        session_id: str,
        tenant: Dict = None
    ) -> Dict[str, Any]:
        """
        Run vector search + history fetch ahead of time (for parallelization).

        Returns a dict with relevant_docs, conversation_history, tenant,
        content_type_filter, and search_duration_ms.
        """
        # Use provided tenant or fetch from service
        if not tenant:
            tenant = await self.tenant_client.get_tenant_by_id(tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")

        content_type_filter = self._detect_content_type_intent(user_message)

        loop = asyncio.get_event_loop()
        search_start = time.time()

        relevant_docs_future = loop.run_in_executor(
            None,
            lambda: self.vector_store.search_similar(
                tenant_id=tenant_id,
                query=user_message,
                k=10,
                content_types=content_type_filter
            )
        )
        history_future = loop.run_in_executor(
            None,
            lambda: self._get_conversation_history(session_id)
        )

        relevant_docs, conversation_history = await asyncio.gather(
            relevant_docs_future, history_future
        )
        search_duration = (time.time() - search_start) * 1000

        return {
            "relevant_docs": relevant_docs,
            "conversation_history": conversation_history,
            "tenant": tenant,
            "content_type_filter": content_type_filter,
            "search_duration_ms": search_duration
        }

    async def generate_response(
        self,
        tenant_id: str,
        user_message: str,
        session_id: str,
        tenant: Dict = None,
        pre_search_result: Dict = None
    ) -> Dict[str, Any]:
        """Generate AI response with RAG and conversation memory"""

        start_time = time.time()

        # Log incoming message
        log_chat_message(
            direction="incoming",
            tenant_id=tenant_id,
            session_id=session_id,
            message_length=len(user_message)
        )

        if pre_search_result:
            # Use pre-computed search results (from parallelized path)
            relevant_docs = pre_search_result["relevant_docs"]
            conversation_history = pre_search_result["conversation_history"]
            tenant = pre_search_result["tenant"]
            content_type_filter = pre_search_result["content_type_filter"]
            search_duration = pre_search_result["search_duration_ms"]
        else:
            # Use provided tenant or fetch from service
            if not tenant:
                tenant = await self.tenant_client.get_tenant_by_id(tenant_id)
            if not tenant:
                self.logger.error(
                    "Tenant not found",
                    tenant_id=tenant_id,
                    session_id=session_id
                )
                raise ValueError("Tenant not found")

            # Detect content type intent for smart filtering
            content_type_filter = self._detect_content_type_intent(user_message)

            # Run vector search and conversation history fetch in parallel
            # Both are sync/blocking, so we offload to the thread pool
            loop = asyncio.get_event_loop()
            search_start = time.time()

            relevant_docs_future = loop.run_in_executor(
                None,
                lambda: self.vector_store.search_similar(
                    tenant_id=tenant_id,
                    query=user_message,
                    k=10,
                    content_types=content_type_filter
                )
            )
            history_future = loop.run_in_executor(
                None,
                lambda: self._get_conversation_history(session_id)
            )

            relevant_docs, conversation_history = await asyncio.gather(
                relevant_docs_future, history_future
            )
            search_duration = (time.time() - search_start) * 1000

        log_tenant_operation(
            operation="tenant_lookup",
            tenant_id=tenant_id,
            tenant_name=tenant.get('name', 'Unknown')
        )

        self.logger.debug(f"Search contents: {relevant_docs}")

        # Calculate average retrieval score from document relevance
        retrieval_score = self._calculate_retrieval_score(relevant_docs)

        log_vector_search(
            tenant_id=tenant_id,
            query_length=len(user_message),
            results_count=len(relevant_docs),
            duration_ms=search_duration
        )

        # Build context from relevant documents
        context_parts = []
        sources = []
        categorization_metadata = {
            'content_types': set(),
            'has_categorization': False
        }

        for doc in relevant_docs:
            context_parts.append(doc.page_content)
            if hasattr(doc, 'metadata') and doc.metadata:
                source = doc.metadata.get('source_name', 'Unknown')
                if source not in sources:
                    sources.append(source)

                # Collect categorization metadata from retrieved documents
                if doc.metadata.get('content_type'):
                    categorization_metadata['content_types'].add(doc.metadata['content_type'])
                    categorization_metadata['has_categorization'] = True

        context = "\n\n".join(context_parts) if context_parts else "No specific context available."

        # Convert sets to lists for JSON serialization
        categorization_metadata['content_types'] = list(categorization_metadata['content_types'])
        
        # Build messages for OpenAI API
        messages = [
            {
                "role": "system",
                "content": self.system_prompt.format(
                    company_name=tenant["name"],
                    context=context
                )
            }
        ]
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Keep last 10 messages
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
        
        # Add current user message
        messages.append({
            "role": "user", 
            "content": user_message
        })
        
        # Generate response using direct OpenAI client
        try:
            ai_start = time.time()
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
                timeout=30.0
            )
            response_content = response.choices[0].message.content
            ai_duration = (time.time() - ai_start) * 1000
            
            # Log AI generation
            log_ai_generation(
                tenant_id=tenant_id,
                session_id=session_id,
                duration_ms=ai_duration,
                token_count=len(response_content)  # Approximate
            )
            
            # Store conversation in Redis for memory (offloaded to avoid blocking event loop)
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, self._store_conversation_turn, session_id, user_message, response_content)
            
            # Log outgoing message
            log_chat_message(
                direction="outgoing",
                tenant_id=tenant_id,
                session_id=session_id,
                message_length=len(response_content)
            )
            
            # Log total request duration
            total_duration = (time.time() - start_time) * 1000
            self.logger.info(
                "Chat response completed",
                tenant_id=tenant_id,
                session_id=session_id,
                total_duration_ms=total_duration,
                context_docs_count=len(relevant_docs),
                sources_count=len(sources)
            )

            # Calculate quality metrics for this response
            answer_confidence = self._estimate_answer_confidence(
                response_content,
                len(relevant_docs),
                retrieval_score
            )

            quality_metrics = {
                "retrieval_score": round(retrieval_score, 3) if retrieval_score else None,
                "documents_retrieved": len(relevant_docs),
                "answer_confidence": round(answer_confidence, 3),
                "sources_cited": len(sources),
                "answer_length": len(response_content),
                "response_time_ms": int(total_duration)
            }

            return {
                "content": response_content,
                "sources": sources,
                "metadata": {
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "context_docs_count": len(relevant_docs),
                    "content_type_filter_applied": content_type_filter,
                    "categorization": categorization_metadata
                },
                "quality_metrics": quality_metrics  # NEW: Quality metrics for event publishing
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to generate AI response",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e))
            raise Exception(f"Failed to generate response: {str(e)}")
    
    def _get_conversation_history(self, session_id: str) -> List[Dict]:
        """Get conversation history from Redis"""
        try:
            history_json = self.redis_client.get(f"chat_history:{session_id}")
            if history_json:
                return json.loads(history_json)
            return []
        except Exception:
            return []
    
    def _store_conversation_turn(self, session_id: str, user_message: str, ai_response: str):
        """Store conversation turn in Redis"""
        try:
            history = self._get_conversation_history(session_id)
            
            # Add new messages
            history.extend([
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": ai_response}
            ])
            
            # Keep only the last 50 messages to prevent memory bloat
            history = history[-50:]
            
            # Store back to Redis with expiration (24 hours)
            self.redis_client.setex(
                f"chat_history:{session_id}",
                86400,  # 24 hours
                json.dumps(history)
            )
        except Exception as e:
            # Log error but don't fail the response
            self.logger.warning(
                "Failed to store conversation history",
                session_id=session_id,
                error=str(e)
            )
    
    def clear_session_history(self, session_id: str):
        """Clear conversation history for a session"""
        self.redis_client.delete(f"chat_history:{session_id}")

    def _calculate_retrieval_score(self, relevant_docs: List) -> Optional[float]:
        """
        Calculate retrieval quality score from vector search results.

        Converts distance scores to relevance scores (0-1 range).
        Lower distance = higher relevance.

        Args:
            relevant_docs: List of documents from vector search

        Returns:
            Average relevance score (0-1) or None if no documents
        """
        if not relevant_docs:
            return None

        relevance_scores = []

        for doc in relevant_docs:
            # Get distance from metadata (default to 1.0 if not present)
            distance = 1.0
            if hasattr(doc, 'metadata') and doc.metadata:
                distance = doc.metadata.get('distance', 1.0)

            # Convert distance to relevance score
            # Using exponential decay: relevance = e^(-distance)
            # Distance 0 -> relevance 1.0
            # Distance 1 -> relevance 0.37
            # Distance 2 -> relevance 0.14
            import math
            relevance = math.exp(-distance)
            relevance_scores.append(relevance)

        # Return average relevance
        return sum(relevance_scores) / len(relevance_scores)

    def _estimate_answer_confidence(
        self,
        response_content: str,
        doc_count: int,
        retrieval_score: Optional[float]
    ) -> float:
        """
        Estimate confidence level of the AI response.

        Uses heuristics based on:
        - Hedging language in the response
        - Quality of retrieved documents
        - Number of documents retrieved
        - Response length

        Args:
            response_content: The AI-generated response text
            doc_count: Number of documents retrieved
            retrieval_score: Quality of document retrieval (0-1)

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.7  # Base confidence

        # Check for hedging language (uncertainty indicators)
        hedging_words = [
            "maybe", "perhaps", "possibly", "might", "could be",
            "not sure", "unclear", "don't know", "can't find",
            "no information", "no specific", "not available"
        ]

        response_lower = response_content.lower()
        hedging_count = sum(1 for word in hedging_words if word in response_lower)

        # Reduce confidence for each hedging phrase found
        confidence -= (hedging_count * 0.15)

        # Adjust based on retrieval quality
        if retrieval_score is not None:
            # Weight retrieval score at 30% of confidence
            confidence = confidence * 0.7 + retrieval_score * 0.3

        # Adjust based on number of documents retrieved
        if doc_count == 0:
            confidence *= 0.3  # Very low confidence with no context
        elif doc_count < 2:
            confidence *= 0.7  # Reduced confidence with limited context
        elif doc_count >= 4:
            confidence *= 1.1  # Boost confidence with good context

        # Adjust based on response length
        response_length = len(response_content)
        if response_length < 50:
            confidence *= 0.8  # Very short responses may indicate uncertainty
        elif response_length > 500:
            confidence *= 1.05  # Longer, detailed responses indicate confidence

        # Clamp to 0-1 range
        return max(0.0, min(1.0, confidence))