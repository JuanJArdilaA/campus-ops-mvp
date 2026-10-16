# Especificación de Requisitos de Software (`specs/requirements.md`)

## 1. Historias de Usuario Principales (User Stories)
- **HU-01 (Coordinador Académico):** Como coordinador, quiero consultar y reservar aulas o cubículos verificando automáticamente el aforo y los cruces de horario, para evitar que dos grupos de campers lleguen al mismo salón a la misma hora.
- **HU-02 (Encargado de Inventario TIC):** Como encargado de recursos, quiero registrar préstamos y devoluciones de equipos validando cuántos equipos tiene prestados cada camper y el estado físico del activo, para evitar pérdidas y préstamos de equipos dañados.
- **HU-03 (Camper / Trainer):** Como miembro de la comunidad, quiero reportar un incidente en lenguaje natural para que la IA lo clasifique, asigne prioridad, lo envíe al área técnica correcta y bloquee automáticamente el salón o equipo si el fallo es grave.
- **HU-04 (Líder Operativo del Campus):** Como líder operativo, quiero describir una necesidad compleja en texto libre (ej. taller para 25 personas con equipos adicionales) y recibir una recomendación inteligente de asignación basada en los espacios y equipos realmente disponibles.
- **HU-05 (Auditor Técnico / Jurado):** Como evaluador, quiero ver qué registros del dataset inicial venían corruptos, por qué fueron aislados en cuarentena y comprobar que el sistema persiste cada operación sin caerse.

---

## 2. Requisitos Funcionales (Sintaxis EARS)

### Módulo 0: Ingesta, Saneamiento y Persistencia de Datos
- **RF-01 (Detección y carga multiformato):** *When* el sistema se inicializa por primera vez o se ejecuta la acción de recarga desde el origen, *the system shall* detectar y leer los archivos oficiales (`.json` o `.csv`) ubicados en `data/raw/`.
- **RF-02 (Normalización de textos y estados):** *When* un registro de entrada contenga estados con minúsculas, espacios adicionales o tildes (ej. `" disponible "`, `"Crítica"`), *the system shall* normalizarlos al formato estándar en mayúsculas sin tildes antes de validarlos.
- **RF-03 (Aislamiento en cuarentena - RN-05):** *When* un registro de entrada carezca de `id` único, tenga un `id` duplicado, posea capacidad menor o igual a 0, o incumpla los tipos de datos requeridos, *the system shall* agregar el registro a la colección `quarantine` con el motivo exacto del fallo y continuar procesando los demás registros.
- **RF-04 (Validación de integridad referencial en carga):** *When* una reserva, préstamo o incidencia inicial haga referencia a un `space_id` o `resource_id` inexistente en el catálogo válido, *the system shall* enviar dicho registro a `quarantine` indicando `"Referencia huérfana: ID de activo no existe"`.
- **RF-05 (Persistencia atómica en disco):** *When* cualquier operación de reserva, préstamo, devolución o incidencia sea aprobada por los validadores, *the system shall* persistir inmediatamente el estado actualizado en `data/processed/campus_state.json`.
- **RF-06 (Restauración controlada del dataset):** *When* el usuario pulse el botón `"Restaurar y Re-procesar Dataset Original"` en la vista de auditoría, *the system shall* reconstruir `campus_state.json` desde `data/raw/` conservando la trazabilidad de cuarentena.

### Módulo 1: Disponibilidad y Asignación de Espacios
- **RF-07 (Catálogo interactivo de espacios):** *When* el usuario abra la pestaña de Espacios, *the system shall* mostrar todos los espacios registrados con filtros por tipo (`AULA`, `CUBICULO`, `LABORATORIO`, `AUDITORIO`), estado actual y capacidad mínima.
- **RF-08 (Creación de reserva válida):** *When* el usuario envíe el formulario de reserva de espacio cumpliendo todas las reglas de negocio, *the system shall* crear un registro `Reservation` con estado `ACTIVA`, guardarlo en persistencia y mostrar confirmación visual con el ID generado.
- **RF-09 (Rechazo por espacio no disponible - RN-01a):** *When* se intente reservar un espacio cuyo estado sea `EN_MANTENIMIENTO` o `INHABILITADO`, *the system shall* rechazar la solicitud mostrando el estado actual y el ID de la incidencia que lo mantiene bloqueado.
- **RF-10 (Rechazo por exceso de aforo - RN-01b):** *When* el número de asistentes ingresados supere el límite ` int(space.capacity * OVERCAPACITY_FACTOR) `, *the system shall* impedir la reserva e informar la capacidad máxima permitida del espacio.
- **RF-11 (Rechazo por solapamiento horario - RN-01c):** *When* una nueva reserva para un mismo `space_id` y `date` cumpla la condición de cruce `(new_start < existing_end) and (new_end > existing_start)` frente a cualquier reserva `ACTIVA`, *the system shall* bloquear el registro y mostrar los datos de la reserva en conflicto (responsable y horario).
- **RF-12 (Rechazo por ventana horaria o duración inválida - RN-04):** *When* la hora de inicio sea anterior a `CAMPUS_OPEN_HOUR`, la hora de fin supere `CAMPUS_CLOSE_HOUR`, la hora de fin sea menor o igual a la de inicio, o la duración exceda `MAX_RESERVATION_HOURS`, *the system shall* rechazar la reserva explicando el límite horario violado.
- **RF-13 (Cancelación y finalización de reservas):** *When* el usuario seleccione una reserva `ACTIVA` y ejecute `"Finalizar / Cancelar Reserva"`, *the system shall* cambiar el estado de la reserva a `FINALIZADA` o `CANCELADA` liberando inmediatamente ese bloque horario.

