from pathlib import Path
import json
import os
import urllib.error
import urllib.request
from uuid import uuid4


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8720")
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://127.0.0.1:4310")
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000001"
REPORT_FILES = [
    "Sponsored_Products_Search_term_report (1).xlsx",
    "Sponsored_Products_Search_term_report (2).xlsx",
]
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def main() -> None:
    product = request(
        "POST",
        f"/v1/workspaces/{WORKSPACE_ID}/products",
        body={
            "product_name": "Sponsored Products Search Term Reports Demo",
            "marketplace": "US",
            "currency": "USD",
            "target_acos": "0.5000",
            "default_budget": "10.0000",
            "default_bid": "1.0000",
        },
    )["data"]
    print(f"product_id={product['id']}")

    for filename in REPORT_FILES:
        path = Path(filename)
        content = path.read_bytes()
        upload = request(
            "POST",
            f"/v1/workspaces/{WORKSPACE_ID}/products/{product['id']}/uploads/init",
            body={
                "original_filename": filename,
                "mime_type": XLSX_MIME_TYPE,
                "file_size_bytes": len(content),
                "source_type": "competitor_keyword_research",
            },
            extra_headers={"Idempotency-Key": f"import-{filename}-{uuid4()}"},
        )["data"]
        upload_object(upload_id=upload["upload_id"], content=content)
        confirmed = request(
            "POST",
            f"/v1/workspaces/{WORKSPACE_ID}/uploads/{upload['upload_id']}/confirm",
            body={},
            extra_headers={"Idempotency-Key": f"confirm-{filename}-{uuid4()}"},
        )["data"]
        print(f"queued {filename}: upload_id={upload['upload_id']} job_id={confirmed['job_id']}")

    processed = request("POST", "/v1/dev/process-upload-jobs")["data"]
    print(f"processed_jobs={processed['processed']}")

    uploads = request("GET", f"/v1/workspaces/{WORKSPACE_ID}/uploads?product_id={product['id']}")["data"]
    for upload in uploads:
        runs = request("GET", f"/v1/workspaces/{WORKSPACE_ID}/uploads/{upload['id']}/parse-runs")["data"]
        profile = request("POST", f"/v1/workspaces/{WORKSPACE_ID}/uploads/{upload['id']}/column-profile")["data"]
        first_run = runs[0] if runs else {}
        print(
            f"{upload['original_filename']}: status={upload['status']} "
            f"rows={first_run.get('parsed_rows_count', 0)} "
            f"errors={first_run.get('error_rows_count', 0)} "
            f"columns={len(profile['columns'])}"
        )

    print(f"open={WEB_APP_URL}/products/{product['id']}/uploads")


def request(method: str, path: str, *, body: dict | None = None, extra_headers: dict | None = None) -> dict:
    headers = auth_headers()
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed with {exc.code}: {message}") from exc


def upload_object(*, upload_id: str, content: bytes) -> None:
    req = urllib.request.Request(
        BASE_URL + f"/v1/workspaces/{WORKSPACE_ID}/uploads/{upload_id}/object",
        data=content,
        method="PUT",
        headers=auth_headers(),
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        response.read()


def auth_headers() -> dict:
    return {
        "x-user-id": USER_ID,
        "x-test-workspaces": f"{WORKSPACE_ID}:analyst",
    }


if __name__ == "__main__":
    main()
