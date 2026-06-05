"""Competitor research API routes.

POST   /v1/workspaces/{workspace_id}/competitor-research
  — Create a new research run and build the keyword queue.

GET    /v1/workspaces/{workspace_id}/competitor-research
  — List research runs.

GET    /v1/workspaces/{workspace_id}/competitor-research/{run_id}
  — Get run detail with keywords + insights.

POST   /v1/workspaces/{workspace_id}/competitor-research/{run_id}/start
  — Start (or resume) running browser searches.
  NOTE: This endpoint runs synchronously — NOT for production async use.
  In production, enqueue this as a background job.

POST   /v1/workspaces/{workspace_id}/competitor-research/{run_id}/control
  — Pause, resume, or cancel a run.

GET    /v1/workspaces/{workspace_id}/competitor-research/{run_id}/results
  — List captured competitor products for a run.

GET    /v1/workspaces/{workspace_id}/competitor-research/{run_id}/insights
  — List AI insights for a run.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_READ_ROLES,
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.competitor_research import (
    CompetitorAiInsight,
    CompetitorResearchControlRequest,
    CompetitorResearchCreateRequest,
    CompetitorResearchKeyword,
    CompetitorResearchResult,
    CompetitorResearchRun,
    CompetitorResearchRunDetail,
    CompetitorResearchStatus,
)
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.competitor_ai_analysis import CompetitorAiAnalysisService
from apps.api.app.services.competitor_research_runner import (
    CompetitorResearchRunner,
    build_keyword_queue,
)
from sqlalchemy import text

router = APIRouter()


# ─── Create run ───────────────────────────────────────────────────────────────


@router.post(
    "/workspaces/{workspace_id}/competitor-research",
    status_code=status.HTTP_201_CREATED,
    summary="Create a competitor research run with keyword queue",
)
def create_competitor_research_run(
    workspace_id: UUID,
    payload: CompetitorResearchCreateRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    # Fetch high-spend and move-to-exact terms from existing recommendations
    high_spend_terms = _fetch_high_spend_terms(workspace_id, payload.product_id)
    move_to_exact_terms = _fetch_move_to_exact_terms(workspace_id, payload.product_id) if payload.include_move_to_exact_terms else []

    keyword_queue = build_keyword_queue(
        seed_keywords=payload.seed_keywords,
        manual_keywords=payload.manual_keywords,
        high_spend_terms=high_spend_terms if payload.include_high_spend_terms else [],
        move_to_exact_terms=move_to_exact_terms,
    )

    # Limit to max_keywords_per_run
    keyword_queue = keyword_queue[: payload.settings.max_keywords_per_run]

    run_id = _persist_run(workspace_id, payload, keyword_queue, principal.user_id)
    run = _load_run(workspace_id, run_id)

    return success_response(data=run.model_dump(mode="json") if run else {"run_id": str(run_id)})


# ─── List runs ────────────────────────────────────────────────────────────────


@router.get(
    "/workspaces/{workspace_id}/competitor-research",
    summary="List competitor research runs",
)
def list_competitor_research_runs(
    workspace_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    runs = _list_runs(workspace_id)
    return success_response(data=[r.model_dump(mode="json") for r in runs], meta={"total": len(runs)})


# ─── Get run detail ───────────────────────────────────────────────────────────


@router.get(
    "/workspaces/{workspace_id}/competitor-research/{run_id}",
    summary="Get research run with keywords and AI insights",
)
def get_competitor_research_run(
    workspace_id: UUID,
    run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    run = _load_run_detail(workspace_id, run_id)
    if not run:
        raise ApiError(code="NOT_FOUND", message="Research run not found.", status_code=404)
    return success_response(data=run.model_dump(mode="json"))


# ─── Start run ────────────────────────────────────────────────────────────────


@router.post(
    "/workspaces/{workspace_id}/competitor-research/{run_id}/start",
    summary="Start or resume a competitor research run (synchronous browser session)",
)
def start_competitor_research_run(
    workspace_id: UUID,
    run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    """
    SAFETY NOTE: This opens a VISIBLE browser (headless=False by default).
    The user can see the browser session. If Amazon shows a CAPTCHA,
    the run pauses — it does NOT attempt to bypass verification.
    No Amazon Ads live changes are made.
    """
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    run = _load_run_detail(workspace_id, run_id)
    if not run:
        raise ApiError(code="NOT_FOUND", message="Research run not found.", status_code=404)

    if run.status == CompetitorResearchStatus.RUNNING:
        raise ApiError(code="ALREADY_RUNNING", message="This run is already in progress.", status_code=409)

    if run.status == CompetitorResearchStatus.SUCCEEDED:
        raise ApiError(code="ALREADY_COMPLETED", message="This run has already completed.", status_code=409)

    # Get queued keywords (skip already-completed ones for resume)
    pending_keywords = [k for k in run.keywords if k.status in ("queued", "failed")]
    if not pending_keywords:
        raise ApiError(code="NO_KEYWORDS", message="No keywords left to process.", status_code=400)

    _update_run_status(run_id, CompetitorResearchStatus.RUNNING)

    runner = CompetitorResearchRunner(
        marketplace=run.marketplace,
        max_competitors_per_keyword=run.max_competitors_per_keyword,
        delay_min_seconds=run.delay_min_seconds,
        delay_max_seconds=run.delay_max_seconds,
        open_product_detail_pages=run.open_product_detail_pages,
        headless=run.headless,
    )
    ai_service = CompetitorAiAnalysisService()

    keyword_strings = [k.keyword for k in pending_keywords]

    try:
        search_results = runner.run_keywords(keyword_strings)
    except RuntimeError as exc:
        _update_run_status(run_id, CompetitorResearchStatus.FAILED, error_message=str(exc))
        raise ApiError(
            code="BROWSER_UNAVAILABLE",
            message=str(exc),
            status_code=503,
        ) from exc

    products_captured = 0
    paused = False

    for result, kw_record in zip(search_results, pending_keywords):
        if result.paused_for_verification:
            # Pause the run — do not bypass CAPTCHA
            _update_run_status(
                run_id,
                CompetitorResearchStatus.PAUSED_MANUAL_VERIFICATION,
                paused_reason=(
                    "Amazon requires manual verification. "
                    "Please complete it in the browser window, then resume this run."
                ),
            )
            _update_keyword_status(kw_record.id, "failed", error_message="Paused for manual verification")
            paused = True
            break

        if result.error:
            _update_keyword_status(kw_record.id, "failed", error_message=result.error)
            continue

        # Persist results
        all_results = result.organic_results + result.sponsored_results
        products_captured += len(all_results)
        for r in all_results:
            _persist_result(workspace_id, run_id, kw_record.id, r)

        # Generate AI insight
        insight_data = ai_service.analyse_keyword(
            keyword=result.keyword,
            organic_results=result.organic_results,
            sponsored_results=result.sponsored_results,
        )
        _persist_insight(workspace_id, run_id, kw_record.id, result.keyword, insight_data)

        _update_keyword_status(
            kw_record.id,
            "succeeded",
            search_url=result.search_url,
            screenshot_path=result.screenshot_path,
            organic_count=len(result.organic_results),
            sponsored_count=len(result.sponsored_results),
        )

    if not paused:
        _update_run_status(
            run_id,
            CompetitorResearchStatus.SUCCEEDED,
            keywords_completed=len(search_results),
            products_captured=products_captured,
        )

    final_run = _load_run(workspace_id, run_id)
    return success_response(data={
        "run": final_run.model_dump(mode="json") if final_run else {"run_id": str(run_id)},
        "paused_for_verification": paused,
        "safety_note": (
            "This research used a visible browser session on public Amazon pages. "
            "No Amazon Ads live changes were made."
        ),
    })


# ─── Control ──────────────────────────────────────────────────────────────────


@router.post(
    "/workspaces/{workspace_id}/competitor-research/{run_id}/control",
    summary="Pause, resume, or cancel a research run",
)
def control_competitor_research_run(
    workspace_id: UUID,
    run_id: UUID,
    payload: CompetitorResearchControlRequest,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    valid_actions = {"pause", "resume", "cancel"}
    if payload.action not in valid_actions:
        raise ApiError(code="INVALID_ACTION", message=f"Action must be one of: {valid_actions}", status_code=400)

    run = _load_run(workspace_id, run_id)
    if not run:
        raise ApiError(code="NOT_FOUND", message="Research run not found.", status_code=404)

    if payload.action == "pause":
        _update_run_status(run_id, CompetitorResearchStatus.PAUSED_MANUAL_VERIFICATION, paused_reason=payload.reason or "User paused")
    elif payload.action == "resume":
        if run.status not in (CompetitorResearchStatus.PAUSED_MANUAL_VERIFICATION,):
            raise ApiError(code="NOT_PAUSED", message="Run is not paused.", status_code=409)
        _update_run_status(run_id, CompetitorResearchStatus.QUEUED)
    elif payload.action == "cancel":
        _update_run_status(run_id, CompetitorResearchStatus.CANCELLED)

    updated = _load_run(workspace_id, run_id)
    return success_response(data=updated.model_dump(mode="json") if updated else {"run_id": str(run_id)})


# ─── Results + insights ───────────────────────────────────────────────────────


@router.get(
    "/workspaces/{workspace_id}/competitor-research/{run_id}/results",
    summary="List captured competitor products for a run",
)
def get_competitor_research_results(
    workspace_id: UUID,
    run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    results = _list_results(workspace_id, run_id)
    return success_response(data=[r.model_dump(mode="json") for r in results], meta={"total": len(results)})


@router.get(
    "/workspaces/{workspace_id}/competitor-research/{run_id}/insights",
    summary="List AI insights for a run",
)
def get_competitor_research_insights(
    workspace_id: UUID,
    run_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    insights = _list_insights(workspace_id, run_id)
    return success_response(data=[i.model_dump(mode="json") for i in insights], meta={"total": len(insights)})


# ─── DB helpers ───────────────────────────────────────────────────────────────


def _fetch_high_spend_terms(workspace_id: UUID, product_id: UUID | None) -> list[str]:
    try:
        engine = get_database_engine()
        with engine.connect() as conn:
            params = {"wid": str(workspace_id)}
            product_filter = ""
            if product_id:
                product_filter = "AND product_id = :pid"
                params["pid"] = str(product_id)
            rows = conn.execute(
                text(f"""
                    SELECT customer_search_term, SUM(spend) as total_spend
                    FROM monitoring_snapshots
                    WHERE workspace_id = :wid AND customer_search_term IS NOT NULL
                    {product_filter}
                    GROUP BY customer_search_term
                    ORDER BY total_spend DESC
                    LIMIT 30
                """),
                params,
            ).mappings().all()
        return [r["customer_search_term"] for r in rows if r["customer_search_term"]]
    except Exception:
        return []


def _fetch_move_to_exact_terms(workspace_id: UUID, product_id: UUID | None) -> list[str]:
    try:
        engine = get_database_engine()
        with engine.connect() as conn:
            params = {"wid": str(workspace_id)}
            product_filter = ""
            if product_id:
                product_filter = "AND product_id = :pid"
                params["pid"] = str(product_id)
            rows = conn.execute(
                text(f"""
                    SELECT customer_search_term FROM recommendations
                    WHERE workspace_id = :wid
                      AND recommendation_type = 'move_to_exact'
                      AND customer_search_term IS NOT NULL
                    {product_filter}
                    LIMIT 20
                """),
                params,
            ).mappings().all()
        return [r["customer_search_term"] for r in rows if r["customer_search_term"]]
    except Exception:
        return []


def _persist_run(
    workspace_id: UUID,
    payload: CompetitorResearchCreateRequest,
    keyword_queue: list[tuple[str, str, int]],
    actor_user_id,
) -> UUID:
    run_id = uuid4()
    s = payload.settings
    engine = get_database_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO competitor_research_runs (
                    id, workspace_id, product_id,
                    marketplace, max_keywords_per_run, max_competitors_per_keyword,
                    delay_min_seconds, delay_max_seconds,
                    open_product_detail_pages, headless,
                    status, keywords_total,
                    created_by, created_at, updated_at
                ) VALUES (
                    :id, :wid, :pid,
                    :marketplace, :max_kw, :max_comp,
                    :delay_min, :delay_max,
                    :open_detail, :headless,
                    'queued', :kw_total,
                    :created_by, NOW(), NOW()
                )
            """),
            {
                "id": str(run_id),
                "wid": str(workspace_id),
                "pid": str(payload.product_id) if payload.product_id else None,
                "marketplace": s.marketplace,
                "max_kw": s.max_keywords_per_run,
                "max_comp": s.max_competitors_per_keyword,
                "delay_min": s.delay_min_seconds,
                "delay_max": s.delay_max_seconds,
                "open_detail": s.open_product_detail_pages,
                "headless": s.headless,
                "kw_total": len(keyword_queue),
                "created_by": str(actor_user_id) if actor_user_id else None,
            },
        )

        for kw, source, rank in keyword_queue:
            conn.execute(
                text("""
                    INSERT INTO competitor_research_keywords (
                        id, workspace_id, run_id, keyword, keyword_source, priority_rank,
                        status, created_at, updated_at
                    ) VALUES (
                        :id, :wid, :run_id, :kw, :source, :rank,
                        'queued', NOW(), NOW()
                    )
                """),
                {
                    "id": str(uuid4()),
                    "wid": str(workspace_id),
                    "run_id": str(run_id),
                    "kw": kw,
                    "source": source,
                    "rank": rank,
                },
            )

    return run_id


