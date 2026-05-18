"""Tests for ToolRegistry.set_enforcement_fn / enforcement hook."""
import json
import pytest
from tools.registry import ToolRegistry


def _make_registry_with_tool(name: str = "test_tool") -> ToolRegistry:
    r = ToolRegistry()
    r.register(
        name=name,
        toolset="test",
        schema={"name": name, "description": "test"},
        handler=lambda args, **kw: json.dumps({"result": "ok"}),
    )
    return r


class TestEnforcementFn:

    def test_dispatch_succeeds_without_enforcement_fn(self):
        r = _make_registry_with_tool()
        result = json.loads(r.dispatch("test_tool", {}))
        assert result == {"result": "ok"}

    def test_enforcement_fn_blocks_dispatch(self):
        """Raising in the enforcement fn prevents the handler from running."""
        r = _make_registry_with_tool()
        r.set_enforcement_fn(
            lambda name, args, **kw: (_ for _ in ()).throw(
                PermissionError(f"{name} denied by enforcement fn")
            )
        )
        result = json.loads(r.dispatch("test_tool", {}))
        assert "error" in result
        assert "denied" in result["error"]

    def test_enforcement_fn_allow_passes_through(self):
        """An enforcement fn that does NOT raise allows the call."""
        r = _make_registry_with_tool()
        r.set_enforcement_fn(lambda name, args, **kw: None)  # always allow
        result = json.loads(r.dispatch("test_tool", {}))
        assert result == {"result": "ok"}

    def test_enforcement_fn_receives_tool_name_and_args(self):
        """The enforcement fn receives name and args for policy decisions."""
        received = {}
        def capture(name, args, **kw):
            received["name"] = name
            received["args"] = args

        r = _make_registry_with_tool()
        r.set_enforcement_fn(capture)
        r.dispatch("test_tool", {"key": "value"})
        assert received["name"] == "test_tool"
        assert received["args"] == {"key": "value"}

    def test_enforcement_fn_receives_kwargs(self):
        """The enforcement fn receives kwargs (e.g. task_id, session_id) for context."""
        received = {}
        def capture(name, args, **kw):
            received.update(kw)

        r = _make_registry_with_tool()
        r.set_enforcement_fn(capture)
        r.dispatch("test_tool", {}, task_id="session-abc", user_id="u1")
        assert received.get("task_id") == "session-abc"

    def test_set_enforcement_fn_none_removes_hook(self):
        """Passing None clears a previously registered enforcement fn."""
        r = _make_registry_with_tool()
        r.set_enforcement_fn(lambda n, a, **kw: (_ for _ in ()).throw(PermissionError("blocked")))
        # Confirm it blocks
        result = json.loads(r.dispatch("test_tool", {}))
        assert "error" in result
        # Now clear it
        r.set_enforcement_fn(None)
        result2 = json.loads(r.dispatch("test_tool", {}))
        assert result2 == {"result": "ok"}

    def test_enforcement_fn_error_message_in_result(self):
        """The exception message surfaces as the tool error string."""
        r = _make_registry_with_tool()
        r.set_enforcement_fn(
            lambda n, a, **kw: (_ for _ in ()).throw(
                PermissionError("path constraint violated: /etc not in /data")
            )
        )
        result = json.loads(r.dispatch("test_tool", {"path": "/etc/passwd"}))
        assert "path constraint violated" in result["error"]

    def test_enforcement_fn_does_not_affect_unknown_tool(self):
        """Unknown tools still return their own error regardless of enforcement fn."""
        r = _make_registry_with_tool()
        r.set_enforcement_fn(lambda n, a, **kw: None)
        result = json.loads(r.dispatch("nonexistent_tool", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]
