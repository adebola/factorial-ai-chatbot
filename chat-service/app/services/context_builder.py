"""Token-aware context builder for agent conversations.

Counts tokens using tiktoken (OpenAI) with a fallback approximation
for other providers. Builds message lists within a token budget by
filling history newest-to-oldest.
"""
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy-loaded tokenizer cache
_tokenizers = {}


def _get_tokenizer(model_name: str):
    """Get or create a tiktoken tokenizer for the given model."""
    if model_name not in _tokenizers:
        try:
            import tiktoken
            try:
                _tokenizers[model_name] = tiktoken.encoding_for_model(model_name)
            except KeyError:
                # Fall back to cl100k_base for unknown models (GPT-4, GPT-3.5 family)
                _tokenizers[model_name] = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken not installed, using approximation for token counting")
            _tokenizers[model_name] = None
    return _tokenizers[model_name]


def count_tokens(text: str, model_name: str = "gpt-4o") -> int:
    """
    Count tokens for a given text.

    Uses tiktoken for accurate counting when available,
    falls back to len(text) // 4 approximation.
    """
    if not text:
        return 0

    tokenizer = _get_tokenizer(model_name)
    if tokenizer is not None:
        return len(tokenizer.encode(text))

    # Fallback: ~4 characters per token is a reasonable approximation
    return max(1, len(text) // 4)


def build_context(
    system_prompt: str,
    current_message: str,
    history: List[dict],
    context_limit_tokens: int,
    max_response_tokens: int = 4096,
    context_summary: Optional[str] = None,
    model_name: str = "gpt-4o",
) -> Tuple[List[dict], int, bool]:
    """
    Build a message list within the token budget.

    Args:
        system_prompt: The system prompt for the agent
        current_message: The user's current message
        history: List of message dicts with 'role', 'content', 'token_count' keys,
                 ordered oldest-to-newest. Each must have pre-computed token_count.
        context_limit_tokens: Total usable token budget
        max_response_tokens: Reserved tokens for the model's response
        context_summary: Optional summary from a parent session (carry-over)
        model_name: Model name for token counting

    Returns:
        Tuple of (messages_list, total_tokens_used, is_at_limit)
        - messages_list: Ready to send to the LLM
        - total_tokens_used: Total tokens in the assembled context
        - is_at_limit: True if some history was excluded due to budget
    """
    budget = context_limit_tokens

    # Reserve space for system prompt
    system_tokens = count_tokens(system_prompt, model_name)
    budget -= system_tokens

    # Reserve space for response generation
    budget -= max_response_tokens

    # Reserve space for current message
    current_tokens = count_tokens(current_message, model_name)
    budget -= current_tokens

    # Reserve space for context summary if present
    summary_tokens = 0
    if context_summary:
        summary_tokens = count_tokens(context_summary, model_name)
        budget -= summary_tokens

    # Fill history from newest to oldest within remaining budget
    included = []
    for msg in reversed(history):
        msg_tokens = msg.get("token_count", 0)
        if msg_tokens == 0:
            # Recount if token_count is missing
            msg_tokens = count_tokens(msg.get("content", ""), model_name)

        if msg_tokens > budget:
            break
        included.insert(0, msg)
        budget -= msg_tokens

    is_at_limit = len(included) < len(history)

    # Assemble the messages list
    messages = [{"role": "system", "content": system_prompt}]

    if context_summary:
        messages.append({
            "role": "system",
            "content": f"Context from previous session:\n{context_summary}"
        })

    for msg in included:
        messages.append({
            "role": msg["role"],
            "content": msg.get("content", ""),
        })

    messages.append({"role": "user", "content": current_message})

    # Calculate total tokens used
    total_used = (
        system_tokens
        + summary_tokens
        + sum(m.get("token_count", count_tokens(m.get("content", ""), model_name)) for m in included)
        + current_tokens
    )

    return messages, total_used, is_at_limit
