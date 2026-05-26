from apps.api.app.schemas.envelope import success_response
from apps.api.app.core.errors import error_response


def test_success_response_envelope() -> None:
    response = success_response(data={"ok": True}, meta={"page": 1})

    assert response == {
        "success": True,
        "data": {"ok": True},
        "meta": {"page": 1},
    }


def test_error_response_envelope() -> None:
    response = error_response(code="EXAMPLE", message="Example error.", details={"field": "name"})

    assert response == {
        "success": False,
        "error": {
            "code": "EXAMPLE",
            "message": "Example error.",
            "details": {"field": "name"},
        },
    }

