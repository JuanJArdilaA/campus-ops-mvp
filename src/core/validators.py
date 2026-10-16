from typing import Optional, Any
from src.core.models import (
    Space,
    Resource,
    Reservation,
    Loan,
    Incident,
    ValidationResult,
)

# ==============================================================================
# CONSTANTES DE REGLAS DE NEGOCIO (MODIFICABLES EN VIVO - RNF-03 / TASK-14)
# ==============================================================================
OVERCAPACITY_FACTOR: float = 1.0           # RN-01: 1.0 = sin sobrecupo (1.1 = +10% permitido)
MAX_ACTIVE_LOANS_PER_USER: int = 2         # RN-02: Máximo de préstamos activos por persona
BLOCKING_PRIORITIES: set[str] = {"CRITICA", "ALTA"}  # RN-03: Prioridades que bloquean activos
CAMPUS_OPEN_TIME: str = "06:00"            # RN-04: Apertura del campus
CAMPUS_CLOSE_TIME: str = "21:30"           # RN-04: Cierre del campus
MAX_RESERVATION_HOURS: float = 4.0         # RN-04: Duración máxima por reserva en horas
MIN_RESERVATION_MINUTES: int = 30          # RN-04: Duración mínima por reserva en minutos

# Alias compatibles con nomenclatura de dominio y simulacro en vivo (TASK-14)
CAMPUS_OPEN_HOUR: str = CAMPUS_OPEN_TIME
CAMPUS_CLOSE_HOUR: str = CAMPUS_CLOSE_TIME
AUDITORIO_ALLOWED_ROLES: set[str] = {"CAMPER", "TRAINER", "STAFF"}  # Cambiar a {"TRAINER"} en simulacro


