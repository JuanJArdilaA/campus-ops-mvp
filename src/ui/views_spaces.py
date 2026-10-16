"""Streamlit view for space availability and reservations."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, time
from typing import Any

import streamlit as st

from src.core.models import Reservation
from src.ui._shared import (
    call_repository,
    exception_message,
    field_value,
    format_failure,
    get_records,
    next_record_id,
    operation_result,
    status_badge,
)


def _space_rows(spaces: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for space in spaces:
        features = field_value(space, "features", []) or []
        if isinstance(features, str):
            features = [features]
        rows.append(
            {
                "ID": field_value(space, "id", ""),
                "Espacio": field_value(space, "name", "Sin nombre"),
                "Tipo": str(field_value(space, "type", "")).upper(),
                "Capacidad": field_value(space, "capacity", 0),
                "Estado": status_badge(field_value(space, "status", "")),
                "Características": ", ".join(str(feature) for feature in features),
            }
        )
    return rows


def _reservation_rows(reservations: list[Any], spaces: list[Any]) -> list[dict[str, Any]]:
    names = {str(field_value(space, "id", "")): field_value(space, "name", "Sin nombre") for space in spaces}
    rows: list[dict[str, Any]] = []
    for reservation in reservations:
        rows.append(
            {
                "ID": field_value(reservation, "id", ""),
                "Espacio": names.get(str(field_value(reservation, "space_id", "")), field_value(reservation, "space_id", "")),
                "Solicitante": field_value(reservation, "requester_name", ""),
                "Fecha": field_value(reservation, "date", ""),
                "Horario": f"{field_value(reservation, 'start_time', '')}–{field_value(reservation, 'end_time', '')}",
                "Asistentes": field_value(reservation, "attendees", ""),
                "Estado": status_badge(field_value(reservation, "status", "")),
            }
        )
    return rows


def render_spaces_view(repo: Any) -> None:
    st.subheader("Módulo 1 · Espacios y reservas")
    spaces = get_records(repo, "spaces")
    reservations = get_records(repo, "reservations")

    if repo is None:
        st.info("La tabla y las reservas se habilitarán cuando esté disponible `CampusRepository` (TASK-06).")

    with st.expander("Filtros del catálogo", expanded=True):
        filter_columns = st.columns(4)
        type_options = ["Todos"] + sorted({str(field_value(space, "type", "")).upper() for space in spaces if field_value(space, "type", "")})
        status_options = ["Todos"] + sorted({str(field_value(space, "status", "")).upper() for space in spaces if field_value(space, "status", "")})
        selected_type = filter_columns[0].selectbox("Tipo", type_options, key="spaces_filter_type")
        selected_status = filter_columns[1].selectbox("Estado", status_options, key="spaces_filter_status")
        min_capacity = filter_columns[2].number_input("Capacidad mínima", min_value=0, value=0, step=1, key="spaces_min_capacity")
        search = filter_columns[3].text_input("Buscar por nombre o ID", key="spaces_search").strip().casefold()

    filtered_spaces = [
        space
        for space in spaces
        if (selected_type == "Todos" or str(field_value(space, "type", "")).upper() == selected_type)
        and (selected_status == "Todos" or str(field_value(space, "status", "")).upper() == selected_status)
        and int(field_value(space, "capacity", 0) or 0) >= int(min_capacity)
        and (
            not search
            or search in str(field_value(space, "name", "")).casefold()
            or search in str(field_value(space, "id", "")).casefold()
        )
    ]
    st.dataframe(_space_rows(filtered_spaces), use_container_width=True, hide_index=True)
    st.caption("Estados: 🟢 disponible · 🟡 ocupado · 🔴 mantenimiento o inhabilitado.")
    if not filtered_spaces:
        st.caption("No hay espacios que coincidan con los filtros actuales.")

    available_spaces = [
        space for space in spaces if str(field_value(space, "status", "")).upper() == "DISPONIBLE"
    ]
    st.markdown("#### Nueva reserva")
    if repo is None:
        st.info("La reserva quedará habilitada cuando esté implementado el repositorio.")
    elif not available_spaces:
        st.warning("No hay espacios disponibles para reservar en este momento.")
    else:
        space_by_id = {str(field_value(space, "id", "")): space for space in available_spaces}
        space_ids = list(space_by_id)
        with st.form("space_reservation_form", clear_on_submit=True):
            selected_space_id = st.selectbox(
                "Espacio disponible",
                space_ids,
                format_func=lambda item: f"{field_value(space_by_id[item], 'name', item)} · capacidad {field_value(space_by_id[item], 'capacity', 0)}",
            )
            identity_columns = st.columns(3)
            requester_id = identity_columns[0].text_input("Documento o código del solicitante")
            requester_name = identity_columns[1].text_input("Nombre del solicitante")
            requester_role = identity_columns[2].selectbox("Rol del solicitante", ("CAMPER", "TRAINER", "STAFF"))
            schedule_columns = st.columns(3)
            reservation_date: date = schedule_columns[0].date_input("Fecha", value=date.today())
            start_time: time = schedule_columns[1].time_input("Hora de inicio", value=time(8, 0), step=1800)
            end_time: time = schedule_columns[2].time_input("Hora de fin", value=time(10, 0), step=1800)
            attendees = st.number_input("Cantidad de asistentes", min_value=1, value=1, step=1)
            purpose = st.text_input("Motivo de la reserva")
            submitted = st.form_submit_button("Crear reserva", type="primary")

        if submitted:
            if not requester_id.strip() or not requester_name.strip() or not purpose.strip():
                st.error("❌ Complete el documento, el nombre y el motivo de la reserva.")
            else:
                reservation = Reservation(
                    id=next_record_id(reservations, "RSV"),
                    space_id=selected_space_id,
                    requester_id=requester_id.strip(),
                    requester_name=requester_name.strip(),
                    date=reservation_date.isoformat(),
                    start_time=start_time.strftime("%H:%M"),
                    end_time=end_time.strftime("%H:%M"),
                    attendees=int(attendees),
                    purpose=purpose.strip(),
                    status="ACTIVA",
                )
                payload = asdict(reservation)
                payload["requester_role"] = requester_role
                try:
                    result = call_repository(
                        repo,
                        ("create_reservation",),
                        payload=payload,
                        entity=reservation,
                        entity_name="reservation",
                    )
                    is_valid, _, _ = operation_result(result)
                    if is_valid:
                        st.session_state["spaces_flash"] = ("success", f"Reserva {reservation.id} registrada correctamente.")
                        st.rerun()
                    st.error("❌ " + format_failure(result, "RN-01/RN-04"))
                except Exception as error:
                    st.error("❌ " + exception_message(error, "RN-01/RN-04"))

    if "spaces_flash" in st.session_state:
        kind, message = st.session_state.pop("spaces_flash")
        if kind == "success":
            st.success(message)
        else:
            st.error(message)

    st.markdown("#### Reservas activas")
    active_reservations = [
        reservation
        for reservation in reservations
        if str(field_value(reservation, "status", "")).upper() == "ACTIVA"
    ]
    st.dataframe(_reservation_rows(active_reservations, spaces), use_container_width=True, hide_index=True)
    if active_reservations and repo is not None:
        reservation_by_id = {str(field_value(item, "id", "")): item for item in active_reservations}
        reservation_ids = list(reservation_by_id)
        with st.form("release_reservation_form"):
            selected_reservation_id = st.selectbox(
                "Seleccione la reserva que desea liberar",
                reservation_ids,
                format_func=lambda item: (
                    f"{item} · {field_value(reservation_by_id[item], 'requester_name', '')} · "
                    f"{field_value(reservation_by_id[item], 'date', '')} "
                    f"{field_value(reservation_by_id[item], 'start_time', '')}"
                ),
            )
            release = st.form_submit_button("Finalizar / cancelar reserva")
        if release:
            try:
                result = call_repository(
                    repo,
                    ("release_reservation", "cancel_reservation", "finish_reservation", "finalize_reservation", "update_reservation_status"),
                    payload={
                        "reservation_id": selected_reservation_id,
                        "id": selected_reservation_id,
                        "status": "CANCELADA",
                        "new_status": "CANCELADA",
                    },
                )
                is_valid, _, _ = operation_result(result)
                if is_valid:
                    st.session_state["spaces_flash"] = ("success", f"La reserva {selected_reservation_id} fue liberada.")
                    st.rerun()
                st.error("❌ " + format_failure(result, "RN-01"))
            except Exception as error:
                st.error("❌ " + exception_message(error, "RN-01"))
