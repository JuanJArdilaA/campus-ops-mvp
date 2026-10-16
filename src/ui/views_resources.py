"""Streamlit view for technology inventory, loans, and returns."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from typing import Any

import streamlit as st

from src.core.models import Loan
from src.core.validators import MAX_ACTIVE_LOANS_PER_USER
from src.ui._shared import (
    call_repository,
    exception_message,
    field_value,
    format_failure,
    get_records,
    next_record_id,
    now_timestamp,
    operation_result,
    status_badge,
)

_RESOURCE_CATEGORIES = ("COMPUTO", "AUDIOVISUAL", "ROBOTICA", "ACCESORIO")


def _resource_rows(resources: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "ID": field_value(resource, "id", ""),
            "Equipo": field_value(resource, "name", "Sin nombre"),
            "Categoría": str(field_value(resource, "category", "")).upper(),
            "Ubicación": field_value(resource, "location", ""),
            "Estado": status_badge(field_value(resource, "status", "")),
            "Prestatario": field_value(resource, "current_borrower", "") or "—",
            "Notas": field_value(resource, "notes", ""),
        }
        for resource in resources
    ]


def _loan_rows(loans: list[Any], resources: list[Any]) -> list[dict[str, Any]]:
    resource_names = {str(field_value(item, "id", "")): field_value(item, "name", "Sin nombre") for item in resources}
    return [
        {
            "ID": field_value(loan, "id", ""),
            "Equipo": resource_names.get(str(field_value(loan, "resource_id", "")), field_value(loan, "resource_id", "")),
            "Prestatario": field_value(loan, "borrower_name", ""),
            "Documento": field_value(loan, "borrower_id", ""),
            "Vencimiento": field_value(loan, "expected_return", ""),
            "Estado": status_badge(field_value(loan, "status", "")),
            "Novedad de devolución": field_value(loan, "return_notes", "") or "—",
        }
        for loan in loans
    ]


def render_resources_view(repo: Any) -> None:
    st.subheader("Módulo 2 · Recursos tecnológicos")
    resources = get_records(repo, "resources")
    loans = get_records(repo, "loans")

    if repo is None:
        st.info("El inventario y sus transacciones se habilitarán cuando esté disponible `CampusRepository` (TASK-06).")

    with st.expander("Filtros del inventario", expanded=True):
        filter_columns = st.columns(3)
        category_options = ["Todas"] + sorted({str(field_value(item, "category", "")).upper() for item in resources if field_value(item, "category", "")})
        status_options = ["Todos"] + sorted({str(field_value(item, "status", "")).upper() for item in resources if field_value(item, "status", "")})
        selected_category = filter_columns[0].selectbox("Categoría", category_options, key="resources_filter_category")
        selected_status = filter_columns[1].selectbox("Estado", status_options, key="resources_filter_status")
        search = filter_columns[2].text_input("Buscar por equipo o ID", key="resources_search").strip().casefold()

    filtered_resources = [
        resource
        for resource in resources
        if (selected_category == "Todas" or str(field_value(resource, "category", "")).upper() == selected_category)
        and (selected_status == "Todos" or str(field_value(resource, "status", "")).upper() == selected_status)
        and (
            not search
            or search in str(field_value(resource, "name", "")).casefold()
            or search in str(field_value(resource, "id", "")).casefold()
        )
    ]
    st.dataframe(_resource_rows(filtered_resources), use_container_width=True, hide_index=True)
    st.caption("Estados: 🟢 operativo · 🟡 prestado · 🔴 mantenimiento · ⚫ dado de baja.")
    if not filtered_resources:
        st.caption("No hay recursos que coincidan con los filtros actuales.")

    operational_resources = [
        resource for resource in resources if str(field_value(resource, "status", "")).upper() == "OPERATIVO"
    ]
    st.markdown("#### Registrar préstamo")
    if repo is None:
        st.info("Los préstamos quedarán habilitados cuando esté implementado el repositorio.")
    elif not operational_resources:
        st.warning("No hay equipos operativos para prestar.")
    else:
        resource_by_id = {str(field_value(item, "id", "")): item for item in operational_resources}
        resource_ids = list(resource_by_id)
        with st.form("resource_loan_form", clear_on_submit=True):
            selected_resource_id = st.selectbox(
                "Equipo operativo",
                resource_ids,
                format_func=lambda item: f"{field_value(resource_by_id[item], 'name', item)} · {field_value(resource_by_id[item], 'category', '')}",
            )
            identity_columns = st.columns(3)
            borrower_id = identity_columns[0].text_input("Documento del solicitante")
            borrower_name = identity_columns[1].text_input("Nombre del solicitante")
            borrower_role = identity_columns[2].selectbox("Rol", ("CAMPER", "TRAINER", "STAFF"))
            return_columns = st.columns(2)
            return_date: date = return_columns[0].date_input("Fecha de devolución esperada", value=date.today())
            return_time: time = return_columns[1].time_input("Hora de devolución esperada", value=time(17, 0), step=1800)
            submitted = st.form_submit_button("Registrar préstamo", type="primary")

        if submitted:
            normalized_borrower_id = borrower_id.strip()
            if not normalized_borrower_id or not borrower_name.strip():
                st.error("❌ Complete el documento y el nombre del solicitante.")
            else:
                user_active_loans = [
                    loan
                    for loan in loans
                    if str(field_value(loan, "borrower_id", "")).strip() == normalized_borrower_id
                    and str(field_value(loan, "status", "")).upper() == "ACTIVO"
                ]
                if len(user_active_loans) >= MAX_ACTIVE_LOANS_PER_USER:
                    st.warning(
                        f"Este documento ya tiene {len(user_active_loans)} préstamos activos. "
                        f"El límite actual es {MAX_ACTIVE_LOANS_PER_USER}; el repositorio validará RN-02."
                    )
                loan = Loan(
                    id=next_record_id(loans, "LN"),
                    resource_id=selected_resource_id,
                    borrower_id=normalized_borrower_id,
                    borrower_name=borrower_name.strip(),
                    borrower_role=borrower_role,
                    loan_timestamp=now_timestamp(),
                    expected_return=datetime.combine(return_date, return_time).isoformat(timespec="minutes"),
                    status="ACTIVO",
                )
                try:
                    result = call_repository(
                        repo,
                        ("create_loan",),
                        payload=asdict(loan),
                        entity=loan,
                        entity_name="loan",
                    )
                    is_valid, _, _ = operation_result(result)
                    if is_valid:
                        st.session_state["resources_flash"] = ("success", f"Préstamo {loan.id} registrado correctamente.")
                        st.rerun()
                    st.error("❌ " + format_failure(result, "RN-02"))
                except Exception as error:
                    st.error("❌ " + exception_message(error, "RN-02"))

    if "resources_flash" in st.session_state:
        kind, message = st.session_state.pop("resources_flash")
        if kind == "success":
            st.success(message)
        else:
            st.error(message)

    active_loans = [loan for loan in loans if str(field_value(loan, "status", "")).upper() == "ACTIVO"]
    st.markdown("#### Préstamos activos y devoluciones")
    st.dataframe(_loan_rows(active_loans, resources), use_container_width=True, hide_index=True)
    if active_loans and repo is not None:
        loan_by_id = {str(field_value(loan, "id", "")): loan for loan in active_loans}
        loan_ids = list(loan_by_id)
        with st.form("resource_return_form"):
            selected_loan_id = st.selectbox(
                "Préstamo a devolver",
                loan_ids,
                format_func=lambda item: (
                    f"{item} · {field_value(loan_by_id[item], 'borrower_name', '')} · "
                    f"{field_value(loan_by_id[item], 'resource_id', '')}"
                ),
            )
            report_damage = st.checkbox("Reportar daño al devolver")
            damage_description = st.text_area(
                "Describe el daño o la novedad",
                disabled=not report_damage,
                help="Al confirmar, el repositorio debe cerrar el préstamo, crear una incidencia y pasar el equipo a mantenimiento.",
            )
            returned = st.form_submit_button("Registrar devolución")

        if returned:
            if report_damage and not damage_description.strip():
                st.error("❌ Describa la novedad para registrar la incidencia asociada.")
            else:
                return_timestamp = now_timestamp()
                payload = {
                    "loan_id": selected_loan_id,
                    "id": selected_loan_id,
                    "resource_id": field_value(loan_by_id[selected_loan_id], "resource_id", ""),
                    "actual_return": return_timestamp,
                    "return_timestamp": return_timestamp,
                    "return_notes": damage_description.strip() if report_damage else "",
                    "notes": damage_description.strip() if report_damage else "",
                    "damaged": report_damage,
                    "has_damage": report_damage,
                    "report_damage": report_damage,
                    "damage_report": damage_description.strip(),
                    "damage_description": damage_description.strip(),
                    "incident_description": damage_description.strip(),
                    "condition": "CON_DANO" if report_damage else "SIN_DANO",
                    "return_condition": "CON_DANO" if report_damage else "SIN_DANO",
                }
                damage_flags = (("damaged", "has_damage", "report_damage", "damage_report", "condition", "return_condition"),)
                try:
                    result = call_repository(
                        repo,
                        ("return_loan", "return_resource_loan", "process_loan_return", "close_loan", "return_resource"),
                        payload=payload,
                        required_any=damage_flags if report_damage else (),
                    )
                    is_valid, _, _ = operation_result(result)
                    if is_valid:
                        message = (
                            f"Devolución de {selected_loan_id} registrada; el recurso quedó en mantenimiento y se generó una incidencia."
                            if report_damage
                            else f"Devolución de {selected_loan_id} registrada correctamente."
                        )
                        st.session_state["resources_flash"] = ("success", message)
                        st.rerun()
                    st.error("❌ " + format_failure(result, "RN-02"))
                except Exception as error:
                    st.error("❌ " + exception_message(error, "RN-02"))
