"""Continue: approved set + campaign plan + bulk export."""
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

def show(label, r, n=2000):
    print(f"\n[{r.status_code}] {label}: {r.text[:n]}")
    try:
        return r.json()
    except Exception:
        return None

st = json.load(open("e2e_state.json"))
product_id = st["product_id"]
scoring_run_id = "fed7c851-5223-46eb-9aae-99a144de91d4"

# Get scoring run summary
print("=== Scoring run ===")
r = requests.get(f"{BASE}/v1/workspaces/{WS}/scoring-runs/{scoring_run_id}", headers=H, timeout=30)
show("scoring run", r, 1500)

# List candidates review
print("\n=== Candidates review (top 5) ===")
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/scoring-runs/{scoring_run_id}/candidates/review?page=1&page_size=5",
    headers=H, timeout=60,
)
show("candidates review", r, 4000)

# Approved set
print("\n=== Create approved keyword set ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/scoring-runs/{scoring_run_id}/approved-keyword-sets",
    json={"name": "E2E Real Approved Set", "notes": "From SP search term"},
    headers={**H, **idemp()}, timeout=300,
)
appr = show("approved set", r, 2500)
if r.status_code >= 400:
    sys.exit(1)
keyword_set_id = appr["data"]["id"]
print("keyword_set_id =", keyword_set_id)

# Items
print("\n=== Approved set items (5) ===")
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/approved-keyword-sets/{keyword_set_id}/items?limit=5",
    headers=H, timeout=30,
)
show("items", r, 2500)

# Campaign plan
print("\n=== Generate campaign plan ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/products/{product_id}/campaign-plans",
    json={"approved_keyword_set_id": keyword_set_id, "plan_name": "E2E Real Plan"},
    headers={**H, **idemp()}, timeout=300,
)
plan = show("campaign plan", r, 4000)
if r.status_code >= 400:
    sys.exit(1)
plan_id = plan["data"]["id"]
print("plan_id =", plan_id)

# Approve plan
print("\n=== Approve plan ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/campaign-plans/{plan_id}/approve",
    headers={**H, **idemp()}, timeout=60,
)
show("approve plan", r, 1500)

# Export bulk
print("\n=== Bulk export ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/campaign-plans/{plan_id}/exports",
    headers={**H, **idemp()}, timeout=300,
)
exp = show("export", r, 3000)
if r.status_code >= 400:
    sys.exit(1)

print("\nDONE")
