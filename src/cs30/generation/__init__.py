"""Member 7: personalised prompting and LLM generation."""

from .batch import BatchItem, BatchResult, generate_batch
from .client import MockJsonLLMClient, OllamaChatClient, OpenAIResponsesClient
from .combined import CombinedEvidenceRetriever
from .conditions import ConditionResult, FourConditionRunner, GenerationCondition
from .fixture import FixtureAnswerGenerator
from .generator import GenerationAttemptTrace, GenerationTrace, PersonalisedAnswerGenerator
from .prompt import PromptBuilder, format_sciq_question
from .reranking import (
    CandidateScore,
    EvidenceRole,
    LevelAwareReranker,
    RerankConfig,
    RerankResult,
    RerankTrace,
    RoleLabel,
)
from .sciq_smoke import (
    build_free_question_items,
    build_sciq_smoke_items,
    load_packaged_free_questions,
    load_packaged_sciq_questions,
    load_sciq_questions,
)

__all__ = [
    "BatchItem",
    "BatchResult",
    "CombinedEvidenceRetriever",
    "ConditionResult",
    "EvidenceRole",
    "FixtureAnswerGenerator",
    "FourConditionRunner",
    "GenerationAttemptTrace",
    "GenerationCondition",
    "GenerationTrace",
    "LevelAwareReranker",
    "MockJsonLLMClient",
    "OllamaChatClient",
    "OpenAIResponsesClient",
    "PersonalisedAnswerGenerator",
    "PromptBuilder",
    "CandidateScore",
    "RerankConfig",
    "RerankResult",
    "RerankTrace",
    "RoleLabel",
    "build_free_question_items",
    "build_sciq_smoke_items",
    "format_sciq_question",
    "generate_batch",
    "load_packaged_free_questions",
    "load_packaged_sciq_questions",
    "load_sciq_questions",
]
