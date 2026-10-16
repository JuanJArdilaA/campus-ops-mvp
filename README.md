# 🏫 Sistema Central de Gestión Operativa de Campuslands (MVP)

Sistema transaccional unificado de misión crítica construido en **Python 3.11+ y Streamlit** bajo metodología **KDD (Knowledge-Driven Development)** y **SDD (Spec-Driven Development)** para coordinar la operación diaria de **Campuslands** bajo alta demanda.

---

## 1. Problema y Propósito del Sistema

En la operación diaria de un centro de entrenamiento intensivo como Campuslands, la gestión desarticulada de salones, préstamos de equipos tecnológicos y reportes de mantenimiento genera tres riesgos críticos:
1. **Cruces de horario y sobrecupo** en aulas, laboratorios, cubículos y auditorios.
2. **Pérdida de trazabilidad y acaparamiento de inventario TIC** (portátiles, proyectores, kits de robótica) o préstamo accidental de equipos averiados.
3. **Desconexión entre reportes de incidentes y disponibilidad real:** un salón con riesgo eléctrico o un equipo dañado sigue apareciendo como reservable si el reporte no bloquea preventivamente el activo.

Este MVP resuelve el problema unificando los **tres dominios operativos** en un único flujo transaccional respaldado por **Inteligencia Artificial (Google Gemini `gemini-2.5-flash`)** con **Fallback Determinista Local** y **Persistencia Atómica JSON**:
- **Módulo 1 (Espacios):** Catálogo filtrable, validación de aforo/horario, reserva y liberación de aulas, laboratorios, cubículos y auditorio.
- **Módulo 2 (Recursos Tecnológicos):** Control de préstamos por cuota de usuario, devolución sana y devolución con daño (que dispara automáticamente una incidencia técnica y envía el equipo a mantenimiento).
- **Módulo 3 (Incidencias, Triaje IA y Recomendador Operativo):** Clasificación automática de reportes en lenguaje natural (Categoría, Prioridad, Área Responsable y Plan de Acción), **Bloqueo/Desbloqueo Preventivo Cruzado (`RN-03`)** y recomendador inteligente de asignación de espacios + equipos.
- **Módulo de Auditoría y Cuarentena (`RN-05`):** Ingesta resiliente desde `data/raw/` que normaliza textos/estados y aísla registros corruptos en cuarentena sin detener el sistema.

---

## 2. Integrantes del Equipo y Roles

| Integrante | Rol Principal | Módulos y Archivos de Propiedad |
| :--- | :--- | :--- |
| **Juan José Ardila** | Arquitecto KDD/SDD & Reglas de Dominio | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `knowledge/campus_domain.md`, `specs/design.md`, `src/core/models.py`, `src/core/validators.py`, `README.md` |
| **Miguel Calderón** | Ingeniería de Datos, Persistencia & QA | `src/core/sanitizer.py`, `src/core/repository.py`, `data/raw/`, `data/processed/campus_state.json`, `tests/test_business_rules.py`, `src/ui/views_audit.py` |
| **Andrés Vásquez** | Integración de IA, Prompting & Fallback | `src/core/ai_service.py`, `.env.example`, `src/ui/views_incidents.py`, `README.md` |
| **Sebastián** | Frontend/UI en Streamlit & UX Operativa | `app.py`, `src/ui/_shared.py`, `src/ui/views_spaces.py`, `src/ui/views_resources.py`, `src/ui/views_incidents.py`, `src/ui/views_audit.py` |

---

## 3. Arquitectura Limpia y Estructura del Proyecto

El sistema implementa una separación estricta en **3 capas** (`RNF-04`), garantizando que `src/core/` tenga **cero dependencias hacia Streamlit** y pueda probarse o modificarse de forma aislada:

```text
[Usuario / Jurado]
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CAPA DE PRESENTACIÓN (Streamlit UI)                                     │
│ app.py -> views_spaces.py | views_resources.py | views_incidents.py     │
│           views_audit.py  | _shared.py                                  │
└──────┬───────────────────────────────┬───────────────────────┬──────────┘
       │ 1. Valida reglas              │ 2. Clasifica / Sugiere│ 3. Persiste estado
       ▼                               ▼                       ▼
┌──────────────────────┐   ┌───────────────────────┐   ┌──────────────────────┐
│ VALIDATORS           │   │ AI SERVICE            │   │ REPOSITORY           │
│ src/core/validators  │   │ src/core/ai_service   │   │ src/core/repository  │
│ RN-01 a RN-04        │   │ Gemini API + Fallback │   │ CRUD + Regla RN-03   │
└──────────────────────┘   └───────────────────────┘   └──────────┬───────────┘
                                                                  │
                                                                  ▼
                                                       ┌──────────────────────┐
                                                       │ SANITIZER (RN-05)    │
                                                       │ data/raw -> JSON     │
                                                       └──────────────────────┘
```

