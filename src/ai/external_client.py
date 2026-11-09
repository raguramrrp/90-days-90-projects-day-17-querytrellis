"""Optional external AI provider adapters (OpenAI-compatible, Anthropic, Gemini) with strict consent gate."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from src.ai.provider_base import AICompletionResult, AIProviderConfig
from src.security.guardrails import sanitize_error_message


def _extract_json_block(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


def test_external_connection(config: AIProviderConfig) -> dict[str, Any]:
    """Validate API key presence and reachability without leaking secrets."""
    if not config.external_api_key:
        return {
            "reachable": False,
            "provider": config.external_provider,
            "error_message": "No external API key is configured in session memory or environment variables.",
        }

    prov = config.external_provider.lower()
    try:
        with httpx.Client(timeout=8) as client:
            if prov in {"openai", "openai_compatible"}:
                url = f"{config.external_base_url.rstrip('/')}/models"
                resp = client.get(url, headers={"Authorization": f"Bearer {config.external_api_key}"})
                resp.raise_for_status()
                return {"reachable": True, "provider": prov, "model": config.external_model}
            if prov == "anthropic":
                resp = client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": config.external_api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                resp.raise_for_status()
                return {"reachable": True, "provider": prov, "model": config.external_model}
            if prov == "gemini":
                resp = client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": config.external_api_key},
                )
                resp.raise_for_status()
                return {"reachable": True, "provider": prov, "model": config.external_model}
            return {"reachable": False, "provider": prov, "error_message": f"Unknown external provider '{prov}'."}
    except Exception as exc:
        return {
            "reachable": False,
            "provider": prov,
            "error_message": sanitize_error_message(f"External API check failed: {exc}"),
        }


def generate_with_external_ai(
    messages: list[dict[str, str]],
    config: AIProviderConfig,
) -> AICompletionResult:
    """Invoke configured external provider ONLY when explicit consent is granted."""
    if not config.external_data_consent:
        return AICompletionResult(
            success=False,
            provider_used="external",
            model_used=config.external_model,
            error_message=(
                "External schema transmission requires explicit consent. Review the data disclosure "
                "and accept external transmission in AI Settings before sending requests externally."
            ),
        )
    if not config.external_api_key:
        return AICompletionResult(
            success=False,
            provider_used="external",
            model_used=config.external_model,
            error_message="External AI provider is selected, but no API key has been provided.",
        )

    prov = config.external_provider.lower()
    try:
        with httpx.Client(timeout=30) as client:
            if prov in {"openai", "openai_compatible"}:
                url = f"{config.external_base_url.rstrip('/')}/chat/completions"
                resp = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {config.external_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.external_model,
                        "messages": messages,
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
            elif prov == "anthropic":
                sys_msg = "\n".join(m["content"] for m in messages if m["role"] == "system")
                usr_msg = "\n".join(m["content"] for m in messages if m["role"] == "user")
                resp = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": config.external_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": config.external_model,
                        "max_tokens": 1400,
                        "system": sys_msg,
                        "messages": [{"role": "user", "content": usr_msg}],
                    },
                )
                resp.raise_for_status()
                content = resp.json()["content"][0]["text"]
            elif prov == "gemini":
                combined = "\n\n".join(m["content"] for m in messages)
                resp = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{config.external_model}:generateContent",
                    params={"key": config.external_api_key},
                    json={
                        "contents": [{"parts": [{"text": combined}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
                    },
                )
                resp.raise_for_status()
                content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return AICompletionResult(
                    success=False,
                    provider_used="external",
                    model_used=config.external_model,
                    error_message=f"Unsupported external provider '{config.external_provider}'.",
                )

        parsed = _extract_json_block(str(content))
        if parsed is None:
            return AICompletionResult(
                success=False,
                provider_used="external",
                model_used=config.external_model,
                raw_text=str(content),
                error_message="External model response did not parse into valid structured JSON.",
            )
        return AICompletionResult(
            success=True,
            provider_used="external",
            model_used=config.external_model,
            raw_text=str(content),
            parsed_json=parsed,
        )
    except Exception as exc:
        return AICompletionResult(
            success=False,
            provider_used="external",
            model_used=config.external_model,
            error_message=sanitize_error_message(f"External AI request failed: {exc}"),
        )
