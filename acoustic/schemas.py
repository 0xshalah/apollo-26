"""Contract-schema validators for daemon boundaries.

Schemas are read once by the composition root from an explicit ``contracts_dir``;
library code never locates or reads contract files implicitly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

TELEMETRY_SCHEMA = "telemetry-frame.schema.json"
WEBSOCKET_SCHEMA = "websocket-events.schema.json"
RPC_SCHEMA = "mcp-daemon-rpc.schema.json"
CATALOG_SCHEMA = "dsky-command-catalog.schema.json"
CATALOG_FILE = "dsky-command-catalog-v1.json"
_RELATIVE_BASE = "https://apollo-26.local/schemas/"


class ContractViolation(ValueError):
    """A payload failed its versioned contract schema."""

    def __init__(self, contract: str, error: ValidationError) -> None:
        path = "/".join(str(part) for part in error.absolute_path)
        super().__init__(f"{contract} violation at '/{path}': {error.message[:200]}")
        self.contract = contract


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"contract {path.name} is not a JSON object")
    return value


@dataclass(frozen=True)
class ContractSchemas:
    """Validators for every contract the daemon reads or writes."""

    registry: Registry
    documents: dict[str, dict[str, Any]]
    _cache: dict[tuple[str, str | None], Draft202012Validator] = field(
        default_factory=dict, compare=False, repr=False
    )

    @classmethod
    def load(cls, contracts_dir: Path) -> ContractSchemas:
        documents = {
            name: _load_json(contracts_dir / name)
            for name in (TELEMETRY_SCHEMA, WEBSOCKET_SCHEMA, RPC_SCHEMA, CATALOG_SCHEMA)
        }
        registry: Registry = Registry()
        for name, document in documents.items():
            resource = Resource.from_contents(document)
            registry = registry.with_resource(document["$id"], resource)
            # Relative ``$ref: "<file>.schema.json"`` resolves against the shared base.
            registry = registry.with_resource(_RELATIVE_BASE + name, resource)
        return cls(registry=registry, documents=documents)

    def _validator(self, name: str, pointer: str | None = None) -> Draft202012Validator:
        cached = self._cache.get((name, pointer))
        if cached is not None:
            return cached
        document = self.documents[name]
        schema: dict[str, Any] = (
            document if pointer is None else {"$ref": f"{document['$id']}#{pointer}"}
        )
        validator = Draft202012Validator(
            schema, registry=self.registry, format_checker=FormatChecker()
        )
        self._cache[(name, pointer)] = validator
        return validator

    def validate(self, name: str, payload: object, pointer: str | None = None) -> None:
        validator = self._validator(name, pointer)
        error = next(iter(sorted(validator.iter_errors(payload), key=lambda e: e.path)), None)
        if error is not None:
            label = name if pointer is None else f"{name}#{pointer}"
            raise ContractViolation(label, error)

    def validate_telemetry(self, record: object) -> None:
        self.validate(TELEMETRY_SCHEMA, record)

    def validate_ws_event(self, event: object) -> None:
        self.validate(WEBSOCKET_SCHEMA, event)

    def validate_rpc(self, pointer: str, payload: object) -> None:
        self.validate(RPC_SCHEMA, payload, pointer)


def load_catalog_document(contracts_dir: Path, schemas: ContractSchemas) -> dict[str, Any]:
    """Read and schema-validate the DSKY command catalog once at startup."""

    document = _load_json(contracts_dir / CATALOG_FILE)
    schemas.validate(CATALOG_SCHEMA, document)
    return document
