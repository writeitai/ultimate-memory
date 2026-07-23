"""Pure RS-LoCoMo-v1 rendering, prompt, diagnostic, and scorer proofs."""

from uuid import uuid4

from benchmarks.locomo.model import LoCoMoQuestion
from benchmarks.locomo.model import LoCoMoSample
from benchmarks.locomo.model import LoCoMoSession
from benchmarks.locomo.model import LoCoMoTurn
from benchmarks.locomo.model import RetrievedClaim
from benchmarks.locomo.protocol import official_f1
from benchmarks.locomo.protocol import render_judge_prompt
from benchmarks.locomo.protocol import render_reader_prompt
from benchmarks.locomo.protocol import render_session
from benchmarks.locomo.protocol import session_diagnostic
import pytest


def test_session_render_preserves_turns_and_discloses_derived_visual_text() -> None:
    session = LoCoMoSession(
        ordinal=1,
        session_id="D1",
        timestamp="1:00 pm on 1 May, 2023",
        turns=(
            LoCoMoTurn(
                speaker="Alpha",
                dia_id="D1:1",
                text="Look at this.",
                blip_caption="a generated image description",
                image_urls=("https://example.test/must-not-appear.jpg",),
                image_query="a generated search phrase",
            ),
        ),
    )
    sample = LoCoMoSample(
        sample_id="conv-test",
        speaker_a="Alpha",
        speaker_b="Beta",
        sessions=(session,),
        questions=(
            LoCoMoQuestion(
                item_id="conv-test/qa/0000",
                sample_id="conv-test",
                question="What?",
                answer="That",
                evidence=("D1:1",),
                category=4,
            ),
        ),
    )

    rendered = render_session(sample=sample, session=session)

    assert "[D1:1 | 1:00 pm on 1 May, 2023] Alpha: Look at this." in rendered
    assert "Dataset-provided derived image caption" in rendered
    assert "Dataset-provided derived image search query" in rendered
    assert "https://example.test" not in rendered
    assert rendered.endswith("\n")


def test_reader_uses_only_ranked_claim_text_and_braces_stay_literal() -> None:
    claim = _claim(rank=1, text="Literal {question}; timestamp 1 May 2023")

    prompt = render_reader_prompt(question="What about {memories}?", claims=(claim,))

    assert "[1] Literal {question}; timestamp 1 May 2023" in prompt
    assert "What about {memories}?" in prompt
    assert claim.source_span not in prompt
    assert "gold answer" not in prompt.lower()


def test_empty_reader_context_is_exactly_none() -> None:
    prompt = render_reader_prompt(question="Unknown?", claims=())
    assert "Ranked memories:\n(none)\n\nQuestion: Unknown?" in prompt


def test_judge_never_receives_retrieved_context() -> None:
    prompt = render_judge_prompt(
        question="Where?", gold_answer="Prague", generated_answer="Prague"
    )
    assert "Gold answer: Prague" in prompt
    assert "Ranked memories" not in prompt
    assert "source_span" not in prompt


@pytest.mark.parametrize(
    ("prediction", "gold", "category", "expected"),
    (
        ("painted", "painting", 4, 1.0),
        (
            "psychology, counseling certificate",
            "Psychology, counseling certification",
            1,
            1.0,
        ),
        ("stress management", "stress management; inferred from context", 3, 1.0),
        ("the blue and green", "blue green", 4, 1.0),
        (None, "anything", 2, 0.0),
    ),
)
def test_official_f1_rules(
    prediction: str | None, gold: str, category: int, expected: float
) -> None:
    assert official_f1(
        prediction=prediction,
        gold_answer=gold,
        category=category,  # type: ignore[arg-type]
    ) == pytest.approx(expected)


def test_session_diagnostic_keeps_valid_ids_and_discloses_malformed_fields() -> None:
    diagnostic = session_diagnostic(
        gold_evidence=("D1:3", "D8:6; D9:17", "D:11:26"),
        retrieved_sessions={"D1", "D8"},
    )

    assert diagnostic.malformed_fields == 2
    assert diagnostic.recall == pytest.approx(2 / 3)
    assert diagnostic.complete is False


def _claim(*, rank: int, text: str) -> RetrievedClaim:
    return RetrievedClaim(
        rank=rank,
        claim_id=uuid4(),
        doc_id=uuid4(),
        chunk_id=uuid4(),
        claim_text=text,
        source_span="SECRET VERBATIM SOURCE",
        char_start=0,
        char_end=22,
        is_attributed=False,
        is_current_testimony=True,
        session_id="D1",
    )
