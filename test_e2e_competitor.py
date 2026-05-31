"""Competitor scoring + campaign generation + bulk export."""
import json
import sys
import uuid
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
WS = "00000000-0000-0000-0000-000000000001"
USER = "11111111-1111-1111-1111-111111111111"
H = {"x-user-id": USER, "x-test-workspaces": f"{WS}:owner"}

def idemp():
    return {"Idempotency-Key": str(uuid.uuid4())}

FILE = Path("Sponsored_Products_Search_term_report (1).xlsx")

def show(label, r, n=1500):
    print(f"\n[{r.status_code}] {label}: {r.text[:n]}")
    try:
        return r.json()
    except Exception:
        return None

# 1) Upload competitor file (multipart)
print("=== 1) Upload competitor file (multipart) ===")
with FILE.open("rb") as f:
    files = {"file": (FILE.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(
        f"{BASE}/v1/workspaces/{WS}/competitor-uploads",
        files=files, headers=H, timeout=180,
    )
up = show("competitor upload", r, 2000)
if r.status_code >= 400:
    sys.exit(1)
upload_id = up["data"]["upload"]["id"]
print("upload_id =", upload_id)

# 2) Score
print("\n=== 2) Score competitor upload ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/competitor-uploads/{upload_id}/score",
    headers={**H, **idemp()}, timeout=240,
)
sc = show("score", r, 3000)
if r.status_code >= 400:
    sys.exit(1)

# 3) List scoring run rows
print("\n=== 3) List rows ===")
r = requests.get(
    f"{BASE}/v1/workspaces/{WS}/competitor-uploads/{upload_id}/rows?limit=5",
    headers=H, timeout=60,
)
show("rows", r, 2500)

# 4) Verify
print("\n=== 4) Verify ===")
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/competitor-uploads/{upload_id}/verify",
    headers={**H, **idemp()}, timeout=120,
)
show("verify", r, 2500)

# 5) Generate campaigns (assigns to a product profile)
print("\n=== 5) Create product + generate campaigns ===")
prod = requests.post(
    f"{BASE}/v1/workspaces/{WS}/products",
    json={"product_name": "A4 Light Pad Comp", "asin": "B08LVC66BP", "sku": "LP-CMP-01",
          "target_acos": "0.30", "default_budget": "20.00", "default_bid": "1.20"},
    headers=H, timeout=30,
).json()
product_id = prod["data"]["id"]
print("product_id =", product_id)

r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/competitor-uploads/{upload_id}/generate-campaigns",
    json={"product_id": product_id},
    headers={**H, **idemp()}, timeout=240,
)
gen = show("generate campaigns", r, 4000)
if r.status_code >= 400:
    sys.exit(1)

Path("e2e_state_comp.json").write_text(json.dumps({
    "upload_id": upload_id,
    "product_id": product_id,
    "gen": gen.get("data") if gen else None,
}, default=str))
print("\nDONE comp phase")
