# Security docs

Threat model, secret-handling policy, and tenant-isolation test notes.
See `CLAUDE.md` for the non-negotiable rules (never trust client
`tenant_id`, never log credentials/PII, secrets encrypted at rest). Fuller
write-ups land as auth (Phase 1) and connectors (Phase 4+) are built.
