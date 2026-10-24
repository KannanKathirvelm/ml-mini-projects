"""Claude client wrapper and mode detection.

LLM mode switches on only when ANTHROPIC_API_KEY is set; otherwise every agent
uses its deterministic rule-based logic. Agents receive precomputed data (not
tool use) and ask Claude for JSON matching a schema via structured outputs, so
LLM and offline mode produce exactly the same report structure.
"""
import json
import os

DEFAULT_MODEL = "claude-opus-5-5"
MODEL = os.getenv("FIN_AGENTS_MODEL", DEFAULT_MODEL)
EFFORT = os.getenv("FIN_AGENTS_EFFORT", "medium")  # low | medium | high | xhigh | max


class LLMError(RuntimeError):
    """Any failure in the LLM path; agents catch it and fall back to rules."""


def llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def mode_label(use_llm: bool, model: str | None = None) -> str:
    return f"LLM mode (Claude: {model or MODEL})" if use_llm else "Offline mode (rule-based, no API key)"


_client = None


def get_client():
    """Lazily build one shared client; the SDK reads ANTHROPIC_API_KEY itself."""
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


def ask_json(system: str, prompt: str, schema: dict, model: str | None = None) -> dict:
    """One Claude call that must return JSON matching `schema`."""
    import anthropic

    try:
        response = get_client().beta.messages.create(
            model=model or MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": schema},
            },
            # On a safety decline the API retries on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIConnectionError as exc:
        raise LLMError(f"network error: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"API error {exc.status_code}: {exc.message}") from exc

    if response.stop_reason == "refusal":
        raise LLMError("model declined the request")
    if response.stop_reason == "max_tokens":
        raise LLMError("response truncated (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError("no text block in response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"invalid JSON from model: {exc}") from exc
