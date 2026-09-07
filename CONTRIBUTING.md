# Contributing

GEO Platform is a local-first SEO/GEO operations workspace built with FastAPI,
SQLAlchemy and Next.js. Contributions are welcome under the MIT license.

Start with the README installation steps. Use synthetic data and an isolated
SQLite database for tests; do not submit customer data, credentials or backups.
Protocol fixtures exercise HTTP behavior without paid models or live CMS writes.

Before submitting a focused pull request, run:

```sh
python -m pip install -r backend/requirements-dev.txt
python -m pytest tests -q -p no:seleniumbase
cd frontend
npm ci
npm run build
npm run typecheck
```

Explain the user-visible change and validation. Preserve immutable evidence,
unknown metric states, version-bound approvals and single-submission semantics.
Technical observations must not claim search indexing or GEO improvement.
Schema changes need an additive Alembic migration and a data-preservation test.

Third-party dependencies retain their respective licenses. Include provenance
and the original license when contributing third-party code or assets.