### Módulo 2: Préstamo y Control de Recursos Tecnológicos
- **RF-14 (Inventario filtrable de recursos):** *When* el usuario acceda a la pestaña de Recursos Tecnológicos, *the system shall* listar todos los equipos mostrando su ID, nombre, categoría, ubicación base, estado actual y el nombre del prestatario si se encuentra `PRESTADO`.
- **RF-15 (Registro de préstamo válido):** *When* se solicite un préstamo para un recurso en estado `OPERATIVO` y el solicitante cumpla la cuota permitida, *the system shall* crear un registro `Loan` con estado `ACTIVO` y cambiar el estado del recurso a `PRESTADO`.
- **RF-16 (Rechazo por recurso no operativo o ya prestado - RN-02a):** *When* se intente prestar un recurso cuyo estado sea `PRESTADO`, `EN_MANTENIMIENTO` o `DADO_DE_BAJA`, *the system shall* bloquear el préstamo e informar el motivo exacto.
- **RF-17 (Rechazo por límite de préstamos simultáneos - RN-02b):** *When* un usuario (`borrower_id`) que ya acumula `MAX_ACTIVE_LOANS_PER_USER` préstamos en estado `ACTIVO` intente solicitar un equipo adicional, *the system shall* denegar la operación listando los IDs de los equipos que debe devolver primero.
- **RF-18 (Devolución sana de recurso):** *When* se registre la devolución de un préstamo `ACTIVO` indicando que el equipo se entrega sin daños, *the system shall* marcar el préstamo como `DEVUELTO`, registrar la hora de entrega y pasar el recurso a estado `OPERATIVO`.
- **RF-19 (Devolución con daño y disparo automático de incidencia):** *When* se registre la devolución de un préstamo marcando la casilla `"Equipo devuelto con novedad/daño"` y describiendo el fallo, *the system shall* cerrar el préstamo, cambiar el recurso a `EN_MANTENIMIENTO` y crear automáticamente una incidencia técnica vinculada a ese `resource_id`.

### Módulo 3: Gestión y Triaje Inteligente de Incidencias con IA
- **RF-20 (Análisis y triaje automatizado con IA):** *When* un usuario ingrese el reporte de una incidencia en texto libre, *the system shall* enviar el contexto al módulo de IA (`ai_service.py`) y obtener automáticamente: `category`, `priority` (`CRITICA`, `ALTA`, `MEDIA`, `BAJA`), `assigned_team`, `suggested_action` y `confidence_source` (`"AI_MODEL"` o `"FALLBACK_RULES"`).
- **RF-21 (Bloqueo preventivo cruzado automático - RN-03):** *When* se confirme el registro de una incidencia cuya prioridad sea `CRITICA` o `ALTA` (o esté dentro de `BLOCKING_PRIORITIES`) y esté asociada a un `space_id` o `resource_id`, *the system shall* actualizar inmediatamente el estado de ese espacio o recurso a `EN_MANTENIMIENTO`.
- **RF-22 (Resolución de incidencia y desbloqueo inteligente):** *When* un operador cambie el estado de una incidencia a `RESUELTA`, *the system shall* verificar si el espacio o recurso afectado tiene otras incidencias abiertas con prioridad bloqueante; si no tiene ninguna, restaurará automáticamente su estado a `DISPONIBLE` (espacio) u `OPERATIVO` (recurso).
- **RF-23 (Asistente IA de Recomendación Operativa Integrada):** *When* el usuario utilice el recomendador inteligente escribiendo un requerimiento operativo (ej. *"Necesito un salón para 20 personas hoy de 14:00 a 16:00 y 2 proyectores disponibles"*), *the system shall* filtrar los espacios y recursos realmente libres en ese horario y usar la IA para proponer el paquete exacto de asignación listo para reservar.
- **RF-24 (Conmutación transparente a Fallback Determinista):** *When* la API de IA arroje error de red, falta de API Key o timeout, *the system shall* clasificar la incidencia o generar la recomendación usando el motor determinista de palabras clave y reglas locales, mostrando un aviso informativo sin interrumpir la operación.

