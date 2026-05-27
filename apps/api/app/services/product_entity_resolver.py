from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID, uuid4

from apps.api.app.schemas.account_imports import (
    AccountImport,
    AccountImportEntity,
    EntityType,
    ProductMappingSuggestion,
    ProductResolutionStatus,
)
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.schemas.upload_parsing import ParsedUploadRow


@dataclass(frozen=True)
class ProductEntityResolution:
    entities: list[AccountImportEntity]
    product_mapping_suggestions: list[ProductMappingSuggestion]


class ProductEntityResolver:
    def resolve(
        self,
        *,
        import_record: AccountImport,
        rows: list[ParsedUploadRow],
        existing_products: list[ProductProfile],
    ) -> ProductEntityResolution:
        now = datetime.now(UTC)
        product_index = _ProductIndex(existing_products)
        product_groups: dict[str, _GroupAccumulator] = {}
        groups: dict[tuple[EntityType, str], _GroupAccumulator] = {}

        for row in rows:
            normalized = {_normalize_header(key): value for key, value in row.row_data_json.items()}
            asin = _clean(_first(normalized, "asin", "advertised asin", "purchased asin", "advertised product asin"))
            sku = _clean(_first(normalized, "sku", "advertised sku", "seller sku", "merchant sku"))
            product_name = _clean(_first(normalized, "product", "product name", "advertised product", "portfolio name"))
            campaign_name = _clean(_first(normalized, "campaign name", "campaign"))
            ad_group_name = _clean(_first(normalized, "ad group name", "ad group"))
            targeting = _clean(_first(normalized, "targeting", "keyword", "keyword text", "targeting expression"))
            search_term = _clean(_first(normalized, "customer search term", "search term", "query"))
            product_id, resolution_status = product_index.resolve(asin=asin, sku=sku, product_name=product_name)
            product_key = _product_key(product_id=product_id, asin=asin, sku=sku, product_name=product_name)

            self._add_group(
                groups,
                EntityType.ACCOUNT,
                "account",
                row=row,
                normalized=normalized,
                now=now,
                import_record=import_record,
                resolution_status=ProductResolutionStatus.MATCHED_EXISTING_PRODUCT,
            )
            if product_key:
                product_groups.setdefault(
                    product_key,
                    _GroupAccumulator(
                        import_record=import_record,
                        entity_type=EntityType.PRODUCT,
                        entity_key=product_key,
                        now=now,
                        product_id=product_id,
                        asin=asin,
                        sku=sku,
                        product_name=product_name,
                        resolution_status=resolution_status,
                    ),
                ).add(row=row, normalized=normalized)
                groups[(EntityType.PRODUCT, product_key)] = product_groups[product_key]

            for entity_type, entity_key in [
                (EntityType.CAMPAIGN, _key(campaign_name)),
                (EntityType.AD_GROUP, _key(campaign_name, ad_group_name)),
                (EntityType.TARGET, _key(campaign_name, ad_group_name, targeting)),
                (EntityType.SEARCH_TERM, _key(campaign_name, ad_group_name, targeting, search_term)),
            ]:
                if not entity_key:
                    continue
                groups.setdefault(
                    (entity_type, entity_key),
                    _GroupAccumulator(
                        import_record=import_record,
                        entity_type=entity_type,
                        entity_key=entity_key,
                        now=now,
                        product_id=product_id,
                        asin=asin,
                        sku=sku,
                        product_name=product_name,
                        campaign_name=campaign_name,
                        ad_group_name=ad_group_name,
                        targeting=targeting,
                        customer_search_term=search_term,
                        resolution_status=resolution_status,
                    ),
                ).add(row=row, normalized=normalized)

        suggestions = _mapping_suggestions(
            import_record=import_record,
            product_groups=list(product_groups.values()),
            now=now,
        )
        entities = [group.to_entity() for group in groups.values()]
        return ProductEntityResolution(
            entities=sorted(entities, key=lambda item: (item.entity_type.value, item.entity_key)),
            product_mapping_suggestions=suggestions,
        )

    def _add_group(
        self,
        groups: dict[tuple[EntityType, str], "_GroupAccumulator"],
        entity_type: EntityType,
        entity_key: str,
        *,
        row: ParsedUploadRow,
        normalized: dict,
        now: datetime,
        import_record: AccountImport,
        resolution_status: ProductResolutionStatus,
    ) -> None:
        groups.setdefault(
            (entity_type, entity_key),
            _GroupAccumulator(
                import_record=import_record,
                entity_type=entity_type,
                entity_key=entity_key,
                now=now,
                resolution_status=resolution_status,
            ),
        ).add(row=row, normalized=normalized)


