"""Streamlit view for data quarantine (RN-05), state inspection, and raw dataset reload (RF-06)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.ui._shared import (
    exception_message,
    field_value,
    get_records,
    record_dict,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATE_FILE = _PROJECT_ROOT / "data" / "processed" / "campus_state.json"


def _quarantine_rows(quarantine_records: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(quarantine_records, start=1):
        raw_data = field_value(item, "raw_data", {})
        if not isinstance(raw_data, dict):
            raw_data = record_dict(raw_data)
        rows.append(
            {
                "#": idx,
                "Entidad Origen": str(field_value(item, "source_entity", "desconocido")),
                "Motivo de Cuarentena (RN-05)": str(field_value(item, "reason", "")),
                "ID en Registro Crudo": str(raw_data.get("id", "—") if isinstance(raw_data, dict) else "—"),
                "Registro Crudo (JSON)": json.dumps(raw_data, ensure_ascii=False),
            }
        )
    return rows


def _load_persisted_json(repo: Any) -> dict[str, Any]:
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "metadata": {"status": "En memoria"},
        "spaces": [record_dict(s) for s in get_records(repo, "spaces")],
        "resources": [record_dict(r) for r in get_records(repo, "resources")],
        "reservations": [record_dict(rv) for rv in get_records(repo, "reservations")],
        "loans": [record_dict(ln) for ln in get_records(repo, "loans")],
        "incidents": [record_dict(inc) for inc in get_records(repo, "incidents")],
        "quarantine": [record_dict(q) for q in get_records(repo, "quarantine")],
    }


def render_audit_view(repo: Any) -> None:
    st.subheader("Módulo de Auditoría · Cuarentena de Datos (RN-05) y Estado Global")
    st.caption(
        "Inspección transparente de registros corruptos aislados durante la ingesta y verificación "
        "en tiempo real de la persistencia atómica en `data/processed/campus_state.json`."
    )

    if "audit_flash" in st.session_state:
        kind, message = st.session_state.pop("audit_flash")
        if kind == "success":
            st.success(message)
        else:
            st.error(message)

    quarantine = get_records(repo, "quarantine")
    spaces = get_records(repo, "spaces")
    resources = get_records(repo, "resources")
    reservations = get_records(repo, "reservations")
    loans = get_records(repo, "loans")
    incidents = get_records(repo, "incidents")

    # Barra de resumen operativo y botón de recarga controlada (RF-06)
    top_col1, top_col2 = st.columns([3, 1.4])
    with top_col1:
        summary_cols = st.columns(5)
        summary_cols[0].metric("Espacios Válidos", len(spaces))
        summary_cols[1].metric("Recursos Válidos", len(resources))
        summary_cols[2].metric("Reservas Totales", len(reservations))
        summary_cols[3].metric("Préstamos Totales", len(loans))
        summary_cols[4].metric("En Cuarentena (RN-05)", len(quarantine))

    with top_col2:
        st.markdown("##### Restauración desde `data/raw/`")
        if st.button(
            "🔄 Restaurar y Re-procesar Dataset Original",
            type="primary",
            use_container_width=True,
            disabled=repo is None,
            help="Reconstruye data/processed/campus_state.json leyendo y sanitizando nuevamente data/raw/ (RF-06).",
        ):
            try:
                reload_fn = getattr(repo, "reload_from_raw", None) or getattr(repo, "reset_from_raw", None)
                if callable(reload_fn):
                    reload_fn()
                    st.session_state["audit_flash"] = (
                        "success",
                        "✅ Dataset original de `data/raw/` re-procesado y persistido en `campus_state.json`.",
                    )
                    st.rerun()
                else:
                    st.error("❌ El repositorio no expone `reload_from_raw()`.")
            except Exception as error:
                st.error("❌ " + exception_message(error, "RN-05"))

    st.divider()

    # ==========================================================================
    # SECCIÓN 1: TABLA DE CUARENTENA DE DATOS (RN-05)
    # ==========================================================================
    st.markdown("#### 1. Registros Aislados en Cuarentena (`RN-05`)")
    if not quarantine:
        st.info("No se encontraron registros en cuarentena en el estado actual.")
    else:
        entity_options = ["Todas"] + sorted(
            {str(field_value(item, "source_entity", "")) for item in quarantine if field_value(item, "source_entity", "")}
        )
        selected_entity = st.selectbox(
            "Filtrar por entidad de origen",
            entity_options,
            key="audit_quarantine_entity_filter",
        )
        filtered_quarantine = [
            item
            for item in quarantine
            if selected_entity == "Todas" or str(field_value(item, "source_entity", "")) == selected_entity
        ]

        st.dataframe(
            _quarantine_rows(filtered_quarantine),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"Total aislados mostrados: {len(filtered_quarantine)} de {len(quarantine)} registro(s). "
            "Estos registros fueron bloqueados preventivamente para no contaminar la operación (RN-05)."
        )

    st.divider()

    # ==========================================================================
    # SECCIÓN 2: VISOR DE PERSISTENCIA JSON EN TIEMPO REAL (RF-05 / RNF-12)
    # ==========================================================================
    st.markdown("#### 2. Visor del Estado Persistido (`data/processed/campus_state.json`)")
    persisted_state = _load_persisted_json(repo)
    metadata = persisted_state.get("metadata", {})

    meta_col1, meta_col2, meta_col3 = st.columns(3)
    meta_col1.caption(f"📄 **Archivo:** `data/processed/campus_state.json`")
    meta_col2.caption(f"🕒 **Última actualización:** `{metadata.get('last_updated', 'N/A')}`")
    meta_col3.caption(f"📦 **Incidencias registradas:** `{len(incidents)}`")

    section_to_inspect = st.selectbox(
        "Sección del JSON a inspeccionar",
        ("Estado Completo", "spaces", "resources", "reservations", "loans", "incidents", "quarantine", "metadata"),
        key="audit_json_section_selector",
    )

    if section_to_inspect == "Estado Completo":
        st.json(persisted_state, expanded=False)
    else:
        st.json(persisted_state.get(section_to_inspect, []), expanded=True)

