"""Agent loop tests with a scripted router (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mitra.agent import ChatAgent
from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel
from mitra.models.router import LLMResponse, ToolCall
from mitra.policy import PolicyEngine
from mitra.tools import TOOL_SPECS, ToolBox


@dataclass
class ScriptedRouter:
    responses: list[LLMResponse]
    provider: str = "nebius"
    daily_budget_usd: float = 10.0
    calls: list[list[dict[str, Any]]] = field(default_factory=list)

    def model_for(self, purpose: str) -> str:
        return "test/model"

    def budget_exceeded(self) -> bool:
        return False

    schemas: list[Any] = field(default_factory=list)

    def chat(self, *, messages, tool_schemas=None, **kwargs) -> LLMResponse:
        self.calls.append(messages)
        self.schemas.append(tool_schemas)
        return self.responses.pop(0)


def _agent(tmp_path, responses):
    ledger = Ledger(tmp_path / "ledger.db")
    selfmodel = SelfModel(tmp_path / "self_model")
    selfmodel.write("priorities.md", "- Ship the submission.\n")
    router = ScriptedRouter(responses)
    policy = PolicyEngine(ledger, tools=TOOL_SPECS)
    toolbox = ToolBox(ledger, selfmodel, data_dir=tmp_path, policy=policy)
    return ChatAgent(ledger, router, selfmodel, toolbox), ledger, selfmodel


def test_reply_persists_messages_and_sources(tmp_path):
    agent, ledger, _ = _agent(
        tmp_path, [LLMResponse(content="Two things need you.", provider="nebius")]
    )
    session = agent.new_session("test")
    reply = agent.reply(session, "What needs a decision?")
    assert reply.text == "Two things need you."
    messages = ledger.messages(session)
    assert [m.role for m in messages] == ["assistant", "user"]  # newest first
    assert ledger.messages(session)[0].content == "Two things need you."
    assert "priorities.md" in reply.sources
    assert reply.provider == "nebius"


def test_tool_call_is_policy_checked_and_audited(tmp_path):
    tool_call = ToolCall(id="call_1", name="memory_search", arguments={"query": "submission"})
    agent, ledger, _ = _agent(
        tmp_path,
        [
            LLMResponse(content="", tool_calls=[tool_call], provider="nebius"),
            LLMResponse(content="Memory says: ship the submission.", provider="nebius"),
        ],
    )
    session = agent.new_session("tool test")
    reply = agent.reply(session, "Check memory for the submission")
    assert "ship the submission" in reply.text
    decisions = [row for row in ledger.audit_log() if row["action"] == "tool_call"]
    assert decisions and decisions[0]["target"] == "memory_search"
    assert any(row["action"] == "tool_exec" for row in ledger.audit_log())
    assert any(step["stage"] == "tool" for step in reply.trace)


def test_approval_required_is_surfaced_not_executed(tmp_path):
    tool_call = ToolCall(id="call_2", name="note_write", arguments={"title": "x", "body": "y"})
    agent, ledger, _ = _agent(
        tmp_path,
        [
            LLMResponse(content="", tool_calls=[tool_call], provider="nebius"),
            LLMResponse(content="The note needs your approval first.", provider="nebius"),
        ],
    )
    session = agent.new_session("approval test")
    reply = agent.reply(session, "Save a note")
    assert "approval" in reply.text.lower()
    assert len(ledger.approvals(status="pending")) == 1
    assert not list((tmp_path / "notes").glob("*.md"))


def test_empty_model_answer_is_not_fabricated(tmp_path):
    agent, _, _ = _agent(tmp_path, [LLMResponse(content="", provider="nebius")])
    session = agent.new_session("empty")
    reply = agent.reply(session, "hello")
    assert "empty answer" in reply.text


def test_exhausted_tool_budget_still_answers_from_what_the_tools_returned(tmp_path):
    """Running out of rounds must degrade to an answer, not to an apology."""
    from mitra.agent import MAX_TOOL_ROUNDS

    responses = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id=f"call_{index}", name="commitment_status", arguments={})],
            provider="nebius",
        )
        for index in range(MAX_TOOL_ROUNDS)
    ]
    responses.append(
        LLMResponse(content="The brief said the weekly scan failed.", provider="nebius")
    )
    agent, ledger, _ = _agent(tmp_path, responses)
    session = agent.new_session("budget")
    reply = agent.reply(session, "What did the brief say?")

    assert reply.text == "The brief said the weekly scan failed."
    assert reply.cost_usd >= 0
    assert any("closing" in step["label"] for step in reply.trace if step.get("label"))
    # The closing call must not offer tools again, or it loops.
    assert agent.router.schemas[-1] == []
    assert ledger.messages(session)[0].content == reply.text


def test_a_promise_to_look_something_up_is_not_accepted_as_the_answer(tmp_path):
    """Live models say "let me check" and stop. Nudge once, then answer."""
    from mitra.agent import _promises_action

    assert _promises_action("Let me check the actual artifact.")
    assert _promises_action("I'll look up yesterday's brief.")
    assert not _promises_action("Let me know if you want the details.")
    assert not _promises_action("Yes, it was delivered at 07:00.")

    agent, _ledger, _ = _agent(
        tmp_path,
        [
            LLMResponse(content="Let me check the artifact.", provider="nebius"),
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_9", name="commitment_status", arguments={})],
                provider="nebius",
            ),
            LLMResponse(content="It was delivered at 07:00.", provider="nebius"),
        ],
    )
    session = agent.new_session("nudge")
    reply = agent.reply(session, "Did yesterday's brief deliver?")

    assert reply.text == "It was delivered at 07:00."
    assert any(step["stage"] == "tool" for step in reply.trace)
    assert any(step["stage"] == "nudge" for step in reply.trace)
