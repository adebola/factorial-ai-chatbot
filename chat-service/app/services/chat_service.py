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


class ChatService:
    """Handles AI chat responses with RAG and memory using a direct OpenAI client"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("chat_service")
        
        # Get OpenAI API key with validation
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        
        self.openai_client = OpenAI(api_key=openai_api_key)
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
        - If you can't find the answer in the context, say so politely
        - Be conversational and helpful
        - Reference specific sources when possible
        """
    
    async def generate_response(
        self, 
        tenant_id: str, 
        user_message: str, 
        session_id: str
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
        
        # Get tenant info from the onboarding service
        tenant = await self.tenant_client.get_tenant_by_id(tenant_id)
        if not tenant:
            self.logger.error(
                "Tenant not found",
                tenant_id=tenant_id,
                session_id=session_id
            )
            raise ValueError("Tenant not found")
        
        log_tenant_operation(
            operation="tenant_lookup",
            tenant_id=tenant_id,
            tenant_name=tenant.get('name', 'Unknown')
        )
        
        # Search relevant documents
        search_start = time.time()
        relevant_docs = self.vector_store.search_similar(
            tenant_id=tenant_id,
            query=user_message,
            k=4
        )
        search_duration = (time.time() - search_start) * 1000

        self.logger.info(f"Search contents: {relevant_docs}")
        
        log_vector_search(
            tenant_id=tenant_id,
            query_length=len(user_message),
            results_count=len(relevant_docs),
            duration_ms=search_duration
        )
        
        # Build context from relevant documents
        context_parts = []
        sources = []
        
        for doc in relevant_docs:
            context_parts.append(doc.page_content)
            if hasattr(doc, 'metadata') and doc.metadata:
                source = doc.metadata.get('source', 'Unknown')
                if source not in sources:
                    sources.append(source)
        
        context = "\n\n".join(context_parts) if context_parts else "No specific context available."
        
        # Get conversation history
        conversation_history = self._get_conversation_history(session_id)
        
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
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=1500
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
            
            # Store conversation in Redis for memory
            self._store_conversation_turn(session_id, user_message, response_content)
            
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
            
            return {
                "content": response_content,
                "sources": sources,
                "metadata": {
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                    "context_docs_count": len(relevant_docs)
                }
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to generate AI response",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
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