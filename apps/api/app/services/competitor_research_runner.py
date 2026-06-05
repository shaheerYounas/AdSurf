"""Competitor research runner using a visible Playwright browser session.

Design principles:
- The browser is VISIBLE (headless=False) by default so the user can see it.
- If Amazon shows a CAPTCHA or challenge page, the run PAUSES immediately
  and returns status=paused_manual_verification. It does NOT attempt to bypass.
- The user must manually complete verification in the browser, then resume.
- Random human-like delays between searches.
- No login, no credentials, no stealth plugins.
- No Amazon Ads live changes.
- Public pages only (Amazon SERP + product detail).
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    pass


AMAZON_MARKETPLACE_HOSTS = {
    "US": "www.amazon.com",
    "CA": "www.amazon.ca",
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "FR": "www.amazon.fr",
    "IT": "www.amazon.it",
    "ES": "www.amazon.es",
}


@dataclass
class KeywordSearchResult:
    keyword: str
    search_url: str
    screenshot_path: str | None
    organic_results: list[dict]
    sponsored_results: list[dict]
    error: str | None = None
    paused_for_verification: bool = False


class CompetitorResearchRunner:
    """
    Runs a series of Amazon keyword searches in a visible browser session.
    The caller polls or awaits results via run_keywords().
    """

    def __init__(
        self,
        *,
        marketplace: str = "US",
        max_competitors_per_keyword: int = 10,
        delay_min_seconds: float = 2.0,
        delay_max_seconds: float = 5.0,
        open_product_detail_pages: bool = False,
        headless: bool = False,
        screenshot_dir: str | None = None,
    ) -> None:
        self.marketplace = marketplace.upper()
        self.host = AMAZON_MARKETPLACE_HOSTS.get(self.marketplace, AMAZON_MARKETPLACE_HOSTS["US"])
        self.max_competitors = max_competitors_per_keyword
        self.delay_min = delay_min_seconds
        self.delay_max = delay_max_seconds
        self.open_product_detail_pages = open_product_detail_pages
        self.headless = headless
        self.screenshot_dir = screenshot_dir

    # ─── Public entry point ───────────────────────────────────────────────────

    def run_keywords(self, keywords: list[str]) -> list[KeywordSearchResult]:
        """
        Run all keywords sequentially in a single browser session.
        Returns results including partial results if paused/failed.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for competitor research. "
                "Install it: python -m pip install playwright && python -m playwright install chromium"
            ) from exc

        results: list[KeywordSearchResult] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless, slow_mo=100)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()

            for keyword in keywords:
                result = self._search_one_keyword(page, keyword)
                results.append(result)

                if result.paused_for_verification:
                    # Stop immediately — do not process more keywords
                    break

                if result.error is None:
                    # Human-like delay between searches
                    delay = random.uniform(self.delay_min, self.delay_max)
                    time.sleep(delay)

            browser.close()

        return results

    # ─── Single keyword search ────────────────────────────────────────────────

    def _search_one_keyword(self, page, keyword: str) -> KeywordSearchResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        cleaned = " ".join(keyword.strip().split())
        search_url = f"https://{self.host}/s?k={quote_plus(cleaned)}"
        screenshot_path: str | None = None

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)

            # ── Check for CAPTCHA / challenge ─────────────────────────────────
            if self._is_challenge_page(page):
                return KeywordSearchResult(
                    keyword=cleaned,
                    search_url=search_url,
                    screenshot_path=None,
                    organic_results=[],
                    sponsored_results=[],
                    paused_for_verification=True,
                )

            # ── Wait for search results ───────────────────────────────────────
            try:
                page.wait_for_selector('[data-component-type="s-search-result"]', timeout=12000)
            except PlaywrightTimeoutError:
                return KeywordSearchResult(
                    keyword=cleaned,
                    search_url=search_url,
                    screenshot_path=None,
                    organic_results=[],
                    sponsored_results=[],
                    error="Timed out waiting for search results.",
                )

            # ── Screenshot ────────────────────────────────────────────────────
            if self.screenshot_dir:
                safe_keyword = re.sub(r"[^\w\-]", "_", cleaned)[:60]
                screenshot_path = f"{self.screenshot_dir}/{safe_keyword}.png"
                try:
                    page.screenshot(path=screenshot_path, full_page=False)
                except Exception:
                    screenshot_path = None

            # ── Extract results ───────────────────────────────────────────────
            organic, sponsored = self._extract_search_results(page)

            # ── Optional product detail enrichment ───────────────────────────
            if self.open_product_detail_pages:
                top_asins = [r["asin"] for r in (organic + sponsored)[:3] if r.get("asin")]
                for asin in top_asins[:3]:
                    detail = self._fetch_product_detail(page, asin)
                    for r in organic + sponsored:
                        if r.get("asin") == asin:
                            r.update(detail)

            return KeywordSearchResult(
                keyword=cleaned,
                search_url=search_url,
                screenshot_path=screenshot_path,
                organic_results=organic,
                sponsored_results=sponsored,
            )

        except PlaywrightTimeoutError as exc:
            return KeywordSearchResult(
                keyword=cleaned,
                search_url=search_url,
                screenshot_path=screenshot_path,
                organic_results=[],
                sponsored_results=[],
                error=f"Page timeout: {exc}",
            )
        except Exception as exc:
            return KeywordSearchResult(
                keyword=cleaned,
                search_url=search_url,
                screenshot_path=screenshot_path,
                organic_results=[],
                sponsored_results=[],
                error=str(exc),
            )

    # ─── Challenge detection ──────────────────────────────────────────────────

    @staticmethod
    def _is_challenge_page(page) -> bool:
        title = (page.title() or "").lower()
        if "captcha" in title or "robot check" in title:
            return True
        try:
            body = (page.locator("body").inner_text(timeout=1500) or "").lower()
            return any(phrase in body for phrase in [
                "enter the characters you see below",
                "type the characters you see in this image",
                "sorry, we just need to make sure you're not a robot",
                "complete the security check",
            ])
        except Exception:
            return False

    # ─── Result extraction ────────────────────────────────────────────────────

    def _extract_search_results(self, page) -> tuple[list[dict], list[dict]]:
        organic: list[dict] = []
        sponsored: list[dict] = []

        cards = page.locator('[data-component-type="s-search-result"]')
        count = min(cards.count(), self.max_competitors * 2)  # grab extra in case of ads

        for i in range(count):
            if len(organic) + len(sponsored) >= self.max_competitors:
                break
            card = cards.nth(i)
            result = self._extract_card(card, position=i + 1)
            if not result:
                continue
            if result.get("is_sponsored"):
                sponsored.append(result)
            else:
                organic.append(result)

        return organic[:self.max_competitors], sponsored[:self.max_competitors]

    @staticmethod
    def _extract_card(card, position: int) -> dict | None:
        asin = card.get_attribute("data-asin")

        title = ""
        for sel in ("h2 span", "h2 a span", "[data-cy='title-recipe-title'] span"):
            try:
                title = card.locator(sel).first.inner_text(timeout=800).strip()
                if title:
                    break
            except Exception:
                pass

        if not title and not asin:
            return None

        # Detect sponsored
        is_sponsored = False
        try:
            sponsored_label = card.locator("span.puis-sponsored-label-text, [data-component-type='sp-sponsored-result']").count()
            is_sponsored = sponsored_label > 0
        except Exception:
            pass

        # Price
        price_text = ""
        price_usd = None
        try:
            price_text = card.locator("span.a-price span.a-offscreen").first.inner_text(timeout=600).strip()
            price_usd = float(price_text.replace("$", "").replace(",", "").strip()) if price_text else None
        except Exception:
            pass

        # Rating + reviews
        rating = None
        review_count = None
        try:
            rating_text = card.locator("[data-cy='reviews-ratings-slot'] span.a-icon-alt").first.inner_text(timeout=600)
            rating = float(rating_text.split()[0]) if rating_text else None
        except Exception:
            pass
        try:
            review_text = card.locator("[data-cy='reviews-ratings-slot'] span.a-size-base").first.inner_text(timeout=600)
            review_count = int(review_text.replace(",", "").strip()) if review_text else None
        except Exception:
            pass

        # Badges
        has_coupon = False
        is_prime = False
        is_best_seller = False
        is_amazon_choice = False
        try:
            has_coupon = card.locator("[id^='coupon']").count() > 0 or card.locator(".s-coupon-highlight-color").count() > 0
            is_prime = card.locator(".s-prime").count() > 0
            is_best_seller = card.locator("span.a-badge-label:has-text('Best Seller')").count() > 0
            is_amazon_choice = card.locator("span.a-badge-label:has-text('Amazon\\'s Choice')").count() > 0
        except Exception:
            pass

        # Image
        image_url = None
        try:
            image_url = card.locator("img.s-image").first.get_attribute("src", timeout=600)
        except Exception:
            pass

        # Product URL
        product_url = None
        try:
            href = card.locator("a.a-link-normal[href]").first.get_attribute("href", timeout=600)
            if href:
                product_url = f"https://www.amazon.com{href}" if href.startswith("/") else href
        except Exception:
            pass

        return {
            "position": position,
            "asin": asin.strip().upper() if asin else None,
            "title": title or None,
            "is_sponsored": is_sponsored,
            "price_text": price_text or None,
            "price_usd": price_usd,
            "rating": rating,
            "review_count": review_count,
            "has_coupon": has_coupon,
            "is_prime": is_prime,
            "is_best_seller": is_best_seller,
            "is_amazon_choice": is_amazon_choice,
            "image_url": image_url,
            "product_url": product_url,
        }

    # ─── Product detail enrichment ────────────────────────────────────────────

    def _fetch_product_detail(self, page, asin: str) -> dict:
        url = f"https://{self.host}/dp/{asin}"
        detail: dict = {}
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if self._is_challenge_page(page):
                return {"detail_challenge": True}

            # Bullet points
            bullets: list[str] = []
            try:
                bullet_els = page.locator("#feature-bullets ul li span").all()
                bullets = [b.inner_text(timeout=600).strip() for b in bullet_els[:8] if b.inner_text(timeout=600).strip()]
            except Exception:
                pass

            # Variations
            variations = None
            try:
                var_count = page.locator("[data-csa-c-type='variation'] .twisterSwatchButtonWrapper").count()
                if var_count:
                    variations = var_count
            except Exception:
                pass

            # A+ content
            aplus = False
            try:
                aplus = page.locator(".aplus-v2").count() > 0
            except Exception:
                pass

            # Image count
            image_count = None
            try:
                image_count = page.locator("#altImages ul li").count() or None
            except Exception:
                pass

            detail = {
                "detail_bullets_json": bullets or None,
                "detail_variations": variations,
                "detail_aplus_present": aplus,
                "detail_image_count": image_count,
            }
        except Exception:
            pass

        return detail


# ─── Keyword queue builder ────────────────────────────────────────────────────


def build_keyword_queue(
    *,
    seed_keywords: list[str],
    manual_keywords: list[str],
    high_spend_terms: list[str],
    move_to_exact_terms: list[str],
) -> list[tuple[str, str, int]]:
    """
    Returns list of (keyword, source, priority_rank).
    Lower priority_rank = higher priority.
    Deduplicates (case-insensitive).
    """
    seen: set[str] = set()
    queue: list[tuple[str, str, int]] = []
    rank = 0

    def add(kw: str, source: str) -> None:
        nonlocal rank
        normalized = " ".join(kw.strip().lower().split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            queue.append((kw.strip(), source, rank))
            rank += 1

    # Priority 1: high_spend + sales (caller pre-sorts)
    for t in high_spend_terms:
        add(t, "high_spend")

    # Priority 2: move_to_exact candidates
    for t in move_to_exact_terms:
        add(t, "move_to_exact")

    # Priority 3: user seeds
    for t in seed_keywords:
        add(t, "user_seed")

    # Priority 4: manual
    for t in manual_keywords:
        add(t, "manual")

    return queue


import re  # noqa: E402 — import needed for screenshot path sanitization above
