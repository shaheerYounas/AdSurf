"""End-to-end smoke test of AdSurf app against a real Amazon search term report."""
import json, sys, time
from pathlib import Path
import requests

BASE = "http://127.0.0.1:8000"
WS = "00000000-0000-0000-0000-000000000001"
USER = "qualheimpilot@gmail.com"
HEADERS = {"x-user-id": USER, "x-test-workspaces": f"{WS}:owner"}
import uuid
def idemp(): return {"Idempotency-Key": str(uuid.uuid4())}
FILE_PATH = Path("Sponsored_Products_Search_term_report (1).xlsx")

def step(name): print(f"\n=== {name} ===")
def show(label, resp, head=1500):
    snippet = resp.text[:head]
    print(f"[{resp.status_code}] {label}: {snippet}")
    try: return resp.json()
    except: return None

# 1: Create product
step("1) Create product profile")
prod_payload = {"product_name":"A4 Light Pad Test","asin":"B08LVC66BP","sku":"LP-A4-002",
    "marketplace":"US","currency":"USD","target_acos":"0.30","default_budget":"20.00",
    "default_bid":"1.20","product_cost":"8.50","product_price":"29.99",
    "category":"Office Products","brand_name":"Litpad"}
r = requests.post(f"{BASE}/v1/workspaces/{WS}/products", json=prod_payload, headers=HEADERS, timeout=30)
prod = show("create product", r, 600)
if r.status_code >= 400: sys.exit(1)
product_id = prod["data"]["id"]

# 2: Init upload
step("2) Init upload")
size = FILE_PATH.stat().st_size
init_payload = {
    "original_filename": FILE_PATH.name,
    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "file_size_bytes": size,
}
r = requests.post(f"{BASE}/v1/workspaces/{WS}/products/{product_id}/uploads/init",
    json=init_payload, headers={**HEADERS, **idemp()}, timeout=30)
init = show("init upload", r, 1200)
if r.status_code >= 400: sys.exit(1)
upload_id = init["data"]["upload_id"]
put_url = init["data"]["upload_url"]
print("upload_id =", upload_id)
print("put_url   =", put_url)

# 3: PUT bytes
step("3) PUT object bytes")
with FILE_PATH.open("rb") as f: data = f.read()
target = f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/object"
r = requests.put(target, data=data, headers={**HEADERS, "Content-Type": init_payload["mime_type"]}, timeout=60)
show("PUT", r, 400)

# 4: Confirm
step("4) Confirm upload")
r = requests.post(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/confirm",
    json={"file_size_bytes": size}, headers={**HEADERS, **idemp()}, timeout=60)
show("confirm", r, 800)

# 5: Process jobs
step("5) Run dev process-upload-jobs (parse)")
r = requests.post(f"{BASE}/v1/dev/process-upload-jobs", headers=HEADERS, timeout=240)
proc = show("process jobs", r, 1500)

# 6: Get parse run rows
step("6) Get upload state")
r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}", headers=HEADERS, timeout=30)
show("upload state", r, 800)

step("7) List parse runs")
r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/parse-runs", headers=HEADERS, timeout=30)
parse_runs = show("parse runs", r, 1500)
prs = parse_runs.get("data", [])
parse_run_id = prs[0]["id"] if prs else None
print("parse_run_id =", parse_run_id)

if parse_run_id:
    step("8) Get parse run rows sample")
    r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/parse-runs/{parse_run_id}/rows?page=1&page_size=3",
        headers=HEADERS, timeout=30)
    show("rows sample", r, 1500)

step("9) Report-type detection")
r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/report-detection", headers=HEADERS, timeout=30)
show("report detection", r, 1500)

step("10) Get column profile")
r = requests.post(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/column-profile", headers=HEADERS, timeout=30)
show("post column profile", r, 800)
r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/column-profile", headers=HEADERS, timeout=30)
prof = show("column profile", r, 1500)

step("11) Get column mappings (suggestions)")
r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/column-mappings", headers=HEADERS, timeout=30)
maps = show("column mappings", r, 2000)

# Save state for next phase
state = {"product_id": product_id, "upload_id": upload_id,
        "parse_run_id": parse_run_id}
Path("e2e_state.json").write_text(json.dumps(state))
print("\nState saved:", state)
