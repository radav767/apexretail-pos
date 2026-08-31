#!/usr/bin/env bash
# Read-only comparison of production inventory aggregates with a Phase 1 clone.
# Run this from the normal VPS host shell only after the validation clone exists.
set -Eeuo pipefail

readonly PRODUCTION_DB="apexretail_pos"
readonly TEMP_PREFIX="apexretail_phase1_validation_"
readonly DEFAULT_CLONE="apexretail_phase1_validation_clone_20260831153014_5763"

fail() { echo "FAIL: $*" >&2; exit 1; }

# Validate every database identifier before interpolating it into SQL or psql.
assert_database_name() {
  local name="$1"
  if [[ "$name" == "$PRODUCTION_DB" ]]; then
    return 0
  fi
  [[ "$name" =~ ^${TEMP_PREFIX}[a-z0-9_]+$ ]] || fail "unsafe validation database name"
  [[ "${#name}" -le 63 ]] || fail "validation database identifier exceeds PostgreSQL limit"
}

# Execute SQL through one read-only psql helper. PGOPTIONS applies the server
# setting to every connection; -qAt and --no-psqlrc ensure tuple output only.
readonly_psql() {
  local db="$1" sql="$2"
  assert_database_name "$db"
  sudo -u postgres env PGOPTIONS='-c default_transaction_read_only=on' \
    psql -X -qAt --no-psqlrc -v ON_ERROR_STOP=1 -d "$db" -c "$sql"
}

# Execute aggregate SELECTs only; no INSERT, UPDATE, DDL, migration, or
# administrative operation is performed.
inventory_totals() {
  local db="$1"
  readonly_psql "$db" "
SELECT
  (SELECT count(*) FROM inventory_balances),
  (SELECT COALESCE(sum(quantity), 0) FROM inventory_balances),
  (SELECT COALESCE(sum(ib.quantity * COALESCE(p.cost_price, 0)), 0)
     FROM inventory_balances ib LEFT JOIN products p ON p.id = ib.product_id),
  (SELECT count(*) FROM inventory_movements),
  (SELECT COALESCE(sum(quantity), 0) FROM inventory_movements),
  (SELECT COALESCE(sum(stock_qty * COALESCE(cost_price, 0)), 0)
     FROM products WHERE deleted = false);"
}

clone_db="${1:-$DEFAULT_CLONE}"
assert_database_name "$clone_db"
[[ "$clone_db" != "$PRODUCTION_DB" ]] || fail "clone cannot be production database"

# Run all PostgreSQL clients from a world-accessible directory so the postgres
# account never attempts to enter the root-owned repository working directory.
cd /tmp

# Confirm both explicitly selected connections identify themselves as the
# requested databases. Empty output is a failed query, never a valid result.
prod_identity="$(readonly_psql "$PRODUCTION_DB" 'SELECT current_database();')"
if [[ -z "$prod_identity" || "$prod_identity" != "$PRODUCTION_DB" ]]; then
  prod_actual_safe="$(printf '%s' "$prod_identity" | tr -cd '[:alnum:]_.-')"
  fail "production database identity mismatch (expected ${PRODUCTION_DB}; actual ${prod_actual_safe:-<empty>})"
fi
clone_identity="$(readonly_psql "$clone_db" 'SELECT current_database();')"
if [[ -z "$clone_identity" || "$clone_identity" != "$clone_db" ]]; then
  clone_actual_safe="$(printf '%s' "$clone_identity" | tr -cd '[:alnum:]_.-')"
  fail "clone database identity mismatch (expected ${clone_db}; actual ${clone_actual_safe:-<empty>})"
fi

production_totals="$(inventory_totals "$PRODUCTION_DB")"
clone_totals="$(inventory_totals "$clone_db")"

# Extract only opaque keys and numeric quantities/values for in-memory
# classification. Keys are never printed; the report below contains totals
# only. The clone query also carries authoritative product stock_qty.
production_rows="$(readonly_psql "$PRODUCTION_DB" "
SELECT company_id, shop_id, branch_id, product_id, quantity, active, deleted
FROM inventory_balances
ORDER BY company_id, shop_id, branch_id, product_id;")"
clone_rows="$(readonly_psql "$clone_db" "
SELECT ib.company_id, ib.shop_id, ib.branch_id, ib.product_id, ib.quantity,
       ib.quantity * COALESCE(p.cost_price, 0), COALESCE(p.stock_qty, 0),
       ib.active, ib.deleted