### Estructura de Directorios
```text
campus-ops-mvp/
├── AGENTS.md                         # Fuente única de verdad (KDD)
├── CLAUDE.md / GEMINI.md             # Puentes de contexto agéntico hacia AGENTS.md
├── README.md                         # Documentación oficial de evaluación
├── requirements.txt                  # 4 dependencias base (streamlit, google-genai, python-dotenv, pytest)
├── .env.example                      # Plantilla segura de variables de entorno
├── .gitignore                        # Protección estricta de .env, .venv y archivos temporales
├── app.py                            # Punto de entrada Streamlit con KPIs en tiempo real
├── knowledge/
│   └── campus_domain.md              # Máquina de estados, diccionario de dominio y casos borde
├── specs/
│   ├── requirements.md               # 5 Historias de Usuario, 24 RF (EARS) y 20 RNF
│   ├── design.md                     # Contratos de dataclasses, validadores, IA y JSON schema
│   └── tasks.md                      # Plan de 14 tareas atómicas verificables
├── data/
│   ├── raw/                          # Datasets iniciales crudos (incluye casos corruptos semilla)
│   └── processed/
│       └── campus_state.json         # Estado transaccional persistido atómicamente
├── src/
│   ├── core/
│   │   ├── models.py                 # Dataclasses y Enums de dominio con tipado estricto
│   │   ├── validators.py             # Constantes configurables en vivo y reglas RN-01 a RN-04
│   │   ├── sanitizer.py              # Ingesta tolerante a fallos y cuarentena RN-05
│   │   ├── repository.py             # CampusRepository con escritura atómica (.tmp + os.replace)
│   │   └── ai_service.py             # Cliente Gemini JSON estructurado + Fallback determinista
│   └── ui/
│       ├── _shared.py                # Adaptadores desacoplados entre UI y repositorio
│       ├── views_spaces.py           # Vista Módulo 1: Espacios y Reservas
│       ├── views_resources.py        # Vista Módulo 2: Recursos, Préstamos y Devoluciones
│       ├── views_incidents.py        # Vista Módulo 3: Triaje IA, Bloqueo RN-03 y Recomendador
│       └── views_audit.py            # Vista de Auditoría: Cuarentena RN-05 y visor JSON
└── tests/
    └── test_business_rules.py        # Suite de 15 pruebas unitarias automatizadas con pytest
```

---

## 4. Tabla de las 5 Reglas de Negocio Oficiales (`RN-01` a `RN-05`)

Todas las constantes de negocio están centralizadas en la cabecera de `src/core/validators.py` para permitir **modificaciones en vivo en menos de 90 segundos (`RNF-03`)**:

| Código | Regla de Negocio | Especificación Técnica y Validación | Constantes en `src/core/validators.py` |
| :--- | :--- | :--- | :--- |
| **RN-01** | **Aforo, Disponibilidad y Anti-Solapamiento** | Un espacio solo puede reservarse si su estado es `DISPONIBLE`, los asistentes no superan `int(space.capacity * OVERCAPACITY_FACTOR)` y no existe cruce `(new_start < existing_end) and (new_end > existing_start)` con otra reserva `ACTIVA` en la misma fecha. | `OVERCAPACITY_FACTOR = 1.0`<br>`AUDITORIO_ALLOWED_ROLES` |
| **RN-02** | **Control de Préstamos y Cuota por Usuario** | Un recurso solo puede prestarse si está `OPERATIVO` y el solicitante (`borrower_id`) tiene menos de `MAX_ACTIVE_LOANS_PER_USER` préstamos en estado `ACTIVO`. | `MAX_ACTIVE_LOANS_PER_USER = 2` |
| **RN-03** | **Bloqueo y Desbloqueo Preventivo Cruzado** | Toda incidencia con prioridad dentro de `BLOCKING_PRIORITIES` (`CRITICA`, `ALTA`) vinculada a un espacio o recurso cambia inmediatamente su estado a `EN_MANTENIMIENTO`. Al marcarse `RESUELTA`, si el activo no tiene otras incidencias bloqueantes abiertas, vuelve automáticamente a `DISPONIBLE` u `OPERATIVO`. | `BLOCKING_PRIORITIES = {"CRITICA", "ALTA"}` |
| **RN-04** | **Ventana Horaria y Duración de Reserva** | Las reservas solo son válidas dentro del horario `[CAMPUS_OPEN_TIME, CAMPUS_CLOSE_TIME]` (`06:00` a `21:30`), con `end_time > start_time` y duración entre `MIN_RESERVATION_MINUTES` (30 min) y `MAX_RESERVATION_HOURS` (4.0 h). | `CAMPUS_OPEN_TIME = "06:00"`<br>`CAMPUS_CLOSE_TIME = "21:30"`<br>`MAX_RESERVATION_HOURS = 4.0`<br>`MIN_RESERVATION_MINUTES = 30` |
| **RN-05** | **Cuarentena de Datos de Origen** | Todo registro en `data/raw/` con ID vacío/duplicado, capacidad `<= 0`, estado irreconocible o referencia huérfana es aislado en `quarantine` (`QuarantineRecord`) con el motivo exacto del fallo sin interrumpir la carga. | Implementado en `src/core/sanitizer.py` |

