"""Turn soft bits into at most one CRC-consistent 34-byte candidate.

Two techniques, both bounded so the false-candidate rate stays measurable:

* **Diversity combining**: soft bits from up to ``MAX_COMBINED`` copies of the
  same burst (the transmitter may repeat a frame) are summed before deciding.
* **Chase decoding**: if the hard decision fails CRC-16, the ``CHASE_BITS``
  least reliable CRC-covered bits are flipped in every combination (at most
  ``2**CHASE_BITS - 1`` trials) and the first CRC-consistent result is kept.

Security note.  CRC-16 here only *selects* a candidate.  With 8 flipped bits a
random wrong frame passes CRC with probability about 2**8 / 2**16 = 0.4 %; such
a candidate still has to pass the 64-bit HMAC and the replay check in
:func:`acoustic.frame.validate_frame`, so a repaired frame cannot be forged or
replayed.  Sync bytes ``A5 26`` are outside the CRC and are never flipped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import Final

import numpy as np
from numpy.typing import NDArray

from acoustic.frame import FRAME_SIZE, crc16_ccitt_false

CHASE_BITS: Final = 8
MAX_COMBINED: Final = 3
_CRC_COVERED_FIRST_BIT: Final = 2 * 8


class RecoveryMethod(StrEnum):
    SOFT = "SOFT"
    CHASE = "CHASE"
    COMBINED = "COMBINED"
    COMBINED_CHASE = "COMBINED_CHASE"


@dataclass(frozen=True, slots=True)
class RecoveredCandidate:
    raw: bytes
    method: RecoveryMethod
    flipped_bits: int
    copies: int


def bits_to_bytes(bits: NDArray[np.bool_]) -> bytes:
    """Pack LSB-first bits (byte order) into bytes."""

    grouped = np.asarray(bits, dtype=np.uint8).reshape(-1, 8)
    weights = (1 << np.arange(8, dtype=np.uint8)).astype(np.uint8)
    return bytes((grouped * weights).sum(axis=1).astype(np.uint8).tolist())


def crc_consistent(raw: bytes) -> bool:
    return len(raw) == FRAME_SIZE and crc16_ccitt_false(raw[2:32]) == int.from_bytes(
        raw[32:34], "big"
    )


def _flip_orders(count: int) -> list[tuple[int, ...]]:
    """All non-empty subsets of ``range(count)``, smallest subsets first."""

    orders: list[tuple[int, ...]] = []
    for size in range(1, count + 1):
        orders.extend(combinations(range(count), size))
    return orders


_FLIP_ORDERS: Final = _flip_orders(CHASE_BITS)


def recover(
    soft_copies: Sequence[NDArray[np.float64]],
    *,
    chase_bits: int = CHASE_BITS,
) -> RecoveredCandidate | None:
    """Return the first CRC-consistent candidate from combined soft bits, if any."""

    copies = [np.asarray(copy, dtype=np.float64) for copy in soft_copies[-MAX_COMBINED:]]
    if not copies:
        return None
    expected = FRAME_SIZE * 8
    if any(copy.shape != (expected,) for copy in copies):
        raise ValueError(f"soft bits must have shape ({expected},)")
    if not 0 <= chase_bits <= CHASE_BITS:
        raise ValueError(f"chase_bits must be in 0..{CHASE_BITS}")
    combined = np.sum(copies, axis=0)
    hard = combined > 0
    raw = bits_to_bytes(hard)
    multi = len(copies) > 1
    if crc_consistent(raw):
        method = RecoveryMethod.COMBINED if multi else RecoveryMethod.SOFT
        return RecoveredCandidate(raw, method, 0, len(copies))
    if chase_bits == 0:
        return None

    reliability = np.abs(combined)
    reliability[:_CRC_COVERED_FIRST_BIT] = np.inf
    weakest = np.argsort(reliability, kind="stable")[:chase_bits]
    orders = _FLIP_ORDERS if chase_bits == CHASE_BITS else _flip_orders(chase_bits)
    for order in orders:
        trial = hard.copy()
        trial[weakest[list(order)]] ^= True
        candidate = bits_to_bytes(trial)
        if crc_consistent(candidate):
            method = RecoveryMethod.COMBINED_CHASE if multi else RecoveryMethod.CHASE
            return RecoveredCandidate(candidate, method, len(order), len(copies))
    return None
