# Release

## Package command

```powershell
.\scripts\irx.ps1 package
```

Creates:

- `release/irx-v1.0/`
- `release/irx-v1.0.zip`
- `release/irx-v1.0/release-summary.json`

## Package structure

```text
release/irx-v1.0/
  backend/                 # Spring Boot jar
  dashboard/dist/           # built Vite frontend
  scripts/irx.ps1           # one-click script
  docs/                     # canonical docs
  artifacts/sample-reports/ # selected evidence summaries
  docker-compose.yml
  Dockerfile.backend
  dashboard/Dockerfile
  .env.example
  README.md
  release-summary.json
```

## Zip policy

The generated zip is large and is not committed to Git. Rebuild locally with `./scripts/irx.ps1 package`. The small release summary is committed under:

`artifacts/test-reports/v0.9.9.6-one-click-start/release-summary.json`

## Tag policy

Milestone tags use:

`v0.9.9.x-short-description`

Current docs rewrite tag target:

`v0.9.9.7-production-docs-rewrite`

## Known limitations

- Package is a local demo bundle, not a signed installer.
- Cloud deployment, Kubernetes, OAuth2, and managed object storage are future work.