---

## 3. Requisitos No Funcionales (20 RNF con Criterios de Verificación)

| Código | Categoría | Especificación Técnica y Métrica Verificable |
| :--- | :--- | :--- |
| **RNF-01** | Seguridad Git | Cero credenciales en código. `.env` excluido en `.gitignore`. Verificable con `git grep -i "AIza"` o `"sk-"` retornando vacío. |
| **RNF-02** | Integridad IA | Prohibido el hardcoding de respuestas. Toda salida de IA debe provenir de inferencia real sobre el prompt + estado actual del JSON, o del algoritmo analizador de tokens en modo fallback. |
| **RNF-03** | Mantenibilidad en Vivo | Modificación de cualquier regla de negocio en menos de 90 segundos editando únicamente constantes o predicados aislados en `src/core/validators.py`. |
| **RNF-04** | Arquitectura | Separación estricta en 3 capas (`ui`, `core/validators`, `core/repository`). `src/core/` tiene 0 dependencias hacia `streamlit`. |
| **RNF-05** | Resiliencia de Datos | El cargador inicial soporta archivos con hasta 100% de filas corruptas sin lanzar excepciones no controladas, poblando la tabla de cuarentena. |
| **RNF-06** | Rendimiento Local | Toda validación en `validators.py` y lectura/escritura en `repository.py` debe completarse en menos de 150 ms para datasets de hasta 5,000 registros. |
| **RNF-07** | Latencia y Timeout IA | Llamadas al cliente de IA configuradas con `timeout=8.0` segundos máximo antes de disparar el motor de Fallback. |
| **RNF-08** | Contrato JSON IA | La respuesta del LLM se valida contra las claves obligatorias (`category`, `priority`, `assigned_team`, `suggested_action`); si falta alguna clave, se sanea por defecto. |
| **RNF-09** | Usabilidad (UX/UI) | Cada formulario en Streamlit limpia o informa su estado tras el envío, usando `st.spinner` en procesos de IA, `st.error` con ícono de alerta en rechazos de negocio y `st.success` en transacciones válidas. |
| **RNF-10** | Portabilidad | Instalación reproducible con máximo 4 librerías externas en `requirements.txt` (`streamlit`, `google-genai`, `python-dotenv`, `pytest`). |
| **RNF-11** | Integridad Referencial | Ninguna entidad hija (`Reservation`, `Loan`, `Incident`) puede guardarse con un ID de espacio o recurso inexistente en el diccionario maestro. |
| **RNF-12** | Atomicidad en Disco | La función `save_state()` escribe primero en `campus_state.tmp.json` y ejecuta `os.replace()` hacia `campus_state.json` para evitar archivos corruptos si se cierra el proceso. |
| **RNF-13** | Estándar de Tipado | El 100% de las funciones en `src/core/` cuentan con anotaciones de tipo (`Type Hints`) en parámetros y retorno. |
| **RNF-14** | Historial Git Limpio | Commits atómicos semánticos (`feat:`, `fix:`, `docs:`, `test:`) distribuidos entre las cuentas o autores de los 4 integrantes del equipo. |
| **RNF-15** | Privacidad | Los prompts enviados a la API de IA solo incluyen metadatos técnicos de aulas, equipos y descripciones de incidentes, omitiendo datos personales sensibles. |
| **RNF-16** | Idempotencia de Sesión | Si `data/processed/campus_state.json` ya existe, el arranque de la aplicación carga dicho estado persistido sin sobrescribirlo con `data/raw/`. |
| **RNF-17** | Manejo de Excepciones UI | Captura global de errores inesperados en `app.py` para mostrar mensajes amigables en lugar de pantallas de traceback de Python. |
| **RNF-18** | Cobertura de Pruebas | Suite `tests/test_business_rules.py` con al menos 10 pruebas unitarias (5 casos válidos y 5 casos inválidos cubriendo RN-01 a RN-05). |
| **RNF-19** | Trazabilidad de Auditoría | Cada cambio automático de estado por IA (RN-03) registra en las notas del activo el ID de la incidencia y la marca temporal ISO-8601. |
| **RNF-20** | Multiplataforma | Uso exclusivo de `pathlib.Path` y codificación `encoding="utf-8"` explícita en todos los `open()` para evitar fallos en Windows (CP1252) y Linux. |