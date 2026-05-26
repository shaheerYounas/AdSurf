from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import SIGNED_UPLOAD_URL_EXPIRES_SECONDS


@dataclass(frozen=True)
class SignedUploadTarget:
    upload_url: str
    expires_at: datetime


class StorageService(ABC):
    @abstractmethod
    def create_signed_upload_url(self, *, storage_path: str, mime_type: str) -> SignedUploadTarget:
        raise NotImplementedError

    @abstractmethod
    def read_upload_object(self, *, storage_path: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def write_upload_object(self, *, storage_path: str, content: bytes) -> None:
        raise NotImplementedError


class LocalFakeStorageService(StorageService):
    def __init__(self, root: str | None = None) -> None:
        settings = get_settings()
        self._root = Path(root or settings.local_upload_storage_root).resolve()

    def create_signed_upload_url(self, *, storage_path: str, mime_type: str) -> SignedUploadTarget:
        expires_at = datetime.now(UTC) + timedelta(seconds=SIGNED_UPLOAD_URL_EXPIRES_SECONDS)
        encoded_path = quote(storage_path, safe="")
        return SignedUploadTarget(
            upload_url=f"local-fake://signed-upload/{encoded_path}?expires_at={quote(expires_at.isoformat())}",
            expires_at=expires_at,
        )

    def read_upload_object(self, *, storage_path: str) -> bytes:
        path = self._local_path(storage_path)
        if not path.exists() or not path.is_file():
            raise ApiError(code="UPLOAD_OBJECT_NOT_FOUND", message="Uploaded object was not found in storage.", status_code=404)
        return path.read_bytes()

    def write_upload_object(self, *, storage_path: str, content: bytes) -> None:
        path = self._local_path(storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _local_path(self, storage_path: str) -> Path:
        parts = [part for part in PurePosixPath(storage_path.lstrip("/")).parts if part not in {"", "."}]
        path = self._root.joinpath(*parts).resolve()
        if self._root not in path.parents and path != self._root:
            raise ApiError(code="INVALID_STORAGE_PATH", message="Storage path escapes the local storage root.", status_code=400)
        return path


class SupabaseStorageService(StorageService):
    def create_signed_upload_url(self, *, storage_path: str, mime_type: str) -> SignedUploadTarget:
        expires_at = datetime.now(UTC) + timedelta(seconds=SIGNED_UPLOAD_URL_EXPIRES_SECONDS)
        object_path = self._object_path(storage_path)
        response = self._request_json(
            method="POST",
            path=f"/storage/v1/object/upload/sign/{quote(self._bucket(), safe='')}/{quote(object_path, safe='/')}",
            body={},
        )
        signed_url = response.get("signedURL") or response.get("signedUrl") or response.get("url")
        token = response.get("token")
        if signed_url and signed_url.startswith("/"):
            signed_url = f"{self._supabase_url()}/storage/v1{signed_url}"
        if not signed_url and token:
            signed_url = (
                f"{self._supabase_url()}/storage/v1/object/upload/sign/"
                f"{quote(self._bucket(), safe='')}/{quote(object_path, safe='/')}?{urlencode({'token': token})}"
            )
        if not signed_url:
            raise ApiError(
                code="STORAGE_SIGNING_FAILED",
                message="Supabase did not return a signed upload URL.",
                status_code=502,
                details={"response_keys": sorted(response.keys())},
            )
        return SignedUploadTarget(upload_url=signed_url, expires_at=expires_at)

    def read_upload_object(self, *, storage_path: str) -> bytes:
        return self._request_bytes(
            method="GET",
            path=f"/storage/v1/object/{quote(self._bucket(), safe='')}/{quote(self._object_path(storage_path), safe='/')}",
        )

    def write_upload_object(self, *, storage_path: str, content: bytes) -> None:
        self._request_bytes(
            method="POST",
            path=f"/storage/v1/object/{quote(self._bucket(), safe='')}/{quote(self._object_path(storage_path), safe='/')}",
            body=content,
            headers={"Content-Type": "application/octet-stream", "x-upsert": "true"},
        )

    def _request_json(self, *, method: str, path: str, body: dict | None = None) -> dict:
        content = self._request_bytes(
            method=method,
            path=path,
            body=json.dumps(body or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(content.decode("utf-8")) if content else {}

    def _request_bytes(self, *, method: str, path: str, body: bytes | None = None, headers: dict | None = None) -> bytes:
        request_headers = {
            "apikey": self._service_role_key(),
            "Authorization": f"Bearer {self._service_role_key()}",
            **(headers or {}),
        }
        request = Request(f"{self._supabase_url()}{path}", data=body, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise ApiError(
                code="SUPABASE_STORAGE_REQUEST_FAILED",
                message="Supabase Storage request failed.",
                status_code=502 if exc.code >= 500 else exc.code,
                details={"storage_status_code": exc.code, "storage_error": message[:500]},
            ) from exc
        except URLError as exc:
            raise ApiError(
                code="SUPABASE_STORAGE_UNREACHABLE",
                message="Supabase Storage could not be reached.",
                status_code=503,
                details={"reason": str(exc.reason)},
            ) from exc

    def _supabase_url(self) -> str:
        settings = get_settings()
        if not settings.supabase_url:
            raise ApiError(code="SUPABASE_URL_NOT_CONFIGURED", message="SUPABASE_URL is required for Supabase storage.", status_code=503)
        return settings.supabase_url.rstrip("/")

    def _service_role_key(self) -> str:
        settings = get_settings()
        if not settings.supabase_service_role_key:
            raise ApiError(
                code="SUPABASE_SERVICE_ROLE_KEY_NOT_CONFIGURED",
                message="SUPABASE_SERVICE_ROLE_KEY is required for server-side Supabase storage.",
                status_code=503,
            )
        return settings.supabase_service_role_key

    def _bucket(self) -> str:
        return get_settings().supabase_storage_uploads_bucket

    def _object_path(self, storage_path: str) -> str:
        parts = [part for part in PurePosixPath(storage_path.lstrip("/")).parts if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise ApiError(code="INVALID_STORAGE_PATH", message="Storage path is invalid.", status_code=400)
        return str(PurePosixPath(*parts))


def get_storage_service() -> StorageService:
    settings = get_settings()
    if settings.storage_adapter == "fake":
        if settings.is_local_or_test or (settings.app_env == "preview" and settings.allow_fake_storage_in_preview):
            return LocalFakeStorageService()
        raise ApiError(
            code="STORAGE_ADAPTER_NOT_ALLOWED",
            message="Fake storage adapter is only allowed in local/test or explicitly enabled preview.",
            status_code=503,
        )
    if settings.storage_adapter == "supabase":
        return SupabaseStorageService()
    raise ApiError(
        code="STORAGE_ADAPTER_NOT_CONFIGURED",
        message="Storage adapter must be configured as fake or supabase.",
        status_code=503,
    )
