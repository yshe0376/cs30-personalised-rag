"""Authors choose locatable source quotes; a retry receives corrective feedback."""

import json
from types import SimpleNamespace as NS

from test_learning_m8_integration import online_runtime
from test_learning_online_quiz import _author_payload

from cs30.learning.budget import BudgetedClient


def test_author_schema_limits_quotes_to_locatable_source_text(tmp_path):
    runtime = online_runtime(tmp_path)
    chunk = runtime.assets.corpus.chunks[0]
    received = []

    class CapturingAuthor:
        model = "local-author"

        def complete(self, prompt, text_format):
            received.append((prompt, text_format))
            return NS(
                text=json.dumps(_author_payload(
                    evidence_chunk_id=chunk.chunk_id, evidence_quote=chunk.text,
                )), usage=NS(input_tokens=1, output_tokens=1),
            )

    runtime.quiz_generator.author_client = BudgetedClient(CapturingAuthor(), runtime.request_budget)
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "offered", view.notice
    prompt, text_format = received[0]
    allowed = text_format["schema"]["properties"]["evidence_quote"]["enum"]
    assert allowed
    assert all(quote in chunk.text for quote in allowed)
    assert "allowed_quotes" in prompt


def test_retry_repairs_bad_quote_with_source_options_and_specific_feedback(tmp_path):
    runtime = online_runtime(tmp_path)
    chunk = runtime.assets.corpus.chunks[0]

    class RepairingAuthor:
        model = "local-author"

        def __init__(self):
            self.prompts = []

        def complete(self, prompt, text_format):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                quote = "The model paraphrased the textbook instead of copying the exact source."
            else:
                assert "Previous candidate failed" in prompt
                assert "not found" in prompt
                quote = text_format["schema"]["properties"]["evidence_quote"]["enum"][0]
            return NS(
                text=json.dumps(_author_payload(
                    evidence_chunk_id=chunk.chunk_id, evidence_quote=quote,
                )), usage=NS(input_tokens=1, output_tokens=1),
            )

    author = RepairingAuthor()
    runtime.quiz_generator.author_client = BudgetedClient(author, runtime.request_budget)
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "offered", view.notice
    assert len(author.prompts) == 2
    assert author.prompts[0] != author.prompts[1]
    assert runtime.request_usage["used"] == 2
    record = runtime.active_turn.private_quizzes[1]
    assert record.question.evidence_anchors[0].verbatim_text in chunk.text


def test_failed_textbook_fallback_still_displays_its_generation_mode(tmp_path):
    from test_learning_textbook_fallback import without_topic_mapping

    runtime = without_topic_mapping(online_runtime(tmp_path))
    runtime.quiz_generator.author_client.client.payload["evidence_quote"] = (
        "This is a fabricated sentence that does not exist in the supplied textbook passage."
    )
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "unavailable"
    assert view.generation_basis == "textbook"
    assert runtime.request_usage["used"] == 2


def test_second_quiz_includes_first_question_to_avoid_repeating_it(tmp_path):
    runtime = online_runtime(tmp_path)
    first = runtime.make_quiz("turn-local", 1)
    assert first.status == "offered", first.notice
    runtime.submit(first.turn_id, first.practice_id, "A")
    chunk = runtime.assets.corpus.chunks[0]

    class SecondQuestionAuthor:
        model = "local-author"

        def complete(self, prompt, text_format):
            assert "quiz_index=2" in prompt
            assert first.question in prompt
            assert "do not repeat or merely reword" in prompt
            return NS(
                text=json.dumps(_author_payload(
                    question="Which other concept is named in the passage?",
                    evidence_chunk_id=chunk.chunk_id,
                    evidence_quote=text_format["schema"]["properties"]["evidence_quote"]["enum"][0],
                )), usage=NS(input_tokens=1, output_tokens=1),
            )

    runtime.quiz_generator.author_client = BudgetedClient(
        SecondQuestionAuthor(), runtime.request_budget,
    )
    second = runtime.make_quiz("turn-local", 2)
    assert second.status == "offered", second.notice
    assert second.question != first.question
    assert runtime.request_usage["used"] == 2
