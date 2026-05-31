"""Continue E2E test: monitoring path."""
import json, uuid, sys
from pathlib import Path
import requests

BASE = "http://127.0.0.1:8000"
WS = "00000000-0000-0000-0000-000000000001"
USER = "11111111-1111-1111-1111-111111111111"
H = {"x-user-id": USER, "x-test-workspaces": f"{WS}:owner"}
def idemp(): return {"Idempotency-Key": str(uuid.uuid4())}

FILE = Path("Sponsored_Products_Search_term_report (1).xlsx")

def show(label, r, n=1500):
    print(f"[{r.status_code}] {label}: {r.text[:n]}")
    try: return r.json()
    except: return None

# Reuse product or create new
prod = requests.post(f"{BASE}/v1/workspaces/{WS}/products",
    json={"product_name":"A4 Light Pad Monitoring","asin":"B08LVC66BP","sku":"LP-MON-01",
          "target_acos":"0.30","default_budget":"20.00","default_bid":"1.20"},
    headers=H, timeout=30).json()
product_id = prod["data"]["id"]
print("product_id =", product_id)

# Init upload with SOURCE_TYPE = sp_search_term_report
size = FILE.stat().st_size
init_payload = {
    "original_filename": FILE.name,
    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "file_size_bytes": size,
    "source_type": "amazon_ads_sp_search_term_report",
}
r = requests.post(f"{BASE}/v1/workspaces/{WS}/products/{product_id}/uploads/init",
    json=init_payload, headers={**H, **idemp()}, timeout=30)
init = show("init upload (monitoring)", r, 700)
upload_id = init["data"]["upload_id"]

# PUT bytes
with FILE.open("rb") as f: data = f.read()
r = requests.put(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/object",
    data=data, headers={**H, "Content-Type": init_payload["mime_type"]}, timeout=60)
print("put status =", r.status_code)

# Confirm
r = requests.post(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}/confirm",
    json={"file_size_bytes": size}, headers={**H, **idemp()}, timeout=60)
show("confirm", r, 400)

# Process
r = requests.post(f"{BASE}/v1/dev/process-upload-jobs", headers=H, timeout=240)
show("process upload jobs", r, 600)

# Verify source_type
r = requests.get(f"{BASE}/v1/workspaces/{WS}/uploads/{upload_id}", headers=H, timeout=30)
u = show("upload state", r, 700)

# Create monitoring import
r = requests.post(
    f"{BASE}/v1/workspaces/{WS}/products/{product_id}/monitoring/imports",
    json={"upload_id": upload_id}, headers={**H, **idemp()}, timeout=30,
)
mi = show("create monitoring import", r, 1500)
if r.status_code >= 400: sys.exit(1)
import_id = mi["data"]["import_record"]["id"]

# Process monitoring job (14-day rules + agents)
r = requests.post(f"{BASE}/v1/dev/process-monitoring-jobs", headers=H, timeout=600)
show("process monitoring jobs", r, 4000)

# Summary
r = requests.get(f"{BASE}/v1/workspaces/{WS}/products/{product_id}/monitoring/summary", headers=H, timeout=30)
show("monitoring summary", r, 2000)

# Monitoring rows
r = requests.get(f"{BASE}/v1/workspaces/{WS}/products/{product_id}/monitoring?limit=3", headers=H, timeout=30)
show("monitoring rows", r, 2000)

# Recommendations
r = requests.get(f"{BASE}/v1/workspaces/{WS}/products/{product_id}/recommendations?limit=10", headers=H, timeout=30)
show("recommendations", r, 4000)

# Save state
Path("e2e_state_monitoring.json").write_text(json.dumps({"product_id":product_id,"upload_id":upload_id,"import_id":import_id}))
print("\nDONE")
