                      # Plan de Tareas Atómicas y Enrutamiento Agéntico (`specs/tasks.md`)

> **Instrucción para Agentes (Antigravity / Codex):** Ejecuta únicamente la tarea solicitada por el desarrollador, respeta estrictamente las firmas de `specs/design.md` y ejecuta el comando de verificación antes de marcarla como completada.

---

## FASE 1: Infraestructura, Modelos y Motor de Datos (Minuto 0 a Minuto 60)

- [x] **TASK-01 | Responsable: Juan José | [Modelo: Gemini Flash]**
  - **Objetivo:** Inicializar estructura de carpetas del proyecto, `.gitignore`, `.env.example`, `requirements.txt` y los archivos de paquete `__init__.py`.
  - **Archivos a crear:** `.gitignore`, `.env.example`, `requirements.txt`, `src/__init__.py`, `src/core/__init__.py`, `src/ui/__init__.py`.
  - **Criterio de Verificación:** Ejecutar en terminal `pip install -r requirements.txt` y comprobar que `.env` aparece ignorado con `git check-ignore -v .env`.

- [x] **TASK-02 | Responsable: Juan José | [Modelo: Claude]**
  - **Objetivo:** Implementar todas las `dataclasses` de dominio en `src/core/models.py` siguiendo exactamente el contrato de la Sección 2 de `specs/design.md`.
  - **Archivos a crear:** `src/core/models.py`.
  - **Criterio de Verificación:** Ejecutar `python -c "from src.core.models import Space, Resource, Reservation, Loan, Incident, ValidationResult, QuarantineRecord; print('Modelos OK')"` y verificar salida `'Modelos OK'`.

- [x] **TASK-03 | Responsable: Juan José | [Modelo: Claude]**
  - **Objetivo:** Implementar `src/core/validators.py` con las constantes configurables en la cabecera y las funciones `validate_space_reservation`, `validate_resource_loan` y `should_block_asset_on_incident` (Reglas RN-01, RN-02, RN-03 y RN-04).
  - **Archivos a crear:** `src/core/validators.py`.
  - **Criterio de Verificación:** Ejecutar `python -c "from src.core.validators import validate_space_reservation, OVERCAPACITY_FACTOR; print('Validadores listos, factor:', OVERCAPACITY_FACTOR)"`.

- [x] **TASK-04 | Responsable: Miguel | [Modelo: Claude]**
  - **Objetivo:** Construir `src/core/sanitizer.py` con mapeo flexible de columnas (español/inglés), normalización de estados en mayúsculas, captura de registros corruptos en `QuarantineRecord` (RN-05) y generador automático de dataset semilla en `data/raw/` (incluyendo registros válidos y 4 registros corruptos intencionales para la demostración).
  - **Archivos a crear:** `src/core/sanitizer.py`.
  - **Criterio de Verificación:** Ejecutar `python -c "from src.core.sanitizer import load_and_sanitize_raw_data; d = load_and_sanitize_raw_data(); print('Espacios:', len(d['spaces']), 'Cuarentena:', len(d['quarantine']))"` verificando que ambos sean mayores a 0.

- [x] **TASK-05 | Responsable: Andrés | [Modelo: Claude]**
  - **Objetivo:** Construir `src/core/ai_service.py` implementando `triage_incident` y `recommend_campus_allocation` conectando con Gemini API (`GEMINI_API_KEY`) u OpenAI (`OPENAI_API_KEY`) mediante salidas JSON estructuradas, más el motor determinista de Fallback por palabras clave si no hay internet o API Key.
  - **Archivos a crear:** `src/core/ai_service.py`.
  - **Criterio de Verificación:** Ejecutar `python -c "from src.core.ai_service import triage_incident; print(triage_incident('Corto circuito', 'Sale humo del tomacorriente del aula', 'ESPACIO', 'Aula Sputnik'))"` y comprobar que devuelve `"priority": "CRITICA"`.

---

## FASE 2: Repositorio Unificado e Interfaz Interactiva (Minuto 60 a Minuto 150)

- [x] **TASK-06 | Responsable: Miguel | [Modelo: Claude]**
  - **Objetivo:** Implementar `src/core/repository.py` con la clase `CampusRepository`, lectura/escritura atómica en `data/processed/campus_state.json`, integración con `validators.py` y ejecución automática del bloqueo/desbloqueo cruzado de la Regla RN-03 al crear o resolver incidencias.
  - **Archivos a crear:** `src/core/repository.py`.
  - **Criterio de Verificación:** Ejecutar prueba en consola creando una incidencia `CRITICA` sobre `"SP-101"` y verificar que `repo.get_space_by_id("SP-101").status == "EN_MANTENIMIENTO"`.

- [x] **TASK-07 | Responsable: Sebastián | [Modelo: Gemini Flash]**
  - **Objetivo:** Crear `app.py` con configuración de página panorámica (`layout="wide"`), inicialización de `CampusRepository` en `st.session_state`, barra superior de KPIs en tiempo real (Aulas Disponibles, Equipos Operativos, Incidencias Críticas Abiertas, Registros en Cuarentena) y navegación por 4 pestañas.
  - **Archivos a crear:** `app.py`.
  - **Criterio de Verificación:** Ejecutar `streamlit run app.py` y comprobar que carga el dashboard principal sin errores.

