"""AI-assisted incident triage and campus allocation recommendations.

The Gemini client is loaded lazily so the app remains usable when the SDK, API
key, quota, or network is unavailable. In those cases the public functions use
the deterministic local rules in this module.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

try:
    from dotenv import dotenv_values
except ImportError:  # Keep deterministic fallback available before dependencies are installed.
    dotenv_values = None  # type: ignore[assignment]

from src.core.models import Resource, Space

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"
_GEMINI_MODEL = "gemini-2.5-flash"

INCIDENT_CATEGORIES = {
    "INFRAESTRUCTURA",
    "HARDWARE",
    "RED_CONECTIVIDAD",
    "MOBILIARIO",
    "BIENESTAR",
    "OTRO",
}
INCIDENT_PRIORITIES = {"CRITICA", "ALTA", "MEDIA", "BAJA"}
ASSIGNED_TEAMS = {
    "Soporte TI",
    "Mantenimiento Físico",
    "Bienestar Estudiantil",
    "Coordinación",
}

_TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": sorted(INCIDENT_CATEGORIES)},
        "priority": {"type": "string", "enum": sorted(INCIDENT_PRIORITIES)},
        "assigned_team": {"type": "string", "enum": sorted(ASSIGNED_TEAMS)},
        "suggested_action": {"type": "string"},
    },
    "required": ["category", "priority", "assigned_team", "suggested_action"],
    "propertyOrdering": ["category", "priority", "assigned_team", "suggested_action"],
}

_ALLOCATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommended_space_id": {"type": ["string", "null"]},
        "recommended_space_name": {"type": "string"},
        "recommended_resource_ids": {"type": "array", "items": {"type": "string"}},
        "justification": {"type": "string"},
    },
    "required": [
        "recommended_space_id",
        "recommended_space_name",
        "recommended_resource_ids",
        "justification",
    ],
    "propertyOrdering": [
        "recommended_space_id",
        "recommended_space_name",
        "recommended_resource_ids",
        "justification",
    ],
}


def _normalize(value: str) -> str:
    """Lowercase text and remove accents for deterministic keyword matching."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _load_gemini_api_key() -> str | None:
    """Read the key only from this project's .env file."""
    if dotenv_values is None:
        return None
    values = dotenv_values(_ENV_FILE)
    value = values.get("GEMINI_API_KEY")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.lower() not in {"tu_api_key_aqui_sin_comillas", "changeme"} else None


