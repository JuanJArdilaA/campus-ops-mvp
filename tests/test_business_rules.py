"""Unit test suite for Campuslands Operations MVP business rules (RN-01 to RN-05)."""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

import src.core.repository as repo_module
from src.core.ai_service import recommend_campus_allocation, triage_incident
from src.core.models import (
    Incident,
    Loan,
    QuarantineRecord,
    Reservation,
    Resource,
    Space,
)
from src.core.repository import CampusRepository
from src.core.sanitizer import _sanitize_reservation, _sanitize_space, load_and_sanitize_raw_data
from src.core.validators import (
    should_block_asset_on_incident,
    validate_resource_loan,
    validate_space_reservation,
)


@pytest.fixture()
def isolated_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CampusRepository:
    """Create a CampusRepository backed by a temporary processed state file."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    state_file = processed_dir / "campus_state.json"
    temp_file = processed_dir / "campus_state.tmp.json"

    monkeypatch.setattr(repo_module, "_PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(repo_module, "STATE_FILE", state_file)
    monkeypatch.setattr(repo_module, "_TEMP_FILE", temp_file)

    return CampusRepository(auto_load=True)


# ==============================================================================
# RN-01: AFORO, DISPONIBILIDAD Y ANTI-SOLAPAMIENTO DE ESPACIOS
# ==============================================================================


def test_rn01_valid_space_reservation(isolated_repo: CampusRepository) -> None:
    """Caso válido RN-01: Reserva en espacio DISPONIBLE dentro del aforo y sin cruce horario."""
    reservation, result = isolated_repo.create_reservation(
        space_id="SP-101",
        requester_id="CC-1001",
        requester_name="Camper Uno",
        date="2026-10-20",
        start_time="08:00",
        end_time="10:00",
        attendees=25,
        purpose="Sesión de algoritmos Python",
    )
    assert result.is_valid is True
    assert result.rule_code == "OK"
    assert reservation is not None
    assert reservation.status == "ACTIVA"


def test_rn01_invalid_overcapacity(isolated_repo: CampusRepository) -> None:
    """Caso inválido RN-01b: Rechazo cuando los asistentes superan la capacidad permitida del aula."""
    # SP-101 (Aula Sputnik) tiene capacidad 30
    reservation, result = isolated_repo.create_reservation(
        space_id="SP-101",
        requester_id="CC-1002",
        requester_name="Trainer Dos",
        date="2026-10-20",
        start_time="10:00",
        end_time="12:00",
        attendees=45,
        purpose="Charla masiva",
    )
    assert reservation is None
    assert result.is_valid is False
    assert result.rule_code == "RN-01"
    assert "[RN-01]" in result.message


def test_rn01_invalid_time_overlap(isolated_repo: CampusRepository) -> None:
    """Caso inválido RN-01c: Rechazo cuando una nueva reserva se solapa en fecha y hora con otra ACTIVA."""
    _, first_result = isolated_repo.create_reservation(
        space_id="SP-101",
        requester_id="CC-1001",
        requester_name="Grupo Mañana",
        date="2026-10-21",
        start_time="08:00",
        end_time="10:00",
        attendees=20,
        purpose="Clase Backend",
    )
    assert first_result.is_valid is True

    overlapping_res, second_result = isolated_repo.create_reservation(
        space_id="SP-101",
        requester_id="CC-1003",
        requester_name="Grupo Intruso",
        date="2026-10-21",
        start_time="09:00",
        end_time="11:00",
        attendees=15,
        purpose="Tutoría",
    )
    assert overlapping_res is None
    assert second_result.is_valid is False
    assert second_result.rule_code == "RN-01"
    assert "Grupo Mañana" in second_result.message


def test_rn01_invalid_space_unavailable() -> None:
    """Caso inválido RN-01a: Rechazo cuando el espacio está EN_MANTENIMIENTO o INHABILITADO."""
    space_maint = Space(
        id="SP-999",
        name="Laboratorio Bloqueado",
        type="LABORATORIO",
        capacity=25,
        status="EN_MANTENIMIENTO",
        notes="Bloqueado por INC-001",
    )
    result = validate_space_reservation(
        space_maint,
        "2026-10-22",
        "08:00",
        "10:00",
        10,
        [],
    )
    assert result.is_valid is False
    assert result.rule_code == "RN-01"
    assert "EN_MANTENIMIENTO" in result.message


# ==============================================================================
# RN-02: CONTROL DE PRÉSTAMOS Y CUOTA MÁXIMA POR USUARIO
# ==============================================================================


def test_rn02_valid_resource_loan(isolated_repo: CampusRepository) -> None:
    """Caso válido RN-02: Préstamo de recurso OPERATIVO a un usuario dentro de su cuota."""
    loan, result = isolated_repo.create_loan(
        resource_id="RES-01",
        borrower_id="CAM-100",
        borrower_name="Laura Gómez",
        borrower_role="CAMPER",
        expected_return="2026-10-16 18:00",
    )
    assert result.is_valid is True
    assert result.rule_code == "OK"
    assert loan is not None
    resource = isolated_repo.get_resource_by_id("RES-01")
    assert resource is not None and resource.status == "PRESTADO"


def test_rn02_invalid_resource_not_operative(isolated_repo: CampusRepository) -> None:
    """Caso inválido RN-02a: Rechazo al intentar prestar un equipo EN_MANTENIMIENTO o PRESTADO."""
    # RES-07 está EN_MANTENIMIENTO en el dataset semilla
    loan, result = isolated_repo.create_loan(
        resource_id="RES-07",
        borrower_id="CAM-101",
        borrower_name="Pedro Pérez",
        borrower_role="CAMPER",
        expected_return="2026-10-16 18:00",
    )
    assert loan is None
    assert result.is_valid is False
    assert result.rule_code == "RN-02"


def test_rn02_invalid_user_loan_quota_exceeded(isolated_repo: CampusRepository) -> None:
    """Caso inválido RN-02b: Rechazo cuando un usuario intenta superar MAX_ACTIVE_LOANS_PER_USER (2)."""
    _, r1 = isolated_repo.create_loan("RES-01", "CAM-777", "Carlos Ruiz", "CAMPER", "2026-10-16 18:00")
    _, r2 = isolated_repo.create_loan("RES-02", "CAM-777", "Carlos Ruiz", "CAMPER", "2026-10-16 18:00")
    assert r1.is_valid and r2.is_valid

    loan3, r3 = isolated_repo.create_loan("RES-03", "CAM-777", "Carlos Ruiz", "CAMPER", "2026-10-16 18:00")
    assert loan3 is None
    assert r3.is_valid is False
    assert r3.rule_code == "RN-02"
    assert "RES-01" in r3.message and "RES-02" in r3.message


# ==============================================================================
# RN-03: BLOQUEO Y DESBLOQUEO PREVENTIVO CRUZADO POR INCIDENCIA
# ==============================================================================


def test_rn03_valid_critical_incident_blocks_and_resolution_unblocks(
    isolated_repo: CampusRepository,
) -> None:
    """Caso válido RN-03: Incidencia CRITICA bloquea el espacio a EN_MANTENIMIENTO y resolverla lo restaura."""
    space = isolated_repo.get_space_by_id("SP-101")
    assert space is not None and space.status == "DISPONIBLE"

    blocked, incident = isolated_repo.create_incident(
        title="Corto circuito en tomacorriente",
        description="Sale humo y chispas del tomacorriente principal",
        reporter_name="Trainer Juan",
        target_type="ESPACIO",
        target_id="SP-101",
        category="INFRAESTRUCTURA",
        priority="CRITICA",
        assigned_team="Mantenimiento Físico",
        suggested_action="Cortar suministro eléctrico y aislar el aula.",
        ai_source="FALLBACK_RULES",
    )
    assert blocked is True
    assert isolated_repo.get_space_by_id("SP-101").status == "EN_MANTENIMIENTO"

    # Resolver incidencia debe restaurar el aula a DISPONIBLE
    res_validation, unblocked = isolated_repo.resolve_incident(incident.id)
    assert res_validation.is_valid is True
    assert unblocked is True
    assert isolated_repo.get_space_by_id("SP-101").status == "DISPONIBLE"


def test_rn03_low_priority_incident_does_not_block_asset(isolated_repo: CampusRepository) -> None:
    """Caso válido RN-03: Incidencia de prioridad BAJA o MEDIA no bloquea el espacio."""
    assert should_block_asset_on_incident("BAJA", "ESPACIO", "SP-101") is False
    blocked, _ = isolated_repo.create_incident(
        title="Falta borrador de tablero",
        description="Se requiere un borrador adicional en el salón",
        reporter_name="Camper Ana",
        target_type="ESPACIO",
        target_id="SP-101",
        category="MOBILIARIO",
        priority="BAJA",
        assigned_team="Coordinación",
        suggested_action="Suministrar borrador.",
        ai_source="FALLBACK_RULES",
    )
    assert blocked is False
    assert isolated_repo.get_space_by_id("SP-101").status == "DISPONIBLE"


def test_rn03_return_loan_with_damage_blocks_resource(isolated_repo: CampusRepository) -> None:
    """Caso válido RF-19 + RN-03: Devolver un préstamo con daño pasa el recurso a EN_MANTENIMIENTO y crea incidencia."""
    loan, _ = isolated_repo.create_loan("RES-03", "CAM-500", "Diego Mora", "CAMPER", "2026-10-16 17:00")
    assert loan is not None

    result, incident = isolated_repo.return_loan(
        loan_id=loan.id,
        report_damage=True,
        damage_description="La lámpara del proyector parpadea y se apaga sola.",
    )
    assert result.is_valid is True
    assert incident is not None
    assert isolated_repo.get_resource_by_id("RES-03").status == "EN_MANTENIMIENTO"


# ==============================================================================
# RN-04: VENTANA HORARIA Y DURACIÓN DE RESERVAS
# ==============================================================================


def test_rn04_invalid_outside_campus_hours() -> None:
    """Caso inválido RN-04: Reserva antes de las 06:00 o después de las 21:30 es rechazada."""
    space = Space(id="SP-101", name="Aula Sputnik", type="AULA", capacity=30, status="DISPONIBLE")
    early_result = validate_space_reservation(space, "2026-10-20", "05:30", "07:30", 15, [])
    late_result = validate_space_reservation(space, "2026-10-20", "20:00", "22:00", 15, [])

    assert early_result.is_valid is False and early_result.rule_code == "RN-04"
    assert late_result.is_valid is False and late_result.rule_code == "RN-04"


def test_rn04_invalid_inverted_or_excessive_duration() -> None:
    """Caso inválido RN-04: Hora fin <= inicio, duración < 30 min o duración > 4.0 horas."""
    space = Space(id="SP-101", name="Aula Sputnik", type="AULA", capacity=30, status="DISPONIBLE")

    inverted = validate_space_reservation(space, "2026-10-20", "14:00", "10:00", 15, [])
    too_short = validate_space_reservation(space, "2026-10-20", "08:00", "08:15", 15, [])
    too_long = validate_space_reservation(space, "2026-10-20", "08:00", "13:00", 15, [])

    assert inverted.is_valid is False and inverted.rule_code == "RN-04"
    assert too_short.is_valid is False and too_short.rule_code == "RN-04"
    assert too_long.is_valid is False and too_long.rule_code == "RN-04"


# ==============================================================================
# RN-05: SANITIZACIÓN E INGESTA CON CUARENTENA DE DATOS CORRUPTOS
# ==============================================================================


def test_rn05_sanitizer_loads_valid_and_isolates_corrupt_records() -> None:
    """Caso válido/inválido RN-05: El sanitizador normaliza registros válidos y aísla los 4 corruptos en cuarentena."""
    data = load_and_sanitize_raw_data()
    assert len(data["spaces"]) > 0
    assert len(data["resources"]) > 0
    assert len(data["quarantine"]) >= 4
    assert all(isinstance(q, QuarantineRecord) and bool(q.reason) for q in data["quarantine"])


def test_rn05_orphan_reference_and_duplicate_id_go_to_quarantine() -> None:
    """Caso inválido RN-05 / RF-04: IDs duplicados y referencias huérfanas se envían a cuarentena."""
    seen_spaces = {"SP-101"}
    dup_space, q_dup = _sanitize_space(
        {"id": "SP-101", "name": "Aula Duplicada", "type": "AULA", "capacity": 20, "status": "DISPONIBLE"},
        seen_spaces,
    )
    assert dup_space is None
    assert q_dup is not None and "duplicado" in q_dup.reason.lower()

    orphan_rsv, q_orphan = _sanitize_reservation(
        {
            "id": "RSV-999",
            "space_id": "SP-INEXISTENTE",
            "requester_id": "123",
            "requester_name": "Test",
            "date": "2026-10-20",
            "start_time": "08:00",
            "end_time": "10:00",
            "attendees": 10,
            "purpose": "Clase",
        },
        set(),
        {"SP-101"},
    )
    assert orphan_rsv is None
    assert q_orphan is not None and "Referencia huérfana" in q_orphan.reason


# ==============================================================================
# SERVICIO DE IA Y FALLBACK DETERMINISTA (RF-20, RF-23, RF-24)
# ==============================================================================


def test_ai_service_triage_and_allocation_contracts(isolated_repo: CampusRepository) -> None:
    """Verifica que triage_incident y recommend_campus_allocation cumplan el contrato JSON estructurado."""
    triage = triage_incident(
        "Corto circuito",
        "Sale humo del tomacorriente del aula",
        "ESPACIO",
        "Aula Sputnik",
    )
    assert triage["priority"] == "CRITICA"
    assert triage["category"] in {
        "INFRAESTRUCTURA",
        "HARDWARE",
        "RED_CONECTIVIDAD",
        "MOBILIARIO",
        "BIENESTAR",
        "OTRO",
    }
    assert triage["ai_source"] in {"AI_MODEL", "FALLBACK_RULES"}

    rec = recommend_campus_allocation(
        "Necesito un salón para 20 personas con videobeam y 1 portátil",
        isolated_repo.get_available_spaces(),
        isolated_repo.get_available_resources(),
    )
    assert "recommended_space_id" in rec
    assert "recommended_resource_ids" in rec
    assert isinstance(rec["recommended_resource_ids"], list)
    assert bool(rec["justification"])
