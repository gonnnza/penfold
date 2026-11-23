"""Tests del resolvedor declarativo de contexto."""

from __future__ import annotations

import pytest

from penfold.errors import ContextResolutionError
from penfold.services.context import ContextResolver


def test_resolves_literals_inputs_outputs_and_status() -> None:
    resolver = ContextResolver(
        {"feature": "JWT"},
        {"planner": {"requirements": ["a", "b"], "nested": {"ok": True}}},
        {"planner": "succeeded"},
    )
    assert resolver.resolve("texto literal") == "texto literal"
    assert resolver.resolve({"feature": "$inputs.feature", "raw": 42}) == {
        "feature": "JWT",
        "raw": 42,
    }
    assert resolver.resolve("$nodes.planner.output.requirements.0") == "a"
    assert resolver.resolve("$nodes.planner.output.nested.ok") is True
    assert resolver.resolve("$nodes.planner.output")["requirements"] == ["a", "b"]
    assert resolver.resolve("$nodes.planner.status") == "succeeded"


def test_mapping_recurses_into_lists() -> None:
    resolver = ContextResolver({"x": 1}, {}, {})
    assert resolver.resolve_mapping({"items": ["$inputs.x", "literal", {"v": "$inputs.x"}]}) == {
        "items": [1, "literal", {"v": 1}]
    }


def test_missing_inputs_and_bad_paths_fail_descriptively() -> None:
    resolver = ContextResolver({}, {"planner": {"a": 1}}, {"planner": "succeeded"})
    with pytest.raises(ContextResolutionError, match="Entrada de workflow"):
        resolver.resolve("$inputs.inexistente")
    with pytest.raises(ContextResolutionError, match="campo 'b'"):
        resolver.resolve("$nodes.planner.output.b")
    with pytest.raises(ContextResolutionError, match="mal formada"):
        resolver.resolve("$random.thing")
    with pytest.raises(ContextResolutionError, match="aún no produjo"):
        ContextResolver({}, {}, {}).resolve("$nodes.otro.output")
