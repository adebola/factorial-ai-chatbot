"""Token cost estimation utility for OpenAI models."""

# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
    },
    "text-embedding-ada-002": {
        "input": 0.10,
        "output": 0.0,
    },
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int = 0) -> float:
    """Estimate cost in USD for a given model and token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4o-mini"))
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 8)
