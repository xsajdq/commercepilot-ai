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
certificate rather than the `insecure: true` dashboard used locally. It
should also add a `providers.file` pointing at
`infrastructure/traefik/dynamic/` (proxy-layer security headers +
a coarse IP rate limit, defense in depth alongside apps/api's own
middleware - see that directory's own comments) and reference those
middleware names on the API/web routers' labels. See
`docs/security/waf.md` for what to actually turn on in Cloudflare
itself (managed WAF ruleset, rate limiting rules, bot protections) -
none of that is configurable from this repo, since it's Cloudflare's
own account/dashboard, not code here.

Backups: PostgreSQL must be backed up to storage that lives outside this
server (Hetzner Object Storage), not just outside the container. See
`infrastructure/backups/README.md` for `backup.sh`/`restore.sh` (real,
tested against a real Postgres in this repo's dev environment) and the
systemd timer that would run `backup.sh` daily once this app is
actually deployed here - installing the timer and creating the real
Hetzner Object Storage bucket are the parts still deferred to that
deploy.

Provisioning scripts (cloud-init, firewall rules, SSH hardening) will be
added here once the app is ready to deploy — not part of Phase 0.

Deploy pipeline, environments (local/staging/production), and monitoring
plan: see `docs/architecture/deployment.md` — also deferred work
(Phase 21+), captured now so it isn't lost by the time it's next.