---

## 5. Rol Estratégico de la IA y Motor de Fallback Determinista

El módulo `src/core/ai_service.py` integra Inteligencia Artificial donde aporta valor real sobre texto no estructurado, manteniendo **disponibilidad del 100%** mediante su motor de respaldo:

1. **Triaje Automatizado de Incidencias (`triage_incident` - `RF-20`):**
   - Recibe el título, descripción en lenguaje natural y activo afectado.
   - Solicita a **Google Gemini (`gemini-2.5-flash`)** una salida estrictamente tipada con `response_schema` JSON (`category`, `priority`, `assigned_team`, `suggested_action`).
   - El resultado alimenta directamente la **Regla `RN-03`**, disparando el bloqueo preventivo del salón o recurso cuando la prioridad inferida es `CRITICA` o `ALTA`.
2. **Recomendador Operativo Inteligente (`recommend_campus_allocation` - `RF-23`):**
   - Recibe una necesidad compleja en texto libre (ej. *"Necesito un salón para 20 personas con videobeam y 2 portátiles"*).
   - Cruza el requerimiento **únicamente contra los espacios `DISPONIBLE` y recursos `OPERATIVO`** del estado actual, evitando alucinaciones de IDs inexistentes o activos en mantenimiento.
3. **Conmutación Transparente a Fallback (`FALLBACK_RULES` - `RF-24`):**
   - Si no existe archivo `.env`, la clave `GEMINI_API_KEY` está vacía, no hay conexión a internet o la API excede cuota, el sistema conmuta automáticamente al analizador determinista de palabras clave y ranking de capacidad sin lanzar errores ni detener la operación, informando en la UI el origen `FALLBACK_RULES`.

---

## 6. Guía de Instalación Reproducible y Ejecución

### Prerrequisitos
- **Python 3.11+**
- **Git**

### Paso 1: Clonar el repositorio y crear el entorno virtual
```bash
git clone https://github.com/JuanJArdilaA/campus-ops-mvp.git
cd campus-ops-mvp
python3 -m venv .venv
source .venv/bin/activate
```

### Paso 2: Instalar dependencias oficiales
```bash
pip install -r requirements.txt
```

### Paso 3: Configurar variables de entorno (Opcional para IA en la nube)
```bash
cp .env.example .env
# Edita .env y coloca tu GEMINI_API_KEY real sin comillas.
# Si se omite o no hay red, el sistema operará automáticamente con FALLBACK_RULES.
```

### Paso 4: Iniciar la aplicación interactiva en Streamlit
```bash
streamlit run app.py
```

---

## 7. Ejecución de Pruebas Automatizadas y Verificación de Seguridad

### Ejecutar la suite de pruebas unitarias (`pytest`)
La suite `tests/test_business_rules.py` incluye **15 pruebas unitarias** que verifican casos válidos e inválidos de las reglas `RN-01` a `RN-05`, devolución con daño (`RF-19`) y contratos del servicio de IA:

```bash
pytest -v
```

### Auditoría de seguridad Git (`RNF-01`)
```bash
# Comprobar que .env está bloqueado por .gitignore
git check-ignore -v .env

# Verificar ausencia total de claves expuestas en el historial
git grep -i "AIza"
```