def _load_run(workspace_id: UUID, run_id: UUID) -> CompetitorResearchRun | None:
    engine = get_database_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM competitor_research_runs WHERE id = :id AND workspace_id = :wid"),
            {"id": str(run_id), "wid": str(workspace_id)},
        ).mappings().first()
    return _row_to_run(row) if row else None


def _load_run_detail(workspace_id: UUID, run_id: UUID) -> CompetitorResearchRunDetail | None:
    engine = get_database_engine()
    with engine.connect() as conn:
        run_row = conn.execute(
            text("SELECT * FROM competitor_research_runs WHERE id = :id AND workspace_id = :wid"),
            {"id": str(run_id), "wid": str(workspace_id)},
        ).mappings().first()
        if not run_row:
            return None

        kw_rows = conn.execute(
            text("SELECT * FROM competitor_research_keywords WHERE run_id = :id ORDER BY priority_rank"),
            {"id": str(run_id)},
        ).mappings().all()

        insight_rows = conn.execute(
            text("SELECT * FROM competitor_ai_insights WHERE run_id = :id ORDER BY generated_at"),
            {"id": str(run_id)},
        ).mappings().all()

    run = _row_to_run(run_row)
    keywords = [_row_to_keyword(k) for k in kw_rows]
    insights = [_row_to_insight(i) for i in insight_rows]
    return CompetitorResearchRunDetail(**run.model_dump(), keywords=keywords, insights=insights)


