def success_response(data: object, meta: dict | None = None) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": meta or {},
    }

