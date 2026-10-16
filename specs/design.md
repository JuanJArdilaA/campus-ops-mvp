# Diseño de Arquitectura y Contratos de Código (`specs/design.md`)

## 1. Diagrama de Flujo y Capas
```text
[Usuario / Jurado]
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ CAPA UI (Streamlit - Sebastián)                                 │
│ app.py -> views_spaces.py | views_resources.py | views_incidents│
└──────┬───────────────────────────────┬───────────────────┬──────┘
       │ 1. Valida regla               │ 2. Clasifica IA   │ 3. Persiste cambio
       ▼                               ▼                   ▼
┌──────────────────────┐   ┌───────────────────────┐   ┌──────────────────────┐
│ VALIDATORS (JuanJo)  │   │ AI SERVICE (Andrés)   │   │ REPOSITORY (Miguel)  │
│ src/core/validators  │   │ src/core/ai_service   │   │ src/core/repository  │
│ RN-01 a RN-05        │   │ Gemini API + Fallback │   │ CRUD + Regla RN-03   │
└──────────────────────┘   └───────────────────────┘   └──────────┬───────────┘
                                                                  │
                                                                  ▼
                                                       ┌──────────────────────┐
                                                       │ SANITIZER (Miguel)   │
                                                       │ data/raw -> JSON     │
                                                       └──────────────────────┘
```

---

## 2. Modelos de Dominio (`src/core/models.py`)

```python
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

@dataclass
class ValidationResult:
    is_valid: bool
    message: str
    rule_code: str = ""  # Ej: "RN-01", "RN-02", "RN-03", "RN-04", "OK"

@dataclass
class Space:
    id: str                     # Ej: "SP-101"
    name: str                   # Ej: "Aula Sputnik"
    type: str                   # "AULA" | "CUBICULO" | "LABORATORIO" | "AUDITORIO"
    capacity: int               # Entero > 0
    status: str                 # "DISPONIBLE" | "OCUPADO" | "EN_MANTENIMIENTO" | "INHABILITADO"
    features: list[str] = field(default_factory=list)  # Ej: ["Videobeam", "Aire Acondicionado"]
    notes: str = ""

@dataclass
class Resource:
    id: str                     # Ej: "RES-01"
    name: str                   # Ej: "MacBook Pro M2 #04"
    category: str               # "COMPUTO" | "AUDIOVISUAL" | "ROBOTICA" | "ACCESORIO"
    status: str                 # "OPERATIVO" | "PRESTADO" | "EN_MANTENIMIENTO" | "DADO_DE_BAJA"
    location: str = "Bodega Central"
    current_borrower: Optional[str] = None
    notes: str = ""

@dataclass
class Reservation:
    id: str                     # Ej: "RSV-001"
    space_id: str               # FK -> Space.id
    requester_id: str           # Documento o código del camper/trainer
    requester_name: str
    date: str                   # Formato "YYYY-MM-DD"
    start_time: str             # Formato "HH:MM" (24h, ej: "08:00")
    end_time: str               # Formato "HH:MM" (24h, ej: "10:00")
    attendees: int              # Cantidad de asistentes (> 0)
    purpose: str
    status: str = "ACTIVA"      # "ACTIVA" | "FINALIZADA" | "CANCELADA"

@dataclass
class Loan:
    id: str                     # Ej: "LN-001"
    resource_id: str            # FK -> Resource.id
    borrower_id: str            # Documento o código del solicitante
    borrower_name: str
    borrower_role: str          # "CAMPER" | "TRAINER" | "STAFF"
    loan_timestamp: str         # Formato ISO o "YYYY-MM-DD HH:MM"
    expected_return: str        # Formato "YYYY-MM-DD HH:MM"
    actual_return: Optional[str] = None
    status: str = "ACTIVO"      # "ACTIVO" | "DEVUELTO"
    return_notes: str = ""

@dataclass
class Incident:
    id: str                     # Ej: "INC-001"
    title: str
    description: str
    reporter_name: str
    target_type: str            # "ESPACIO" | "RECURSO" | "GENERAL"
    target_id: Optional[str]    # Space.id, Resource.id o None
    category: str               # "INFRAESTRUCTURA" | "HARDWARE" | "RED_CONECTIVIDAD" | "MOBILIARIO" | "BIENESTAR" | "OTRO"
    priority: str               # "CRITICA" | "ALTA" | "MEDIA" | "BAJA"
    assigned_team: str          # "Soporte TI" | "Mantenimiento Físico" | "Bienestar Estudiantil" | "Coordinación"
    suggested_action: str       # Generado por IA o Fallback
    ai_source: str              # "AI_MODEL" | "FALLBACK_RULES"
    status: str = "ABIERTA"     # "ABIERTA" | "EN_PROCESO" | "RESUELTA"
    created_at: str = ""

@dataclass
class QuarantineRecord:
    source_entity: str          # "spaces" | "resources" | "reservations" | "loans" | "incidents"
    raw_data: dict[str, Any]
    reason: str                 # Explicación clara del rechazo (RN-05)
```

---

## 3. Reglas de Negocio y Validadores (`src/core/validators.py`)