def _list_runs(workspace_id: UUID) -> list[CompetitorResearchRun]:
    engine = get_database_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM competitor_research_runs WHERE workspace_id = :wid ORDER BY created_at DESC LIMIT 50"),
            {"wid": str(workspace_id)},
        ).mappings().all()
    return [_row_to_run(r) for r in rows]


def _list_results(workspace_id: UUID, run_id: UUID) -> list[CompetitorResearchResult]:
    engine = get_database_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM competitor_research_results WHERE run_id = :id ORDER BY keyword_id, position"),
            {"id": str(run_id)},
        ).mappings().all()
    return [_row_to_result(r) for r in rows]


def _list_insights(workspace_id: UUID, run_id: UUID) -> list[CompetitorAiInsight]:
    engine = get_database_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM competitor_ai_insights WHERE run_id = :id ORDER BY generated_at"),
            {"id": str(run_id)},
        ).mappings().all()
    return [_row_to_insight(i) for i in rows]


def _persist_result(workspace_id: UUID, run_id: UUID, keyword_id: UUID, result: dict) -> None:
    try:
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO competitor_research_results (
                        id, workspace_id, run_id, keyword_id, position, result_type,
                        asin, title, brand, price_text, price_usd, rating, review_count,
                        has_coupon, is_prime, is_amazon_choice, is_best_seller,
                        image_url, product_url, created_at
                    ) VALUES (
                        :id, :wid, :run_id, :kw_id, :pos, :rtype,
                        :asin, :title, :brand, :price_text, :price_usd, :rating, :reviews,
                        :coupon, :prime, :choice, :bestseller,
                        :image, :url, NOW()
                    )
                """),
                {
                    "id": str(uuid4()),
                    "wid": str(workspace_id),
                    "run_id": str(run_id),
                    "kw_id": str(keyword_id),
                    "pos": result.get("position", 0),
                    "rtype": "sponsored" if result.get("is_sponsored") else "organic",
                    "asin": result.get("asin"),
                    "title": result.get("title"),
                    "brand": result.get("brand"),
                    "price_text": result.get("price_text"),
                    "price_usd": result.get("price_usd"),
                    "rating": result.get("rating"),
                    "reviews": result.get("review_count"),
                    "coupon": result.get("has_coupon", False),
                    "prime": result.get("is_prime", False),
                    "choice": result.get("is_amazon_choice", False),
                    "bestseller": result.get("is_best_seller", False),
                    "image": result.get("image_url"),
                    "url": result.get("product_url"),
                },
            )
    except Exception:
        pass


def _persist_insight(workspace_id: UUID, run_id: UUID, keyword_id: UUID, keyword: str, data: dict) -> None:
    try:
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO competitor_ai_insights (
                        id, workspace_id, run_id, keyword_id, keyword,
                        opportunity_score, competitor_strength_score, relevance_score, risk_score,
                        competitor_strength, sponsored_intensity, organic_difficulty, product_market_fit,
                        avg_price_range, avg_review_count,
                        avg_price_min_usd, avg_price_max_usd, avg_review_count_number,
                        recommended_ad_strategy, listing_improvement, action_recommendation,
                        full_summary, ai_provider, ai_model, generated_at
                    ) VALUES (
                        :id, :wid, :run_id, :kw_id, :kw,
                        :opp, :cs, :rel, :risk,
                        :cstrength, :sint, :odifficulty, :pmfit,
                        :price_range, :review_range,
                        :price_min, :price_max, :review_num,
                        :ad_strategy, :listing, :action,
                        :summary, :provider, :model, NOW()
                    )
                    ON CONFLICT (keyword_id) DO UPDATE SET
                        opportunity_score = EXCLUDED.opportunity_score,
                        competitor_strength_score = EXCLUDED.competitor_strength_score,
                        full_summary = EXCLUDED.full_summary,
                        action_recommendation = EXCLUDED.action_recommendation,
                        ai_provider = EXCLUDED.ai_provider,
                        ai_model = EXCLUDED.ai_model,
                        generated_at = EXCLUDED.generated_at
                """),
                {
                    "id": str(uuid4()),
                    "wid": str(workspace_id),
                    "run_id": str(run_id),
                    "kw_id": str(keyword_id),
                    "kw": keyword,
                    "opp": data.get("opportunity_score"),
                    "cs": data.get("competitor_strength_score"),
                    "rel": data.get("relevance_score"),
                    "risk": data.get("risk_score"),
                    "cstrength": data.get("competitor_strength"),
                    "sint": data.get("sponsored_intensity"),
                    "odifficulty": data.get("organic_difficulty"),
                    "pmfit": data.get("product_market_fit"),
                    "price_range": data.get("avg_price_range"),
                    "review_range": data.get("avg_review_count"),
                    "price_min": data.get("avg_price_min_usd"),
                    "price_max": data.get("avg_price_max_usd"),
                    "review_num": data.get("avg_review_count_number"),
                    "ad_strategy": data.get("recommended_ad_strategy"),
                    "listing": data.get("listing_improvement"),
                    "action": data.get("action_recommendation"),
                    "summary": data.get("full_summary"),
                    "provider": data.get("ai_provider"),
                    "model": data.get("ai_model"),
                },
            )
    except Exception:
        pass


