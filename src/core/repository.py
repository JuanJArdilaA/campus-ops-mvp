"""
src/core/repository.py — Operaciones CRUD y persistencia atómica sobre campus_state.json.

Responsable: Miguel
Implementa CampusRepository con lectura/escritura atómica (RNF-12),
integración con validators.py y bloqueo/desbloqueo cruzado automático (RN-03).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.core.models import (
    Space,
    Resource,
    Reservation,
    Loan,
    Incident,
    QuarantineRecord,
    ValidationResult,
)
import src.core.validators as _validators
from src.core.sanitizer import load_and_sanitize_raw_data

# ──────────────────────────────────────────────────────────────
# Rutas de persistencia
# ──────────────────────────────────────────────────────────────

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_PROCESSED_DIR: Path = _PROJECT_ROOT / "data" / "processed"
STATE_FILE: Path = _PROCESSED_DIR / "campus_state.json"
_TEMP_FILE: Path = _PROCESSED_DIR / "campus_state.tmp.json"


# ──────────────────────────────────────────────────────────────
# Helpers internos de validación (delegados a src/core/validators.py)
# ──────────────────────────────────────────────────────────────

def _validate_space_reservation(
    space: Space,
    attendees: int,
    date: str,
    start_time: str,
    end_time: str,
    existing_reservations: list[Reservation],
    requester_role: str = "CAMPER",
) -> ValidationResult:
    """Delega la validación RN-01 y RN-04 a src.core.validators."""
    return _validators.validate_space_reservation(
        space,
        date,
        start_time,
        end_time,
        attendees,
        existing_reservations,
        requester_role=requester_role,
    )


def _validate_resource_loan(
    resource: Resource,
    borrower_id: str,
    active_loans: list[Loan],
) -> ValidationResult:
    """Delega la validación RN-02 a src.core.validators."""
    return _validators.validate_resource_loan(
        resource=resource,
        borrower_or_loan=borrower_id,
        active_loans=active_loans,
    )


def _should_block_asset_on_incident(
    priority: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> bool:
    """Delega la validación RN-03 a src.core.validators."""
    return _validators.should_block_asset_on_incident(priority, target_type, target_id)


# ──────────────────────────────────────────────────────────────
# CampusRepository
# ──────────────────────────────────────────────────────────────

class CampusRepository:
    """
    Repositorio unificado con CRUD transaccional y persistencia atómica
    sobre data/processed/campus_state.json.
    """

    def __init__(self, auto_load: bool = True) -> None:
        self.spaces: dict[str, Space] = {}
        self.resources: dict[str, Resource] = {}
        self.reservations: list[Reservation] = []
        self.loans: list[Loan] = []
        self.incidents: list[Incident] = []
        self.quarantine: list[QuarantineRecord] = []
        self._counters: dict[str, int] = {
            "reservations": 0,
            "loans": 0,
            "incidents": 0,
        }

        if auto_load:
            self._initialize()

    # ──────── Inicialización y Persistencia ────────

    def _initialize(self) -> None:
        """
        RNF-16: Si campus_state.json ya tiene datos, cargarlo y sincronizar
        el catálogo base de espacios/recursos si data/raw/ tiene cambios.
        En caso contrario, inicializar desde data/raw/ vía el sanitizer.
        """
        _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

        if STATE_FILE.exists():
            state = self._load_state_from_disk()
            if state and self._state_has_data(state):
                self._hydrate_from_dict(state)
                self._sync_catalog_from_raw_if_changed()
                return

        # Inicialización desde raw
        self.reload_from_raw()

    def _sync_catalog_from_raw_if_changed(self) -> None:
        """Sincroniza nombres, tipos, capacidades y nuevos espacios/recursos desde data/raw/."""
        raw_data = load_and_sanitize_raw_data()
        changed = False

        raw_spaces: dict[str, Space] = {s.id: s for s in raw_data["spaces"]}
        if set(raw_spaces.keys()) != set(self.spaces.keys()):
            changed = True

        # Mantener estado operativo de espacios existentes con incidencias o reservas,
        # pero actualizar atributos de catálogo (name, type, capacity, features) y agregar nuevos
        blocked_space_ids = {
            inc.target_id
            for inc in self.incidents
            if inc.status in ("ABIERTA", "EN_PROCESO") and inc.target_type == "ESPACIO"
        }
        updated_spaces: dict[str, Space] = {}
        for sid, raw_sp in raw_spaces.items():
            existing = self.spaces.get(sid)
            if existing is None:
                updated_spaces[sid] = raw_sp
                changed = True
            else:
                if (
                    existing.name != raw_sp.name
                    or existing.type != raw_sp.type
                    or existing.capacity != raw_sp.capacity
                    or existing.features != raw_sp.features
                ):
                    changed = True
                status_to_keep = existing.status if sid in blocked_space_ids else existing.status
                notes_to_keep = existing.notes if sid in blocked_space_ids else raw_sp.notes
                updated_spaces[sid] = Space(
                    id=sid,
                    name=raw_sp.name,
                    type=raw_sp.type,
                    capacity=raw_sp.capacity,
                    status=status_to_keep,
                    features=raw_sp.features,
                    notes=notes_to_keep,
                )

        raw_resources: dict[str, Resource] = {r.id: r for r in raw_data["resources"]}
        if set(raw_resources.keys()) != set(self.resources.keys()):
            changed = True

        blocked_res_ids = {
            inc.target_id
            for inc in self.incidents
            if inc.status in ("ABIERTA", "EN_PROCESO") and inc.target_type == "RECURSO"
        }
        active_loan_res_ids = {
            ln.resource_id for ln in self.loans if ln.status == "ACTIVO"
        }
        updated_resources: dict[str, Resource] = {}
        for rid, raw_res in raw_resources.items():
            existing_res = self.resources.get(rid)
            if existing_res is None:
                updated_resources[rid] = raw_res
                changed = True
            else:
                if (
                    existing_res.name != raw_res.name
                    or existing_res.category != raw_res.category
                    or existing_res.location != raw_res.location
                ):
                    changed = True
                keep_dynamic = rid in blocked_res_ids or rid in active_loan_res_ids
                updated_resources[rid] = Resource(
                    id=rid,
                    name=raw_res.name,
                    category=raw_res.category,
                    status=existing_res.status if keep_dynamic else existing_res.status,
                    location=raw_res.location,
                    current_borrower=existing_res.current_borrower,
                    notes=existing_res.notes if keep_dynamic else raw_res.notes,
                )

        if changed:
            self.spaces = updated_spaces
            self.resources = updated_resources
            self.quarantine = raw_data["quarantine"]
            self.save_state()

    @staticmethod
    def _state_has_data(state: dict[str, Any]) -> bool:
        """Verifica que el estado cargado tiene al menos un espacio o recurso."""
        return bool(state.get("spaces")) or bool(state.get("resources"))

    def _load_state_from_disk(self) -> dict[str, Any]:
        """Lee campus_state.json desde disco."""
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _hydrate_from_dict(self, state: dict[str, Any]) -> None:
        """Reconstruye todas las colecciones desde un dict serializado."""
        self.spaces = {
            s["id"]: Space(**s)
            for s in state.get("spaces", [])
        }
        self.resources = {
            r["id"]: Resource(**r)
            for r in state.get("resources", [])
        }
        self.reservations = [
            Reservation(**rv) for rv in state.get("reservations", [])
        ]
        self.loans = [
            Loan(**ln) for ln in state.get("loans", [])
        ]
        self.incidents = [
            Incident(**inc) for inc in state.get("incidents", [])
        ]
        self.quarantine = [
            QuarantineRecord(**q) for q in state.get("quarantine", [])
        ]

        # Restaurar contadores
        self._counters["reservations"] = len(self.reservations)
        self._counters["loans"] = len(self.loans)
        self._counters["incidents"] = len(self.incidents)

    def reload_from_raw(self) -> None:
        """RF-06: Reconstruye campus_state.json desde data/raw/."""
        data = load_and_sanitize_raw_data()

        self.spaces = {s.id: s for s in data["spaces"]}
        self.resources = {r.id: r for r in data["resources"]}
        self.reservations = data["reservations"]
        self.loans = data["loans"]
        self.incidents = data["incidents"]
        self.quarantine = data["quarantine"]

        self._counters["reservations"] = len(self.reservations)
        self._counters["loans"] = len(self.loans)
        self._counters["incidents"] = len(self.incidents)

        self.save_state()

    def save_state(self) -> None:
        """
        RNF-12: Escritura atómica — escribe primero a .tmp.json y
        luego hace os.replace() para evitar corrupción.
        """
        _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

        state: dict[str, Any] = {
            "metadata": {
                "last_updated": datetime.now().isoformat(timespec="seconds"),
                "initialized_from_raw": True,
            },
            "spaces": [asdict(s) for s in self.spaces.values()],
            "resources": [asdict(r) for r in self.resources.values()],
            "reservations": [asdict(rv) for rv in self.reservations],
            "loans": [asdict(ln) for ln in self.loans],
            "incidents": [asdict(inc) for inc in self.incidents],
            "quarantine": [asdict(q) for q in self.quarantine],
        }

        with open(_TEMP_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        os.replace(str(_TEMP_FILE), str(STATE_FILE))

    # ──────── Generadores de IDs ────────

    def _next_id(self, prefix: str, counter_key: str) -> str:
        """Genera el siguiente ID secuencial."""
        self._counters[counter_key] += 1
        return f"{prefix}-{self._counters[counter_key]:03d}"

    # ──────── Consultas (Read) ────────

    def get_space_by_id(self, space_id: str) -> Optional[Space]:
        """Retorna un espacio por su ID o None."""
        return self.spaces.get(space_id)

    def get_resource_by_id(self, resource_id: str) -> Optional[Resource]:
        """Retorna un recurso por su ID o None."""
        return self.resources.get(resource_id)

    def get_all_spaces(self) -> list[Space]:
        """Retorna todos los espacios."""
        return list(self.spaces.values())

    def get_all_resources(self) -> list[Resource]:
        """Retorna todos los recursos."""
        return list(self.resources.values())

    def get_available_spaces(self) -> list[Space]:
        """Retorna espacios con status DISPONIBLE."""
        return [s for s in self.spaces.values() if s.status == "DISPONIBLE"]

    def get_available_resources(self) -> list[Resource]:
        """Retorna recursos con status OPERATIVO."""
        return [r for r in self.resources.values() if r.status == "OPERATIVO"]

    def get_active_reservations(self, space_id: Optional[str] = None) -> list[Reservation]:
        """Retorna reservas activas, opcionalmente filtradas por espacio."""
        result = [rv for rv in self.reservations if rv.status == "ACTIVA"]
        if space_id:
            result = [rv for rv in result if rv.space_id == space_id]
        return result

    def get_active_loans(self, borrower_id: Optional[str] = None) -> list[Loan]:
        """Retorna préstamos activos, opcionalmente filtrados por prestatario."""
        result = [ln for ln in self.loans if ln.status == "ACTIVO"]
        if borrower_id:
            result = [ln for ln in result if ln.borrower_id == borrower_id]
        return result

    def get_open_incidents(self, target_id: Optional[str] = None) -> list[Incident]:
        """Retorna incidencias abiertas o en proceso, opcionalmente por activo."""
        result = [
            inc for inc in self.incidents
            if inc.status in ("ABIERTA", "EN_PROCESO")
        ]
        if target_id:
            result = [inc for inc in result if inc.target_id == target_id]
        return result

    # ──────── Creación de Reserva (RN-01, RN-04) ────────

    def create_reservation(
        self,
        space_id: str,
        requester_id: str,
        requester_name: str,
        date: str,
        start_time: str,
        end_time: str,
        attendees: int,
        purpose: str,
        requester_role: str = "CAMPER",
    ) -> tuple[Optional[Reservation], ValidationResult]:
        """
        Crea una nueva reserva validando RN-01 y RN-04.

        Retorna:
            (Reservation, ValidationResult(is_valid=True)) si tiene éxito.
            (None, ValidationResult(is_valid=False)) si la validación falla.
        """
        # RNF-11: Integridad referencial
        space = self.get_space_by_id(space_id)
        if space is None:
            return None, ValidationResult(
                is_valid=False,
                message=f"El espacio '{space_id}' no existe en el sistema.",
                rule_code="REF",
            )

        # Validar reglas de negocio
        validation = _validate_space_reservation(
            space=space,
            attendees=attendees,
            date=date,
            start_time=start_time,
            end_time=end_time,
            existing_reservations=self.reservations,
            requester_role=requester_role,
        )

        if not validation.is_valid:
            return None, validation

        # Crear reserva
        reservation = Reservation(
            id=self._next_id("RSV", "reservations"),
            space_id=space_id,
            requester_id=requester_id,
            requester_name=requester_name,
            date=date,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            purpose=purpose,
            status="ACTIVA",
        )

        self.reservations.append(reservation)
        self.save_state()
        return reservation, validation

    def cancel_reservation(self, reservation_id: str) -> ValidationResult:
        """Cancela una reserva activa por su ID."""
        for rv in self.reservations:
            if rv.id == reservation_id and rv.status == "ACTIVA":
                rv.status = "CANCELADA"
                self.save_state()
                return ValidationResult(
                    is_valid=True,
                    message=f"Reserva '{reservation_id}' cancelada exitosamente.",
                    rule_code="OK",
                )
        return ValidationResult(
            is_valid=False,
            message=f"Reserva '{reservation_id}' no encontrada o no está activa.",
            rule_code="NOT_FOUND",
        )

    def finalize_reservation(self, reservation_id: str) -> ValidationResult:
        """Finaliza una reserva activa por su ID."""
        for rv in self.reservations:
            if rv.id == reservation_id and rv.status == "ACTIVA":
                rv.status = "FINALIZADA"
                self.save_state()
                return ValidationResult(
                    is_valid=True,
                    message=f"Reserva '{reservation_id}' finalizada exitosamente.",
                    rule_code="OK",
                )
        return ValidationResult(
            is_valid=False,
            message=f"Reserva '{reservation_id}' no encontrada o no está activa.",
            rule_code="NOT_FOUND",
        )

    # ──────── Creación de Préstamo (RN-02) ────────

    def create_loan(
        self,
        resource_id: str,
        borrower_id: str,
        borrower_name: str,
        borrower_role: str,
        expected_return: str,
    ) -> tuple[Optional[Loan], ValidationResult]:
        """
        Crea un nuevo préstamo validando RN-02.

        Retorna:
            (Loan, ValidationResult(is_valid=True)) si tiene éxito.
            (None, ValidationResult(is_valid=False)) si la validación falla.
        """
        # RNF-11: Integridad referencial
        resource = self.get_resource_by_id(resource_id)
        if resource is None:
            return None, ValidationResult(
                is_valid=False,
                message=f"El recurso '{resource_id}' no existe en el sistema.",
                rule_code="REF",
            )

        # Validar reglas de negocio
        validation = _validate_resource_loan(
            resource=resource,
            borrower_id=borrower_id,
            active_loans=self.loans,
        )

        if not validation.is_valid:
            return None, validation

        # Crear préstamo
        now = datetime.now().isoformat(timespec="minutes")
        loan = Loan(
            id=self._next_id("LN", "loans"),
            resource_id=resource_id,
            borrower_id=borrower_id,
            borrower_name=borrower_name,
            borrower_role=borrower_role,
            loan_timestamp=now,
            expected_return=expected_return,
            status="ACTIVO",
        )

        # Actualizar estado del recurso a PRESTADO
        resource.status = "PRESTADO"
        resource.current_borrower = borrower_id

        self.loans.append(loan)
        self.save_state()
        return loan, validation

    def return_loan(
        self,
        loan_id: str,
        report_damage: bool = False,
        damage_description: str = "",
    ) -> tuple[ValidationResult, Optional[Incident]]:
        """
        Registra la devolución de un préstamo.
        Si report_damage=True, crea automáticamente una incidencia (RF-19).

        Retorna:
            (ValidationResult, Optional[Incident]) — la incidencia si se creó por daño.
        """
        target_loan: Optional[Loan] = None
        for ln in self.loans:
            if ln.id == loan_id and ln.status == "ACTIVO":
                target_loan = ln
                break

        if target_loan is None:
            return ValidationResult(
                is_valid=False,
                message=f"Préstamo '{loan_id}' no encontrado o ya devuelto.",
                rule_code="NOT_FOUND",
            ), None

        # Marcar préstamo como devuelto
        now = datetime.now().isoformat(timespec="minutes")
        target_loan.status = "DEVUELTO"
        target_loan.actual_return = now

        resource = self.get_resource_by_id(target_loan.resource_id)
        created_incident: Optional[Incident] = None

        if resource is not None:
            if report_damage:
                # RF-19: Devolución con daño → EN_MANTENIMIENTO + Incidencia automática
                resource.status = "EN_MANTENIMIENTO"
                resource.current_borrower = None
                target_loan.return_notes = damage_description or "Devuelto con novedad/daño"

                # Crear incidencia automática vinculada al recurso
                _, created_incident = self._create_incident_internal(
                    title=f"Daño reportado en devolución de {resource.name}",
                    description=damage_description or f"El recurso {resource.name} fue devuelto con daño.",
                    reporter_name=target_loan.borrower_name,
                    target_type="RECURSO",
                    target_id=resource.id,
                    category="HARDWARE",
                    priority="ALTA",
                    assigned_team="Soporte TI",
                    suggested_action=f"Revisar estado físico de {resource.name} y evaluar reparación.",
                    ai_source="FALLBACK_RULES",
                )
            else:
                # RF-18: Devolución sana → OPERATIVO
                resource.status = "OPERATIVO"
                resource.current_borrower = None

        self.save_state()
        return ValidationResult(
            is_valid=True,
            message=f"Préstamo '{loan_id}' devuelto exitosamente.",
            rule_code="OK",
        ), created_incident

    # ──────── Creación de Incidencia con Bloqueo Cruzado (RN-03) ────────

    def _create_incident_internal(
        self,
        title: str,
        description: str,
        reporter_name: str,
        target_type: str,
        target_id: Optional[str],
        category: str,
        priority: str,
        assigned_team: str,
        suggested_action: str,
        ai_source: str,
    ) -> tuple[bool, Incident]:
        """
        Método interno que crea la incidencia y aplica bloqueo RN-03.
        No llama save_state() — el caller es responsable de persistir.

        Retorna:
            (blocked: bool, incident: Incident)
        """
        now = datetime.now().isoformat(timespec="seconds")
        incident = Incident(
            id=self._next_id("INC", "incidents"),
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
            status="ABIERTA",
            created_at=now,
        )
        self.incidents.append(incident)

        # RN-03: Bloqueo preventivo cruzado
        blocked = False
        if target_id and _should_block_asset_on_incident(priority):
            blocked = self._block_asset(target_type, target_id, incident.id, now)

        return blocked, incident

    def create_incident(
        self,
        title: str,
        description: str,
        reporter_name: str,
        target_type: str,
        target_id: Optional[str],
        category: str,
        priority: str,
        assigned_team: str,
        suggested_action: str,
        ai_source: str,
    ) -> tuple[bool, Incident]:
        """
        Crea una incidencia y aplica bloqueo automático RN-03 si corresponde.

        Retorna:
            (blocked: bool, incident: Incident)
            blocked=True si un activo fue puesto EN_MANTENIMIENTO.
        """
        # RNF-11: Validar integridad referencial si se especifica target_id
        if target_id:
            if target_type == "ESPACIO" and target_id not in self.spaces:
                # No bloquear si el espacio no existe, pero crear incidencia como GENERAL
                target_type = "GENERAL"
                target_id = None
            elif target_type == "RECURSO" and target_id not in self.resources:
                target_type = "GENERAL"
                target_id = None

        blocked, incident = self._create_incident_internal(
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
        )

        self.save_state()
        return blocked, incident

    def _block_asset(
        self,
        target_type: str,
        target_id: str,
        incident_id: str,
        timestamp: str,
    ) -> bool:
        """
        RN-03: Bloquea un activo poniéndolo EN_MANTENIMIENTO.
        RNF-19: Registra en las notas del activo el ID de la incidencia y la marca temporal.
        """
        note = f"[RN-03] Bloqueado por incidencia {incident_id} ({timestamp})"

        if target_type == "ESPACIO":
            space = self.spaces.get(target_id)
            if space and space.status not in ("EN_MANTENIMIENTO", "INHABILITADO"):
                space.status = "EN_MANTENIMIENTO"
                space.notes = f"{space.notes}; {note}".lstrip("; ")
                return True

        elif target_type == "RECURSO":
            resource = self.resources.get(target_id)
            if resource and resource.status not in ("EN_MANTENIMIENTO", "DADO_DE_BAJA"):
                resource.status = "EN_MANTENIMIENTO"
                resource.notes = f"{resource.notes}; {note}".lstrip("; ")
                return True

        return False

    def resolve_incident(self, incident_id: str) -> tuple[ValidationResult, bool]:
        """
        Marca una incidencia como RESUELTA y desbloquea el activo si no tiene
        otras incidencias abiertas de prioridad bloqueante (RN-03).

        Retorna:
            (ValidationResult, unblocked: bool)
        """
        target_incident: Optional[Incident] = None
        for inc in self.incidents:
            if inc.id == incident_id and inc.status in ("ABIERTA", "EN_PROCESO"):
                target_incident = inc
                break

        if target_incident is None:
            return ValidationResult(
                is_valid=False,
                message=f"Incidencia '{incident_id}' no encontrada o ya resuelta.",
                rule_code="NOT_FOUND",
            ), False

        target_incident.status = "RESUELTA"

        # RN-03: Desbloqueo automático si no hay más incidencias bloqueantes abiertas
        unblocked = False
        if target_incident.target_id:
            unblocked = self._try_unblock_asset(
                target_incident.target_type,
                target_incident.target_id,
            )

        self.save_state()
        return ValidationResult(
            is_valid=True,
            message=f"Incidencia '{incident_id}' resuelta exitosamente.",
            rule_code="OK",
        ), unblocked

    def _try_unblock_asset(self, target_type: str, target_id: str) -> bool:
        """
        RN-03: Restaura el estado de un activo si no quedan incidencias
        bloqueantes abiertas sobre él.
        """
        # Verificar si hay otras incidencias abiertas de prioridad bloqueante
        blocking_open = [
            inc for inc in self.incidents
            if inc.target_id == target_id
            and inc.status in ("ABIERTA", "EN_PROCESO")
            and inc.priority in _validators.BLOCKING_PRIORITIES
        ]

        if blocking_open:
            return False  # Aún hay incidencias bloqueantes

        now = datetime.now().isoformat(timespec="seconds")
        note = f"[RN-03] Desbloqueado automáticamente ({now})"

        if target_type == "ESPACIO":
            space = self.spaces.get(target_id)
            if space and space.status == "EN_MANTENIMIENTO":
                space.status = "DISPONIBLE"
                space.notes = f"{space.notes}; {note}".lstrip("; ")
                return True

        elif target_type == "RECURSO":
            resource = self.resources.get(target_id)
            if resource and resource.status == "EN_MANTENIMIENTO":
                resource.status = "OPERATIVO"
                resource.notes = f"{resource.notes}; {note}".lstrip("; ")
                return True

        return False

    # ──────── KPIs para Dashboard ────────

    def get_kpis(self) -> dict[str, int]:
        """Retorna métricas globales para el dashboard."""
        return {
            "available_spaces": len(self.get_available_spaces()),
            "total_spaces": len(self.spaces),
            "operative_resources": len(self.get_available_resources()),
            "total_resources": len(self.resources),
            "critical_open_incidents": len([
                inc for inc in self.incidents
                if inc.status in ("ABIERTA", "EN_PROCESO")
                and inc.priority == "CRITICA"
            ]),
            "total_open_incidents": len(self.get_open_incidents()),
            "quarantine_records": len(self.quarantine),
            "active_reservations": len(self.get_active_reservations()),
            "active_loans": len(self.get_active_loans()),
        }

