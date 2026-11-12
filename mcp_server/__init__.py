"""Apollo-26 MCP bridge (stdio) with a code-enforced safety gate.

This package never imports ``agc_core`` or ``acoustic``; it talks to the
acoustic daemon only through the schema-validated local RPC on 127.0.0.1.
"""
