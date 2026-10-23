"""Thin TopicResolver adapter over the shared v2 topic-resolution functions."""

from cs30.v2 import topics
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import RetrievalResult, TopicRegistry, TopicResolution, ValidatedAnswer
from cs30.v2.topics import LoadedChunkTopicMap


class ChunkTopicResolver:
    """Reuse a map validated at load time and the configured support threshold."""

    def __init__(
        self,
        topic_map: LoadedChunkTopicMap | None,
        registry: TopicRegistry | None,
        config: ConceptCheckConfig,
    ) -> None:
        self.topic_map = topic_map
        self.registry = registry
        self.config = config

    def resolve_retrieval_topic(self, retrieval: RetrievalResult) -> TopicResolution:
        return topics.resolve_topic_from_retrieval(
            retrieval,
            self.topic_map,
            self.registry,
            min_topic_support=self.config.min_topic_support,
        )

    def resolve_cited_topic(
        self, retrieval: RetrievalResult, validated: ValidatedAnswer
    ) -> TopicResolution:
        return topics.resolve_topic_from_citations(
            retrieval,
            validated,
            self.topic_map,
            self.registry,
            min_topic_support=self.config.min_topic_support,
        )
