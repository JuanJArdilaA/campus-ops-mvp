"""Streamlit view for Module 3: AI-assisted incident triage and allocation recommender."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import streamlit as st

from src.core.ai_service import recommend_campus_allocation, triage_incident
from src.core.models import Incident, Resource, Space
from src.core.validators import BLOCKING_PRIORITIES
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


def _priority_badge(priority: Any) -> str:
    normalized = str(priority or "MEDIA").strip().upper()
    icons = {
        "CRITICA": "🚨",
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAJA": "🟢",
    }
    return f"{icons.get(normalized, '⚪')} {normalized}"


def _incident_rows(
    incidents: list[Any],
    spaces: list[Any],
    resources: list[Any],
) -> list[dict[str, Any]]:
    asset_names: dict[str, str] = {}
    for space in spaces:
        asset_names[str(field_value(space, "id", ""))] = str(field_value(space, "name", ""))
    for resource in resources:
        asset_names[str(field_value(resource, "id", ""))] = str(field_value(resource, "name", ""))

    rows: list[dict[str, Any]] = []
    for inc in incidents:
        target_id = field_value(inc, "target_id", None)
        target_type = str(field_value(inc, "target_type", "GENERAL")).upper()
        if target_id:
            target_label = f"{target_type}: {target_id} ({asset_names.get(str(target_id), str(target_id))})"
        else:
            target_label = "GENERAL"

        rows.append(
            {
                "ID": field_value(inc, "id", ""),
                "Título": field_value(inc, "title", ""),
                "Prioridad": _priority_badge(field_value(inc, "priority", "")),
                "Categoría": str(field_value(inc, "category", "")).upper(),
                "Activo afectado": target_label,
                "Área asignada": field_value(inc, "assigned_team", ""),
                "Estado": status_badge(field_value(inc, "status", "")),
                "Fuente IA": field_value(inc, "ai_source", ""),
                " Acción sugerida": field_value(inc, "suggested_action", ""),
            }
        )
    return rows


def _to_space_objects(raw_spaces: list[Any]) -> list[Space]:
    result: list[Space] = []
    for item in raw_spaces:
        if isinstance(item, Space):
            result.append(item)
        elif isinstance(item, dict):
            result.append(Space.from_dict(item))
    return result


def _to_resource_objects(raw_resources: list[Any]) -> list[Resource]:
    result: list[Resource] = []
    for item in raw_resources:
        if isinstance(item, Resource):
            result.append(item)
        elif isinstance(item, dict):
            result.append(Resource.from_dict(item))
    return result


def render_incidents_view(repo: Any) -> None:
    st.subheader("Módulo 3 · Incidencias, Triaje IA y Recomendador Operativo")

    spaces = get_records(repo, "spaces")
    resources = get_records(repo, "resources")
    incidents = get_records(repo, "incidents")

    if repo is None:
        st.info("El registro transaccional de incidencias requiere que `CampusRepository` esté inicializado.")

    triage_col, recommender_col = st.columns([1.15, 1.0], gap="large")

    # ==========================================================================
    # SUB-SECCIÓN 1: TRIAJE INTELIGENTE DE INCIDENCIAS + BLOQUEO RN-03
    # ==========================================================================
    with triage_col:
        st.markdown("#### 1. Triaje Inteligente de Incidencias (RN-03)")
        st.caption(
            "Describe el incidente en lenguaje natural. La IA clasificará categoría, prioridad, "
            "área responsable y plan de acción, bloqueando automáticamente el salón o equipo si es grave."
        )

        target_type = st.radio(
            "Tipo de objetivo afectado",
            ("ESPACIO", "RECURSO", "GENERAL"),
            horizontal=True,
            key="incident_target_type_selector",
        )

        space_by_id = {str(field_value(s, "id", "")): s for s in spaces if field_value(s, "id", "")}
        resource_by_id = {str(field_value(r, "id", "")): r for r in resources if field_value(r, "id", "")}

        with st.form("incident_triage_form", clear_on_submit=True):
            title = st.text_input(
                "Título breve del reporte",
                placeholder="Ej. Corto circuito en tomacorriente / Proyector no enciende",
            )
            reporter_name = st.text_input(
                "Reportado por",
                placeholder="Nombre del camper, trainer o coordinador",
            )

            selected_target_id: str | None = None
            selected_target_name: str = ""

            if target_type == "ESPACIO":
                if space_by_id:
                    selected_target_id = st.selectbox(
                        "Espacio afectado",
                        list(space_by_id.keys()),
                        format_func=lambda sid: (
                            f"{sid} · {field_value(space_by_id[sid], 'name', sid)} "
                            f"({field_value(space_by_id[sid], 'status', '')})"
                        ),
                    )
                    if selected_target_id:
                        selected_target_name = str(field_value(space_by_id[selected_target_id], "name", selected_target_id))
                else:
                    st.warning("No hay espacios cargados en el catálogo.")
            elif target_type == "RECURSO":
                if resource_by_id:
                    selected_target_id = st.selectbox(
                        "Recurso tecnológico afectado",
                        list(resource_by_id.keys()),
                        format_func=lambda rid: (
                            f"{rid} · {field_value(resource_by_id[rid], 'name', rid)} "
                            f"({field_value(resource_by_id[rid], 'status', '')})"
                        ),
                    )
                    if selected_target_id:
                        selected_target_name = str(field_value(resource_by_id[selected_target_id], "name", selected_target_id))
                else:
                    st.warning("No hay recursos cargados en el inventario.")
            else:
                st.caption("Incidencia general del campus (no bloquea un aula o equipo específico).")

            description = st.text_area(
                "Descripción detallada en lenguaje natural",
                placeholder="Ej. Sale humo y olor a quemado del tomacorriente junto al tablero del salón...",
                height=110,
            )

            submitted_incident = st.form_submit_button(
                "Analizar con IA y Registrar Incidencia",
                type="primary",
            )

        if submitted_incident:
            if not title.strip() or not description.strip() or not reporter_name.strip():
                st.error("❌ Complete el título, el nombre del reportante y la descripción del incidente.")
            elif repo is None:
                st.error("❌ El repositorio no está disponible para guardar la incidencia.")
            else:
                with st.spinner("Clasificando incidencia mediante IA y verificando reglas de bloqueo (RN-03)..."):
                    triage = triage_incident(
                        title=title.strip(),
                        description=description.strip(),
                        target_type=target_type,
                        target_name=selected_target_name,
                    )

                    incident_obj = Incident(
                        id=next_record_id(incidents, "INC"),
                        title=title.strip(),
                        description=description.strip(),
                        reporter_name=reporter_name.strip(),
                        target_type=target_type,
                        target_id=selected_target_id,
                        category=str(triage.get("category", "OTRO")),
                        priority=str(triage.get("priority", "MEDIA")),
                        assigned_team=str(triage.get("assigned_team", "Coordinación")),
                        suggested_action=str(triage.get("suggested_action", "")),
                        ai_source=str(triage.get("ai_source", "FALLBACK_RULES")),
                        status="ABIERTA",
                        created_at=now_timestamp(),
                    )

                    try:
                        raw_result = call_repository(
                            repo,
                            ("create_incident",),
                            payload=asdict(incident_obj),
                            entity=incident_obj,
                            entity_name="incident",
                        )

                        blocked_asset = False
                        created_inc = incident_obj
                        if isinstance(raw_result, tuple) and len(raw_result) == 2:
                            if isinstance(raw_result[0], bool):
                                blocked_asset = raw_result[0]
                                if isinstance(raw_result[1], Incident):
                                    created_inc = raw_result[1]
                            elif isinstance(raw_result[1], bool):
                                blocked_asset = raw_result[1]

                        st.session_state["incidents_last_triage"] = {
                            "id": created_inc.id,
                            "title": created_inc.title,
                            "category": created_inc.category,
                            "priority": created_inc.priority,
                            "assigned_team": created_inc.assigned_team,
                            "suggested_action": created_inc.suggested_action,
                            "ai_source": created_inc.ai_source,
                            "target_type": created_inc.target_type,
                            "target_id": created_inc.target_id,
                            "target_name": selected_target_name,
                            "blocked": blocked_asset,
                        }
                        st.session_state["incidents_flash"] = (
                            "success",
                            f"✅ Incidencia {created_inc.id} clasificada y registrada correctamente.",
                        )
                        st.rerun()
                    except Exception as error:
                        st.error("❌ " + exception_message(error, "RN-03"))

        if "incidents_flash" in st.session_state:
            kind, msg = st.session_state.pop("incidents_flash")
            if kind == "success":
                st.success(msg)
            else:
                st.error(msg)

        last_triage = st.session_state.get("incidents_last_triage")
        if isinstance(last_triage, dict):
            with st.container(border=True):
                st.markdown(f"**Resultado del Triaje IA · `{last_triage.get('id', '')}`**")
                meta_cols = st.columns(4)
                meta_cols[0].metric("Prioridad", str(last_triage.get("priority", "")))
                meta_cols[1].metric("Categoría", str(last_triage.get("category", "")))
                meta_cols[2].metric("Equipo Asignado", str(last_triage.get("assigned_team", "")))
                meta_cols[3].metric("Motor", str(last_triage.get("ai_source", "")))

                st.markdown(f"**Plan de acción sugerido:** {last_triage.get('suggested_action', '')}")

                if last_triage.get("ai_source") == "FALLBACK_RULES":
                    st.info(
                        "ℹ️ Clasificación generada por el motor determinista local (`FALLBACK_RULES`) "
                        "debido a ausencia de clave/red de API externa (RF-24)."
                    )

                if last_triage.get("blocked") or (
                    str(last_triage.get("priority", "")).upper() in BLOCKING_PRIORITIES
                    and last_triage.get("target_id")
                ):
                    st.error(
                        f"🚨 **[RN-03] Bloqueo Preventivo Cruzado Activado:** "
                        f"El activo `{last_triage.get('target_id')}` ({last_triage.get('target_name') or last_triage.get('target_type')}) "
                        f"cambió automáticamente a estado **EN_MANTENIMIENTO** por incidencia de prioridad "
                        f"**{last_triage.get('priority')}**."
                    )

    # ==========================================================================
    # SUB-SECCIÓN 2: RECOMENDADOR INTELIGENTE DE ASIGNACIÓN IA (RF-23)
    # ==========================================================================
    with recommender_col:
        st.markdown("#### 2. Recomendador Inteligente de Asignación IA (RF-23)")
        st.caption(
            "Describe tu necesidad operativa (aforo, tipo de actividad y equipos requeridos). "
            "El asistente filtrará únicamente los espacios `DISPONIBLE` y recursos `OPERATIVO`."
        )

        with st.form("ai_allocation_recommender_form"):
            user_query = st.text_area(
                "Requerimiento operativo en texto libre",
                placeholder=(
                    "Ej. Necesito un salón o laboratorio para 20 personas con videobeam "
                    "y 2 portátiles adicionales para taller práctico."
                ),
                height=135,
            )
            ask_recommendation = st.form_submit_button(
                "Obtener Recomendación Inteligente",
                type="primary",
            )

        if ask_recommendation:
            if not user_query.strip():
                st.error("❌ Escriba una descripción de la necesidad operativa para generar la recomendación.")
            else:
                space_objs = _to_space_objects(spaces)
                resource_objs = _to_resource_objects(resources)
                with st.spinner("Evaluando inventario disponible y generando paquete de asignación..."):
                    recommendation = recommend_campus_allocation(
                        user_query=user_query.strip(),
                        available_spaces=space_objs,
                        available_resources=resource_objs,
                    )
                    st.session_state["last_ai_recommendation"] = recommendation

        recommendation = st.session_state.get("last_ai_recommendation")
        if isinstance(recommendation, dict):
            with st.container(border=True):
                st.markdown("**Paquete de Asignación Recomendado**")
                rec_space_id = recommendation.get("recommended_space_id")
                rec_space_name = recommendation.get("recommended_space_name", "Sin espacio disponible")
                rec_resource_ids: list[str] = list(recommendation.get("recommended_resource_ids", []))
                rec_source = recommendation.get("ai_source", "FALLBACK_RULES")

                if rec_space_id:
                    st.success(f"🏫 **Espacio sugerido:** {rec_space_name} (`{rec_space_id}`)")
                else:
                    st.warning(f"🏫 **Espacio sugerido:** {rec_space_name}")

                if rec_resource_ids:
                    res_labels = [
                        f"`{rid}` · {field_value(resource_by_id.get(rid, {}), 'name', rid)}"
                        for rid in rec_resource_ids
                    ]
                    st.markdown("**💻 Recursos tecnológicos sugeridos:**\n- " + "\n- ".join(res_labels))
                else:
                    st.caption("💻 Sin recursos tecnológicos adicionales sugeridos.")

                st.markdown(f"**Justificación:** {recommendation.get('justification', '')}")
                st.caption(f"Fuente de recomendación: `{rec_source}`")
                if rec_source == "FALLBACK_RULES":
                    st.info(
                        "ℹ️ Recomendación calculada con el motor determinista local (`FALLBACK_RULES`) "
                        "sobre el inventario realmente disponible."
                    )

    # ==========================================================================
    # LISTADO Y RESOLUCIÓN DE INCIDENCIAS (RF-22 / RN-03)
    # ==========================================================================
    st.divider()
    st.markdown("#### Historial de Incidencias y Resolución (Desbloqueo Inteligente RN-03)")

    filter_cols = st.columns(3)
    status_filter = filter_cols[0].selectbox(
        "Filtrar por estado",
        ("Todas", "ABIERTA", "EN_PROCESO", "RESUELTA"),
        key="incidents_status_filter",
    )
    priority_filter = filter_cols[1].selectbox(
        "Filtrar por prioridad",
        ("Todas", "CRITICA", "ALTA", "MEDIA", "BAJA"),
        key="incidents_priority_filter",
    )
    search_inc = filter_cols[2].text_input("Buscar por ID, título o área", key="incidents_search").strip().casefold()

    filtered_incidents = [
        inc
        for inc in incidents
        if (status_filter == "Todas" or str(field_value(inc, "status", "")).upper() == status_filter)
        and (priority_filter == "Todas" or str(field_value(inc, "priority", "")).upper() == priority_filter)
        and (
            not search_inc
            or search_inc in str(field_value(inc, "id", "")).casefold()
            or search_inc in str(field_value(inc, "title", "")).casefold()
            or search_inc in str(field_value(inc, "assigned_team", "")).casefold()
        )
    ]

    st.dataframe(_incident_rows(filtered_incidents, spaces, resources), use_container_width=True, hide_index=True)

    open_incidents = [
        inc
        for inc in incidents
        if str(field_value(inc, "status", "")).upper() in {"ABIERTA", "EN_PROCESO"}
    ]

    if open_incidents and repo is not None:
        inc_by_id = {str(field_value(inc, "id", "")): inc for inc in open_incidents}
        with st.form("resolve_incident_form"):
            selected_inc_id = st.selectbox(
                "Seleccione una incidencia abierta para marcarla como RESUELTA",
                list(inc_by_id.keys()),
                format_func=lambda iid: (
                    f"{iid} · [{field_value(inc_by_id[iid], 'priority', '')}] "
                    f"{field_value(inc_by_id[iid], 'title', '')} "
                    f"(Activo: {field_value(inc_by_id[iid], 'target_id', None) or 'GENERAL'})"
                ),
            )
            resolve_submitted = st.form_submit_button("Marcar incidencia como RESUELTA")

        if resolve_submitted:
            try:
                raw_resolve = call_repository(
                    repo,
                    ("resolve_incident",),
                    payload={"incident_id": selected_inc_id, "id": selected_inc_id},
                )
                is_valid, _, _ = operation_result(raw_resolve)
                unblocked = False
                if isinstance(raw_resolve, tuple) and len(raw_resolve) == 2 and isinstance(raw_resolve[1], bool):
                    unblocked = raw_resolve[1]

                if is_valid:
                    target_inc = inc_by_id[selected_inc_id]
                    t_id = field_value(target_inc, "target_id", None)
                    if unblocked and t_id:
                        msg = (
                            f"✅ Incidencia {selected_inc_id} marcada como RESUELTA. "
                            f"[RN-03] El activo `{t_id}` no tiene más incidencias críticas/altas abiertas "
                            f"y fue restaurado automáticamente a estado operativo/disponible."
                        )
                    else:
                        msg = f"✅ Incidencia {selected_inc_id} marcada como RESUELTA."
                    st.session_state["incidents_flash"] = ("success", msg)
                    st.rerun()
                else:
                    st.error("❌ " + format_failure(raw_resolve, "RN-03"))
            except Exception as error:
                st.error("❌ " + exception_message(error, "RN-03"))

