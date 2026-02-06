"""Pricing data for LLM API providers."""

from __future__ import annotations

from typing import Tuple

# Pricing per million tokens: (input_price_usd, output_price_usd)
PRICING_PER_MILLION_TOKENS: dict[str, Tuple[float, float]] = {
    # Anthropic
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    # Legacy Anthropic models
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),

    # OpenRouter - Open Source Models
    "qwen/qwen3-235b-a22b": (0.50, 2.00),
    "moonshotai/kimi-k2.5": (1.00, 4.00),
    "meta-llama/llama-3.3-70b-instruct": (0.40, 0.40),
    "deepseek/deepseek-chat-v3-0324": (0.27, 1.10),
    "deepseek/deepseek-r1": (0.55, 2.19),
    "mistralai/mistral-large-2411": (2.00, 6.00),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "google/gemini-2.5-pro-preview-06-05": (1.25, 10.00),

    # OpenRouter - Anthropic (same pricing)
    "anthropic/claude-3.5-haiku": (0.80, 4.00),
    "anthropic/claude-3.5-sonnet": (3.00, 15.00),
    "anthropic/claude-3-opus": (15.00, 75.00),

    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),

    # Ollama (free - local)
    "ollama/llama3.3": (0.0, 0.0),
    "ollama/qwen2.5": (0.0, 0.0),
    "ollama/mistral": (0.0, 0.0),
    "ollama/gemma2": (0.0, 0.0),
}

# Aliases for common model references
MODEL_ALIASES: dict[str, str] = {
    "haiku": "claude-3-5-haiku-latest",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "qwen3": "qwen/qwen3-235b-a22b",
    "kimi": "moonshotai/kimi-k2.5",
    "llama3": "meta-llama/llama-3.3-70b-instruct",
    "deepseek": "deepseek/deepseek-chat-v3-0324",
    "gemini-flash": "google/gemini-2.0-flash-001",
    "gemini-pro": "google/gemini-2.5-pro-preview-06-05",
}


def get_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate the cost for an API call.

    Args:
        model: Model name or alias.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Cost in USD.
    """
    # Resolve alias if needed
    resolved_model = MODEL_ALIASES.get(model, model)

    # Look up pricing
    if resolved_model in PRICING_PER_MILLION_TOKENS:
        input_price, output_price = PRICING_PER_MILLION_TOKENS[resolved_model]
    elif resolved_model.startswith("ollama/"):
        # Ollama models are free
        return 0.0
    else:
        # Check for partial matches (provider prefix)
        for key, pricing in PRICING_PER_MILLION_TOKENS.items():
            if key.endswith(resolved_model) or resolved_model.endswith(key):
                input_price, output_price = pricing
                break
        else:
            # Unknown model - use conservative estimate
            input_price, output_price = 5.00, 15.00

    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return cost


def estimate_game_cost(
    model: str,
    avg_turns: int = 20,
    avg_input_tokens_per_turn: int = 500,
    avg_output_tokens_per_turn: int = 200,
) -> float:
    """Estimate the cost for a single game.

    Args:
        model: Model name or alias.
        avg_turns: Average number of turns per game.
        avg_input_tokens_per_turn: Average input tokens per turn.
        avg_output_tokens_per_turn: Average output tokens per turn.

    Returns:
        Estimated cost in USD.
    """
    total_input = avg_turns * avg_input_tokens_per_turn
    total_output = avg_turns * avg_output_tokens_per_turn
    return get_cost(model, total_input, total_output)


def estimate_tournament_cost(
    models: list[str],
    games_per_match: int = 10,
    avg_turns_per_game: int = 20,
) -> dict[str, float]:
    """Estimate costs for a tournament.

    Args:
        models: List of model names participating.
        games_per_match: Games per pairwise matchup.
        avg_turns_per_game: Average turns per game.

    Returns:
        Dict with 'per_model' costs and 'total' cost.
    """
    # In round-robin, each model plays (n-1) * games_per_match games
    # Each game has avg_turns_per_game turns for the LLM player
    # (assuming opponent is not an LLM or is counted separately)
    n = len(models)
    games_per_model = (n - 1) * games_per_match

    per_model = {}
    total = 0.0

    for model in models:
        # Estimate cost per game
        game_cost = estimate_game_cost(model, avg_turns_per_game)
        model_total = game_cost * games_per_model
        per_model[model] = model_total
        total += model_total

    return {
        "per_model": per_model,
        "total": total,
        "games_per_model": games_per_model,
        "total_games": n * (n - 1) // 2 * games_per_match,
    }