def _update_run_status(
    run_id: UUID,
    status: CompetitorResearchStatus,
    *,
    paused_reason: str | None = None,
    keywords_completed: int | None = None,
    products_captured: int | None = None,
    error_message: str | None = None,
) -> None:
    try:
        engine = get_database_engine()
        with engine.begin() as conn:
            updates = ["status = :status", "updated_at = NOW()"]
            params: dict = {"status": status.value, "id": str(run_id)}
            if paused_reason is not None:
                updates.append("paused_reason = :paused_reason")
                params["paused_reason"] = paused_reason
            if keywords_completed is not None:
                updates.append("keywords_completed = :kw_completed")
                params["kw_completed"] = keywords_completed
            if products_captured is not None:
                updates.append("products_captured = :products_captured")
                params["products_captured"] = products_captured
            if error_message is not None:
                updates.append("error_message = :error_message")
                params["error_message"] = error_message
            if status == CompetitorResearchStatus.RUNNING:
                updates.append("started_at = COALESCE(started_at, NOW())")
            if status in (CompetitorResearchStatus.SUCCEEDED, CompetitorResearchStatus.FAILED, CompetitorResearchStatus.CANCELLED):
                updates.append("completed_at = NOW()")
            conn.execute(
                text(f"UPDATE competitor_research_runs SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
    except Exception:
        pass


def _update_keyword_status(
    keyword_id: UUID,
    status_val: str,
    *,
    error_message: str | None = None,
    search_url: str | None = None,
    screenshot_path: str | None = None,
    organic_count: int | None = None,
    sponsored_count: int | None = None,
) -> None:
    try:
        engine = get_database_engine()
        with engine.begin() as conn:
            updates = ["status = :status", "updated_at = NOW()"]
            params: dict = {"status": status_val, "id": str(keyword_id)}
            if error_message is not None:
                updates.append("error_message = :error_message")
                params["error_message"] = error_message
            if search_url:
                updates.append("search_url = :search_url")
                params["search_url"] = search_url
            if screenshot_path:
                updates.append("screenshot_path = :screenshot_path")
                params["screenshot_path"] = screenshot_path
            if organic_count is not None:
                updates.append("organic_count = :organic_count")
                params["organic_count"] = organic_count
            if sponsored_count is not None:
                updates.append("sponsored_count = :sponsored_count")
                params["sponsored_count"] = sponsored_count
            if status_val == "succeeded":
                updates.append("searched_at = NOW()")
            conn.execute(
                text(f"UPDATE competitor_research_keywords SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
    except Exception:
        pass


# ─── Row → schema mappers ──────────────────────────────────────────────────────


def _row_to_run(r) -> CompetitorResearchRun:
    return CompetitorResearchRun(
        id=r["id"],
        workspace_id=r["workspace_id"],
        product_id=r.get("product_id"),
        marketplace=r["marketplace"],
        max_keywords_per_run=r["max_keywords_per_run"],
        max_competitors_per_keyword=r["max_competitors_per_keyword"],
        delay_min_seconds=float(r["delay_min_seconds"]),
        delay_max_seconds=float(r["delay_max_seconds"]),
        open_product_detail_pages=r["open_product_detail_pages"],
        headless=r["headless"],
        status=r["status"],
        keywords_total=r["keywords_total"],
        keywords_completed=r["keywords_completed"],
        keywords_failed=r["keywords_failed"],
        products_captured=r["products_captured"],
        current_keyword_index=r["current_keyword_index"],
        paused_reason=r.get("paused_reason"),
        started_at=r.get("started_at"),
        completed_at=r.get("completed_at"),
        error_message=r.get("error_message"),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_keyword(r) -> CompetitorResearchKeyword:
    return CompetitorResearchKeyword(
        id=r["id"],
        run_id=r["run_id"],
        keyword=r["keyword"],
        keyword_source=r.get("keyword_source"),
        priority_rank=r["priority_rank"],
        status=r["status"],
        search_url=r.get("search_url"),
        searched_at=r.get("searched_at"),
        screenshot_path=r.get("screenshot_path"),
        organic_count=r.get("organic_count"),
        sponsored_count=r.get("sponsored_count"),
        error_message=r.get("error_message"),
    )


def _row_to_result(r) -> CompetitorResearchResult:
    return CompetitorResearchResult(
        id=r["id"],
        run_id=r["run_id"],
        keyword_id=r["keyword_id"],
        position=r["position"],
        result_type=r["result_type"],
        asin=r.get("asin"),
        title=r.get("title"),
        brand=r.get("brand"),
        price_text=r.get("price_text"),
        price_usd=r.get("price_usd"),
        rating=r.get("rating"),
        review_count=r.get("review_count"),
        has_coupon=r.get("has_coupon"),
        is_prime=r.get("is_prime"),
        is_amazon_choice=r.get("is_amazon_choice"),
        is_best_seller=r.get("is_best_seller"),
        image_url=r.get("image_url"),
        product_url=r.get("product_url"),
    )


def _row_to_insight(r) -> CompetitorAiInsight:
    return CompetitorAiInsight(
        id=r["id"],
        run_id=r["run_id"],
        keyword_id=r["keyword_id"],
        keyword=r["keyword"],
        opportunity_score=r.get("opportunity_score"),
        competitor_strength_score=r.get("competitor_strength_score"),
        relevance_score=r.get("relevance_score"),
        risk_score=r.get("risk_score"),
        competitor_strength=r.get("competitor_strength"),
        sponsored_intensity=r.get("sponsored_intensity"),
        organic_difficulty=r.get("organic_difficulty"),
        product_market_fit=r.get("product_market_fit"),
        avg_price_range=r.get("avg_price_range"),
        avg_review_count=r.get("avg_review_count"),
        avg_price_min_usd=r.get("avg_price_min_usd"),
        avg_price_max_usd=r.get("avg_price_max_usd"),
        avg_review_count_number=r.get("avg_review_count_number"),
        recommended_ad_strategy=r.get("recommended_ad_strategy"),
        listing_improvement=r.get("listing_improvement"),
        action_recommendation=r.get("action_recommendation"),
        full_summary=r.get("full_summary"),
        ai_provider=r.get("ai_provider"),
        ai_model=r.get("ai_model"),
        generated_at=r["generated_at"],
    )
