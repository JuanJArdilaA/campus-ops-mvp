"""
src/core/sanitizer.py — Ingesta tolerante a fallos y cuarentena de datos sucios (RN-05).

Responsable: Miguel
Genera datasets semilla en data/raw/ si no existen, lee archivos JSON/CSV,
normaliza estados/tipos, y aísla registros corruptos en QuarantineRecord.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path
from typing import Any

from src.core.models import (
    Space,
    Resource,
    Reservation,
    Loan,
    Incident,
    QuarantineRecord,
)

# ──────────────────────────────────────────────────────────────
# Constantes de normalización
# ──────────────────────────────────────────────────────────────

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
RAW_DIR: Path = _PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR: Path = _PROJECT_ROOT / "data" / "processed"

# Mapeo flexible de nombres de columna (español → inglés canónico)
_COLUMN_ALIASES: dict[str, str] = {
    # Spaces
    "nombre": "name",
    "tipo": "type",
    "capacidad": "capacity",
    "estado": "status",
    "caracteristicas": "features",
    "notas": "notes",
    "ubicacion": "location",
    # Resources
    "categoria": "category",
    "prestatario_actual": "current_borrower",
    # Reservations
    "espacio_id": "space_id",
    "solicitante_id": "requester_id",
    "nombre_solicitante": "requester_name",
    "fecha": "date",
    "hora_inicio": "start_time",
    "hora_fin": "end_time",
    "asistentes": "attendees",
    "proposito": "purpose",
    # Loans
    "recurso_id": "resource_id",
    "prestatario_id": "borrower_id",
    "nombre_prestatario": "borrower_name",
    "rol_prestatario": "borrower_role",
    "fecha_prestamo": "loan_timestamp",
    "retorno_esperado": "expected_return",
    "retorno_real": "actual_return",
    "notas_devolucion": "return_notes",
    # Incidents
    "titulo": "title",
    "descripcion": "description",
    "reportante": "reporter_name",
    "tipo_objetivo": "target_type",
    "id_objetivo": "target_id",
    "prioridad": "priority",
    "equipo_asignado": "assigned_team",
    "accion_sugerida": "suggested_action",
    "fuente_ia": "ai_source",
    "creado_en": "created_at",
}

# Valores válidos por campo (para normalización y validación)
VALID_SPACE_TYPES: set[str] = {"AULA", "CUBICULO", "LABORATORIO", "AUDITORIO"}
VALID_SPACE_STATUSES: set[str] = {"DISPONIBLE", "OCUPADO", "EN_MANTENIMIENTO", "INHABILITADO"}
VALID_RESOURCE_CATEGORIES: set[str] = {"COMPUTO", "AUDIOVISUAL", "ROBOTICA", "ACCESORIO"}
VALID_RESOURCE_STATUSES: set[str] = {"OPERATIVO", "PRESTADO", "EN_MANTENIMIENTO", "DADO_DE_BAJA"}
VALID_RESERVATION_STATUSES: set[str] = {"ACTIVA", "FINALIZADA", "CANCELADA"}
VALID_LOAN_STATUSES: set[str] = {"ACTIVO", "DEVUELTO"}
VALID_INCIDENT_STATUSES: set[str] = {"ABIERTA", "EN_PROCESO", "RESUELTA"}
VALID_INCIDENT_PRIORITIES: set[str] = {"CRITICA", "ALTA", "MEDIA", "BAJA"}
VALID_INCIDENT_CATEGORIES: set[str] = {
    "INFRAESTRUCTURA", "HARDWARE", "RED_CONECTIVIDAD",
    "MOBILIARIO", "BIENESTAR", "OTRO",
}
VALID_TARGET_TYPES: set[str] = {"ESPACIO", "RECURSO", "GENERAL"}
VALID_BORROWER_ROLES: set[str] = {"CAMPER", "TRAINER", "STAFF"}


# ──────────────────────────────────────────────────────────────
# Utilidades de normalización
# ──────────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Elimina tildes/diacríticos de una cadena Unicode."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_text(value: str) -> str:
    """Normaliza un string: strip, quita tildes, MAYÚSCULAS."""
    return _strip_accents(value.strip()).upper()


def _normalize_columns(record: dict[str, Any]) -> dict[str, Any]:
    """Traduce columnas en español a sus nombres canónicos en inglés."""
    normalized: dict[str, Any] = {}
    for key, val in record.items():
        canonical = _COLUMN_ALIASES.get(key.lower().strip(), key.lower().strip())
        normalized[canonical] = val
    return normalized


# ──────────────────────────────────────────────────────────────
# Lectura de archivos crudos (JSON o CSV)
# ──────────────────────────────────────────────────────────────

def _read_raw_file(file_path: Path) -> list[dict[str, Any]]:
    """Lee un archivo JSON o CSV y retorna una lista de dicts."""
    if not file_path.exists():
        return []

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    elif suffix == ".csv":
        with open(file_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
    else:
        return []


def _discover_raw_files(entity_prefix: str) -> list[Path]:
    """Encuentra archivos en data/raw/ que coincidan con un prefijo de entidad."""
    if not RAW_DIR.exists():
        return []
    matches: list[Path] = []
    for p in sorted(RAW_DIR.iterdir()):
        if p.stem.lower().startswith(entity_prefix.lower()) and p.suffix.lower() in (".json", ".csv"):
            matches.append(p)
    return matches


# ──────────────────────────────────────────────────────────────
# Sanitizadores por entidad
# ──────────────────────────────────────────────────────────────

def _sanitize_space(raw: dict[str, Any], seen_ids: set[str]) -> tuple[Space | None, QuarantineRecord | None]:
    """Intenta construir un Space válido; si falla, genera QuarantineRecord."""
    rec = _normalize_columns(raw)

    # 1. ID obligatorio y no duplicado
    space_id = str(rec.get("id", "")).strip()
    if not space_id:
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason="ID vacío o ausente",
        )
    if space_id in seen_ids:
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason=f"ID duplicado: '{space_id}'",
        )

    # 2. Nombre obligatorio
    name = str(rec.get("name", "")).strip()
    if not name:
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason="Nombre vacío o ausente",
        )

    # 3. Tipo válido
    raw_type = _normalize_text(str(rec.get("type", "")))
    if raw_type not in VALID_SPACE_TYPES:
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason=f"Tipo de espacio no reconocido: '{rec.get('type')}'",
        )

    # 4. Capacidad > 0 y numérica
    try:
        capacity = int(rec.get("capacity", 0))
    except (ValueError, TypeError):
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason=f"Capacidad no numérica: '{rec.get('capacity')}'",
        )
    if capacity <= 0:
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason=f"Capacidad inválida (<= 0): {capacity}",
        )

    # 5. Estado — normalizar variantes conocidas
    raw_status = _normalize_text(str(rec.get("status", "DISPONIBLE")))
    if raw_status not in VALID_SPACE_STATUSES:
        return None, QuarantineRecord(
            source_entity="spaces",
            raw_data=raw,
            reason=f"Estado de espacio no reconocido: '{rec.get('status')}'",
        )

    # 6. Features
    features_raw = rec.get("features", [])
    if isinstance(features_raw, str):
        features = [f.strip() for f in features_raw.split(",") if f.strip()]
    elif isinstance(features_raw, list):
        features = [str(f).strip() for f in features_raw if str(f).strip()]
    else:
        features = []

    notes = str(rec.get("notes", ""))

    seen_ids.add(space_id)
    return Space(
        id=space_id,
        name=name,
        type=raw_type,
        capacity=capacity,
        status=raw_status,
        features=features,
        notes=notes,
    ), None


def _sanitize_resource(raw: dict[str, Any], seen_ids: set[str]) -> tuple[Resource | None, QuarantineRecord | None]:
    """Intenta construir un Resource válido; si falla, genera QuarantineRecord."""
    rec = _normalize_columns(raw)

    # 1. ID obligatorio y no duplicado
    res_id = str(rec.get("id", "")).strip()
    if not res_id:
        return None, QuarantineRecord(
            source_entity="resources",
            raw_data=raw,
            reason="ID vacío o ausente",
        )
    if res_id in seen_ids:
        return None, QuarantineRecord(
            source_entity="resources",
            raw_data=raw,
            reason=f"ID duplicado: '{res_id}'",
        )

    # 2. Nombre obligatorio
    name = str(rec.get("name", "")).strip()
    if not name:
        return None, QuarantineRecord(
            source_entity="resources",
            raw_data=raw,
            reason="Nombre vacío o ausente",
        )

    # 3. Categoría válida
    raw_cat = _normalize_text(str(rec.get("category", "")))
    if raw_cat not in VALID_RESOURCE_CATEGORIES:
        return None, QuarantineRecord(
            source_entity="resources",
            raw_data=raw,
            reason=f"Categoría de recurso no reconocida: '{rec.get('category')}'",
        )

    # 4. Estado — normalizar
    raw_status = _normalize_text(str(rec.get("status", "OPERATIVO")))
    if raw_status not in VALID_RESOURCE_STATUSES:
        return None, QuarantineRecord(
            source_entity="resources",
            raw_data=raw,
            reason=f"Estado de recurso no reconocido: '{rec.get('status')}'",
        )

    location = str(rec.get("location", "Bodega Central")).strip()
    borrower = rec.get("current_borrower")
    if borrower is not None:
        borrower = str(borrower).strip() or None
    notes = str(rec.get("notes", ""))

    seen_ids.add(res_id)
    return Resource(
        id=res_id,
        name=name,
        category=raw_cat,
        status=raw_status,
        location=location,
        current_borrower=borrower,
        notes=notes,
    ), None


def _sanitize_reservation(
    raw: dict[str, Any],
    seen_ids: set[str],
    valid_space_ids: set[str],
) -> tuple[Reservation | None, QuarantineRecord | None]:
    """Intenta construir una Reservation válida."""
    rec = _normalize_columns(raw)

    rsv_id = str(rec.get("id", "")).strip()
    if not rsv_id:
        return None, QuarantineRecord(source_entity="reservations", raw_data=raw, reason="ID vacío o ausente")
    if rsv_id in seen_ids:
        return None, QuarantineRecord(source_entity="reservations", raw_data=raw, reason=f"ID duplicado: '{rsv_id}'")

    space_id = str(rec.get("space_id", "")).strip()
    if space_id and space_id not in valid_space_ids:
        return None, QuarantineRecord(
            source_entity="reservations",
            raw_data=raw,
            reason=f"Referencia huérfana: ID de activo no existe (space_id='{space_id}')",
        )

    # Validación básica de campos obligatorios
    requester_id = str(rec.get("requester_id", "")).strip()
    requester_name = str(rec.get("requester_name", "")).strip()
    date = str(rec.get("date", "")).strip()
    start_time = str(rec.get("start_time", "")).strip()
    end_time = str(rec.get("end_time", "")).strip()
    purpose = str(rec.get("purpose", "")).strip()

    for field_name, field_val in [
        ("requester_id", requester_id), ("date", date),
        ("start_time", start_time), ("end_time", end_time),
    ]:
        if not field_val:
            return None, QuarantineRecord(
                source_entity="reservations", raw_data=raw,
                reason=f"Campo obligatorio vacío: '{field_name}'",
            )

    try:
        attendees = int(rec.get("attendees", 0))
    except (ValueError, TypeError):
        return None, QuarantineRecord(
            source_entity="reservations", raw_data=raw,
            reason=f"Asistentes no numérico: '{rec.get('attendees')}'",
        )
    if attendees <= 0:
        return None, QuarantineRecord(
            source_entity="reservations", raw_data=raw,
            reason=f"Asistentes inválido (<= 0): {attendees}",
        )

    raw_status = _normalize_text(str(rec.get("status", "ACTIVA")))
    if raw_status not in VALID_RESERVATION_STATUSES:
        return None, QuarantineRecord(
            source_entity="reservations", raw_data=raw,
            reason=f"Estado de reserva no reconocido: '{rec.get('status')}'",
        )

    seen_ids.add(rsv_id)
    return Reservation(
        id=rsv_id,
        space_id=space_id,
        requester_id=requester_id,
        requester_name=requester_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        attendees=attendees,
        purpose=purpose,
        status=raw_status,
    ), None


def _sanitize_loan(
    raw: dict[str, Any],
    seen_ids: set[str],
    valid_resource_ids: set[str],
) -> tuple[Loan | None, QuarantineRecord | None]:
    """Intenta construir un Loan válido."""
    rec = _normalize_columns(raw)

    loan_id = str(rec.get("id", "")).strip()
    if not loan_id:
        return None, QuarantineRecord(source_entity="loans", raw_data=raw, reason="ID vacío o ausente")
    if loan_id in seen_ids:
        return None, QuarantineRecord(source_entity="loans", raw_data=raw, reason=f"ID duplicado: '{loan_id}'")

    resource_id = str(rec.get("resource_id", "")).strip()
    if resource_id and resource_id not in valid_resource_ids:
        return None, QuarantineRecord(
            source_entity="loans", raw_data=raw,
            reason=f"Referencia huérfana: ID de activo no existe (resource_id='{resource_id}')",
        )

    borrower_id = str(rec.get("borrower_id", "")).strip()
    borrower_name = str(rec.get("borrower_name", "")).strip()
    borrower_role = _normalize_text(str(rec.get("borrower_role", "")))
    loan_timestamp = str(rec.get("loan_timestamp", "")).strip()
    expected_return = str(rec.get("expected_return", "")).strip()

    for field_name, field_val in [
        ("borrower_id", borrower_id), ("loan_timestamp", loan_timestamp),
        ("expected_return", expected_return),
    ]:
        if not field_val:
            return None, QuarantineRecord(
                source_entity="loans", raw_data=raw,
                reason=f"Campo obligatorio vacío: '{field_name}'",
            )

    if borrower_role and borrower_role not in VALID_BORROWER_ROLES:
        return None, QuarantineRecord(
            source_entity="loans", raw_data=raw,
            reason=f"Rol de prestatario no reconocido: '{rec.get('borrower_role')}'",
        )

    raw_status = _normalize_text(str(rec.get("status", "ACTIVO")))
    if raw_status not in VALID_LOAN_STATUSES:
        return None, QuarantineRecord(
            source_entity="loans", raw_data=raw,
            reason=f"Estado de préstamo no reconocido: '{rec.get('status')}'",
        )

    actual_return = rec.get("actual_return")
    if actual_return is not None:
        actual_return = str(actual_return).strip() or None
    return_notes = str(rec.get("return_notes", ""))

    seen_ids.add(loan_id)
    return Loan(
        id=loan_id,
        resource_id=resource_id,
        borrower_id=borrower_id,
        borrower_name=borrower_name,
        borrower_role=borrower_role or "CAMPER",
        loan_timestamp=loan_timestamp,
        expected_return=expected_return,
        actual_return=actual_return,
        status=raw_status,
        return_notes=return_notes,
    ), None


def _sanitize_incident(
    raw: dict[str, Any],
    seen_ids: set[str],
    valid_space_ids: set[str],
    valid_resource_ids: set[str],
) -> tuple[Incident | None, QuarantineRecord | None]:
    """Intenta construir un Incident válido."""
    rec = _normalize_columns(raw)

    inc_id = str(rec.get("id", "")).strip()
    if not inc_id:
        return None, QuarantineRecord(source_entity="incidents", raw_data=raw, reason="ID vacío o ausente")
    if inc_id in seen_ids:
        return None, QuarantineRecord(source_entity="incidents", raw_data=raw, reason=f"ID duplicado: '{inc_id}'")

    target_type = _normalize_text(str(rec.get("target_type", "GENERAL")))
    if target_type not in VALID_TARGET_TYPES:
        return None, QuarantineRecord(
            source_entity="incidents", raw_data=raw,
            reason=f"Tipo de objetivo no reconocido: '{rec.get('target_type')}'",
        )

    target_id = rec.get("target_id")
    if target_id is not None:
        target_id = str(target_id).strip() or None

    # Validar referencia huérfana
    if target_id:
        if target_type == "ESPACIO" and target_id not in valid_space_ids:
            return None, QuarantineRecord(
                source_entity="incidents", raw_data=raw,
                reason=f"Referencia huérfana: ID de activo no existe (space_id='{target_id}')",
            )
        if target_type == "RECURSO" and target_id not in valid_resource_ids:
            return None, QuarantineRecord(
                source_entity="incidents", raw_data=raw,
                reason=f"Referencia huérfana: ID de activo no existe (resource_id='{target_id}')",
            )

    title = str(rec.get("title", "")).strip()
    description = str(rec.get("description", "")).strip()
    reporter_name = str(rec.get("reporter_name", "")).strip()

    if not title:
        return None, QuarantineRecord(
            source_entity="incidents", raw_data=raw,
            reason="Campo obligatorio vacío: 'title'",
        )

    category = _normalize_text(str(rec.get("category", "OTRO")))
    if category not in VALID_INCIDENT_CATEGORIES:
        category = "OTRO"

    priority = _normalize_text(str(rec.get("priority", "MEDIA")))
    if priority not in VALID_INCIDENT_PRIORITIES:
        return None, QuarantineRecord(
            source_entity="incidents", raw_data=raw,
            reason=f"Prioridad no reconocida: '{rec.get('priority')}'",
        )

    raw_status = _normalize_text(str(rec.get("status", "ABIERTA")))
    if raw_status not in VALID_INCIDENT_STATUSES:
        return None, QuarantineRecord(
            source_entity="incidents", raw_data=raw,
            reason=f"Estado de incidencia no reconocido: '{rec.get('status')}'",
        )

    assigned_team = str(rec.get("assigned_team", "Coordinación")).strip()
    suggested_action = str(rec.get("suggested_action", "")).strip()
    ai_source = str(rec.get("ai_source", "FALLBACK_RULES")).strip()
    created_at = str(rec.get("created_at", "")).strip()

    seen_ids.add(inc_id)
    return Incident(
        id=inc_id,
        title=title,
        description=description,
        reporter_name=reporter_name,
        target_type=target_type,
        target_id=target_id,
        category=category,
        priority=priority,
        assigned_team=assigned_team,
        suggested_action=suggested_action,
        ai_source=ai_source,
        status=raw_status,
        created_at=created_at,
    ), None


# ──────────────────────────────────────────────────────────────
# Función pública principal
# ──────────────────────────────────────────────────────────────

def load_and_sanitize_raw_data() -> dict[str, list[Any]]:
    """
    Lee todos los archivos de data/raw/, los sanitiza y retorna un dict
    con las listas de entidades válidas y los registros en cuarentena.

    Retorna:
        {
            "spaces": list[Space],
            "resources": list[Resource],
            "reservations": list[Reservation],
            "loans": list[Loan],
            "incidents": list[Incident],
            "quarantine": list[QuarantineRecord],
        }
    """
    result: dict[str, list[Any]] = {
        "spaces": [],
        "resources": [],
        "reservations": [],
        "loans": [],
        "incidents": [],
        "quarantine": [],
    }

    # --- Generar dataset semilla si data/raw/ está vacío ---
    _ensure_seed_data_exists()

    # --- 1. Espacios ---
    space_ids: set[str] = set()
    for file_path in _discover_raw_files("space"):
        for raw_record in _read_raw_file(file_path):
            space, quarantine = _sanitize_space(raw_record, space_ids)
            if space is not None:
                result["spaces"].append(space)
            if quarantine is not None:
                result["quarantine"].append(quarantine)

    # --- 2. Recursos ---
    resource_ids: set[str] = set()
    for file_path in _discover_raw_files("resource"):
        for raw_record in _read_raw_file(file_path):
            resource, quarantine = _sanitize_resource(raw_record, resource_ids)
            if resource is not None:
                result["resources"].append(resource)
            if quarantine is not None:
                result["quarantine"].append(quarantine)

    valid_space_ids = {s.id for s in result["spaces"]}
    valid_resource_ids = {r.id for r in result["resources"]}

    # --- 3. Reservaciones ---
    reservation_ids: set[str] = set()
    for file_path in _discover_raw_files("reservation"):
        for raw_record in _read_raw_file(file_path):
            reservation, quarantine = _sanitize_reservation(
                raw_record, reservation_ids, valid_space_ids,
            )
            if reservation is not None:
                result["reservations"].append(reservation)
            if quarantine is not None:
                result["quarantine"].append(quarantine)

    # --- 4. Préstamos ---
    loan_ids: set[str] = set()
    for file_path in _discover_raw_files("loan"):
        for raw_record in _read_raw_file(file_path):
            loan, quarantine = _sanitize_loan(
                raw_record, loan_ids, valid_resource_ids,
            )
            if loan is not None:
                result["loans"].append(loan)
            if quarantine is not None:
                result["quarantine"].append(quarantine)

    # --- 5. Incidencias ---
    incident_ids: set[str] = set()
    for file_path in _discover_raw_files("incident"):
        for raw_record in _read_raw_file(file_path):
            incident, quarantine = _sanitize_incident(
                raw_record, incident_ids, valid_space_ids, valid_resource_ids,
            )
            if incident is not None:
                result["incidents"].append(incident)
            if quarantine is not None:
                result["quarantine"].append(quarantine)

    return result


# ──────────────────────────────────────────────────────────────
# Generador de dataset semilla
# ──────────────────────────────────────────────────────────────

_SEED_SPACES: list[dict[str, Any]] = [
    {
        "id": "SP-101", "name": "Aula Sputnik", "type": "AULA",
        "capacity": 30, "status": "DISPONIBLE",
        "features": ["Videobeam", "Aire Acondicionado"], "notes": "",
    },
    {
        "id": "SP-102", "name": "Aula Apolo", "type": "AULA",
        "capacity": 25, "status": "disponible",
        "features": ["Televisor 55\""], "notes": "",
    },
    {
        "id": "SP-103", "name": "Laboratorio Artemis", "type": "LABORATORIO",
        "capacity": 20, "status": "DISPONIBLE",
        "features": ["Videobeam", "Tablero Digital"], "notes": "",
    },
    {
        "id": "SP-104", "name": "Cubículo Halley", "type": "CUBICULO",
        "capacity": 6, "status": "DISPONIBLE", "features": [], "notes": "",
    },
    {
        "id": "SP-105", "name": "Auditorio Principal", "type": "AUDITORIO",
        "capacity": 120, "status": "Disponible",
        "features": ["Sonido Profesional", "Videobeam", "Aire Acondicionado"],
        "notes": "",
    },
    {
        "id": "SP-106", "name": "Aula Gagarin", "type": "AULA",
        "capacity": 28, "status": "OCUPADO",
        "features": ["Videobeam"], "notes": "En uso por cohorte Java",
    },
    {
        "id": "SP-107", "name": "Cubículo Kepler", "type": "CUBICULO",
        "capacity": 4, "status": "DISPONIBLE", "features": [], "notes": "",
    },
    # --- Registros corruptos intencionales ---
    {
        "id": "", "name": "Aula Fantasma", "type": "AULA",
        "capacity": 15, "status": "DISPONIBLE", "features": [],
        "notes": "CORRUPTO: ID vacío",
    },
    {
        "id": "SP-109", "name": "Aula Negativa", "type": "AULA",
        "capacity": -15, "status": "DISPONIBLE", "features": [],
        "notes": "CORRUPTO: capacidad negativa",
    },
]

_SEED_RESOURCES: list[dict[str, Any]] = [
    {
        "id": "RES-01", "name": "MacBook Pro M2 #01", "category": "COMPUTO",
        "status": "OPERATIVO", "location": "Bodega Central",
        "current_borrower": None, "notes": "",
    },
    {
        "id": "RES-02", "name": "MacBook Pro M2 #02", "category": "COMPUTO",
        "status": "operativo", "location": "Bodega Central",
        "current_borrower": None, "notes": "",
    },
    {
        "id": "RES-03", "name": "Proyector Epson S41+", "category": "AUDIOVISUAL",
        "status": "OPERATIVO", "location": "Bodega Central",
        "current_borrower": None, "notes": "",
    },
    {
        "id": "RES-04", "name": "Kit Arduino Mega #01", "category": "ROBOTICA",
        "status": "OPERATIVO", "location": "Laboratorio Artemis",
        "current_borrower": None, "notes": "",
    },
    {
        "id": "RES-05", "name": "Cable HDMI 3m", "category": "ACCESORIO",
        "status": "OPERATIVO", "location": "Bodega Central",
        "current_borrower": None, "notes": "",
    },
    {
        "id": "RES-06", "name": "ThinkPad T14 #03", "category": "COMPUTO",
        "status": "PRESTADO", "location": "Bodega Central",
        "current_borrower": "CAM-2024-050", "notes": "",
    },
    {
        "id": "RES-07", "name": "Proyector Epson S41+ #02", "category": "AUDIOVISUAL",
        "status": "EN_MANTENIMIENTO", "location": "Bodega Central",
        "current_borrower": None, "notes": "Lámpara quemada",
    },
    # --- Registros corruptos intencionales ---
    {
        "id": "RES-08", "name": "Equipo Roto Fantasma", "category": "COMPUTO",
        "status": "Averiado", "location": "Bodega Central",
        "current_borrower": None, "notes": "CORRUPTO: estado 'Averiado'",
    },
    {
        "id": "RES-09", "name": "Cable misterioso", "category": "DESCONOCIDO",
        "status": "OPERATIVO", "location": "Bodega Central",
        "current_borrower": None, "notes": "CORRUPTO: categoría 'DESCONOCIDO'",
    },
]


def _ensure_seed_data_exists() -> None:
    """Genera archivos semilla en data/raw/ si la carpeta está vacía."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    spaces_file = RAW_DIR / "spaces.json"
    resources_file = RAW_DIR / "resources.json"

    if not spaces_file.exists():
        with open(spaces_file, "w", encoding="utf-8") as f:
            json.dump(_SEED_SPACES, f, ensure_ascii=False, indent=2)

    if not resources_file.exists():
        with open(resources_file, "w", encoding="utf-8") as f:
            json.dump(_SEED_RESOURCES, f, ensure_ascii=False, indent=2)

