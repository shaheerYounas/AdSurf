from datetime import UTC, datetime
from uuid import uuid4

from apps.api.app.schemas.column_mapping import (
    ColumnInferredDataType,
    ColumnMappingStatus,
    ColumnProfile,
    ColumnProfileColumn,
    ColumnProfileStatus,
    ManualMappingJson,
)
from apps.api.app.services.column_mapping import validate_manual_mapping


def test_manual_mapping_valid_case() -> None:
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["running shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Rank 1", ColumnInferredDataType.INTEGER, [3]),
        ]
    )

    status, messages, mapping = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(search_term="Search Term", search_volume="Search Volume", competitor_rank_columns=["Rank 1"]),
    )

    assert status == ColumnMappingStatus.VALID
    assert messages == []
    assert mapping["search_term"]["original_column_name"] == "Search Term"


def test_missing_required_mapping_fields_are_invalid() -> None:
    profile, columns = _profile_with_columns([("Rank 1", ColumnInferredDataType.INTEGER, [3])])

    status, messages, _ = validate_manual_mapping(profile=profile, columns=columns, mapping_json=ManualMappingJson())

    assert status == ColumnMappingStatus.INVALID
    assert {message["code"] for message in messages} >= {
        "MISSING_SEARCH_TERM",
        "MISSING_SEARCH_VOLUME",
        "MISSING_COMPETITOR_RANK_COLUMNS",
    }


def test_duplicate_role_columns_are_invalid() -> None:
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Rank 1", ColumnInferredDataType.INTEGER, [1]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(search_term="Search Term", search_volume="Search Term", competitor_rank_columns=["Rank 1", "Rank 1"]),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "DUPLICATE_SEARCH_TERM_SEARCH_VOLUME" in {message["code"] for message in messages}
    assert "DUPLICATE_COMPETITOR_RANK_COLUMNS" in {message["code"] for message in messages}


def test_non_numeric_search_volume_is_invalid() -> None:
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.TEXT, ["many"]),
            ("Rank 1", ColumnInferredDataType.INTEGER, [1]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(search_term="Search Term", search_volume="Search Volume", competitor_rank_columns=["Rank 1"]),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "SEARCH_VOLUME_NOT_NUMERIC" in {message["code"] for message in messages}


def test_numeric_like_text_mapping_is_valid_with_warning() -> None:
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.TEXT, ["1000"]),
            ("Rank 1", ColumnInferredDataType.TEXT, ["3"]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(search_term="Search Term", search_volume="Search Volume", competitor_rank_columns=["Rank 1"]),
    )

    assert status == ColumnMappingStatus.VALID
    assert {message["severity"] for message in messages} == {"warning"}
    assert "SEARCH_VOLUME_NOT_NUMERIC_TEXT" in {message["code"] for message in messages}


def test_numeric_only_search_term_is_invalid() -> None:
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["12345"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Rank 1", ColumnInferredDataType.INTEGER, [1]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(search_term="Search Term", search_volume="Search Volume", competitor_rank_columns=["Rank 1"]),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "SEARCH_TERM_NUMERIC_ONLY" in {message["code"] for message in messages}


# ── New tests: competitor rank semantic validation ──


def test_competitor_rank_with_rank_in_name_passes() -> None:
    """Column named 'Organic Rank 1' should pass semantic validation."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Organic Rank 1", ColumnInferredDataType.INTEGER, [3, 5, 12]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Organic Rank 1"],
        ),
    )

    assert status == ColumnMappingStatus.VALID
    rank_errors = [m for m in messages if "competitor_rank" in m.get("code", "").lower()]
    assert rank_errors == [], f"Unexpected rank errors: {rank_errors}"


def test_competitor_rank_with_position_in_name_passes() -> None:
    """Column named 'Position' should pass semantic validation."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Position", ColumnInferredDataType.INTEGER, [3, 5, 12]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Position"],
        ),
    )

    assert status == ColumnMappingStatus.VALID
    rank_errors = [m for m in messages if m["severity"] == "error" and "RANK" in m["code"]]
    assert rank_errors == [], f"Unexpected rank errors: {rank_errors}"


