"""Streamlit entry point for the Campuslands operations dashboard."""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from src.ui._shared import field_value, get_records
from src.ui.views_audit import render_audit_view
from src.ui.views_incidents import render_incidents_view
from src.ui.views_resources import render_resources_view
from src.ui.views_spaces import render_spaces_view

try:
    from src.core.repository import CampusRepository
except ImportError as error:
    CampusRepository = None  # type: ignore[assignment,misc]
    _REPOSITORY_IMPORT_ERROR = str(error)
else:
    _REPOSITORY_IMPORT_ERROR = ""

LOGGER = logging.getLogger(__name__)


def _initialize_repository() -> Any:
    if "repo" in st.session_state:
        return st.session_state["repo"]

    if CampusRepository is None:
        st.session_state["repo"] = None
        st.session_state["repository_error"] = (
            "La clase CampusRepository todavía no está implementada en "
            "src/core/repository.py."
        )
        return None

    try:
        repository = CampusRepository()
    except Exception as error:  # Show an actionable message instead of a traceback.
        LOGGER.exception("No fue posible inicializar el repositorio del campus.")
        st.session_state["repo"] = None
        st.session_state["repository_error"] = str(error)
        return None

    st.session_state["repo"] = repository
    st.session_state["repository_error"] = ""
    return repository


def _count_status(records: list[Any], expected_status: str) -> int:
    return sum(
        1
        for record in records
        if str(field_value(record, "status", "")).strip().upper() == expected_status
    )


def _render_kpis(repo: Any) -> None:
    spaces = get_records(repo, "spaces")
    resources = get_records(repo, "resources")
    incidents = get_records(repo, "incidents")
    quarantine = get_records(repo, "quarantine")
    critical_open = sum(
        1
        for incident in incidents
        if str(field_value(incident, "priority", "")).upper() == "CRITICA"
        and str(field_value(incident, "status", "ABIERTA")).upper() != "RESUELTA"
    )

    columns = st.columns(4)
    columns[0].metric("Aulas disponibles", _count_status(spaces, "DISPONIBLE"))
    columns[1].metric("Equipos operativos", _count_status(resources, "OPERATIVO"))
    columns[2].metric("Incidencias críticas abiertas", critical_open)
    columns[3].metric("Registros en cuarentena", len(quarantine))


def main() -> None:
    st.set_page_config(page_title="Campuslands | Gestión Operativa", page_icon="🏫", layout="wide")
    st.title("Campuslands · Gestión Operativa")
    st.caption("Espacios, inventario tecnológico e incidencias en un solo tablero.")

    repo = _initialize_repository()
    repository_error = st.session_state.get("repository_error", "")
    if repo is None:
        st.warning(
            "El dashboard está disponible, pero las transacciones requieren "
            "que `CampusRepository` esté implementado."
        )
        if repository_error:
            st.caption(repository_error or _REPOSITORY_IMPORT_ERROR)

    try:
        _render_kpis(repo)
        spaces_tab, resources_tab, incidents_tab, audit_tab = st.tabs(
            ["Espacios", "Recursos tecnológicos", "Incidencias + IA", "Auditoría"]
        )
        with spaces_tab:
            render_spaces_view(repo)
        with resources_tab:
            render_resources_view(repo)
        with incidents_tab:
            render_incidents_view(repo)
        with audit_tab:
            render_audit_view(repo)
    except Exception:
        LOGGER.exception("Error inesperado al renderizar el dashboard.")
        st.error("No se pudo cargar una sección del dashboard. Revise el estado del repositorio e inténtelo de nuevo.")


if __name__ == "__main__":
    main()
