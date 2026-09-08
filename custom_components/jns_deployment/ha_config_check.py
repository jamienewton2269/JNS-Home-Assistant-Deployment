from __future__ import annotations
from typing import Any

def summarize_config_check_result(result: Any) -> dict[str, Any]:
    """Interpret Home Assistant's HomeAssistantConfig correctly."""
    errors = getattr(result, "errors", None)
    warnings = getattr(result, "warnings", None)
    if errors is None or warnings is None:
        raise TypeError(
            "Unexpected Home Assistant configuration-check result: "
            "missing errors/warnings attributes."
        )
    error_messages = [str(getattr(item, "message", item)) for item in errors]
    warning_messages = [str(getattr(item, "message", item)) for item in warnings]
    return {
        "status": "failed" if error_messages else "passed",
        "errors": error_messages,
        "warnings": warning_messages,
    }
