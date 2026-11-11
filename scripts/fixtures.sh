#!/usr/bin/env bash
# Reproduce data/demo_small from the committed origin scenarios.
#
# Deviation D1 (recorded here because the target layout has no data README):
#   The origin contractors_control scenario is 3 businesses x 3 customers, not
#   5 x 20. demo_small therefore uses those three pairs plus two pairs from
#   contractors/contractors_10_30 (business_0005/customer_0002 and
#   business_0008/customer_0003), then replicates each of the five base
#   customers four times with fresh ids/names and identical
#   menu_features/amenities/request. Every other YAML key is copied verbatim.
#   Business progenitor_customer values are repointed at the first demo
#   customer of the matching base group.
set -euo pipefail
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  for candidate in python3 python python.exe; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done
fi
if [[ -z "$PYTHON" ]]; then
  echo "fixtures.sh requires Python 3 with PyYAML" >&2
  exit 1
fi


ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="data/demo_small"
CONTROL="data/competitive_description/contractors_control"
TEN="data/contractors/contractors_10_30"

rm -rf "$OUT"
mkdir -p "$OUT/businesses" "$OUT/customers"

SOURCE_BUSINESSES=(
  "$CONTROL/businesses/business_0001.yaml"
  "$CONTROL/businesses/business_0004.yaml"
  "$CONTROL/businesses/business_0007.yaml"
  "$TEN/businesses/business_0005.yaml"
  "$TEN/businesses/business_0008.yaml"
)

SOURCE_CUSTOMERS=(
  "$CONTROL/customers/customer_0001.yaml"
  "$CONTROL/customers/customer_0002.yaml"
  "$CONTROL/customers/customer_0003.yaml"
  "$TEN/customers/customer_0002.yaml"
  "$TEN/customers/customer_0003.yaml"
)

BASE_NAMES=(
  "Grace Wang"
  "Alexander Chen"
  "Lisa Harris"
  "Alexander Chen"
  "Lisa Harris"
)

for index in "${!SOURCE_BUSINESSES[@]}"; do
  target_number=$((index + 1))
  target_id="$(printf 'business_%04d' "$target_number")"
  first_customer="$(printf 'customer_%04d' $((index * 4 + 1)))"
  cp "${SOURCE_BUSINESSES[$index]}" "$OUT/businesses/${target_id}.yaml"
  sed -i -E \
    "s/^id: .*/id: ${target_id}/; s/^progenitor_customer: .*/progenitor_customer: ${first_customer}/" \
    "$OUT/businesses/${target_id}.yaml"
done

# A base name can repeat across the two origin scenarios (Alexander Chen,
# Lisa Harris). The first group keeps the plain name; later groups with the
# same base name get a " B" marker before the copy suffix so all 20 names are
# unique while the " 2"/" 3"/" 4" copy suffixes stay deterministic.
declare -A USED_NAMES=()
for index in "${!SOURCE_CUSTOMERS[@]}"; do
  base_name="${BASE_NAMES[$index]}"
  for copy in 1 2 3 4; do
    target_number=$((index * 4 + copy))
    target_id="$(printf 'customer_%04d' "$target_number")"
    if (( copy == 1 )); then
      name="$base_name"
    else
      name="$base_name $copy"
    fi
    if [[ -n "${USED_NAMES[$name]:-}" ]]; then
      if (( copy == 1 )); then
        name="$base_name B"
      else
        name="$base_name B $copy"
      fi
    fi
    USED_NAMES[$name]=1
    cp "${SOURCE_CUSTOMERS[$index]}" "$OUT/customers/${target_id}.yaml"
    sed -i -E \
      "s/^id: .*/id: ${target_id}/; s/^name: .*/name: \"${name}\"/" \
      "$OUT/customers/${target_id}.yaml"
  done
done

"$PYTHON" - "$OUT" <<'PY'
import pathlib
import sys

import yaml

root = pathlib.Path(sys.argv[1])
business_files = sorted((root / "businesses").glob("*.yaml"))
customer_files = sorted((root / "customers").glob("*.yaml"))
assert len(business_files) == 5, f"expected 5 businesses, found {len(business_files)}"
assert len(customer_files) == 20, f"expected 20 customers, found {len(customer_files)}"

businesses = [yaml.safe_load(path.read_text()) for path in business_files]
customers = [yaml.safe_load(path.read_text()) for path in customer_files]

business_ids = [business["id"] for business in businesses]
assert business_ids == [f"business_{i:04d}" for i in range(1, 6)]
customer_ids = [customer["id"] for customer in customers]
assert customer_ids == [f"customer_{i:04d}" for i in range(1, 21)]
names = [customer["name"] for customer in customers]
assert len(set(names)) == 20, f"customer names are not unique: {names}"

union = set()
for business in businesses:
    union.update(business["menu_features"].keys())

for index, customer in enumerate(customers):
    base_business = businesses[index // 4]
    missing = set(customer["menu_features"]) - union
    assert not missing, f"{customer['id']} menu items outside union: {sorted(missing)}"
    not_in_base = set(customer["menu_features"]) - set(base_business["menu_features"])
    assert not not_in_base, (
        f"{customer['id']} menu items missing from base {base_business['id']}: "
        f"{sorted(not_in_base)}"
    )
    for amenity in customer["amenity_features"]:
        assert base_business["amenity_features"].get(amenity) is True, (
            f"{customer['id']} requires {amenity!r} but {base_business['id']} "
            "does not offer it"
        )

for path in [*business_files, *customer_files]:
    text = path.read_text()
    assert "\t" not in text, f"tabs are not allowed in {path}"
    assert text.endswith("\n"), f"{path} must end with a newline"

print(f"demo_small OK: {len(business_files)} businesses, {len(customer_files)} customers")
PY
