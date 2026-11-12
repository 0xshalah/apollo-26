from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from acoustic.frame import (
    CommandFrame,
    KeyMaterial,
    RejectReason,
    Verdict,
    encode_frame,
    validate_and_commit_frame,
)
from acoustic.sequence import (
    FileSequenceStore,
    SequenceErrorCode,
    SequenceStatus,
    SequenceStoreError,
)

KEYS = KeyMaterial(b"apollo26-link-demo-key-v1", b"apollo26-operator-demo-key-v1")


def _command(seq: int) -> bytes:
    return encode_frame(
        CommandFrame(
            seq=seq,
            critical=False,
            verb=25,
            noun=0,
            program=0,
            r1_centidegrees=0,
            r2_centidegrees=0,
            delta_v_tenths_fps=0,
        ),
        KEYS,
    )


def test_missing_state_fails_closed_without_implicit_provision(tmp_path: Path) -> None:
    state_path = tmp_path / "sequence.json"
    store = FileSequenceStore(state_path)

    with pytest.raises(SequenceStoreError) as error:
        store.load()

    assert error.value.code is SequenceErrorCode.MISSING
    assert store.status is SequenceStatus.DEGRADED
    assert not state_path.exists()


@pytest.mark.parametrize(
    "document, expected_code",
    [
        ("not-json", SequenceErrorCode.MALFORMED),
        ('{"schema_version":"2.0","last_accepted_seq":0}', SequenceErrorCode.UNSUPPORTED_VERSION),
        ('{"schema_version":"1.0","last_accepted_seq":-1}', SequenceErrorCode.OUT_OF_RANGE),
        ('{"schema_version":"1.0","last_accepted_seq":true}', SequenceErrorCode.OUT_OF_RANGE),
        ('{"schema_version":"1.0","last_accepted_seq":0,"extra":1}', SequenceErrorCode.MALFORMED),
    ],
)
def test_corrupt_sequence_state_fails_closed(
    tmp_path: Path, document: str, expected_code: SequenceErrorCode
) -> None:
    state_path = tmp_path / "sequence.json"
    state_path.write_text(document, encoding="utf-8")
    store = FileSequenceStore(state_path)

    with pytest.raises(SequenceStoreError) as error:
        store.load()

    assert error.value.code is expected_code
    assert store.status is SequenceStatus.DEGRADED
    with pytest.raises(SequenceStoreError):
        _ = store.last_accepted_seq


def test_p6_restart_persists_replay_boundary(tmp_path: Path) -> None:
    state_path = tmp_path / "sequence.json"
    first_process = FileSequenceStore(state_path)
    first_process.provision(41)

    accepted = validate_and_commit_frame(_command(42), KEYS, first_process)

    assert accepted.verdict is Verdict.ACCEPTED
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted == {"schema_version": "1.0", "last_accepted_seq": 42}
    assert not list(tmp_path.glob(".sequence.json.*.tmp"))

    restarted_process = FileSequenceStore(state_path)
    restarted_process.load()
    replay = validate_and_commit_frame(_command(42), KEYS, restarted_process)

    assert replay.reason is RejectReason.REPLAY
    assert restarted_process.last_accepted_seq == 42


def test_commit_uses_atomic_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "sequence.json"
    store = FileSequenceStore(state_path)
    store.provision(1)
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        replacements.append((Path(source), Path(target)))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", recording_replace)
    store.commit(2)

    assert len(replacements) == 1
    source, target = replacements[0]
    assert source.parent == state_path.parent
    assert target == state_path
    assert not source.exists()


def test_commit_failure_degrades_and_preserves_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "sequence.json"
    store = FileSequenceStore(state_path)
    store.provision(7)
    original = state_path.read_bytes()

    def failing_replace(source: object, target: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(SequenceStoreError) as error:
        store.commit(8)

    assert error.value.code is SequenceErrorCode.COMMIT
    assert store.status is SequenceStatus.DEGRADED
    assert state_path.read_bytes() == original
    assert not list(tmp_path.glob(".sequence.json.*.tmp"))


def test_exhausted_state_is_loaded_but_locked(tmp_path: Path) -> None:
    store = FileSequenceStore(tmp_path / "sequence.json")
    store.provision(0xFFFFFFFF)

    restarted = FileSequenceStore(store.path)
    state = restarted.load()

    assert state.last_accepted_seq == 0xFFFFFFFF
    assert restarted.status is SequenceStatus.EXHAUSTED
    with pytest.raises(SequenceStoreError) as error:
        restarted.commit(0xFFFFFFFF)
    assert error.value.code is SequenceErrorCode.EXHAUSTED
