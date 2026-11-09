"""Shared Engine & Optional External API configuration manager (zero hardcoded secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AIProviderConfig:
    """Active SQL synthesis engine settings with strict privacy and consent separation."""

    active_provider: str = "deterministic"  # deterministic | external
    external_provider: str = "openai"  # openai | anthropic | gemini | openai_compatible
    external_base_url: str = "https://api.openai.com/v1"
    external_model: str = "gpt-4o-mini"
    external_api_key: str = field(default="", repr=False)
    external_data_consent: bool = False
    include_sample_rows_in_external: bool = False
    deterministic_fallback_enabled: bool = True

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize configuration cleanly WITHOUT ever returning raw API keys."""
        return {
            "active_provider": self.active_provider,
            "external_provider": self.external_provider,
            "external_base_url": self.external_base_url,
            "external_model": self.external_model,
            "external_api_key_configured": bool(self.external_api_key),
            "external_data_consent": self.external_data_consent,
            "include_sample_rows_in_external": self.include_sample_rows_in_external,
            "deterministic_fallback_enabled": self.deterministic_fallback_enabled,
        }


@dataclass(slots=True)
class AICompletionResult:
    """Outcome of invoking an external API model adapter."""

    success: bool
    provider_used: str
    model_used: str
    raw_text: str = ""
    parsed_json: dict[str, Any] | None = None
    error_message: str = ""
    offer_external_fallback: bool = False


class AISettingsManager:
    """Maintains runtime engine & API gateway config initialized from environment defaults."""

    def __init__(self) -> None:
        raw_provider = os.getenv("QT_AI_PROVIDER", "deterministic").strip().lower()
        normalized_provider = "external" if raw_provider == "external" else "deterministic"
        self.config = AIProviderConfig(
            active_provider=normalized_provider,
            external_provider=os.getenv("QT_EXTERNAL_AI_PROVIDER", "openai").strip() or "openai",
            external_base_url=os.getenv("QT_EXTERNAL_AI_BASE_URL", "https://api.openai.com/v1").strip()
            or "https://api.openai.com/v1",
            external_model=os.getenv("QT_EXTERNAL_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            external_api_key=os.getenv("QT_EXTERNAL_AI_API_KEY", ""),
            external_data_consent=False,
        )

    def update(self, payload: dict[str, Any]) -> AIProviderConfig:
        if "active_provider" in payload and payload["active_provider"] in {"deterministic", "external"}:
            self.config.active_provider = str(payload["active_provider"])
        if "external_provider" in payload:
            self.config.external_provider = str(payload["external_provider"]).strip()
        if "external_base_url" in payload:
            self.config.external_base_url = str(payload["external_base_url"]).strip().rstrip("/")
        if "external_model" in payload:
            self.config.external_model = str(payload["external_model"]).strip()
        if "external_api_key" in payload and payload["external_api_key"] is not None:
            new_key = str(payload["external_api_key"]).strip()
            if new_key:
                self.config.external_api_key = new_key
        if payload.get("clear_external_api_key"):
            self.config.external_api_key = ""
        if "external_data_consent" in payload:
            self.config.external_data_consent = bool(payload["external_data_consent"])
        if "include_sample_rows_in_external" in payload:
            self.config.include_sample_rows_in_external = bool(payload["include_sample_rows_in_external"])
        if "deterministic_fallback_enabled" in payload:
            self.config.deterministic_fallback_enabled = bool(payload["deterministic_fallback_enabled"])
        elif "cpu_fallback_enabled" in payload:
            self.config.deterministic_fallback_enabled = bool(payload["cpu_fallback_enabled"])
        return self.config
