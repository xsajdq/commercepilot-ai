# Architecture overview

See `CLAUDE.md` at the repo root for the mission, core principles, and the
mandatory control flow every mutation follows. See
`docs/architecture/roadmap.md` for the phased build plan and current
status.

```
CLOUDFLARE → TRAEFIK → { NEXT.JS, FASTAPI }
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
          POSTGRES         REDIS         STORAGE
                             │
                          CELERY
                             │
                  ┌──────────┼──────────┐
                  ▼          ▼          ▼
               SYNC        AI       ANALYTICS
              WORKER     WORKER      WORKER
                  │
                  ▼
             CONNECTORS
                  │
        ┌─────────┼─────────┬─────────┐
        ▼         ▼         ▼         ▼
      Woo     Allegro    Shoper    Presta...
```

Multi-tenancy: every business table carries `tenant_id`, and it is always
derived server-side from the authenticated session — never accepted from
the client.
