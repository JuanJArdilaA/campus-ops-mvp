triage_incident(title: str, description: str, target_type: str, target_name: str = "") -> dict[str, str]

{
    "category": "INFRAESTRUCTURA" | "HARDWARE" | "RED_CONECTIVIDAD" | "MOBILIARIO" | "BIENESTAR" | "OTRO",
    "priority": "CRITICA" | "ALTA" | "MEDIA" | "BAJA",
    "assigned_team": str,
    "suggested_action": str,
    "ai_source": "AI_MODEL" | "FALLBACK_RULES"
}

recommend_campus_allocation(user_query: str, available_spaces: list[Space], available_resources: list[Resource]) -> dict[str, Any]

{
    "recommended_space_id": Optional[str],
    "recommended_space_name": str,
    "recommended_resource_ids": list[str],
    "justification": str,
    "ai_source": "AI_MODEL" | "FALLBACK_RULES"
}