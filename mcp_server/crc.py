"""CRC-16/CCITT-FALSE audit utility (poly 0x1021, init 0xFFFF, no reflection, xorout 0).

Duplicated from the wire contract on purpose (the MCP process does not import
``acoustic.frame``); ``tests/test_mcp_tools.py`` asserts equality with the codec.
"""

from __future__ import annotations

from typing import Final

ALGORITHM: Final = "CRC-16/CCITT-FALSE"
POLYNOMIAL: Final = 0x1021
INITIAL: Final = 0xFFFF


def crc16_ccitt_false(data: bytes) -> int:
    crc = INITIAL
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ POLYNOMIAL) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc
