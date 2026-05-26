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
