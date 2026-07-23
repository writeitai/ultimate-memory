"""Synthetic-only remote-boundary, cost, and denominator proofs."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from benchmarks.locomo import runner
from benchmarks.locomo.dataset import DATASET_COMMIT
from benchmarks.locomo.dataset import DATASET_SHA256
from benchmarks.locomo.dataset import item_ids_hash
from benchmarks.locomo.model import JudgeOutput
from benchmarks.locomo.model import LoCoMoDataset
from benchmarks.locomo.model import LoCoMoQuestion
from benchmarks.locomo.model import LoCoMoSample
from benchmarks.locomo.model import LoCoMoSession
from benchmarks.locomo.model import LoCoMoTurn
from benchmarks.locomo.model import QuestionManifest
from benchmarks.locomo.model import ReaderOutput
from benchmarks.locomo.model import RunState
from benchmarks.locomo.protocol import READER_MODEL
from benchmarks.locomo.runner import _answer_one
from benchmarks.locomo.runner import _judge_one
from benchmarks.locomo.runner import answer_sample
from benchmarks.locomo.runner import BenchmarkRunError
from benchmarks.locomo.runner import ExecutionGuardError
from benchmarks.locomo.runner import ingest_sample
from benchmarks.locomo.runner import judge_sample
from benchmarks.locomo.runner import prepare_run
from benchmarks.locomo.runner import summarize_run
import httpx
import pytest

from rememberstack.adapters.testing import FakeModelProvider
from rememberstack.model import EmbeddingRequest
from rememberstack.model import EmbeddingResponse
from rememberstack.model import Envelope
from rememberstack.model import Freshness
from rememberstack.model import GeneratedResponse
from rememberstack.model import Grain
from rememberstack.model import ModelRequest
from rememberstack.model import Negative
from rememberstack.model import NegativeKind
from rememberstack.model import ProviderCallUsage
from rememberstack.model import StructuredResponseModel
from rememberstack.surfaces.sdk import MemoryClient

ResponseT = TypeVar("ResponseT", bound=StructuredResponseModel)


@pytest.mark.parametrize("known_empty", (False, True))
def test_successful_empty_retrieval_still_calls_reader_once(known_empty: bool) -> None:
    envelope = _empty_envelope(known_empty=known_empty)
    client, raw_client = _memory_client(envelope=envelope)
    provider = FakeModelProvider(generate_payload={"answer": "Unknown"})
    state = RunState()
    try:
        answer = _answer_one(
            question=_question(),
            client=client,
            provider=provider,
            doc_sessions={},
            state=state,
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
        )
    finally:
        raw_client.close()

    assert answer.retrieval_succeeded is True
    assert answer.reader_called is True
    assert answer.failure is None
    assert answer.generated_answer == "Unknown"
    assert provider.generated_prompts[0].count("(none)") == 1


def test_transport_failure_does_not_call_reader() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    raw_client = httpx.Client(
        base_url="http://memory.test", transport=httpx.MockTransport(fail)
    )
    provider = FakeModelProvider(generate_payload={"answer": "must not run"})
    try:
        answer = _answer_one(
            question=_question(),
            client=MemoryClient(client=raw_client),
            provider=provider,
            doc_sessions={},
            state=RunState(),
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
        )
    finally:
        raw_client.close()

    assert answer.retrieval_succeeded is False
    assert answer.reader_called is False
    assert answer.failure is not None
    assert answer.failure.kind == "retrieval"
    assert provider.generated_prompts == []


def test_invalid_empty_reader_answer_is_a_terminal_reader_failure() -> None:
    client, raw_client = _memory_client(envelope=_empty_envelope())
    provider = FakeModelProvider(generate_payload={"answer": ""})
    try:
        answer = _answer_one(
            question=_question(),
            client=client,
            provider=provider,
            doc_sessions={},
            state=RunState(),
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
        )
    finally:
        raw_client.close()

    assert answer.generated_answer is None
    assert answer.reader_called is True
    assert answer.failure is not None
    assert answer.failure.kind == "invalid_response"


def test_reader_and_judge_share_one_run_absolute_cost_ceiling() -> None:
    client, raw_client = _memory_client(envelope=_empty_envelope())
    provider = _CostProvider(cost=Decimal("0.60"))
    state = RunState()
    try:
        answer = _answer_one(
            question=_question(),
            client=client,
            provider=provider,
            doc_sessions={},
            state=state,
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("0.60"),
        )
    finally:
        raw_client.close()

    assert state.evaluator_cost_usd == Decimal("0.60")
    with pytest.raises(ExecutionGuardError, match="reached run ceiling"):
        _judge_one(
            question=_question(),
            answer=answer,
            provider=provider,
            state=state,
            max_judge_calls=1,
            max_evaluator_cost_usd=Decimal("0.60"),
        )
    assert provider.models == [READER_MODEL]


def test_model_request_temperature_is_bounded() -> None:
    assert ModelRequest(model="m", prompt="p", temperature=0).temperature == 0
    with pytest.raises(ValueError):
        ModelRequest(model="m", prompt="p", temperature=-0.1)
    with pytest.raises(ValueError):
        ModelRequest(model="m", prompt="p", temperature=2.1)


def test_staged_mock_run_resumes_without_duplicate_checkpointed_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staged contract executes only against synthetic local boundaries."""
    _patch_prepared_inputs(monkeypatch=monkeypatch)
    run_dir = tmp_path / "run"
    prepare_run(dataset_path=tmp_path / "synthetic.json", tier="smoke", output=run_dir)
    raw_client = httpx.Client(
        base_url="http://memory.test", transport=httpx.MockTransport(_run_transport)
    )
    client = MemoryClient(client=raw_client)
    provider = FakeModelProvider(
        generate_payloads={
            "ReaderOutput": {"answer": "Prague"},
            "JudgeOutput": {"label": "CORRECT"},
        }
    )
    try:
        ingests = ingest_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_documents=1,
            execute=True,
            isolated_deployment_confirmation="conv-test",
            client=client,
        )
        first_answers = answer_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_questions=1,
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
            execute=True,
            index_ready_confirmation="conv-test",
            client=client,
            provider=provider,
        )
        second_answers = answer_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_questions=1,
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
            execute=True,
            index_ready_confirmation="conv-test",
            client=client,
            provider=provider,
        )
        first_judges = judge_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_judge_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
            execute=True,
            provider=provider,
        )
        second_judges = judge_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_judge_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
            execute=True,
            provider=provider,
        )
    finally:
        raw_client.close()

    assert len(ingests) == 1
    assert first_answers == second_answers
    assert first_judges == second_judges
    assert len(provider.generated_prompts) == 2
    summary = summarize_run(run_dir=run_dir)
    assert summary.questions == 1
    assert summary.judge_correct == 1
    assert summary.judge_percent == 100
    assert summary.official_f1 == 1


