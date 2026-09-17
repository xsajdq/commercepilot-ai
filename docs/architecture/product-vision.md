# Product vision: what turns this into something worth paying for

Captured ahead of building it. Nothing here is implemented yet - it
becomes actionable once the current phased build (`roadmap.md`) reaches
the phases it depends on (mainly Phase 7 onward: AI tool system,
approval engine, and the agents). Don't start building against this
document directly; check `roadmap.md` for what phase is actually next.

## What "real MVP" means

A concrete product goal, not just a feature list: a store connects
WooCommerce and Allegro. The agent analyzes the catalog and sales, finds
problems, prepares change proposals, and a human approves them with one
click. Everything in Phases 0-5 exists to make that possible; Phases 7-15
are what actually deliver it.

## The three "magic" workflows

These are the demos that should make someone want to pay for this - each
one is a concrete product milestone, not just "the agents are done."

### 1. "Analyze my store"

```
18,421 products
   ↓ analysis
127 problems
   ↓
43 recommendations
   ↓
17 require approval
```

Depends on: Catalog Agent (Phase 12), Analytics Agent (Phase 13),
Competition Agent (Phase 14), Recommendations scheduler (Phase 15).

### 2. "Get this product ready to sell"

```
SKU, EAN, cost, images, manufacturer data
   ↓
Product Agent → description, parameters, SEO, variants
   ↓
Listing Agent → WooCommerce + Allegro
   ↓
Approval → Publish
```

Depends on: Product Agent (Phase 10), Listing Agent (Phase 11), the
approval engine (Phase 8), and both connectors' `publish_offer`/
`get_category_parameters` (already built, Phases 4-5).

### 3. "Handle pricing"

```
20,000 products
   ↓
Pricing Engine → Competition → Sales → Margin → Recommendations
   ↓
Approval → Price updates
```

Depends on: the deterministic Pricing Engine before any AI layer (Phase
9), Competition Agent (Phase 14), the approval engine (Phase 8). This is
where the largest, most defensible business value is - price changes are
the action most directly tied to revenue, which is also exactly why the
pricing math must stay deterministic code (CONTRIBUTING.md #10), not an LLM
guess, and why every price change is HIGH/MEDIUM risk requiring approval,
never auto-applied.
