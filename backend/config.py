# ---------------------------------------------------------------------------
# Shared LLM config — single source of truth for all AI modules
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:1.7b"

# Default generation options used by every LLM call
DEFAULT_OPTIONS = {
    "temperature": 0,
    "num_predict": 400,
}