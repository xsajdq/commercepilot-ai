# Shared Docker fragments

Per-app Dockerfiles live next to their app (`apps/api/Dockerfile`,
`apps/web/Dockerfile`, `apps/worker/Dockerfile`). This directory is for
compose fragments or base images shared across more than one of them, once
there's actual duplication to remove — nothing here yet.
