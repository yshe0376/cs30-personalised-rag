from types import SimpleNamespace

from cs30.learning.topic_selection import select_cited_demo_topic


def _select(approved):
    return select_cited_demo_topic(
        profile_id="p", turn_id="t", quiz_index=1,
        cited_chunk_ids=("light-chunk",),
        ranked_hits=[SimpleNamespace(chunk_id="light-chunk", rank=1)],
        topic_assignments={
            "light-chunk": ("speed-of-light", "refraction"),
            "not-cited": ("ohm-s-law",),
        },
        rank_weighted_support={"speed-of-light": 0.5, "refraction": 0.5},
        approved_topic_ids=approved, resolver_status="unresolved",
        resolver_error_code="TOPIC_TIE", allow_selection=True, rng_seed=42,
    )


def test_multi_topic_citation_can_generate_quiz_with_all_topics_enabled():
    trace = _select(("speed-of-light", "refraction", "ohm-s-law"))
    assert trace.selected_topic_id in {"speed-of-light", "refraction"}
    assert trace.selection_method == "weighted_random"
    assert all(candidate.eligible for candidate in trace.candidates)
    assert all(candidate.sufficient_evidence_chunk_ids == ("light-chunk",)
               for candidate in trace.candidates)
    assert "ohm-s-law" not in {candidate.topic_id for candidate in trace.candidates}
    assert trace.policy_version.endswith("v2")


def test_explicit_scope_still_excludes_other_topics():
    trace = _select(("ohm-s-law",))
    assert trace.selected_topic_id is None
    assert not trace.candidates