def test_missing_records_remain_in_full_manifest_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_prepared_inputs(monkeypatch=monkeypatch)
    run_dir = tmp_path / "run"
    prepare_run(dataset_path=tmp_path / "synthetic.json", tier="smoke", output=run_dir)

    summary = summarize_run(run_dir=run_dir)

    assert summary.questions == 1
    assert summary.judge_correct == 0
    assert summary.official_f1 == 0
    assert summary.failures == {"missing_answer": 1, "missing_judge": 1}


def test_upstream_failure_gets_local_wrong_without_fake_judge_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_prepared_inputs(monkeypatch=monkeypatch)
    run_dir = tmp_path / "run"
    prepare_run(dataset_path=tmp_path / "synthetic.json", tier="smoke", output=run_dir)
    ingest_raw = httpx.Client(
        base_url="http://memory.test", transport=httpx.MockTransport(_run_transport)
    )
    try:
        ingest_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_documents=1,
            execute=True,
            isolated_deployment_confirmation="conv-test",
            client=MemoryClient(client=ingest_raw),
        )
    finally:
        ingest_raw.close()
    failed_raw = httpx.Client(
        base_url="http://memory.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(503, text="offline")
        ),
    )
    provider = FakeModelProvider(generate_payload={"answer": "must not run"})
    try:
        answer_sample(
            run_dir=run_dir,
            sample_id="conv-test",
            max_questions=1,
            max_reader_calls=1,
            max_evaluator_cost_usd=Decimal("1"),
            execute=True,
            index_ready_confirmation="conv-test",
            client=MemoryClient(client=failed_raw),
            provider=provider,
        )
    finally:
        failed_raw.close()
    judges = judge_sample(
        run_dir=run_dir,
        sample_id="conv-test",
        max_judge_calls=1,
        max_evaluator_cost_usd=Decimal("1"),
        execute=True,
        provider=provider,
    )

    summary = summarize_run(run_dir=run_dir)
    assert judges[0].model_called is False
    assert judges[0].failure is None
    assert summary.judge_correct == 0
    assert summary.failures == {"answer_retrieval": 1}
    assert provider.generated_prompts == []


def test_protocol_mutation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_prepared_inputs(monkeypatch=monkeypatch)
    run_dir = tmp_path / "run"
    prepare_run(dataset_path=tmp_path / "synthetic.json", tier="smoke", output=run_dir)
    run_path = run_dir / "run.json"
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["reader_prompt_sha256"] = "0" * 64
    run_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkRunError, match="fingerprint"):
        summarize_run(run_dir=run_dir)