FROM inventory_balances ib
LEFT JOIN products p ON p.id = ib.product_id
ORDER BY ib.company_id, ib.shop_id, ib.branch_id, ib.product_id;")"

# Confirm the migration's applicable uniqueness rule without changing schema.
unique_constraint_count="$(readonly_psql "$clone_db" "
SELECT count(*)
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
WHERE t.relname = 'inventory_balances'
  AND c.contype = 'u'
  AND pg_get_constraintdef(c.oid) LIKE '%company_id%'
  AND pg_get_constraintdef(c.oid) LIKE '%branch_id%'
  AND pg_get_constraintdef(c.oid) LIKE '%product_id%';")"

classification="$(awk -F'|' -v OFS='|' \
  'NR == FNR {
     key = $1 FS $2 FS $4; product = $1 FS $4;
     key_product[key] = product;
     prod[key] += ($5 + 0); prod_count[key]++;
     prod_product[product] += ($5 + 0); prod_product_count[product]++;
     if ($1 == "" || $2 == "" || $3 == "" || $4 == "") prod_legacy[key] = 1;
     if ($6 != "true" || $7 == "true") prod_archived[key] = 1;
     next
   }
   {
     key = $1 FS $2 FS $4; product = $1 FS $4;
     key_product[key] = product;
     clone_count[key]++;
     clone_product[product] += ($5 + 0);
     stock[product] = ($7 + 0);
     if ($1 == "" || $2 == "" || $3 == "" || $4 == "") clone_legacy[key] = 1;
     if ($8 != "true" || $9 == "true") clone_archived[key] = 1;
     if (!(key in prod)) {
       inserted_count++;
       inserted_qty += ($5 + 0);
       inserted_value += ($6 + 0);
       inserted_key[inserted_count] = key;
       inserted_product[inserted_count] = product;
       affected_product[product] = 1;
       inserted_row_qty[inserted_count] = ($5 + 0);
       inserted_row_value[inserted_count] = ($6 + 0);
     }
   }
   END {
     for (k in prod_count) if (prod_count[k] > 1) production_duplicates++;
     for (k in clone_count) if (clone_count[k] > 1) clone_duplicates++;
     for (k in prod_count) {
       if (prod_count[k] > 1 && (key_product[k] in affected_product)) affected_prod_duplicates++;
       if (prod_count[k] > 1 && prod_legacy[k]) production_legacy_duplicates++;
       if (prod_count[k] > 1 && prod_archived[k]) production_archived_duplicates++;
       if ((prod_count[k] > 1) != (clone_count[k] > 1)) global_duplicate_set_changed++;
     }
     for (k in clone_count) {
       if (clone_count[k] > 1 && (key_product[k] in affected_product)) affected_clone_duplicates++;
       if (clone_count[k] > 1 && prod_count[k] <= 1) {
         new_duplicate_keys++;
         global_duplicate_set_changed++;
       }
     }
     for (i = 1; i <= inserted_count; i++) {
       k = inserted_key[i]; p = inserted_product[i];
       if (clone_count[k] > 1) class_c++;
       else if (prod_product_count[p] > 0) class_b++;
       else class_a++;
     }
     for (p in affected_product) {
       affected_products++;
       pre = prod_product[p] + 0; upgraded = clone_product[p] + 0; authoritative = stock[p] + 0;
       pre_total += pre; upgraded_total += upgraded; stock_total += authoritative;
       if (sprintf("%.3f", pre) != sprintf("%.3f", authoritative)) pre_stock_mismatch++;
       if (sprintf("%.3f", upgraded) != sprintf("%.3f", authoritative)) upgraded_stock_mismatch++;
     }
     printf "inserted_rows|%d\n", inserted_count;
     printf "inserted_quantity|%.3f\n", inserted_qty;
     printf "inserted_value|%.3f\n", inserted_value;
     printf "class_A_rows|%d\n", class_a;
     printf "class_B_rows|%d\n", class_b;
     printf "class_C_rows|%d\n", class_c;
     printf "production_duplicate_keys|%d\n", production_duplicates;
     printf "clone_duplicate_keys|%d\n", clone_duplicates;
     printf "affected_production_duplicate_keys|%d\n", affected_prod_duplicates;
     printf "affected_clone_duplicate_keys|%d\n", affected_clone_duplicates;
     printf "new_duplicate_keys|%d\n", new_duplicate_keys;
     printf "global_duplicate_set_changed|%d\n", (global_duplicate_set_changed > 0);
     printf "global_duplicate_key_delta|%d\n", clone_duplicates - production_duplicates;
     printf "production_legacy_duplicate_keys|%d\n", production_legacy_duplicates;
     printf "production_archived_duplicate_keys|%d\n", production_archived_duplicates;
     printf "affected_products|%d\n", affected_products;
     printf "pre_quantity_total|%.3f\n", pre_total;
     printf "authoritative_stock_total|%.3f\n", stock_total;
     printf "upgraded_quantity_total|%.3f\n", upgraded_total;
     printf "pre_vs_stock_mismatches|%d\n", pre_stock_mismatch;
     printf "upgraded_vs_stock_mismatches|%d\n", upgraded_stock_mismatch;
   }' <(printf '%s\n' "$production_rows") <(printf '%s\n' "$clone_rows") )"

