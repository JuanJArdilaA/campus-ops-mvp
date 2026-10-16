OVERCAPACITY_FACTOR: float = 1.0           # RN-01: 1.0 = sin sobrecupo (1.1 = +10% permitido)
MAX_ACTIVE_LOANS_PER_USER: int = 2         # RN-02: Máximo de préstamos activos por persona
BLOCKING_PRIORITIES: set[str] = {"CRITICA", "ALTA"}  # RN-03: Prioridades que bloquean activos
CAMPUS_OPEN_TIME: str = "06:00"            # RN-04: Apertura del campus
CAMPUS_CLOSE_TIME: str = "21:30"           # RN-04: Cierre del campus
MAX_RESERVATION_HOURS: float = 4.0         # RN-04: Duración máxima por reserva en horas
MIN_RESERVATION_MINUTES: int = 30          # RN-04: Duración mínima por reserva en minutos