def test_remote_stage_requires_explicit_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_prepared_inputs(monkeypatch=monkeypatch)
    run_dir = tmp_path / "run"
    prepare_run(dataset_path=tmp_path / "synthetic.json", tier="smoke", output=run_dir)
    client, raw_client = _memory_client(envelope=_empty_envelope())
    try:
        with pytest.raises(ExecutionGuardError, match="--execute"):
            ingest_sample(
                run_dir=run_dir,
                sample_id="conv-test",
                max_documents=1,
                execute=False,
                isolated_deployment_confirmation="conv-test",
                client=client,
            )
    finally:
        raw_client.close()


def _memory_client(*, envelope: Envelope) -> tuple[MemoryClient, httpx.Client]:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=envelope.model_dump(mode="json"))

    raw = httpx.Client(
        base_url="http://memory.test", transport=httpx.MockTransport(respond)
    )
    return MemoryClient(client=raw), raw


def _empty_envelope(*, known_empty: bool = False) -> Envelope:
    return Envelope(
        grain=Grain.EVIDENCE,
        freshness=Freshness(pg_live_ts=datetime(2026, 7, 23, tzinfo=timezone.utc)),
        negative=(
            Negative(kind=NegativeKind.KNOWN_EMPTY, explanation="No current claims.")
            if known_empty
            else None
        ),
    )


def _question() -> LoCoMoQuestion:
    return LoCoMoQuestion(
        item_id="conv-test/qa/0000",
        sample_id="conv-test",
        question="Where?",
        answer="Prague",
        evidence=("D1:1",),
        category=4,
    )


class _CostProvider:
    """Structured provider with exact non-zero usage for shared-ledger tests."""

    def __init__(self, *, cost: Decimal) -> None:
        self.cost = cost
        self.models: list[str] = []

    def generate(
        self, *, request: ModelRequest, response_type: type[ResponseT]
    ) -> GeneratedResponse[ResponseT]:
        self.models.append(request.model)
        payload: dict[str, str]
        if response_type is ReaderOutput:
            payload = {"answer": "Prague"}
        elif response_type is JudgeOutput:
            payload = {"label": "CORRECT"}
        else:  # pragma: no cover - the test provider supports only protocol calls
            raise AssertionError(response_type)
        return GeneratedResponse(
            output=response_type.model_validate(payload),
            usage=ProviderCallUsage(
                model_name=request.model,
                tokens_in=10,
                tokens_out=1,
                cost_usd=self.cost,
                latency_ms=1,
            ),
        )

    def embed(self, *, request: EmbeddingRequest) -> EmbeddingResponse:
        raise AssertionError(f"unexpected embed call: {request.model}")


def _patch_prepared_inputs(*, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _synthetic_dataset()
    item_ids = ("conv-test/qa/0000",)
    manifest = QuestionManifest(
        tier="smoke",
        dataset_commit=DATASET_COMMIT,
        dataset_sha256=DATASET_SHA256,
        item_ids=item_ids,
        item_ids_sha256=item_ids_hash(item_ids=item_ids),
    )
    monkeypatch.setattr(runner, "load_dataset", lambda _path: dataset)
    monkeypatch.setattr(runner, "load_manifest", lambda _tier: manifest)
    monkeypatch.setattr(runner, "_repository_revision", lambda: "a" * 40)
    monkeypatch.setattr(runner, "_repository_dirty", lambda: False)


def _synthetic_dataset() -> LoCoMoDataset:
    question = _question()
    session = LoCoMoSession(
        ordinal=1,
        session_id="D1",
        timestamp="1:00 pm on 1 May, 2023",
        turns=(
            LoCoMoTurn(speaker="Alpha", dia_id="D1:1", text="Alpha lives in Prague."),
        ),
    )
    return LoCoMoDataset(
        sha256=DATASET_SHA256,
        samples=(
            LoCoMoSample(
                sample_id="conv-test",
                speaker_a="Alpha",
                speaker_b="Beta",
                sessions=(session,),
                questions=(question,),
            ),
        ),
    )


def _run_transport(request: httpx.Request) -> httpx.Response:
    if request.method == "POST" and request.url.path == "/ingest":
        return httpx.Response(
            200,
            json={
                "deployment_id": str(UUID("57000000-0000-0000-0000-000000000001")),
                "doc_id": str(UUID("57000000-0000-0000-0000-000000000002")),
                "version_id": str(UUID("57000000-0000-0000-0000-000000000003")),
                "content_hash": hashlib.sha256(request.content).hexdigest(),
                "created": True,
            },
        )
    if request.method == "GET" and request.url.path == "/search/claims":
        return httpx.Response(200, json=_empty_envelope().model_dump(mode="json"))
    return httpx.Response(404, text="unexpected synthetic request")
