# packages/domain

Platform-agnostic domain model: `Product`, `Variant`, `Brand`, `Category`,
`Offer`, `Price`, `Cost`, `Stock`, `Image`, `Marketplace`, `Order`,
`Review`, `Competitor`, `Recommendation`, `AIJob`, `Approval`,
`AuditEvent`.

Empty scaffold — populated in Phase 2. The domain model must never import
a marketplace SDK or connector; platform-specific data lives in mapping
tables owned by `packages/connectors`, not here.
