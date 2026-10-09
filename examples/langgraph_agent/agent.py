"""Offline LangGraph agent example for Stepfork.

A deterministic scripted chat model stands in for a real LLM, so this example
never needs an API key, network access, or a paid provider. The agent looks up
a customer, reads the refund policy, and decides whether a fixed refund can be
approved. The buggy variant inverts the eligibility comparison.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import Field
from typing_extensions import TypedDict

from stepfork.integrations.langgraph import traced_chat_model, traced_tool

MODEL_NAME = "scripted-triage-model"
CUSTOMER_EMAIL = "ada@example.com"
REFUND_AMOUNT = 80

MODEL_EXECUTIONS: list[str] = []
TOOL_EXECUTIONS: list[tuple[str, str]] = []

SCRIPT: list[AIMessage] = [
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "lookup_customer",
                "args": {"email": CUSTOMER_EMAIL},
                "id": "call_lookup",
            }
        ],
    ),
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_refund_policy",
                "args": {"tier": "gold"},
                "id": "call_policy",
            }
        ],
    ),
    AIMessage(content="Triage complete."),
]


class ScriptedChatModel(BaseChatModel):
    """Deterministic chat model that returns a fixed script of messages."""

    model_name: str = MODEL_NAME
    script: list[AIMessage] = Field(default_factory=list)
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        MODEL_EXECUTIONS.append(self.model_name)
        index = min(self.cursor, len(self.script) - 1)
        self.cursor = index + 1
        return ChatResult(
            generations=[ChatGeneration(message=self.script[index])],
        )


def lookup_customer(email: str) -> str:
    """Look up a customer record by email address."""
    TOOL_EXECUTIONS.append(("lookup_customer", email))
    return "customer_id=c-100;tier=gold;name=Ada"


def get_refund_policy(tier: str) -> str:
    """Return the refund limit for a customer tier."""
    TOOL_EXECUTIONS.append(("get_refund_policy", tier))
    return "max_amount=100"


class TriageState(TypedDict):
    """Messages exchanged by the graph plus the final decision."""

    messages: Annotated[list[BaseMessage], add_messages]
    decision: dict[str, Any] | None


def _build_graph(*, buggy: bool) -> Any:
    model = traced_chat_model(ScriptedChatModel(script=list(SCRIPT)))
    tools = [traced_tool(lookup_customer), traced_tool(get_refund_policy)]
    model_with_tools = model.bind_tools(tools)

    def agent_node(state: TriageState) -> dict[str, Any]:
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def route(state: TriageState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else "finalize"

    def finalize(state: TriageState) -> dict[str, Any]:
        customer_id = _customer_id(state["messages"])
        maximum = _max_amount(state["messages"])
        approved = maximum < REFUND_AMOUNT if buggy else maximum >= REFUND_AMOUNT
        return {
            "decision": {
                "approved": approved,
                "customer_id": customer_id,
            }
        }

    builder: StateGraph[TriageState] = StateGraph(TriageState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route,
        {"tools": "tools", "finalize": "finalize"},
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("finalize", END)
    return builder.compile()


def _tool_content(messages: list[BaseMessage], name: str) -> str:
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == name:
            return str(message.content)
    return ""


def _customer_id(messages: list[BaseMessage]) -> str:
    for token in _tool_content(messages, "lookup_customer").split(";"):
        if token.startswith("customer_id="):
            return token.split("=", 1)[1]
    return ""


def _max_amount(messages: list[BaseMessage]) -> int:
    for token in _tool_content(messages, "get_refund_policy").split(";"):
        if token.startswith("max_amount="):
            return int(token.split("=", 1)[1])
    return 0


def run_agent() -> dict[str, Any]:
    """Buggy triage: approves only refunds that exceed the policy limit."""
    graph = _build_graph(buggy=True)
    result = graph.invoke({"messages": [HumanMessage(content="Refund for Ada?")]})
    return dict(result["decision"] or {})


def run_agent_fixed() -> dict[str, Any]:
    """Corrected triage: approves refunds within the policy limit."""
    graph = _build_graph(buggy=False)
    result = graph.invoke({"messages": [HumanMessage(content="Refund for Ada?")]})
    return dict(result["decision"] or {})


EXPECTED_OUTPUT: dict[str, Any] = {"approved": True, "customer_id": "c-100"}
