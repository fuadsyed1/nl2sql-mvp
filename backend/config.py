# ---------------------------------------------------------------------------
# Shared LLM config — single source of truth for all AI modules
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:1.7b"

# num_predict: qwen3 emits <think> blocks before its answer even with /no_think.
# 600 gives enough headroom for ~400 tokens of thinking + 200 tokens of JSON.
# Individual call sites can override this with {**DEFAULT_OPTIONS, "num_predict": N}.
DEFAULT_OPTIONS = {
    "temperature": 0,
    "num_predict": 600,
}