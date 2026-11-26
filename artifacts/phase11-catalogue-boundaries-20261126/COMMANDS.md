# Catalogue selector boundaries — 26 November 2026

No application behavior/schema changes. New contract in docs/PHASE11-CATALOGUE-SELECTOR-BOUNDARIES.md explicitly gates future management/recipe selection; POS stays daily-selling/stock lookup. Existing general/charge purposes unchanged.

Inspected fixture chain test_phase11_product_selection → test_phase7d_operations → test_phase7c_printing: whitelisted disposable database, outer transaction and per-session savepoints; no inherited production settings/provider activity. Exact command:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests APP_ENV=test JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' /tmp/apex-phase11-document-venv/bin/python -m unittest test_phase11_product_selection -v
```

**4 pass**, no skips. Includes archived/deleted/actual foreign-tenant/missing selected IDs through API AND direct service; general/charge cannot become management reads. Unknown management/recipe/components purposes422 through both paths, even owner. Sales-read employee can search current stock without costs, cannot PATCH catalogue403 or select profile charges403. Existing pages/wildcard/barcode/tenant/branch/expired-read regression retained. Reads preserve preexisting sale and movement counts. Initial fixture assertion expected zero sales, but printing fixture intentionally already owns a synthetic sale; corrected to compare before/after counts, no guard weakened.

Navigation increment993b9ddb941dc0a435a96994252eb55b1e9ed1a0 already committed. Authorized git push origin phase11/baseline-reconciliation failed128: unavailable HTTPS Username. No credential changes; continued independent local tests. No advanced selector/recipe/posting enablement; all prior gates remain.