def _generate_json(prompt: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Call Gemini in JSON mode, returning None on any provider/parse failure."""
    api_key = _load_gemini_api_key()
    if not api_key:
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )
        response_text = getattr(response, "text", None)
        if not isinstance(response_text, str) or not response_text.strip():
            return None
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        # The local rules are the availability path for missing SDK, network,
        # quota, malformed responses, and provider errors.
        return None


def _category_for(text: str, target_type: str) -> str:
    if any(word in text for word in ("wifi", "internet", "red", "conectividad", "router", "senal")):
        return "RED_CONECTIVIDAD"
    if any(word in text for word in ("acoso", "ansiedad", "crisis emocional", "bienestar", "salud mental")):
        return "BIENESTAR"
    if any(word in text for word in ("silla", "mesa", "escritorio", "pupitre", "mobiliario")):
        return "MOBILIARIO"
    if any(word in text for word in ("portatil", "laptop", "computador", "teclado", "mouse", "proyector", "videobeam", "robot", "cable", "bateria")):
        return "HARDWARE"
    if any(word in text for word in ("aula", "salon", "tomacorriente", "corto circuito", "cortocircuito", "humo", "incendio", "aire acondicionado", "filtracion", "techo", "puerta", "luz", "electrico")):
        return "INFRAESTRUCTURA"
    if target_type.upper() == "RECURSO":
        return "HARDWARE"
    return "OTRO"


def _priority_for(text: str) -> str:
    critical_terms = (
        "humo", "incendio", "fuego", "corto circuito", "cortocircuito",
        "electrocut", "explosion", "herido", "lesionado", "olor a quemado",
    )
    if any(term in text for term in critical_terms):
        return "CRITICA"
    high_terms = (
        "no funciona", "no enciende", "sin internet", "sin energia", "inundacion",
        "fuga de agua", "danado", "averiado", "roto", "bloquea la salida",
    )
    if any(term in text for term in high_terms):
        return "ALTA"
    if any(term in text for term in ("falla", "intermitente", "ruido", "desconecta", "lento", "incomodo")):
        return "MEDIA"
    return "BAJA"


def _team_for(category: str) -> str:
    if category in {"INFRAESTRUCTURA", "MOBILIARIO"}:
        return "Mantenimiento Físico"
    if category in {"HARDWARE", "RED_CONECTIVIDAD"}:
        return "Soporte TI"
    if category == "BIENESTAR":
        return "Bienestar Estudiantil"
    return "Coordinación"


def _fallback_triage(title: str, description: str, target_type: str, target_name: str) -> dict[str, str]:
    combined = _normalize(" ".join((title, description, target_type, target_name)))
    category = _category_for(combined, target_type)
    priority = _priority_for(combined)
    action_by_category = {
        "INFRAESTRUCTURA": "Aislar el área y solicitar inspección de mantenimiento antes de volver a habilitarla.",
        "HARDWARE": "Retirar el equipo de servicio, registrar el daño y solicitar revisión técnica.",
        "RED_CONECTIVIDAD": "Verificar conectividad y equipos de red; escalar a soporte TI si persiste.",
        "MOBILIARIO": "Señalizar el elemento y solicitar reparación o reemplazo.",
        "BIENESTAR": "Contactar al equipo de Bienestar Estudiantil y atender el caso con privacidad.",
        "OTRO": "Validar el reporte y asignarlo a Coordinación para determinar el área responsable.",
    }
    if priority == "CRITICA":
        action = "Atender de inmediato, aislar el activo o área afectada y avisar al equipo responsable. " + action_by_category[category]
    elif priority == "ALTA":
        action = "Priorizar la atención y evitar el uso del activo afectado hasta su revisión. " + action_by_category[category]
    else:
        action = action_by_category[category]
    return {
        "category": category,
        "priority": priority,
        "assigned_team": _team_for(category),
        "suggested_action": action,
        "ai_source": "FALLBACK_RULES",
    }


def triage_incident(title: str, description: str, target_type: str, target_name: str = "") -> dict[str, str]:
    """Classify an incident and return the contract used by the UI/repository."""
    fallback = _fallback_triage(title, description, target_type, target_name)
    prompt = f"""Clasifica el reporte operativo de Campuslands. Usa solo estas categorías: {', '.join(sorted(INCIDENT_CATEGORIES))}.
Usa solo estas prioridades: CRITICA, ALTA, MEDIA, BAJA. Asigna el equipo adecuado de esta lista: {', '.join(sorted(ASSIGNED_TEAMS))}.
Devuelve exclusivamente los campos del esquema JSON. Prioriza el riesgo a personas y fuego/electricidad.

Título: {title}
Descripción: {description}
Tipo de activo: {target_type}
Activo: {target_name or 'No especificado'}"""
    model_result = _generate_json(prompt, _TRIAGE_SCHEMA)
    if not model_result:
        return fallback

    category = model_result.get("category")
    priority = model_result.get("priority")
    team = model_result.get("assigned_team")
    action = model_result.get("suggested_action")
    if (
        not isinstance(category, str)
        or category not in INCIDENT_CATEGORIES
        or not isinstance(priority, str)
        or priority not in INCIDENT_PRIORITIES
    ):
        return fallback
    if not isinstance(action, str) or not action.strip():
        return fallback
    if not isinstance(team, str) or team not in ASSIGNED_TEAMS:
        team = _team_for(category)
    return {
        "category": category,
        "priority": priority,
        "assigned_team": team,
        "suggested_action": action.strip(),
        "ai_source": "AI_MODEL",
    }


def _available_spaces(spaces: list[Space]) -> list[Space]:
    return [space for space in spaces if space.status.upper() == "DISPONIBLE"]


def _available_resources(resources: list[Resource]) -> list[Resource]:
    return [resource for resource in resources if resource.status.upper() == "OPERATIVO"]


def _requested_capacity(query: str) -> int | None:
    match = re.search(r"\b(\d{1,4})\s*(?:personas?|estudiantes?|asistentes?|campers?|participantes?)\b", query)
    return int(match.group(1)) if match else None


def _space_score(space: Space, query: str, requested_capacity: int | None) -> tuple[int, int, str]:
    normalized_name = _normalize(space.name)
    normalized_type = _normalize(space.type)
    normalized_features = _normalize(" ".join(space.features))
    score = 0
    if any(term in query for term in ("auditorio", "conferencia", "exposicion", "presentacion")) and "auditorio" in normalized_type:
        score += 8
    if any(term in query for term in ("laboratorio", "robotica", "electronica", "experimento")) and "laboratorio" in normalized_type:
        score += 8
    if any(term in query for term in ("cubiculo", "reunion pequena", "tutoria")) and "cubiculo" in normalized_type:
        score += 6
    feature_terms = {
        "proyector": ("proyector", "videobeam"),
        "videobeam": ("proyector", "videobeam"),
        "aire acondicionado": ("aire acondicionado", "aire"),
        "computador": ("computador", "pc", "computo"),
        "tablero": ("tablero",),
        "robotica": ("robotica", "kit de robotica"),
    }
    for requested, aliases in feature_terms.items():
        if requested in query and any(alias in normalized_features for alias in aliases):
            score += 3
    if any(token in query for token in normalized_name.split() if len(token) > 3):
        score += 2
    if requested_capacity is not None:
        score += 5 if space.capacity >= requested_capacity else -1000
        capacity_tiebreak = space.capacity
    else:
        capacity_tiebreak = 0
    return score, -capacity_tiebreak, space.id


def _resource_requested(query: str, resource: Resource) -> bool:
    category = resource.category.upper()
    resource_text = _normalize(f"{resource.name} {resource.category}")
    category_terms = {
        "COMPUTO": ("portatil", "laptop", "computador", "computo", "pc"),
        "AUDIOVISUAL": ("proyector", "videobeam", "microfono", "parlante", "audiovisual"),
        "ROBOTICA": ("robot", "robotica", "arduino", "kit"),
        "ACCESORIO": ("cable", "adaptador", "accesorio"),
    }
    terms = category_terms.get(category, ())
    return any(term in query for term in terms) or any(term in query for term in resource_text.split() if len(term) > 3)


def _fallback_allocation(
    user_query: str,
    available_spaces: list[Space],
    available_resources: list[Resource],
) -> dict[str, Any]:
    query = _normalize(user_query)
    spaces = _available_spaces(available_spaces)
    resources = _available_resources(available_resources)
    requested_capacity = _requested_capacity(query)
    recommended_space: Space | None = None
    if spaces:
        ranked_spaces = sorted(spaces, key=lambda space: _space_score(space, query, requested_capacity), reverse=True)
        best = ranked_spaces[0]
        if requested_capacity is None or best.capacity >= requested_capacity:
            recommended_space = best

    matching_resources = [resource for resource in resources if _resource_requested(query, resource)]
    quantity_match = re.search(
        r"\b(\d{1,2})\s*(?:portatiles?|laptops?|computadores?|proyectores?|kits?|microfonos?|cables?)\b",
        query,
    )
    requested_quantity = int(quantity_match.group(1)) if quantity_match else 1
    recommended_resource_ids = [resource.id for resource in matching_resources[:requested_quantity]]

    if recommended_space is None and not recommended_resource_ids:
        justification = "No se encontró un espacio o recurso operativo que satisfaga la solicitud."
    else:
        choices: list[str] = []
        if recommended_space:
            choices.append(f"{recommended_space.name} (capacidad {recommended_space.capacity})")
        if recommended_resource_ids:
            choices.append(f"{len(recommended_resource_ids)} recurso(s) operativo(s) solicitado(s)")
        justification = "Recomendación basada en disponibilidad actual y coincidencia con la solicitud: " + "; ".join(choices) + "."
    return {
        "recommended_space_id": recommended_space.id if recommended_space else None,
        "recommended_space_name": recommended_space.name if recommended_space else "Sin espacio disponible",
        "recommended_resource_ids": recommended_resource_ids,
        "justification": justification,
        "ai_source": "FALLBACK_RULES",
    }


def recommend_campus_allocation(
    user_query: str,
    available_spaces: list[Space],
    available_resources: list[Resource],
) -> dict[str, Any]:
    """Recommend only currently operational inventory relevant to the request."""
    fallback = _fallback_allocation(user_query, available_spaces, available_resources)
    spaces = _available_spaces(available_spaces)
    resources = _available_resources(available_resources)
    inventory = {
        "spaces": [
            {"id": space.id, "name": space.name, "type": space.type, "capacity": space.capacity, "features": space.features}
            for space in spaces
        ],
        "resources": [
            {"id": resource.id, "name": resource.name, "category": resource.category}
            for resource in resources
        ],
    }
    prompt = f"""Recomienda recursos para esta solicitud del campus usando exclusivamente el inventario disponible incluido abajo.
No inventes IDs. Si no hay un espacio adecuado, recommended_space_id debe ser null y el nombre debe indicar que no hay espacio.
Devuelve exclusivamente los campos del esquema JSON.

Solicitud: {user_query}
Inventario disponible: {json.dumps(inventory, ensure_ascii=False)}"""
    model_result = _generate_json(prompt, _ALLOCATION_SCHEMA)
    if not model_result:
        return fallback

    allowed_space_ids = {space.id for space in spaces}
    allowed_resources_by_id = {resource.id: resource for resource in resources}
    space_id = model_result.get("recommended_space_id")
    if not isinstance(space_id, str) or space_id not in allowed_space_ids:
        space_id = None
    space_name = next((space.name for space in spaces if space.id == space_id), "Sin espacio disponible")

    raw_resource_ids = model_result.get("recommended_resource_ids")
    if not isinstance(raw_resource_ids, list):
        return fallback
    resource_ids: list[str] = []
    for resource_id in raw_resource_ids:
        if isinstance(resource_id, str) and resource_id in allowed_resources_by_id and resource_id not in resource_ids:
            resource_ids.append(resource_id)
    justification = model_result.get("justification")
    if not isinstance(justification, str) or not justification.strip():
        return fallback
    return {
        "recommended_space_id": space_id,
        "recommended_space_name": space_name,
        "recommended_resource_ids": resource_ids,
        "justification": justification.strip(),
        "ai_source": "AI_MODEL",
    }
