"""Small adapters shared by the Streamlit views.

The UI accepts dataclass records and dictionaries, and keeps repository method
calls at the boundary so the presentation layer does not own business rules.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import inspect
import re
from typing import Any, Iterable, Mapping, Sequence


def record_dict(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    if is_dataclass(record):
        return asdict(record)
    values = getattr(record, "__dict__", None)
    if isinstance(values, dict):
        return {key: value for key, value in values.items() if not key.startswith("_")}
    return {}


def field_value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def get_records(repo: Any, collection: str) -> list[Any]:
    """Read a collection from common repository APIs or their state mapping."""
    if repo is None:
        return []

    state = getattr(repo, "state", None)
    if callable(state):
        state = state()
    if not isinstance(state, Mapping):
        state = getattr(repo, "_state", None)
    if isinstance(state, Mapping) and collection in state:
        values = state[collection]
        if isinstance(values, Mapping):
            return list(values.values())
        return list(values) if isinstance(values, (list, tuple)) else []

    for method_name in (f"get_{collection}", f"list_{collection}", f"get_all_{collection}"):
        method = getattr(repo, method_name, None)
        if callable(method):
            values = method()
            if isinstance(values, Mapping) and collection in values:
                values = values[collection]
            if isinstance(values, Mapping):
                return list(values.values())
            return list(values) if isinstance(values, (list, tuple)) else []

    values = getattr(repo, collection, None)
    if callable(values):
        values = values()
    if isinstance(values, Mapping):
        return list(values.values())
    return list(values) if isinstance(values, (list, tuple)) else []


def next_record_id(records: Iterable[Any], prefix: str) -> str:
    """Generate the next readable ID, preserving the project's sample format."""
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$", re.IGNORECASE)
    highest = 0
    for record in records:
        record_id = str(field_value(record, "id", ""))
        match = pattern.fullmatch(record_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def call_repository(
    repo: Any,
    method_names: Sequence[str],
    *,
    payload: Mapping[str, Any],
    entity: Any = None,
    entity_name: str | None = None,
    required_any: Sequence[Sequence[str]] = (),
) -> Any:
    """Call the first available repository method using its declared signature."""
    if repo is None:
        raise RuntimeError("El repositorio CampusRepository aún no está disponible.")
    method = next((getattr(repo, name, None) for name in method_names if callable(getattr(repo, name, None))), None)
    if method is None:
        raise RuntimeError(f"El repositorio no implementa la operación {method_names[0]}.")

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        if entity is not None:
            return method(entity)
        return method(**dict(payload))

    parameters = [parameter for parameter in signature.parameters.values() if parameter.name != "self"]
    accepts_extra = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    supported = {parameter.name for parameter in parameters}
    for alternatives in required_any:
        if not accepts_extra and not supported.intersection(alternatives):
            raise RuntimeError("El repositorio no admite todos los datos requeridos para esta operación.")

    entity_aliases = {"entity", "record", "item", "data", "reservation", "loan", "incident"}
    values = dict(payload)
    if entity is not None:
        for alias in entity_aliases:
            values.setdefault(alias, entity)
        if entity_name:
            values.setdefault(entity_name, entity)

    if accepts_extra and not supported:
        return method(**dict(payload))

    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    entity_used = False
    for parameter in parameters:
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if parameter.name in values:
            value = values[parameter.name]
            entity_used = entity_used or (entity is not None and value is entity)
        elif parameter.default is not inspect.Parameter.empty:
            continue
        elif entity is not None and not entity_used:
            value = entity
            entity_used = True
        else:
            raise RuntimeError(f"No se pudo preparar el parámetro requerido '{parameter.name}' del repositorio.")

        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[parameter.name] = value

    if accepts_extra:
        for key, value in payload.items():
            if key not in kwargs and key not in supported:
                kwargs[key] = value
    return method(*args, **kwargs)


def _detail_from(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    detail = getattr(value, "message", None)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if isinstance(value, Mapping):
        for key in ("message", "detail", "error"):
            detail = value.get(key)
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
    return ""


def operation_result(result: Any) -> tuple[bool, str, str]:
    """Normalize booleans, ValidationResult objects, tuples, and result maps."""
    if result is None:
        return True, "", ""
    if isinstance(result, tuple) and result:
        for item in result:
            if getattr(item, "is_valid", None) is not None:
                return (
                    bool(getattr(item, "is_valid")),
                    _detail_from(item),
                    str(getattr(item, "rule_code", "") or ""),
                )
        first = result[0]
        if isinstance(first, bool):
            detail = _detail_from(result[1]) if len(result) > 1 else ""
            return first, detail, ""
        result = first
    if isinstance(result, bool):
        return result, "", ""

    is_valid = getattr(result, "is_valid", None)
    if is_valid is not None:
        message = _detail_from(result)
        code = str(getattr(result, "rule_code", "") or "")
        return bool(is_valid), message, code

    if isinstance(result, Mapping):
        success = result.get("is_valid", result.get("success", result.get("ok")))
        if success is not None:
            return bool(success), _detail_from(result), str(result.get("rule_code", "") or "")

    return True, _detail_from(result), ""


def format_failure(result: Any, default_code: str) -> str:
    ok, message, rule_code = operation_result(result)
    del ok
    code = rule_code.strip()
    if code and not message.startswith(f"[{code}]"):
        return f"[{code}] {message or 'La operación fue rechazada por una regla de negocio.'}"
    if message.startswith("[RN-"):
        return message
    return f"[{default_code}] {message or 'La operación fue rechazada. Revise los datos e inténtelo de nuevo.'}"


def exception_message(error: Exception, default_code: str) -> str:
    code = str(getattr(error, "rule_code", "") or "")
    message = str(getattr(error, "message", "") or error).strip()
    if code and not message.startswith(f"[{code}]"):
        return f"[{code}] {message}"
    if message.startswith("[RN-"):
        return message
    return f"[{default_code}] {message or 'No se pudo completar la operación.'}"


def now_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")


def status_badge(status: Any) -> str:
    normalized = str(status or "SIN ESTADO").strip().upper()
    icons = {
        "DISPONIBLE": "🟢",
        "OPERATIVO": "🟢",
        "ACTIVA": "🟢",
        "ACTIVO": "🟢",
        "OCUPADO": "🟡",
        "PRESTADO": "🟡",
        "EN_PROCESO": "🟡",
        "EN_MANTENIMIENTO": "🔴",
        "INHABILITADO": "🔴",
        "DADO_DE_BAJA": "⚫",
        "CANCELADA": "⚫",
        "FINALIZADA": "⚫",
        "DEVUELTO": "⚫",
        "RESUELTA": "⚫",
        "ABIERTA": "🔴",
    }
    return f"{icons.get(normalized, '⚪')} {normalized}"
