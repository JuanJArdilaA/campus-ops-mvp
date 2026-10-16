# AGENTS.md — Fuente Única de Verdad (KDD)
## Proyecto: Sistema Central de Gestión Operativa de Campuslands (MVP)

### 1. Visión y Propósito del Sistema
Este proyecto es un Producto Mínimo Viable (MVP) de misión crítica construido 100% en Python para gestionar la operación diaria de Campuslands bajo alta demanda. 
El sistema unifica tres dominios operativos en un solo flujo transaccional asistido por Inteligencia Artificial:
1. **Módulo 1 (Espacios):** Disponibilidad, reserva y liberación de aulas, salas y cubículos sin solapamientos horarios ni sobrecupo.
2. **Módulo 2 (Recursos Tecnológicos):** Préstamo, devolución y trazabilidad de estado de equipos (portátiles, proyectores, kits de robótica, cables, etc.).
3. **Módulo 3 (Incidencias y Triaje IA):** Recepción de reportes en lenguaje natural, clasificación automatizada mediante IA (Categoría, Prioridad, Área Responsable, Plan de Acción) y **bloqueo preventivo cruzado** de espacios o recursos cuando una incidencia es de prioridad `CRITICA` o `ALTA`.

### 2. Stack Tecnológico Innegociable
- **Lenguaje Base:** Python 3.11+ (Tipado estricto con `typing` y `dataclasses`).
- **Interfaz de Usuario (Frontend/UI):** `streamlit` >= 1.38.0 (Ejecución multipágina mediante pestañas y control de estado con `st.session_state`).
- **Integración de IA:** SDK oficial `google-genai` (modelo `gemini-2.5-flash`) o `openai` (`gpt-4o-mini`), con salidas JSON estructuradas y motor de respaldo local determinista (*Fallback*) en caso de caída de red o falta de cuota.
- **Gestión de Configuración y Seguridad:** `python-dotenv` leyendo exclusivamente desde `.env`.
- **Persistencia de Datos:** Almacenamiento transaccional en JSON (`data/processed/campus_state.json`) con escritura atómica (archivo temporal + reemplazo) y lectura inicial desde datasets crudos (`data/raw/`).
- **Testing:** `pytest` para validación automatizada de las reglas de negocio.

### 3. Arquitectura de Directorios y Propiedad por Desarrollador
Para evitar conflictos de `git merge` durante las 4 horas, cada archivo tiene un propietario único:

```text
campus-ops-mvp/
├── AGENTS.md                         # [Juan José] Fuente única de verdad KDD
├── CLAUDE.md                         # [Juan José] Puente hacia AGENTS.md
├── GEMINI.md                         # [Juan José] Puente hacia AGENTS.md
├── README.md                         # [Juan José + Andrés] Documentación oficial de evaluación
├── requirements.txt                  # [Juan José] Dependencias del entorno
├── .env.example                      # [Andrés] Plantilla de variables de entorno sin claves reales
├── .gitignore                        # [Juan José] Bloqueo estricto de .env, __pycache__, .venv
├── app.py                            # [Sebastián] Punto de entrada Streamlit y layout global
├── knowledge/
│   └── campus_domain.md              # [Juan José] Diccionario de dominio, estados y reglas
├── specs/
│   ├── requirements.md               # [Equipo] Historias de usuario, 24 RF (EARS) y 20 RNF
│   ├── design.md                     # [Juan José] Contratos de funciones, modelos y JSON schema
│   └── tasks.md                      # [Equipo] Checklist atómico con enrutamiento de modelos
├── data/
│   ├── raw/                          # [Miguel] Archivos originales entregados por Campuslands (SOLO LECTURA)
│   └── processed/
│       └── campus_state.json         # [Miguel] Base de datos unificada persistente y cuarentena
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                 # [Juan José] Dataclasses, Enums y tipos de retorno
│   │   ├── validators.py             # [Juan José] Reglas de negocio (RN-01 a RN-05) y constantes en vivo
│   │   ├── sanitizer.py              # [Miguel] Ingesta tolerante a fallos y cuarentena de datos sucios
│   │   ├── repository.py             # [Miguel] Operaciones CRUD y persistencia atómica sobre campus_state.json
│   │   └── ai_service.py             # [Andrés] Cliente IA (Triaje + Recomendador) con Fallback local
│   └── ui/
│       ├── __init__.py
│       ├── views_spaces.py           # [Sebastián] Vista interactiva del Módulo 1 (Espacios)
│       ├── views_resources.py        # [Sebastián] Vista interactiva del Módulo 2 (Recursos)
│       ├── views_incidents.py        # [Sebastián + Andrés] Vista del Módulo 3 (Incidencias + IA)
│       └── views_audit.py            # [Sebastián + Miguel] Vista de Cuarentena de Datos y Estado Global
└── tests/
    └── test_business_rules.py        # [Miguel] Pruebas unitarias de casos válidos e inválidos