import uuid
from dataclasses import dataclass

from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import RecommendationType, RiskLevel

from cp_ai.tools.builtin.product_tools import request_listing_publish_tool


@dataclass(frozen=True)
class ListingPublishProposal:
    """Everything `cp_policies.propose_recommendation` needs to record
    this as a pending recommendation - the caller (a Celery task, see
    `apps/worker`) just has to pass these straight through, plus a
    `tenant_id`."""

    tool_name: str
    tool_arguments: dict
    type: RecommendationType
    risk_level: RiskLevel
    entity_type: str
    entity_id: uuid.UUID
    title: str
    reason: str


def build_listing_publish_proposal(
    *, offer: Offer, product: Product, price: Price | None
) -> ListingPublishProposal | None:
    """Decides whether a draft listing is ready to go live, and if so,
    builds the proposal - never publishes anything itself.

    Deliberately not an `AIProvider` call (no text to generate here,
    unlike the product agent's copywriting): "is this listing ready" is
    a checklist against data we already have, not a creative judgement,
    so this agent's whole "intelligence" is the checklist itself -
    mirroring the pricing agent (Phase 9), which is also a deterministic
    decision-maker wearing an "AI-proposed" hat rather than a real LLM
    call.

    Returns `None` - nothing to propose - unless every one of these
    holds: the offer already exists on the marketplace (`external_id`
    set - creating it there in the first place is a future sync/push
    concern, not this agent's), it's still `DRAFT` (not already live,
    not already mid-publish), the product has real listing content (a
    non-empty name and description - the Product Agent's job, Phase 10),
    and it has been priced (a `Price` row exists). Category-specific
    mandatory parameters (e.g. Allegro's per-category attributes) aren't
    checked here - category/brand mapping across platforms isn't
    modeled yet (see `cp_sync`'s own README), a known simplification
    documented in the roadmap rather than guessed at.
    """
    if offer.external_id is None:
        return None
    if offer.status is not OfferStatus.DRAFT:
        return None
    if not product.name or not product.name.strip():
        return None
    if not product.description or not product.description.strip():
        return None
    if price is None:
        return None

    risk_level = RiskLevel(request_listing_publish_tool().permission.risk_level.value)

    return ListingPublishProposal(
        tool_name="request_listing_publish",
        tool_arguments={"offer_id": str(offer.id)},
        type=RecommendationType.LISTING_PUBLISH,
        risk_level=risk_level,
        entity_type="offer",
        entity_id=offer.id,
        title=f"Publish {product.sku} live on its marketplace",
        reason=(
            "Listing has a name, description, and price, and already exists as a "
            "marketplace draft - ready to go live."
        ),
    )
