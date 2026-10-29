from types import SimpleNamespace as NS

from cs30.ui.learning_views import _profile_topic_ids


def test_sidebar_uses_quiz_topic_when_retrieval_is_ambiguous():
    runtime = NS(
        active_turn=NS(
            quizzes={1: NS(topic_id="speed-of-light"), 2: NS(topic_id="refraction")},
            retrieval_topic=NS(status="unresolved", topic_id=None),
        ),
        learner_state=NS(topics={"speed-of-light": NS(mastery_score=0.6)}),
        assets=NS(topic_registry=NS(topics=[
            NS(topic_id="speed-of-light"), NS(topic_id="refraction"),
        ])),
    )
    assert _profile_topic_ids(runtime) == ["refraction", "speed-of-light"]


def test_sidebar_keeps_previously_practiced_topics_without_current_turn():
    runtime = NS(
        active_turn=None, learner_state=NS(topics={"light": NS(), "unknown": NS()}),
        assets=NS(topic_registry=NS(topics=[NS(topic_id="light")])),
    )
    assert _profile_topic_ids(runtime) == ["light"]
