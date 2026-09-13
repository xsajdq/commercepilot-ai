# Hetzner deployment notes

MVP target: a single Hetzner Cloud server (CX43 or similar), no Kubernetes.

```
Docker
├── traefik
├── frontend
├── backend
├── worker
├── scheduler (celery beat)
├── postgres
├── redis
├── prometheus   (added in Phase 21 — production hardening)
└── grafana      (added in Phase 21 — production hardening)
```

Cloudflare sits in front for DNS/CDN/WAF and issues TLS; Traefik's
production `traefik.yml` should terminate TLS via a Cloudflare-origin
certificate rather than the `insecure: true` dashboard used locally.

Backups: PostgreSQL must be backed up to storage that lives outside this
server (Hetzner Object Storage), not just outside the container. See
`infrastructure/backups/README.md`. This is deferred implementation work
for Phase 21, tracked here so it isn't forgotten.

Provisioning scripts (cloud-init, firewall rules, SSH hardening) will be
added here once the app is ready to deploy — not part of Phase 0.

Deploy pipeline, environments (local/staging/production), and monitoring
plan: see `docs/architecture/deployment.md` — also deferred work
(Phase 21+), captured now so it isn't lost by the time it's next.