def _parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Convierte una hora en formato 'HH:MM' (24h) a minutos desde medianoche."""
    if not isinstance(time_str, str):
        return None
    cleaned = time_str.strip()
    parts = cleaned.split(":")
    if len(parts) != 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def _resolve_open_close_times() -> tuple[str, str]:
    """Resuelve dinámicamente la ventana horaria permitiendo cambios en CAMPUS_OPEN_TIME o CAMPUS_OPEN_HOUR."""
    open_t = CAMPUS_OPEN_TIME if CAMPUS_OPEN_TIME != "06:00" else CAMPUS_OPEN_HOUR
    close_t = CAMPUS_CLOSE_TIME if CAMPUS_CLOSE_TIME != "21:30" else CAMPUS_CLOSE_HOUR
    return open_t, close_t


def validate_space_reservation(
    space: Optional[Space] = None,
    *args: Any,
    **kwargs: Any,
) -> ValidationResult:
    """
    Valida las reglas de negocio RN-01 (Estado del espacio, Aforo máximo y Anti-solapamiento)
    y RN-04 (Ventana horaria operativa del campus y duración mínima/máxima).

    Soporta tanto invocación con objeto Reservation:
        validate_space_reservation(space, new_reservation, existing_reservations)
    como invocación por parámetros individuales:
        validate_space_reservation(space, date, start_time, end_time, attendees, existing_reservations)
    """
    new_reservation: Optional[Reservation] = kwargs.get("new_reservation") or kwargs.get("reservation")
    existing_reservations: list[Reservation] = (
        kwargs.get("existing_reservations")
        if kwargs.get("existing_reservations") is not None
        else kwargs.get("active_reservations", [])
    )
    date: str = kwargs.get("date", "")
    start_time: str = kwargs.get("start_time", "")
    end_time: str = kwargs.get("end_time", "")
    attendees: Optional[int] = kwargs.get("attendees")
    requester_role: str = str(kwargs.get("requester_role", "CAMPER"))
    reservation_id: str = ""

    # Si el primer argumento posicional fue una Reservation e invirtieron el orden (reservation, space, ...)
    if isinstance(space, Reservation):
        new_reservation = space
        space = args[0] if len(args) >= 1 and isinstance(args[0], Space) else kwargs.get("space")
        if len(args) >= 2 and isinstance(args[1], list):
            existing_reservations = args[1]
    else:
        # Analizar argumentos posicionales adicionales
        if len(args) >= 1 and isinstance(args[0], Reservation):
            new_reservation = args[0]
            if len(args) >= 2 and isinstance(args[1], list):
                existing_reservations = args[1]
            if len(args) >= 3 and isinstance(args[2], str):
                requester_role = args[2]
        elif len(args) >= 1 and isinstance(args[0], dict) and "start_time" in args[0]:
            raw_res = args[0]
            date = str(raw_res.get("date", date))
            start_time = str(raw_res.get("start_time", start_time))
            end_time = str(raw_res.get("end_time", end_time))
            attendees = int(raw_res.get("attendees", 0))
            reservation_id = str(raw_res.get("id", ""))
            if "requester_role" in raw_res:
                requester_role = str(raw_res["requester_role"])
            if len(args) >= 2 and isinstance(args[1], list):
                existing_reservations = args[1]
        elif len(args) >= 4:
            # Formato: (space, date, start_time, end_time, attendees, [existing_reservations], [requester_role])
            date = str(args[0])
            start_time = str(args[1])
            end_time = str(args[2])
            attendees = args[3]
            if len(args) >= 5 and isinstance(args[4], list):
                existing_reservations = args[4]
            if len(args) >= 6 and isinstance(args[5], str):
                requester_role = args[5]

    if new_reservation is not None:
        date = new_reservation.date
        start_time = new_reservation.start_time
        end_time = new_reservation.end_time
        attendees = new_reservation.attendees
        reservation_id = new_reservation.id
        if hasattr(new_reservation, "requester_role"):
            requester_role = str(getattr(new_reservation, "requester_role"))

    # 1. RN-01a: Existencia y disponibilidad del espacio (RF-09)
    if space is None:
        return ValidationResult(
            is_valid=False,
            message="[RN-01] El espacio solicitado no existe en el catálogo maestro.",
            rule_code="RN-01",
        )

    space_status = str(space.status).strip().upper()
    if space_status != "DISPONIBLE":
        note_detail = f" Detalle/Incidencia: {space.notes}" if space.notes else ""
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-01] El espacio '{space.name}' ({space.id}) no está disponible para reservar "
                f"(Estado actual: {space.status}).{note_detail}"
            ),
            rule_code="RN-01",
        )

    # Restricción configurable por rol para AUDITORIO (Soporte para Simulacro TASK-14)
    if str(space.type).strip().upper() == "AUDITORIO":
        if requester_role.strip().upper() not in AUDITORIO_ALLOWED_ROLES:
            allowed_str = ", ".join(sorted(AUDITORIO_ALLOWED_ROLES))
            return ValidationResult(
                is_valid=False,
                message=(
                    f"[RN-01] El rol '{requester_role}' no tiene permisos para reservar el "
                    f"auditorio '{space.name}'. Roles autorizados: {allowed_str}."
                ),
                rule_code="RN-01",
            )

    # 2. RN-01b: Validación de aforo y sobrecupo (RF-10)
    if attendees is None or isinstance(attendees, bool) or not isinstance(attendees, int) or attendees <= 0:
        return ValidationResult(
            is_valid=False,
            message="[RN-01] La cantidad de asistentes debe ser un número entero mayor a 0.",
            rule_code="RN-01",
        )

    max_allowed_capacity = int(space.capacity * OVERCAPACITY_FACTOR)
    if attendees > max_allowed_capacity:
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-01] Exceso de aforo en '{space.name}': se solicitaron {attendees} asistentes, "
                f"pero la capacidad máxima permitida es de {max_allowed_capacity} personas."
            ),
            rule_code="RN-01",
        )

    # 3. RN-04: Validación de ventana horaria y duración (RF-12)
    if not str(date).strip():
        return ValidationResult(
            is_valid=False,
            message="[RN-04] La fecha de la reserva es obligatoria (formato YYYY-MM-DD).",
            rule_code="RN-04",
        )

    start_min = _parse_time_to_minutes(start_time)
    end_min = _parse_time_to_minutes(end_time)
    if start_min is None or end_min is None:
        return ValidationResult(
            is_valid=False,
            message=f"[RN-04] Formato de hora inválido ('{start_time}' a '{end_time}'). Use el formato 24h HH:MM.",
            rule_code="RN-04",
        )

    if end_min <= start_min:
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-04] Rango horario inválido: la hora de finalización ({end_time}) "
                f"debe ser estrictamente mayor a la hora de inicio ({start_time})."
            ),
            rule_code="RN-04",
        )

    open_time_str, close_time_str = _resolve_open_close_times()
    open_min = _parse_time_to_minutes(open_time_str)
    close_min = _parse_time_to_minutes(close_time_str)

    if (open_min is not None and start_min < open_min) or (close_min is not None and end_min > close_min):
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-04] Horario fuera de la ventana operativa del campus ({open_time_str} a {close_time_str}). "
                f"Horario solicitado: {start_time} a {end_time}."
            ),
            rule_code="RN-04",
        )

    duration_minutes = end_min - start_min
    if duration_minutes < MIN_RESERVATION_MINUTES:
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-04] La duración de la reserva ({duration_minutes} min) es menor "
                f"al mínimo requerido de {MIN_RESERVATION_MINUTES} minutos."
            ),
            rule_code="RN-04",
        )

    max_duration_minutes = int(round(MAX_RESERVATION_HOURS * 60))
    if duration_minutes > max_duration_minutes:
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-04] La duración de la reserva ({duration_minutes / 60:.1f} horas) "
                f"excede el límite máximo permitido de {MAX_RESERVATION_HOURS} horas."
            ),
            rule_code="RN-04",
        )

    # 4. RN-01c: Validación de anti-solapamiento horario (RF-11)
    for existing in existing_reservations or []:
        if str(existing.status).strip().upper() != "ACTIVA":
            continue
        if existing.space_id != space.id:
            continue
        if reservation_id and existing.id == reservation_id:
            continue
        if str(existing.date).strip() != str(date).strip():
            continue

        ex_start_min = _parse_time_to_minutes(existing.start_time)
        ex_end_min = _parse_time_to_minutes(existing.end_time)

        if ex_start_min is not None and ex_end_min is not None:
            is_overlapping = (start_min < ex_end_min) and (end_min > ex_start_min)
        else:
            is_overlapping = (start_time < existing.end_time) and (end_time > existing.start_time)

        if is_overlapping:
            return ValidationResult(
                is_valid=False,
                message=(
                    f"[RN-01] Solapamiento horario en '{space.name}' el {date}: el bloque "
                    f"({start_time} - {end_time}) se cruza con la reserva activa {existing.id} "
                    f"de {existing.requester_name} ({existing.start_time} - {existing.end_time})."
                ),
                rule_code="RN-01",
            )

    return ValidationResult(
        is_valid=True,
        message=f"Reserva válida para '{space.name}' ({date} de {start_time} a {end_time}).",
        rule_code="OK",
    )


def validate_resource_loan(
    resource: Optional[Resource] = None,
    borrower_or_loan: Optional[str | Loan] = None,
    active_loans: Optional[list[Loan]] = None,
    **kwargs: Any,
) -> ValidationResult:
    """
    Valida la regla de negocio RN-02 (Control de Préstamos y Cuota por Usuario):
    - RN-02a (RF-16): El recurso debe existir y estar en estado OPERATIVO.
    - RN-02b (RF-17): El usuario no puede superar MAX_ACTIVE_LOANS_PER_USER préstamos en estado ACTIVO.

    Soporta invocación con borrower_id (str) o con objeto Loan:
        validate_resource_loan(resource, borrower_id, active_loans)
        validate_resource_loan(resource, new_loan, existing_loans)
    """
    # Soporte si el primer argumento fue un Loan e invirtieron el orden (loan, resource, active_loans)
    if isinstance(resource, Loan):
        loan_obj = resource
        resource = borrower_or_loan if isinstance(borrower_or_loan, Resource) else kwargs.get("resource")
        borrower_or_loan = loan_obj.borrower_id

    if borrower_or_loan is None:
        borrower_or_loan = (
            kwargs.get("borrower_id")
            or kwargs.get("user_id")
            or kwargs.get("new_loan")
            or kwargs.get("loan")
        )

    if active_loans is None:
        active_loans = (
            kwargs.get("existing_loans")
            if kwargs.get("existing_loans") is not None
            else kwargs.get("loans", [])
        )

    borrower_id = (
        borrower_or_loan.borrower_id
        if isinstance(borrower_or_loan, Loan)
        else str(borrower_or_loan or "")
    ).strip()

    # 1. RN-02a: Existencia y estado operativo del recurso (RF-16)
    if resource is None:
        return ValidationResult(
            is_valid=False,
            message="[RN-02] El recurso tecnológico solicitado no existe en el inventario.",
            rule_code="RN-02",
        )

    resource_status = str(resource.status).strip().upper()
    if resource_status != "OPERATIVO":
        holder_info = f" (Prestado a: {resource.current_borrower})" if resource.current_borrower else ""
        note_info = f" Detalle: {resource.notes}" if resource.notes else ""
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-02] El recurso '{resource.name}' ({resource.id}) no puede prestarse "
                f"porque su estado actual es '{resource.status}'{holder_info}.{note_info}"
            ),
            rule_code="RN-02",
        )

    # 2. RN-02b: Validación de solicitante y cuota máxima de préstamos simultáneos (RF-17)
    if not borrower_id:
        return ValidationResult(
            is_valid=False,
            message="[RN-02] Debe proporcionar un documento o código de solicitante válido.",
            rule_code="RN-02",
        )

    user_active_loans = [
        loan
        for loan in (active_loans or [])
        if str(loan.status).strip().upper() == "ACTIVO"
        and str(loan.borrower_id).strip().upper() == borrower_id.upper()
    ]

    if len(user_active_loans) >= MAX_ACTIVE_LOANS_PER_USER:
        held_ids = ", ".join(loan.resource_id for loan in user_active_loans)
        return ValidationResult(
            is_valid=False,
            message=(
                f"[RN-02] Límite de préstamos alcanzado: el usuario '{borrower_id}' ya tiene "
                f"{len(user_active_loans)} préstamo(s) ACTIVO(S) (máximo permitido: {MAX_ACTIVE_LOANS_PER_USER}). "
                f"Equipos que debe devolver primero: [{held_ids}]."
            ),
            rule_code="RN-02",
        )

    return ValidationResult(
        is_valid=True,
        message=f"Préstamo autorizado para el recurso '{resource.name}' ({resource.id}).",
        rule_code="OK",
    )


def should_block_asset_on_incident(
    incident_or_priority: Incident | dict[str, Any] | str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> bool:
    """
    Evalúa la Regla de Negocio RN-03 (Bloqueo Preventivo Cruzado por Incidencia - RF-21):
    Determina si una incidencia tiene una prioridad dentro de BLOCKING_PRIORITIES ('CRITICA', 'ALTA')
    y está vinculada a un espacio o recurso que debe pasar automáticamente a EN_MANTENIMIENTO.

     Formas de invocación soportadas:
    - should_block_asset_on_incident(incident: Incident)
    - should_block_asset_on_incident(priority: str)
    - should_block_asset_on_incident(priority: str, target_id: Optional[str])
    - should_block_asset_on_incident(priority: str, target_type: str, target_id: Optional[str])
    """
    if isinstance(incident_or_priority, Incident):
        priority_norm = str(incident_or_priority.priority).strip().upper()
        t_type_norm = str(incident_or_priority.target_type).strip().upper()
        t_id = incident_or_priority.target_id
        return (
            priority_norm in BLOCKING_PRIORITIES
            and t_type_norm in {"ESPACIO", "RECURSO"}
            and bool(t_id and str(t_id).strip())
        )

    if isinstance(incident_or_priority, dict):
        priority_norm = str(incident_or_priority.get("priority", "")).strip().upper()
        t_type_norm = str(incident_or_priority.get("target_type", "ESPACIO")).strip().upper()
        t_id = incident_or_priority.get("target_id")
        if "target_id" not in incident_or_priority and "target_type" not in incident_or_priority:
            return priority_norm in BLOCKING_PRIORITIES
        return (
            priority_norm in BLOCKING_PRIORITIES
            and t_type_norm in {"ESPACIO", "RECURSO"}
            and bool(t_id and str(t_id).strip())
        )

    priority_norm = str(incident_or_priority).strip().upper()
    if priority_norm not in BLOCKING_PRIORITIES:
        return False

    # Solo se pasó la prioridad: should_block_asset_on_incident("CRITICA")
    if target_type is None and target_id is None:
        return True

    # Se pasaron 2 argumentos: (priority, target_id_or_target_type)
    if target_type is not None and target_id is None:
        second_arg = str(target_type).strip()
        if not second_arg or second_arg.upper() == "GENERAL":
            return False
        return True

    # Se pasaron los 3 argumentos: (priority, target_type, target_id)
    t_type_norm = str(target_type or "").strip().upper()
    return t_type_norm in {"ESPACIO", "RECURSO"} and bool(target_id and str(target_id).strip())


def should_unblock_asset_after_resolution(
    target_id: str,
    incidents: list[Incident],
    resolved_incident_id: Optional[str] = None,
) -> bool:
    """
    Evalúa la Regla RN-03 en resolución (RF-22):
    Verifica si un activo (espacio o recurso) puede volver a DISPONIBLE / OPERATIVO
    comprobando que no tenga otras incidencias abiertas o en proceso con prioridad en BLOCKING_PRIORITIES.
    """
    clean_target = str(target_id).strip()
    if not clean_target:
        return False

    for inc in incidents:
        if resolved_incident_id and inc.id == resolved_incident_id:
            continue
        if inc.target_id != clean_target:
            continue
        if str(inc.status).strip().upper() in {"ABIERTA", "EN_PROCESO"}:
            if str(inc.priority).strip().upper() in BLOCKING_PRIORITIES:
                return False
    return True