echo "Production aggregates (inventory rows|quantity|inventory value|movement rows|movement quantity|product stock value):"
echo "$production_totals"
echo "Clone aggregates ($clone_db):"
echo "$clone_totals"
echo "Inventory delta classification (aggregate only):"
echo "$classification"
echo "applicable_unique_constraint_count|${unique_constraint_count}"

if [[ "$production_totals" == "$clone_totals" ]]; then
  echo "PASS: inventory aggregates match exactly"
else
  echo "Inventory aggregate delta (clone - production):"
  awk -F'|' -v OFS='|' \
    'NR == 1 { for (i = 1; i <= NF; i++) clone[i] = $i + 0; next }
     NR == 2 { for (i = 1; i <= NF; i++) printf "%s%s", clone[i] - ($i + 0), (i == NF ? ORS : OFS) }' \
    <(printf '%s\n%s\n' "$clone_totals" "$production_totals")
fi

class_b="$(awk -F'|' '$1 == "class_B_rows" { print $2 }' <<< "$classification")"
class_c="$(awk -F'|' '$1 == "class_C_rows" { print $2 }' <<< "$classification")"
pre_mismatch="$(awk -F'|' '$1 == "pre_vs_stock_mismatches" { print $2 }' <<< "$classification")"
upgraded_mismatch="$(awk -F'|' '$1 == "upgraded_vs_stock_mismatches" { print $2 }' <<< "$classification")"
clone_duplicates="$(awk -F'|' '$1 == "clone_duplicate_keys" { print $2 }' <<< "$classification")"
affected_prod_duplicates="$(awk -F'|' '$1 == "affected_production_duplicate_keys" { print $2 }' <<< "$classification")"
affected_clone_duplicates="$(awk -F'|' '$1 == "affected_clone_duplicate_keys" { print $2 }' <<< "$classification")"
new_duplicates="$(awk -F'|' '$1 == "new_duplicate_keys" { print $2 }' <<< "$classification")"
global_duplicate_set_changed="$(awk -F'|' '$1 == "global_duplicate_set_changed" { print $2 }' <<< "$classification")"
# A pre-migration mismatch is expected for a genuinely missing balance; the
# upgraded total must reconcile to the authoritative product stock instead.
if [[ "$class_b" == 0 && "$class_c" == 0 && "$upgraded_mismatch" == 0 && "$unique_constraint_count" -gt 0 && "$affected_prod_duplicates" == 0 && "$affected_clone_duplicates" == 0 && "$new_duplicates" == 0 && "$global_duplicate_set_changed" == 0 ]]; then
  if [[ "$clone_duplicates" -gt 0 ]]; then
    echo "CONCLUSION: SAFE EXPECTED BACKFILL WITH PRE-EXISTING DATA WARNING"
  else
    echo "CONCLUSION: SAFE EXPECTED BACKFILL"
  fi
else
  echo "CONCLUSION: UNSAFE DUPLICATION" >&2
  exit 1
fi
