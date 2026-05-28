import os
import sys
from functools import lru_cache
from pydantic import BaseModel
from dotenv import load_dotenv


if "pytest" not in sys.modules:
    load_dotenv()


ACCEPTED_APP_ENVS = {"local", "test", "preview", "staging", "production"}
DEPLOYED_APP_ENVS = {"preview", "staging", "production"}


class Settings(BaseModel):
    app_name: str = "Amazon Ads AI Automation Control Center"
    app_version: str = "0.1.0"
    app_env: str | None = None
    api_base_url: str = "http://localhost:8000"
    web_app_url: str = "http://localhost:3000"
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    database_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_publishable_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    storage_adapter: str = "supabase"
    allow_fake_storage_in_preview: bool = False
    supabase_storage_uploads_bucket: str = "raw-uploads"
    local_upload_storage_root: str = ".local-storage/uploads"
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_default_model: str | None = None
    ai_fallback_provider: str | None = None
    ai_fallback_api_key: str | None = None
    ai_fallback_model: str | None = None
    ai_fallback_base_url: str | None = None
    ai_recommendation_mode: str = "deterministic_fallback"
    agent_ai_config_json: str | None = None
    ai_request_timeout_seconds: int = 60
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    agent_orchestrator: str = "langgraph"
    queue_backend: str = "local"
    redis_url: str | None = None
    langgraph_checkpoint_backend: str = "postgres"

    @property
    def is_known_app_env(self) -> bool:
        return self.app_env in ACCEPTED_APP_ENVS

    @property
    def is_local_or_test(self) -> bool:
        return self.app_env in {"local", "test"}

    @property
    def is_deployed_environment(self) -> bool:
        return self.app_env in DEPLOYED_APP_ENVS


@lru_cache
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL") or None
    if database_url and database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    app_env = os.getenv("APP_ENV") or None
    default_storage_adapter = "fake" if app_env in {"local", "test"} else "supabase"

    return Settings(
        app_name=os.getenv("PUBLIC_APP_NAME", "Amazon Ads AI Automation Control Center"),
        app_env=app_env,
        api_base_url=os.getenv("API_BASE_URL", "http://localhost:8000"),
        web_app_url=os.getenv("WEB_APP_URL", "http://localhost:3000"),
        cors_allowed_origins=tuple(
            origin.strip()
            for origin in os.getenv("CORS_ALLOWED_ORIGINS", os.getenv("WEB_APP_URL", "http://localhost:3000")).split(",")
            if origin.strip()
        ),
        database_url=database_url,
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY") or None,
        supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET") or None,
        storage_adapter=os.getenv("STORAGE_ADAPTER", default_storage_adapter),
        allow_fake_storage_in_preview=os.getenv("ALLOW_FAKE_STORAGE_IN_PREVIEW", "false").lower() == "true",
        supabase_storage_uploads_bucket=os.getenv("SUPABASE_STORAGE_BUCKET_UPLOADS")
        or os.getenv("SUPABASE_STORAGE_UPLOADS_BUCKET", "raw-uploads"),
        local_upload_storage_root=os.getenv("LOCAL_UPLOAD_STORAGE_ROOT", ".local-storage/uploads"),
        ai_provider=os.getenv("AI_PROVIDER"),
        ai_api_key=os.getenv("AI_API_KEY"),
        ai_base_url=os.getenv("AI_BASE_URL"),
        ai_default_model=os.getenv("AI_DEFAULT_MODEL"),
        ai_fallback_provider=os.getenv("AI_FALLBACK_PROVIDER", "freemodel"),
        ai_fallback_api_key=os.getenv("AI_FALLBACK_API_KEY"),
        ai_fallback_model=os.getenv("AI_FALLBACK_MODEL", "FRE-5.5"),
        ai_fallback_base_url=os.getenv("AI_FALLBACK_BASE_URL", "https://api.freemodel.dev/v1"),
        ai_recommendation_mode=os.getenv("AI_RECOMMENDATION_MODE", "deterministic_fallback"),
        agent_ai_config_json=os.getenv("ADSURF_AGENT_AI_CONFIG_JSON") or None,
        ai_request_timeout_seconds=int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        agent_orchestrator=os.getenv("AGENT_ORCHESTRATOR", "langgraph"),
        queue_backend=os.getenv("QUEUE_BACKEND", "local"),
        redis_url=os.getenv("REDIS_URL") or None,
        langgraph_checkpoint_backend=os.getenv("LANGGRAPH_CHECKPOINT_BACKEND", "postgres"),
    )
