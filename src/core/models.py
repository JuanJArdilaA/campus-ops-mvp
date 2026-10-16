from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class SpaceType(str, Enum):
    AULA = "AULA"
    CUBICULO = "CUBICULO"
    LABORATORIO = "LABORATORIO"
    AUDITORIO = "AUDITORIO"


class SpaceStatus(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    OCUPADO = "OCUPADO"
    EN_MANTENIMIENTO = "EN_MANTENIMIENTO"
    INHABILITADO = "INHABILITADO"


class ResourceCategory(str, Enum):
    COMPUTO = "COMPUTO"
    AUDIOVISUAL = "AUDIOVISUAL"
    ROBOTICA = "ROBOTICA"
    ACCESORIO = "ACCESORIO"


class ResourceStatus(str, Enum):
    OPERATIVO = "OPERATIVO"
    PRESTADO = "PRESTADO"
    EN_MANTENIMIENTO = "EN_MANTENIMIENTO"
    DADO_DE_BAJA = "DADO_DE_BAJA"


class ReservationStatus(str, Enum):
    ACTIVA = "ACTIVA"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"


class LoanStatus(str, Enum):
    ACTIVO = "ACTIVO"
    DEVUELTO = "DEVUELTO"


class BorrowerRole(str, Enum):
    CAMPER = "CAMPER"
    TRAINER = "TRAINER"
    STAFF = "STAFF"


class TargetType(str, Enum):
    ESPACIO = "ESPACIO"
    RECURSO = "RECURSO"
    GENERAL = "GENERAL"


class IncidentCategory(str, Enum):
    INFRAESTRUCTURA = "INFRAESTRUCTURA"
    HARDWARE = "HARDWARE"
    RED_CONECTIVIDAD = "RED_CONECTIVIDAD"
    MOBILIARIO = "MOBILIARIO"
    BIENESTAR = "BIENESTAR"
    OTRO = "OTRO"


class IncidentPriority(str, Enum):
    CRITICA = "CRITICA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"


class IncidentStatus(str, Enum):
    ABIERTA = "ABIERTA"
    EN_PROCESO = "EN_PROCESO"
    RESUELTA = "RESUELTA"


class AISource(str, Enum):
    AI_MODEL = "AI_MODEL"
    FALLBACK_RULES = "FALLBACK_RULES"


@dataclass
class ValidationResult:
    is_valid: bool
    message: str
    rule_code: str = ""  # Ej: "RN-01", "RN-02", "RN-03", "RN-04", "OK"

    def __bool__(self) -> bool:
        return self.is_valid

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Space:
    id: str                     # Ej: "SP-101"
    name: str                   # Ej: "Aula Sputnik"
    type: str                   # "AULA" | "CUBICULO" | "LABORATORIO" | "AUDITORIO"
    capacity: int               # Entero > 0
    status: str                 # "DISPONIBLE" | "OCUPADO" | "EN_MANTENIMIENTO" | "INHABILITADO"
    features: list[str] = field(default_factory=list)  # Ej: ["Videobeam", "Aire Acondicionado"]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Space":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            type=str(data["type"]),
            capacity=int(data["capacity"]),
            status=str(data["status"]),
            features=list(data.get("features", [])),
            notes=str(data.get("notes", "")),
        )


@dataclass
class Resource:
    id: str                     # Ej: "RES-01"
    name: str                   # Ej: "MacBook Pro M2 #04"
    category: str               # "COMPUTO" | "AUDIOVISUAL" | "ROBOTICA" | "ACCESORIO"
    status: str                 # "OPERATIVO" | "PRESTADO" | "EN_MANTENIMIENTO" | "DADO_DE_BAJA"
    location: str = "Bodega Central"
    current_borrower: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Resource":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            category=str(data["category"]),
            status=str(data["status"]),
            location=str(data.get("location", "Bodega Central")),
            current_borrower=data.get("current_borrower"),
            notes=str(data.get("notes", "")),
        )


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reservation":
        return cls(
            id=str(data["id"]),
            space_id=str(data["space_id"]),
            requester_id=str(data["requester_id"]),
            requester_name=str(data["requester_name"]),
            date=str(data["date"]),
            start_time=str(data["start_time"]),
            end_time=str(data["end_time"]),
            attendees=int(data["attendees"]),
            purpose=str(data.get("purpose", "")),
            status=str(data.get("status", "ACTIVA")),
        )


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Loan":
        return cls(
            id=str(data["id"]),
            resource_id=str(data["resource_id"]),
            borrower_id=str(data["borrower_id"]),
            borrower_name=str(data["borrower_name"]),
            borrower_role=str(data.get("borrower_role", "CAMPER")),
            loan_timestamp=str(data["loan_timestamp"]),
            expected_return=str(data["expected_return"]),
            actual_return=data.get("actual_return"),
            status=str(data.get("status", "ACTIVO")),
            return_notes=str(data.get("return_notes", "")),
        )


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Incident":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            description=str(data["description"]),
            reporter_name=str(data.get("reporter_name", "Anónimo")),
            target_type=str(data["target_type"]),
            target_id=data.get("target_id"),
            category=str(data["category"]),
            priority=str(data["priority"]),
            assigned_team=str(data["assigned_team"]),
            suggested_action=str(data["suggested_action"]),
            ai_source=str(data.get("ai_source", "FALLBACK_RULES")),
            status=str(data.get("status", "ABIERTA")),
            created_at=str(data.get("created_at", "")),
        )


@dataclass
class QuarantineRecord:
    source_entity: str          # "spaces" | "resources" | "reservations" | "loans" | "incidents"
    raw_data: dict[str, Any]
    reason: str                 # Explicación clara del rechazo (RN-05)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuarantineRecord":
        return cls(
            source_entity=str(data.get("source_entity", "unknown")),
            raw_data=dict(data.get("raw_data", {})),
            reason=str(data.get("reason", "")),
        )