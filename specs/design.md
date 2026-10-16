# Diseño de Arquitectura y Contratos de Código (`specs/design.md`)

## 1. Diagrama de Flujo y Capas
```text
[Usuario / Jurado]
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ CAPA UI (Streamlit - Sebastián)                                 │
│ app.py -> views_spaces.py | views_resources.py | views_incidents│
└──────┬───────────────────────────────┬───────────────────┬──────┘
       │ 1. Valida regla               │ 2. Clasifica IA   │ 3. Persiste cambio
       ▼                               ▼                   ▼
┌──────────────────────┐   ┌───────────────────────┐   ┌──────────────────────┐
│ VALIDATORS (JuanJo)  │   │ AI SERVICE (Andrés)   │   │ REPOSITORY (Miguel)  │
│ src/core/validators  │   │ src/core/ai_service   │   │ src/core/repository  │
│ RN-01 a RN-05        │   │ Gemini API + Fallback │   │ CRUD + Regla RN-03   │
└──────────────────────┘   └───────────────────────┘   └──────────┬───────────┘
                                                                  │
                                                                  ▼
                                                       ┌──────────────────────┐
                                                       │ SANITIZER (Miguel)   │
                                                       │ data/raw -> JSON     │
                                                       └──────────────────────┘