def test_spend_column_rejected_as_competitor_rank() -> None:
    """Column named 'Spend' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Spend", ColumnInferredDataType.DECIMAL, [1.23, 4.56, 7.89]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Spend"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_clicks_column_rejected_as_competitor_rank() -> None:
    """Column named 'Clicks' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Clicks", ColumnInferredDataType.INTEGER, [50, 200, 300]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Clicks"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_orders_column_rejected_as_competitor_rank() -> None:
    """Column named 'Orders' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Orders", ColumnInferredDataType.INTEGER, [1, 2, 0]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Orders"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_cpc_column_rejected_as_competitor_rank() -> None:
    """Column named 'CPC' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("CPC", ColumnInferredDataType.DECIMAL, [0.45, 0.67, 1.23]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["CPC"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_sales_column_rejected_as_competitor_rank() -> None:
    """Column named 'Sales' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Sales", ColumnInferredDataType.DECIMAL, [49.99, 99.99, 149.99]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Sales"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_acos_column_rejected_as_competitor_rank() -> None:
    """Column named 'ACOS' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("ACOS", ColumnInferredDataType.DECIMAL, [0.15, 0.25, 0.35]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["ACOS"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_impressions_column_rejected_as_competitor_rank() -> None:
    """Column named 'Impressions' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Impressions", ColumnInferredDataType.INTEGER, [5000, 12000, 8000]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Impressions"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_ctr_column_rejected_as_competitor_rank() -> None:
    """Column named 'CTR' should be rejected as competitor rank (ad metric token)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("CTR", ColumnInferredDataType.DECIMAL, [0.01, 0.02, 0.03]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["CTR"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_budget_column_rejected_as_competitor_rank() -> None:
    """Column named 'Daily Budget' should be rejected as competitor rank (ad metric)."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Daily Budget", ColumnInferredDataType.DECIMAL, [10.00, 20.00, 15.00]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Daily Budget"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_high_value_warning_for_non_rank_data() -> None:
    """Column with values > 1000 should trigger a warning about not looking like ranks."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("UnknownColumn", ColumnInferredDataType.INTEGER, [5000, 12000, 8000]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["UnknownColumn"],
        ),
    )

    # Should be INVALID due to name-based rejection AND get value-level warnings
    assert status == ColumnMappingStatus.INVALID
    error_codes = {m["code"] for m in messages}
    assert "COMPETITOR_RANK_NAME_NOT_RANK_LIKE" in error_codes
    assert "COMPETITOR_RANK_HIGH_VALUES" in error_codes


def test_decimal_values_warning() -> None:
    """Column with decimal values should trigger a warning about not looking like ranks."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("UnknownColumn", ColumnInferredDataType.DECIMAL, [1.23, 4.56, 7.89]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["UnknownColumn"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    error_codes = {m["code"] for m in messages}
    assert "COMPETITOR_RANK_NAME_NOT_RANK_LIKE" in error_codes
    assert "COMPETITOR_RANK_DECIMAL_VALUES" in error_codes


def test_multiple_rank_columns_mix_valid_and_invalid() -> None:
    """A mix of valid (rank) and invalid (spend) columns should catch the ad metric."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Organic Rank", ColumnInferredDataType.INTEGER, [3, 5, 12]),
            ("Spend", ColumnInferredDataType.DECIMAL, [1.23, 4.56, 7.89]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Organic Rank", "Spend"],
        ),
    )

    assert status == ColumnMappingStatus.INVALID
    assert "COMPETITOR_RANK_IS_AD_METRIC" in {m["code"] for m in messages}


def test_competitor_in_name_passes() -> None:
    """Column with 'competitor' in name should pass semantic validation."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Competitor Rank", ColumnInferredDataType.INTEGER, [3, 5, 12]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Competitor Rank"],
        ),
    )

    assert status == ColumnMappingStatus.VALID
    rank_errors = [m for m in messages if m["severity"] == "error" and "RANK" in m["code"]]
    assert rank_errors == [], f"Unexpected rank errors: {rank_errors}"


def test_comp_in_token_passes() -> None:
    """Column with 'comp' as a token should pass semantic validation."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("comp_1", ColumnInferredDataType.INTEGER, [3, 5, 12]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["comp_1"],
        ),
    )

    assert status == ColumnMappingStatus.VALID
    rank_errors = [m for m in messages if m["severity"] == "error" and "RANK" in m["code"]]
    assert rank_errors == [], f"Unexpected rank errors: {rank_errors}"


def test_organic_in_name_passes() -> None:
    """Column with 'organic' in name should pass semantic validation."""
    profile, columns = _profile_with_columns(
        [
            ("Search Term", ColumnInferredDataType.TEXT, ["shoes"]),
            ("Search Volume", ColumnInferredDataType.INTEGER, [1000]),
            ("Organic Position", ColumnInferredDataType.INTEGER, [3, 5, 12]),
        ]
    )

    status, messages, _ = validate_manual_mapping(
        profile=profile,
        columns=columns,
        mapping_json=ManualMappingJson(
            search_term="Search Term",
            search_volume="Search Volume",
            competitor_rank_columns=["Organic Position"],
        ),
    )

    assert status == ColumnMappingStatus.VALID
    rank_errors = [m for m in messages if m["severity"] == "error" and "RANK" in m["code"]]
    assert rank_errors == [], f"Unexpected rank errors: {rank_errors}"


def _profile_with_columns(definitions: list[tuple[str, ColumnInferredDataType, list]]) -> tuple[ColumnProfile, list[ColumnProfileColumn]]:
    now = datetime.now(UTC)
    workspace_id = uuid4()
    product_id = uuid4()
    upload_id = uuid4()
    parse_run_id = uuid4()
    profile_id = uuid4()
    profile = ColumnProfile(
        id=profile_id,
        workspace_id=workspace_id,
        product_id=product_id,
        upload_id=upload_id,
        parse_run_id=parse_run_id,
        status=ColumnProfileStatus.GENERATED,
        total_columns=len(definitions),
        total_rows_sampled=1,
        created_at=now,
        updated_at=now,
    )
    columns = [
        ColumnProfileColumn(
            id=uuid4(),
            workspace_id=workspace_id,
            product_id=product_id,
            upload_id=upload_id,
            parse_run_id=parse_run_id,
            column_profile_id=profile_id,
            original_column_name=name,
            normalized_column_name=name.lower(),
            column_index=index,
            non_null_count=len(samples),
            sample_values_json=samples,
            inferred_data_type=data_type,
            created_at=now,
        )
        for index, (name, data_type, samples) in enumerate(definitions)
    ]
    return profile, columns