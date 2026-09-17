import json
import uuid
from dataclasses import dataclass

from cp_domain.product import Product
from cp_domain.recommendation import RecommendationType, RiskLevel
from pydantic import BaseModel

from cp_ai.providers.base import AIProvider, TokenUsage
from cp_ai.tools.builtin.product_tools import update_product_content_tool

_SPEC_FIELDS = ("ean", "weight_kg", "dimensions_cm", "brand", "category")

_SYSTEM_PROMPT = (
    "You are a product copywriter for an e-commerce catalog. Write a compelling "
    "title, a short description, and 3-5 bullet points for the product below, "
    "using only the information given to you. Never invent technical "
    "specifications you were not given - for any specification you have no "
    'value for, write exactly "UNKNOWN".'
)


class ProductContent(BaseModel):
    title: str
    description: str
    bullet_points: list[str]
    specifications: dict[str, str]


@dataclass(frozen=True)
class ProductContentProposal:
    """Everything `cp_policies.propose_recommendation` needs to record
    this as a pending recommendation."""

    tool_name: str
    tool_arguments: dict
    type: RecommendationType
    risk_level: RiskLevel
    entity_type: str
    entity_id: uuid.UUID
    title: str
    reason: str


def _known_specs(product: Product, fields: tuple[str, ...]) -> dict[str, str]:
    known: dict[str, str] = {}
    if "ean" in fields and product.ean:
        known["ean"] = product.ean
    if "weight_kg" in fields and product.weight_kg is not None:
        known["weight_kg"] = str(product.weight_kg)
    if "dimensions_cm" in fields and product.dimensions_cm:
        known["dimensions_cm"] = json.dumps(product.dimensions_cm)
    if product.extra_attributes:
        known.update({k: str(v) for k, v in product.extra_attributes.items()})
    return known


async def build_product_content_proposal(
    *, provider: AIProvider, product: Product, spec_fields: tuple[str, ...] = _SPEC_FIELDS
) -> tuple[ProductContentProposal, TokenUsage | None]:
    """Decides what listing content to propose for a product, using
    `provider` to generate a title/description/bullet points - and,
    deterministically in this function, never in the model's hands,
    forces every specification field we have no real data for to the
    literal `"UNKNOWN"` regardless of what the model returned.

    That enforcement matters because `product.description` (read into
    the prompt below) is untrusted external content per CONTRIBUTING.md #18 -
    it may have been synced from a marketplace listing an attacker
    controls, and could contain text trying to steer the model into
    inventing a plausible-looking spec value. The model is *asked* not
    to; this function does not trust that it complied.
    """
    known = _known_specs(product, spec_fields)
    unknown = [f for f in spec_fields if f not in known]

    user_prompt = (
        f"Product SKU: {product.sku}\n"
        f"Current name: {product.name}\n"
        f"Current description: {product.description or '(none)'}\n"
        f"Known specifications: {known or '(none)'}\n"
        f"Specifications with no known value - do not guess these: {unknown}"
    )

    output = await provider.generate_structured(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=ProductContent.model_json_schema(),
        schema_name="product_content",
    )
    content = ProductContent.model_validate(output.data)

    for field in unknown:
        content.specifications[field] = "UNKNOWN"

    risk_level = RiskLevel(update_product_content_tool().permission.risk_level.value)

    proposal = ProductContentProposal(
        tool_name="update_product_content",
        tool_arguments={
            "sku": product.sku,
            "new_name": content.title,
            "new_description": content.description,
            "new_extra_attributes": {
                "bullet_points": content.bullet_points,
                "specifications": content.specifications,
            },
        },
        type=RecommendationType.CONTENT_UPDATE,
        risk_level=risk_level,
        entity_type="product",
        entity_id=product.id,
        title=f"Update listing content for {product.sku}",
        reason=(
            "Generated title/description/bullet points from known data. "
            f"Specifications left UNKNOWN (no source data): {', '.join(unknown) or 'none'}."
        ),
    )
    return proposal, output.usage
