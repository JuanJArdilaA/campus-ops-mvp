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