"""Keyword scoring -> approved set -> campaign plan -> bulk export."""
import json
import sys
import uuid

import requests

BASE = "http://127.0.0.1:8000"
WS = "00000000-0000-0000-0000-000000000001"
USER = "11111111-1111-1111-1111-111111111111"
H = {"x-user-id": USER, "x-test-workspaces": f"{WS}:owner"}

def idemp():
    return {"Idempotency-Key": str(uuid.uuid4())}


def show(label, r, n=1800):
    print(f"\n[{r.status_code}] {label}: {r.text[:n]}")
    try:
        return r.json()
    except Exception:
        return None


st = json.load(open("e2e_state.json"))
upload_id = st["upload_id"]
product_id = st["product_id"]
print("Re-using upload_id =", upload_id, "product_id =", product_id)

# Get column profile to get its id
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/column-profile",
    headers=H, timeout=30,
)
prof = r.json()
profile_id = prof["data"]["profile"]["id"]
cols = prof["data"]["columns"]
print(f"profile_id = {profile_id}, columns = {len(cols)}")
print("Cols:", [c["original_column_name"] for c in cols][:10])

# Create column mapping: search_term -> "Customer Search Term"
print("\n=== 1) Create column mapping ===")
payload = {
    "column_profile_id": profile_id,
    "mapping_json": {
        "search_term": "Customer Search Term",
        "search_volume": "Impressions",
        "competitor_rank_columns": ["Clicks", "Spend"],
    },
}
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/column-mappings",
    json=payload, headers=H, timeout=60,
)
mapping = show("create column mapping", r, 1500)
if r.status_code >= 400:
    sys.exit(1)
mapping_id = mapping["data"]["id"]
print("mapping_id =", mapping_id, "status =", mapping["data"]["status"])

# Approve
print("\n=== 2) Approve column mapping ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/column-mappings/{mapping_id}/approve",
    headers=H, timeout=30,
)
show("approve mapping", r, 1200)

# Score
print("\n=== 3) Run keyword scoring ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/column-mappings/{mapping_id}/score",
    headers={**H, **idemp()}, timeout=600,
)
sc = show("score", r, 3000)
if r.status_code >= 400:
    sys.exit(1)
scoring_run_id = sc["data"]["id"] if "id" in sc["data"] else sc["data"].get("scoring_run", {}).get("id")
print("scoring_run_id =", scoring_run_id)

# Inspect scoring run
print("\n=== 4) Get scoring run ===")
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/scoring-runs/{scoring_run_id}",
    headers=H, timeout=30,
)
show("scoring run", r, 1500)

# List candidates (review)
print("\n=== 5) Review candidates ===")
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/scoring-runs/{scoring_run_id}/candidates/review?page=1&page_size=20",
    headers=H, timeout=60,
)
cands = show("candidates review", r, 4000)

# Create approved keyword set
print("\n=== 6) Create approved keyword set ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/scoring-runs/{scoring_run_id}/approved-keyword-sets",
    json={"name": "Real Test Approved Set", "notes": "From SP search term report E2E test"},
    headers={**H, **idemp()}, timeout=120,
)
appr = show("approved set", r, 2000)
if r.status_code >= 400:
    sys.exit(1)
keyword_set_id = appr["data"]["id"]

# Get items
print("\n=== 7) List approved set items ===")
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/approved-keyword-sets/{keyword_set_id}/items?limit=5",
    headers=H, timeout=30,
)
show("items", r, 2000)

# Campaign plan
print("\n=== 8) Generate campaign plan ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/products/{product_id}/campaign-plans",
    json={"approved_keyword_set_id": keyword_set_id, "plan_name": "E2E Real Plan"},
    headers={**H, **idemp()}, timeout=180,
)
plan = show("campaign plan", r, 3000)
if r.status_code >= 400:
    sys.exit(1)
plan_id = plan["data"]["id"]

# Approve plan
print("\n=== 9) Approve plan ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/campaign-plans/{plan_id}/approve",
    headers={**H, **idemp()}, timeout=60,
)
show("approve plan", r, 1500)

# Export
print("\n=== 10) Export bulk sheet ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/campaign-plans/{plan_id}/exports",
    headers={**H, **idemp()}, timeout=120,
)
exp = show("export", r, 2000)

print("\nDONE keyword phase")
