"""Configuración de la aplicación, leída de variables de entorno.

Ver environment/.env.example para la lista completa y sus valores por defecto
de desarrollo local.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://social_sim:change_me_local_dev@db:5432/social_sim_chat"
    env: str = "development"
    # Clave compartida del terapeuta (cabecera X-API-Key) para los endpoints de análisis y corrección. Vacía = autenticación
    # desactivada (solo desarrollo local; /health lo indica). El chat del menor (crear conversación y enviar turnos) no la exige.
    api_key_terapeuta: str | None = None
    # Resumen del último entrenamiento (lo escribe scripts.train_classifier); la API lo sirve en /modelo/metricas.
    metrics_path: Path = Path(__file__).resolve().parent.parent / "models" / "metrics.json"

    # --- Motor conversacional (LLM local) ---
    # "ollama"   -> Ollama con su API nativa (por defecto; permite think:false y keep_alive).
    # "openai"   -> cualquier servidor con API compatible con OpenAI (/v1/chat/completions): el /v1 de Ollama,
    #               vLLM, LM Studio, TabbyAPI... Es la interfaz que fija NF2 para sustituir el motor local.
    # "tabbyapi" -> alias histórico de "openai" con las variables TABBYAPI_* (stack TabbyAPI/ExLlamaV3 externo).
    # "simulado" -> sin LLM ni GPU: valoración 0/1/2 por reglas (app/simulado.py). Para ejecutar y evaluar el prototipo en cualquier
    #               equipo (historia 11) y como plan B; NO es el evaluador del producto (ver docs/modo-simulado.md).
    # Ver environment/.env.example para cómo apuntarlo a tu PC y qué modelo usar.
    llm_provider: str = "ollama"

    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3:14b"
    ollama_think: bool = False  # qwen3 y similares: razonamiento apagado para conversar

    # --- Cliente de chat (Ollama) ---
    # num_ctx explícito: sin él Ollama usa su valor por defecto y TRUNCA EN SILENCIO el prompt
    # (los guiones largos pierden el principio). Si el prompt estimado no cabe, se falla con error claro.
    ollama_num_ctx: int = 8192
    ollama_keep_alive: str = "30m"       # mantiene el modelo cargado entre turnos (evita recargas de ~10 s)
    ollama_temperature: float = 0.3
    ollama_num_predict: int = 200        # tope de tokens generados por turno
    ollama_timeout_s: float = 120.0      # por intento
    ollama_max_reintentos: int = 2       # reintentos acotados si Ollama no responde (0 = ninguno)
    ollama_reintento_espera_s: float = 0.5   # espera inicial; se duplica en cada reintento
    ollama_cola_timeout_s: float = 120.0     # máx. espera para entrar en la cola (1 petición a la vez)

    # Modo simulado: sus conversaciones son `es_prueba` (no generan sesión ni métricas reales) para no mezclar valoraciones por reglas
    # con datos reales. Ponlo a true SOLO en una base de datos de demostración, para ver el recorrido completo en el dashboard.
    simulado_registra_sesiones: bool = False

    tabbyapi_host: str = "http://host.docker.internal:5000"
    tabbyapi_model: str = "Qwen3.8-27B-EXL3-3.0bpw"
    tabbyapi_api_key: str | None = None

    # --- Proveedor "openai" (API compatible con OpenAI) ---
    # Por defecto apunta al /v1 del Ollama del host, para poder probar la interfaz sin instalar nada más.
    # Los nombres LLM_COMPAT_* evitan OPENAI_API_KEY / OPENAI_BASE_URL a propósito: si el entorno del usuario tiene una clave
    # real de OpenAI, no debe acabar enviándose a este proveedor (los datos son de menores).
    llm_compat_url: str = "http://host.docker.internal:11434"   # raíz del servidor, sin /v1
    llm_compat_model: str = "qwen3:14b"
    llm_compat_api_key: str | None = None
    # Pide al servidor el JSON del evaluador con response_format=json_schema. Si tu servidor lo rechaza (HTTP 400), ponlo a false:
    # el cliente extrae el JSON del texto igualmente.
    llm_compat_response_format: bool = True
    # Esfuerzo de razonamiento que se pide al servidor. Con el /v1 de Ollama y un modelo que razona (qwen3), el razonamiento
    # consume max_tokens y la respuesta llega cortada ("{\n\"analis"): "none" lo desactiva (como think=false en la API nativa).
    # Vacío = no se envía el campo (úsalo si tu servidor lo rechaza con HTTP 400). Medido con Ollama 0.40 y qwen3:0.6b.
    llm_compat_reasoning_effort: str | None = "none"

    @property
    def llm_simulado(self) -> bool:
        return self.llm_provider == "simulado"

    @property
    def llm_openai_compatible(self) -> bool:
        return self.llm_provider in ("openai", "tabbyapi")

    @property
    def llm_base_url(self) -> str:
        if self.llm_provider == "tabbyapi":
            return self.tabbyapi_host
        return self.llm_compat_url if self.llm_provider == "openai" else self.ollama_host

    @property
    def llm_model(self) -> str:
        if self.llm_provider == "simulado":
            return "simulado"
        if self.llm_provider == "tabbyapi":
            return self.tabbyapi_model
        return self.llm_compat_model if self.llm_provider == "openai" else self.ollama_model


settings = Settings()
