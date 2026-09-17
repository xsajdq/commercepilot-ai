from dataclasses import dataclass
from decimal import Decimal

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    input_price_per_million_tokens: Decimal
    output_price_per_million_tokens: Decimal


# USD per million tokens - a maintained rate table, not a fact about the
# world, so update it (alongside the vendor's own published pricing)
# whenever it changes rather than treating these numbers as permanent.
# An unrecognized (provider, model) pair is genuinely unpriceable, not a
# case to guess at - see compute_cost below.
MODEL_PRICING: dict[tuple[str, str], ModelPrice] = {
    ("anthropic", "claude-sonnet-5"): ModelPrice(
        input_price_per_million_tokens=Decimal("3.00"),
        output_price_per_million_tokens=Decimal("15.00"),
    ),
    ("anthropic", "claude-opus-5"): ModelPrice(
        input_price_per_million_tokens=Decimal("15.00"),
        output_price_per_million_tokens=Decimal("75.00"),
    ),
    ("anthropic", "claude-haiku-4-5-20251001"): ModelPrice(
        input_price_per_million_tokens=Decimal("0.80"),
        output_price_per_million_tokens=Decimal("4.00"),
    ),
}


def compute_cost(
    *, provider: str, model: str, input_tokens: int, output_tokens: int
) -> Decimal | None:
    """Deterministic cost estimate from real token counts (CONTRIBUTING.md #10:
    this is math, done in code, never delegated to an LLM to compute
    about itself). Returns `None` - not a fabricated number - for a
    (provider, model) pair this table doesn't recognize; a caller should
    treat that as `cost_estimate = UNKNOWN`, the same way `cp_pricing`
    leaves a value `None` rather than guess one."""
    price = MODEL_PRICING.get((provider, model))
    if price is None:
        return None
    input_cost = (Decimal(input_tokens) / _MILLION) * price.input_price_per_million_tokens
    output_cost = (Decimal(output_tokens) / _MILLION) * price.output_price_per_million_tokens
    return input_cost + output_cost
