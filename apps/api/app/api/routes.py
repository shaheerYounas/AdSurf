from fastapi import APIRouter

from apps.api.app.api.v1.account_imports import router as account_imports_router
from apps.api.app.api.v1.agents import router as agents_router
from apps.api.app.api.v1.campaigns import router as campaigns_router
from apps.api.app.api.v1.dev import router as dev_router
from apps.api.app.api.v1.monitoring import router as monitoring_router
from apps.api.app.api.v1.products import router as products_router
from apps.api.app.api.v1.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(account_imports_router, prefix="/v1", tags=["account-imports"])
api_router.include_router(agents_router, prefix="/v1", tags=["agents"])
api_router.include_router(products_router, prefix="/v1", tags=["product-profiles"])
api_router.include_router(uploads_router, prefix="/v1", tags=["uploads"])
api_router.include_router(campaigns_router, prefix="/v1", tags=["campaigns"])
api_router.include_router(monitoring_router, prefix="/v1", tags=["monitoring"])
api_router.include_router(dev_router, prefix="/v1", tags=["dev"])
