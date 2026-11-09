"""Shared backend singleton services initialized cleanly on server startup."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.ai.provider_base import AISettingsManager
from src.connectors.demo_sandbox import ensure_sample_export_files
from src.context.context_manager import ActiveContextManager


@dataclass(slots=True)
class PlatformContainer:
    """Dependency container holding active DB context manager and AI settings manager."""

    context_manager: ActiveContextManager = field(default_factory=ActiveContextManager)
    ai_manager: AISettingsManager = field(default_factory=AISettingsManager)

    def ensure_assets(self) -> None:
        ensure_sample_export_files()


_container: PlatformContainer | None = None


def get_container() -> PlatformContainer:
    global _container
    if _container is None:
        _container = PlatformContainer()
        _container.ensure_assets()
    return _container