- [x] **TASK-08 | Responsable: Sebastián | [Modelo: Claude]**
  - **Objetivo:** Implementar `src/ui/views_spaces.py` (Módulo 1) con tabla filtrable de espacios, código de colores por estado, formulario de nueva reserva (conectado a `repo.create_reservation` mostrando `st.error` detallado cuando salte RN-01 o RN-04) y botón para liberar reservas activas.
  - **Archivos a crear:** `src/ui/views_spaces.py`.
  - **Criterio de Verificación:** En el navegador, intentar reservar un aula con más asistentes que su capacidad y verificar que aparece la alerta roja con el código `[RN-01]`.

- [x] **TASK-09 | Responsable: Sebastián | [Modelo: Claude]**
  - **Objetivo:** Implementar `src/ui/views_resources.py` (Módulo 2) con tabla de inventario tecnológico, formulario de préstamo validando cuota por usuario (`RN-02`), y sección de devolución con checkbox `"Reportar daño al devolver"` que dispara automáticamente una incidencia y pasa el equipo a mantenimiento.
  - **Archivos a crear:** `src/ui/views_resources.py`.
  - **Criterio de Verificación:** En el navegador, prestar 2 equipos al mismo documento de estudiante e intentar prestar un 3ro; comprobar que el sistema lo rechaza con `[RN-02]`.

- [x] **TASK-10 | Responsable: Andrés + Sebastián | [Modelo: Claude]**
  - **Objetivo:** Implementar `src/ui/views_incidents.py` (Módulo 3 + Asistente IA) con dos sub-secciones:
    1. **Triaje Inteligente de Incidencias:** Formulario en texto libre que llama a `triage_incident()`, muestra la clasificación de la IA, guarda la incidencia y alerta en pantalla si bloqueó automáticamente el salón o recurso (`RN-03`), más botón para marcar incidencias como `RESUELTA`.
    2. **Recomendador Inteligente de Asignación IA:** Cuadro de texto donde el usuario describe qué necesita y la IA le recomienda el aula y los recursos disponibles libres de conflicto.
  - **Archivos a crear:** `src/ui/views_incidents.py`.
  - **Criterio de Verificación:** Reportar una incidencia grave en un aula disponible, ver la respuesta de la IA y verificar en la pestaña de Espacios que el aula pasó a `EN_MANTENIMIENTO`.

- [x] **TASK-11 | Responsable: Miguel + Sebastián | [Modelo: Gemini Flash]**
  - **Objetivo:** Implementar `src/ui/views_audit.py` mostrando la tabla de registros aislados en **Cuarentena de Datos (`RN-05`)** con su motivo de rechazo, el visor del JSON persistido en tiempo real y el botón para recargar los archivos de `data/raw/`.
  - **Archivos a crear:** `src/ui/views_audit.py`.
  - **Criterio de Verificación:** Abrir la pestaña de Auditoría y verificar que se listan los registros corruptos aislados sin afectar la aplicación.

---

## FASE 3: Pruebas Automatizadas, Documentación y Simulacro (Minuto 150 a Minuto 240)

- [x] **TASK-12 | Responsable: Miguel | [Modelo: GPT]**
  - **Objetivo:** Crear la suite de pruebas unitarias `tests/test_business_rules.py` probando casos válidos e inválidos de las 5 reglas de negocio (`RN-01` a `RN-05`), incluyendo bloqueo y desbloqueo automático por incidencia crítica.
  - **Archivos a crear:** `tests/test_business_rules.py`.
  - **Criterio de Verificación:** Ejecutar `pytest -v` en terminal y obtener 100% de tests aprobados (`PASSED`).

- [x] **TASK-13 | Responsable: Juan José + Andrés | [Modelo: GPT]**
  - **Objetivo:** Redactar el `README.md` de alto impacto orientado a la rúbrica oficial (Problema, Integrantes y Roles, Arquitectura Limpia, Tabla de las 5 Reglas de Negocio, Rol Estratégico de la IA + Fallback, Guía de Instalación Reproducible y Cómo Ejecutar los Tests).
  - **Archivos a crear:** `README.md`.
  - **Criterio de Verificación:** Auditar el repositorio ejecutando `git status` y `git log -p` para confirmar que no hay archivos `.env` ni claves expuestas.

- [x] **TASK-14 | Responsable: Todo el Equipo | Simulacro de Sustentación**
  - **Objetivo:** Practicar 3 ejercicios de modificación en vivo sobre `src/core/validators.py` cronometrando menos de 2 minutos:
    1. Cambiar el máximo de préstamos por usuario de 2 a 1 (`MAX_ACTIVE_LOANS_PER_USER = 1`).
    2. Permitir que solo los `TRAINER` puedan reservar `AUDITORIO`.
    3. Hacer que las incidencias de prioridad `MEDIA` también bloqueen preventivamente los recursos (`BLOCKING_PRIORITIES = {"CRITICA", "ALTA", "MEDIA"}`).