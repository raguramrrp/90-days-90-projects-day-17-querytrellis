"""SQL synthesis configuration and optional consent-gated external API adapters."""

from src.ai.external_client import generate_with_external_ai, test_external_connection
from src.ai.prompt_builder import build_nl2sql_messages, build_transmission_disclosure
from src.ai.provider_base import AICompletionResult, AIProviderConfig, AISettingsManager

__all__ = [
    "AICompletionResult",
    "AIProviderConfig",
    "AISettingsManager",
    "build_nl2sql_messages",
    "build_transmission_disclosure",
    "generate_with_external_ai",
    "test_external_connection",
]
