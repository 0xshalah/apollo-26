"""Schema validation for the MCP side of every process boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

RPC_SCHEMA: Final = "mcp-daemon-rpc.schema.json"
TELEMETRY_SCHEMA: Final = "telemetry-frame.schema.json"
AUDIT_SCHEMA: Final = "mcp-audit-event.schema.json"
CATALOG_SCHEMA: Final = "dsky-command-catalog.schema.json"
CATALOG_FILE: Final = "dsky-command-catalog-v1.json"
_BASE: Final = "https://apollo-26.local/schemas/"


class SchemaError(ValueError):
    def __init__(self, label: str, message: str) -> None:
        super().__init__(f"{label}: {message}")
        self.label = label


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SchemaError(path.name, "contract is not a JSON object")
    return value


@dataclass(frozen=True)
class BridgeContracts:
    documents: dict[str, dict[str, Any]]
    registry: Registry
    catalog: dict[str, Any]
    _cache: dict[tuple[str, str | None], Draft202012Validator] = field(
        default_factory=dict, compare=False, repr=False
    )

    @classmethod
    def load(cls, contracts_dir: Path) -> BridgeContracts:
        documents = {
            name: _read(contracts_dir / name)
            for name in (RPC_SCHEMA, TELEMETRY_SCHEMA, AUDIT_SCHEMA, CATALOG_SCHEMA)
        }
        registry: Registry = Registry()
        for name, document in documents.items():
            resource = Resource.from_contents(document)
            registry = registry.with_resource(document["$id"], resource).with_resource(
                _BASE + name, resource
            )
        catalog = _read(contracts_dir / CATALOG_FILE)
        contracts = cls(documents=documents, registry=registry, catalog=catalog)
        contracts.validate(CATALOG_SCHEMA, catalog)
        return contracts

    def _validator(self, name: str, pointer: str | None) -> Draft202012Validator:
        key = (name, pointer)
        if key not in self._cache:
            document = self.documents[name]
            schema = document if pointer is None else {"$ref": f"{document['$id']}#{pointer}"}
            self._cache[key] = Draft202012Validator(
                schema, registry=self.registry, format_checker=FormatChecker()
            )
        return self._cache[key]

    def validate(self, name: str, payload: object, pointer: str | None = None) -> None:
        errors = sorted(self._validator(name, pointer).iter_errors(payload), key=lambda e: e.path)
        if errors:
            first = errors[0]
            path = "/".join(str(part) for part in first.absolute_path)
            label = name if pointer is None else f"{name}#{pointer}"
            raise SchemaError(label, f"at '/{path}': {first.message[:200]}")

    def validate_rpc(self, pointer: str, payload: object) -> None:
        self.validate(RPC_SCHEMA, payload, pointer)

    def validate_audit(self, payload: object) -> None:
        self.validate(AUDIT_SCHEMA, payload)
