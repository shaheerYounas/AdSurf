from fastapi import APIRouter

from apps.api.app.api.v1.account_imports import router as account_imports_router
from apps.api.app.api.v1.agents import router as agents_router
from apps.api.app.api.v1.bulk_products import router as bulk_products_router
from apps.api.app.api.v1.bulk_sheet import router as bulk_sheet_router
from apps.api.app.api.v1.campaigns import router as campaigns_router
from apps.api.app.api.v1.competitor import router as competitor_router
from apps.api.app.api.v1.competitor_research import router as competitor_research_router
from apps.api.app.api.v1.dev import router as dev_router
from apps.api.app.api.v1.monitoring import router as monitoring_router
from apps.api.app.api.v1.products import router as products_router
from apps.api.app.api.v1.file_upload import router as file_upload_router
from apps.api.app.api.v1.uploads import router as uploads_router
from apps.api.app.api.v1.custom_agents import router as custom_agents_router
from apps.api.app.api.v1.insights import router as insights_router
from apps.api.app.api.v1.marketing_pipeline import router as marketing_pipeline_router
from apps.api.app.api.v1.workflows import router as workflows_router

api_router = APIRouter()
api_router.include_router(account_imports_router, prefix="/v1", tags=["account-imports"])
api_router.include_router(agents_router, prefix="/v1", tags=["agents"])
api_router.include_router(bulk_products_router, prefix="/v1", tags=["bulk-product-import"])
api_router.include_router(bulk_sheet_router, prefix="/v1", tags=["bulk-sheet"])
api_router.include_router(competitor_router, prefix="/v1", tags=["competitor"])
api_router.include_router(competitor_research_router, prefix="/v1", tags=["competitor-research"])
api_router.include_router(products_router, prefix="/v1", tags=["product-profiles"])
api_router.include_router(file_upload_router, prefix="/v1", tags=["file-uploads"])
api_router.include_router(uploads_router, prefix="/v1", tags=["uploads"])
api_router.include_router(campaigns_router, prefix="/v1", tags=["campaigns"])
api_router.include_router(monitoring_router, prefix="/v1", tags=["monitoring"])
api_router.include_router(dev_router, prefix="/v1", tags=["dev"])
api_router.include_router(custom_agents_router, prefix="/v1", tags=["custom-agents"])
api_router.include_router(insights_router, prefix="/v1", tags=["insights"])
api_router.include_router(workflows_router, prefix="/v1", tags=["workflows"])
api_router.include_router(marketing_pipeline_router, prefix="/v1", tags=["marketing-pipeline"])
