"""
Conversational AI Foundation — Natural Language Parsing, Memory, Grounded Synthesis & LLM Providers.
Rule: Never computes actuarial figures directly; delegates all numerical operations to Analytical Foundation.
"""

from chubb.conversational_ai.memory_manager import ConversationMemoryManager
from chubb.conversational_ai.query_parser import ActuarialQueryParser
from chubb.conversational_ai.grounding import (
    build_human_narrative,
    format_executive_summary_response,
    format_recommendations_response,
    format_business_rules_response,
    format_insufficient_kpi_response,
    format_unsupported_granularity_response,
)
from chubb.conversational_ai.assistant import (
    GroundedActuarialAssistant,
    LlamaColabDataAgent,
)
from chubb.conversational_ai.providers import (
    LLMProvider,
    MockLlama3Provider,
    OllamaProvider,
    OpenAICompatibleProvider,
)

__all__ = [
    "ConversationMemoryManager",
    "ActuarialQueryParser",
    "build_human_narrative",
    "format_executive_summary_response",
    "format_recommendations_response",
    "format_business_rules_response",
    "format_insufficient_kpi_response",
    "format_unsupported_granularity_response",
    "GroundedActuarialAssistant",
    "LlamaColabDataAgent",
    "LLMProvider",
    "MockLlama3Provider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
]

