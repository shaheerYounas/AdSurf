"""Browser-based Amazon search evidence collection for competitor verification.

The agent uses ordinary browser automation to collect visible search results.
It does not log in, bypass CAPTCHA, use stealth plugins, mutate Amazon Ads, or
make verification decisions. The deterministic verifier consumes its evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from urllib.parse import quote_plus

from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.competitor_cleaned import CompetitorVerificationEvidenceRow


AMAZON_MARKETPLACE_HOSTS = {
    "US": "www.amazon.com",
    "CA": "www.amazon.ca",
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "FR": "www.amazon.fr",
    "IT": "www.amazon.it",
    "ES": "www.amazon.es",
}


@dataclass(frozen=True)
class AmazonSearchAgentOptions:
    marketplace: str = "US"
    max_results: int = 15
    timeout_ms: int = 15000
    delay_seconds: float = 1.5
    headless: bool = True


class AmazonSearchEvidenceProvider:
    def search(self, *, search_term: str, options: AmazonSearchAgentOptions) -> CompetitorVerificationEvidenceRow:
        raise NotImplementedError


class PlaywrightAmazonSearchProvider(AmazonSearchEvidenceProvider):
    """Collect visible Amazon search results with Playwright when installed."""

    def search(self, *, search_term: str, options: AmazonSearchAgentOptions) -> CompetitorVerificationEvidenceRow:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ApiError(
                code="BROWSER_AUTOMATION_UNAVAILABLE",
                message=(
                    "Agentic Amazon verification requires Playwright for Python. "
                    "Install it with `python -m pip install playwright` and `python -m playwright install chromium`."
                ),
                status_code=503,
            ) from exc

        host = AMAZON_MARKETPLACE_HOSTS.get(options.marketplace.upper(), AMAZON_MARKETPLACE_HOSTS["US"])
        url = f"https://{host}/s?k={quote_plus(search_term)}"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=options.headless)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=options.timeout_ms)
                self._raise_if_blocked(page)
                page.wait_for_selector('[data-component-type="s-search-result"]', timeout=options.timeout_ms)
                results = self._extract_results(page=page, max_results=options.max_results)
            except PlaywrightTimeoutError as exc:
                raise ApiError(
                    code="AMAZON_SEARCH_TIMEOUT",
                    message=f"Amazon search timed out for `{search_term}`. Try again later or reduce the batch size.",
                    status_code=503,
                ) from exc
            finally:
                browser.close()

        sleep(max(options.delay_seconds, 0))
        return CompetitorVerificationEvidenceRow(search_term=search_term, results=results)

    @staticmethod
    def _raise_if_blocked(page) -> None:
        title = (page.title() or "").lower()
        body_text = ""
        try:
            body_text = (page.locator("body").inner_text(timeout=1500) or "").lower()
        except Exception:
            body_text = ""
        if "captcha" in title or "enter the characters you see below" in body_text:
            raise ApiError(
                code="AMAZON_BROWSER_CHALLENGE",
                message="Amazon returned a browser challenge. The agent stopped without bypassing it.",
                status_code=503,
            )

    @staticmethod
    def _extract_results(*, page, max_results: int) -> list[dict]:
        extracted: list[dict] = []
        cards = page.locator('[data-component-type="s-search-result"]')
        count = min(cards.count(), max_results)
        for index in range(count):
            card = cards.nth(index)
            asin = card.get_attribute("data-asin")
            title = ""
            for selector in ("h2 span", "h2 a span", "[data-cy='title-recipe-title']"):
                try:
                    title = card.locator(selector).first.inner_text(timeout=1000).strip()
                except Exception:
                    title = ""
                if title:
                    break
            if not title and not asin:
                continue
            extracted.append({
                "position": len(extracted) + 1,
                "title": title or None,
                "asin": asin.strip().upper() if asin else None,
            })
        return extracted


class AmazonSearchEvidenceAgent:
    """Runs browser searches and returns verifier-compatible evidence rows."""

    def __init__(self, provider: AmazonSearchEvidenceProvider | None = None) -> None:
        self._provider = provider or PlaywrightAmazonSearchProvider()

    def collect(
        self,
        *,
        search_terms: list[str],
        options: AmazonSearchAgentOptions,
    ) -> list[CompetitorVerificationEvidenceRow]:
        evidence_rows: list[CompetitorVerificationEvidenceRow] = []
        for term in search_terms:
            cleaned = " ".join(term.strip().split())
            if not cleaned:
                continue
            evidence_rows.append(self._provider.search(search_term=cleaned, options=options))
        return evidence_rows