### Constantes Configurables en Cabecera (Modificación en Vivo - RNF-03)
```python
OVERCAPACITY_FACTOR: float = 1.0           # RN-01: 1.0 = sin sobrecupo (1.1 = +10% permitido)
MAX_ACTIVE_LOANS_PER_USER: int = 2         # RN-02: Máximo de préstamos activos por persona
BLOCKING_PRIORITIES: set[str] = {"CRITICA", "ALTA"}  # RN-03: Prioridades que bloquean activos
CAMPUS_OPEN_TIME: str = "06:00"            # RN-04: Apertura del campus
CAMPUS_CLOSE_TIME: str = "21:30"           # RN-04: Cierre del campus
MAX_RESERVATION_HOURS: float = 4.0         # RN-04: Duración máxima por reserva en horas
MIN_RESERVATION_MINUTES: int = 30          # RN-04: Duración mínima por reserva en minutos
```

### Contratos de Funciones
```python
def validate_space_reservation(
    space: Optional[Space],
    new_reservation: Reservation,
    existing_reservations: list[Reservation],
    requester_role: str = "CAMPER",
) -> ValidationResult:
    """Valida RN-01 (estado DISPONIBLE, aforo <= int(capacity * OVERCAPACITY_FACTOR), sin solapamiento horario)
    y RN-04 (ventana horaria CAMPUS_OPEN_TIME..CAMPUS_CLOSE_TIME y duración entre MIN_RESERVATION_MINUTES y MAX_RESERVATION_HOURS).
    También soporta invocación por campos individuales (space, date, start_time, end_time, attendees, existing_reservations)."""

def validate_resource_loan(
    resource: Optional[Resource],
    borrower_id: str | Loan,
    active_loans: list[Loan],
) -> ValidationResult:
    """Valida RN-02: recurso en estado OPERATIVO y usuario con menos de MAX_ACTIVE_LOANS_PER_USER préstamos ACTIVO."""

def should_block_asset_on_incident(
    incident_or_priority: Incident | str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> bool:
    """Valida RN-03: determina si una incidencia tiene prioridad dentro de BLOCKING_PRIORITIES
    y apunta a un activo válido (ESPACIO o RECURSO) que deba pasar a EN_MANTENIMIENTO."""
```

---

## 4. Ingesta, Saneamiento y Repositorio (`src/core/sanitizer.py` y `src/core/repository.py`)

```python
# src/core/sanitizer.py
def load_and_sanitize_raw_data(raw_dir: Optional[Path] = None) -> dict[str, list[Any]]:
    """Carga datasets desde data/raw/, normaliza textos/estados y aísla registros corruptos en quarantine (RN-05)."""

# src/core/repository.py
class CampusRepository:
    def __init__(self, state_path: Optional[Path] = None, raw_dir: Optional[Path] = None) -> None: ...
    def load_state(self) -> None: ...
    def save_state(self) -> None: ...
    def reset_from_raw(self) -> None: ...
    def get_space_by_id(self, space_id: str) -> Optional[Space]: ...
    def get_resource_by_id(self, resource_id: str) -> Optional[Resource]: ...
    def create_reservation(self, reservation: Reservation) -> ValidationResult: ...
    def cancel_or_finish_reservation(self, reservation_id: str, new_status: str = "FINALIZADA") -> ValidationResult: ...
    def create_loan(self, loan: Loan) -> ValidationResult: ...
    def return_loan(self, loan_id: str, reported_damage: bool = False, damage_notes: str = "") -> ValidationResult: ...
    def create_incident(self, incident: Incident) -> tuple[ValidationResult, bool]: ...
    def resolve_incident(self, incident_id: str) -> tuple[ValidationResult, bool]: ...
```

---

## 5. Servicio de Inteligencia Artificial y Fallback (`src/core/ai_service.py`)

```python
def triage_incident(title: str, description: str, target_type: str, target_name: str = "") -> dict[str, str]:
    """Retorna:
    {
        "category": "INFRAESTRUCTURA" | "HARDWARE" | "RED_CONECTIVIDAD" | "MOBILIARIO" | "BIENESTAR" | "OTRO",
        "priority": "CRITICA" | "ALTA" | "MEDIA" | "BAJA",
        "assigned_team": str,
        "suggested_action": str,
        "ai_source": "AI_MODEL" | "FALLBACK_RULES"
    }
    """

def recommend_campus_allocation(
    user_query: str,
    available_spaces: list[Space],
    available_resources: list[Resource],
) -> dict[str, Any]:
    """Retorna:
    {
        "recommended_space_id": Optional[str],
        "recommended_space_name": str,
        "recommended_resource_ids": list[str],
        "justification": str,
        "ai_source": "AI_MODEL" | "FALLBACK_RULES"
    }
    """
```

---

## 6. Esquema de Persistencia (`data/processed/campus_state.json`)

```json
{
  "metadata": {
    "last_updated": "2026-10-16T08:30:00",
    "initialized_from_raw": true
  },
  "spaces": [],
  "resources": [],
  "reservations": [],
  "loans": [],
  "incidents": [],
  "quarantine": []
}
```