class _ProductIndex:
    def __init__(self, products: list[ProductProfile]) -> None:
        self._by_asin = {_norm(product.asin): product for product in products if product.asin}
        self._by_sku = {_norm(product.sku): product for product in products if product.sku}
        self._by_name = {_norm(product.product_name): product for product in products if product.product_name}

    def resolve(self, *, asin: str | None, sku: str | None, product_name: str | None) -> tuple[UUID | None, ProductResolutionStatus]:
        asin_match = self._by_asin.get(_norm(asin))
        sku_match = self._by_sku.get(_norm(sku))
        if asin_match and sku_match and asin_match.id != sku_match.id:
            return None, ProductResolutionStatus.NEEDS_USER_MAPPING
        match = asin_match or sku_match or self._by_name.get(_norm(product_name))
        if match:
            return match.id, ProductResolutionStatus.MATCHED_EXISTING_PRODUCT
        if asin or sku or product_name:
            return None, ProductResolutionStatus.SUGGESTED_NEW_PRODUCT
        return None, ProductResolutionStatus.UNKNOWN_PRODUCT


class _GroupAccumulator:
    def __init__(
        self,
        *,
        import_record: AccountImport,
        entity_type: EntityType,
        entity_key: str,
        now: datetime,
        resolution_status: ProductResolutionStatus,
        product_id: UUID | None = None,
        asin: str | None = None,
        sku: str | None = None,
        product_name: str | None = None,
        campaign_name: str | None = None,
        ad_group_name: str | None = None,
        targeting: str | None = None,
        customer_search_term: str | None = None,
    ) -> None:
        self.import_record = import_record
        self.entity_type = entity_type
        self.entity_key = entity_key
        self.now = now
        self.product_id = product_id
        self.asin = asin
        self.sku = sku
        self.product_name = product_name
        self.campaign_name = campaign_name
        self.ad_group_name = ad_group_name
        self.targeting = targeting
        self.customer_search_term = customer_search_term
        self.resolution_status = resolution_status
        self.row_numbers: list[int] = []
        self.metrics = defaultdict(Decimal)
        self.row_count = 0

    def add(self, *, row: ParsedUploadRow, normalized: dict) -> None:
        self.row_count += 1
        self.row_numbers.append(row.row_number)
        self.metrics["impressions"] += _decimal(_first(normalized, "impressions"))
        self.metrics["clicks"] += _decimal(_first(normalized, "clicks"))
        self.metrics["spend"] += _decimal(_first(normalized, "spend", "cost"))
        self.metrics["sales"] += _decimal(_first(normalized, "sales", "7 day total sales", "14 day total sales"))
        self.metrics["orders"] += _decimal(_first(normalized, "orders", "7 day total orders", "14 day total orders"))
        self.metrics["units"] += _decimal(_first(normalized, "units", "7 day total units", "14 day total units"))

    def to_entity(self) -> AccountImportEntity:
        metrics = {key: _metric_value(value) for key, value in self.metrics.items()}
        metrics["row_count"] = self.row_count
        metrics["acos"] = _ratio(metrics.get("spend"), metrics.get("sales"))
        metrics["roas"] = _ratio(metrics.get("sales"), metrics.get("spend"))
        return AccountImportEntity(
            id=uuid4(),
            workspace_id=self.import_record.workspace_id,
            account_import_id=self.import_record.id,
            product_id=self.product_id,
            asin=self.asin,
            sku=self.sku,
            product_name=self.product_name,
            campaign_name=self.campaign_name,
            ad_group_name=self.ad_group_name,
            targeting=self.targeting,
            customer_search_term=self.customer_search_term,
            entity_type=self.entity_type,
            entity_key=self.entity_key,
            resolution_status=self.resolution_status,
            metrics_json=metrics,
            raw_row_refs_json=sorted(set(self.row_numbers)),
            created_at=self.now,
        )


def _mapping_suggestions(*, import_record: AccountImport, product_groups: list[_GroupAccumulator], now: datetime) -> list[ProductMappingSuggestion]:
    suggestions: list[ProductMappingSuggestion] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for group in product_groups:
        if group.resolution_status == ProductResolutionStatus.MATCHED_EXISTING_PRODUCT:
            continue
        key = (group.asin, group.sku, group.product_name)
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(
            ProductMappingSuggestion(
                id=uuid4(),
                workspace_id=import_record.workspace_id,
                account_import_id=import_record.id,
                asin=group.asin,
                sku=group.sku,
                detected_product_name=group.product_name,
                suggested_product_id=group.product_id,
                created_at=now,
                updated_at=now,
            )
        )
    return suggestions


def _product_key(*, product_id: UUID | None, asin: str | None, sku: str | None, product_name: str | None) -> str:
    if product_id:
        return f"product_id:{product_id}"
    if asin:
        return f"asin:{asin}"
    if sku:
        return f"sku:{sku}"
    if product_name:
        return f"product_name:{product_name}"
    return "unknown_product"


def _key(*parts: str | None) -> str | None:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return "|".join(cleaned) if cleaned else None


def _first(data: dict, *keys: str):
    for key in keys:
        value = data.get(_normalize_header(key))
        if value not in {None, ""}:
            return value
    return None


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _metric_value(value: Decimal) -> int | str:
    if value == value.to_integral_value():
        return int(value)
    return str(value.quantize(Decimal("0.0001")))


def _ratio(numerator, denominator) -> str | None:
    if numerator is None or denominator in {None, 0, "0", "0.0000"}:
        return None
    denominator_decimal = Decimal(str(denominator))
    if denominator_decimal == 0:
        return None
    return str((Decimal(str(numerator)) / denominator_decimal).quantize(Decimal("0.0001")))
