# Conocimiento de Dominio: Operación Campuslands (`knowledge/campus_domain.md`)

## 1. Máquina de Estados del Dominio

### 1.1 Estados de un Espacio (`SpaceStatus`)
- `DISPONIBLE`: Puede recibir reservas si el horario no se cruza y el aforo es válido.
- `OCUPADO`: Estado informativo cuando existe una reserva en curso en la hora actual.
- `EN_MANTENIMIENTO`: Inhabilitado para cualquier nueva reserva. Se activa manualmente o automáticamente por la **Regla RN-03** cuando se reporta una incidencia `CRITICA` o `ALTA` vinculada al espacio.
- `INHABILITADO`: Cerrado por disposición administrativa.

### 1.2 Estados de un Recurso Tecnológico (`ResourceStatus`)
- `OPERATIVO`: Disponible para ser prestado a un camper o trainer.
- `PRESTADO`: Actualmente en posesión de un usuario con un préstamo `ACTIVO`. No puede prestarse a otra persona hasta su devolución.
- `EN_MANTENIMIENTO`: Bloqueado para préstamos. Se activa automáticamente si se devuelve con reporte de daño o si recibe una incidencia `CRITICA` / `ALTA` (**Regla RN-03**).
- `DADO_DE_BAJA`: Equipo retirado definitivamente del inventario activo.

### 1.3 Estados y Prioridades de una Incidencia (`Incident`)
- **Prioridades (`IncidentPriority`):**
  - `CRITICA`: Riesgo eléctrico, caída total de red en un salón, daño severo de equipo, goteras sobre equipos o riesgo físico. **Dispara bloqueo automático RN-03.**
  - `ALTA`: Equipo principal no enciende, aire acondicionado dañado en aula llena, proyector averiado. **Dispara bloqueo automático RN-03.**
  - `MEDIA`: Faltan marcadores, silla desajustada, lentitud intermitente de red. No bloquea el espacio completo.
  - `BAJA`: Sugerencia estética, limpieza menor o solicitud informativa.
- **Categorías (`IncidentCategory`):** `INFRAESTRUCTURA`, `HARDWARE`, `RED_CONECTIVIDAD`, `MOBILIARIO`, `BIENESTAR`, `OTRO`.
- **Estados (`IncidentStatus`):** `ABIERTA`, `EN_PROCESO`, `RESUELTA`.

## 2. Catálogo de Casos Borde Esperados en los Datos Crudos (`data/raw/`)
En las hackatones de Campuslands, el dataset inicial suele incluir "trampas de datos sucios" para evaluar la resiliencia del sistema:
1. **IDs duplicados o vacíos:** Ej. dos aulas con `id: "SP-01"` o un recurso con `id: ""` o `null`.
2. **Capacidades absurdas o tipos mezclados:** Ej. `capacity: -15`, `capacity: 0`, `capacity: "treinta"`, o `capacity: 99999`.
3. **Fechas y horas invertidas o fuera de rango:** Ej. reservas con `start_time: "14:00"` y `end_time: "10:00"`, o formatos como `"25:99"`.
4. **Estados no reconocidos o en minúsculas/con tildes:** Ej. `"disponible"`, `"Averiado"`, `"Crítica"`, `"DESCONOCIDO"`. El `sanitizer.py` debe normalizar variantes conocidas (ej. `"Crítica" -> "CRITICA"`) y enviar a cuarentena los valores irrecuperables.
5. **Referencias huérfanas:** Reservas o incidencias en el archivo inicial que apuntan a un `space_id` o `resource_id` que no existe en el catálogo maestro.

## 3. Reglas de Negocio Oficiales del Sistema
- **RN-01 (Aforo y Anti-Solapamiento):** Ninguna reserva puede exceder `space.capacity * OVERCAPACITY_FACTOR`, ni solaparse en fecha y rango `[start_time, end_time]` con otra reserva `ACTIVA` del mismo `space_id`, ni asignarse a un espacio que no esté `DISPONIBLE`.
- **RN-02 (Control de Préstamos y Cuota por Usuario):** Ningún recurso puede prestarse si su estado no es `OPERATIVO`. Además, ningún usuario (`user_id`) puede tener más de `MAX_ACTIVE_LOANS_PER_USER` préstamos en estado `ACTIVO` simultáneamente.
- **RN-03 (Bloqueo Preventivo Cruzado por Incidencia):** Toda incidencia creada con prioridad `CRITICA` o `ALTA` que referencie un `target_id` (espacio o recurso) cambia automáticamente el estado de ese activo a `EN_MANTENIMIENTO`. Al marcarse la incidencia como `RESUELTA`, si el activo no tiene otras incidencias abiertas de prioridad `CRITICA` o `ALTA`, vuelve automáticamente a `DISPONIBLE` (si es espacio) u `OPERATIVO` (si es recurso).
- **RN-04 (Ventana Horaria y Duración Máxima):** Las reservas de espacios solo son válidas dentro de la ventana `[CAMPUS_OPEN_HOUR, CAMPUS_CLOSE_HOUR]` (por defecto `06:00` a `21:30`), con `end_time` estrictamente mayor que `start_time`, y una duración entre `MIN_RESERVATION_MINUTES` (30 min) y `MAX_RESERVATION_HOURS` (4.0 horas).
- **RN-05 (Cuarentena de Datos de Origen):** Todo registro del dataset de entrada que viole integridad estructural o referencial se registra en `quarantine_logs` detallando `source_file`, `raw_record` y `error_reason`, impidiendo que contamine el estado operativo.