"""LangGraph refund agent with a deterministic fake model provider.

The fake provider interprets the system prompt and tool messages. This tests
Stepfork's mechanics; it is not evidence of improvement in a real model.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from stepfork.integrations.langgraph import traced_chat_model, traced_tool

BUGGY_PROMPT = "Approve a refund only when the amount is above the policy limit."
FIXED_PROMPT = "Approve a refund when the amount is at or below the policy limit."
MODEL_LABEL = "fake-refund/refund-decision-v1"
MODEL_CALLS: list[str] = []
TOOL_CALLS: list[str] = []


class RefundModel(BaseChatModel):
    """Deterministic fake provider that makes the refund decision."""

    model_name: str = "refund-decision-v1"

    @property
    def _llm_type(self) -> str:
        return "fake-refund"

    def bind_tools(self, tools: Any, **kwargs: Any) -> RefundModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        MODEL_CALLS.append(self.model_name)
        results = [message for message in messages if isinstance(message, ToolMessage)]
        if not results:
            answer = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_customer",
                        "args": {"email": "ada@example.com"},
                        "id": "lookup",
                    }
                ],
            )
        elif len(results) == 1:
            answer = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_refund_policy",
                        "args": {"tier": "gold"},
                        "id": "policy",
                    }
                ],
            )
        else:
            prompt = next(
                str(message.content)
                for message in messages
                if isinstance(message, SystemMessage)
            )
            limit = int(str(results[-1].content).split("=", 1)[1])
            amount = 80
            approved = (
                (amount <= limit) if "at or below" in prompt else (amount > limit)
            )
            answer = AIMessage(content=json.dumps({"approved": approved}))
        return ChatResult(generations=[ChatGeneration(message=answer)])


def lookup_customer(email: str) -> str:
    """Return a customer record from a fake local service."""
    TOOL_CALLS.append("lookup_customer")
    return "customer_id=c-100;tier=gold"


def get_refund_policy(tier: str) -> str:
    """Return a refund limit from a fake local policy service."""
    TOOL_CALLS.append("get_refund_policy")
    return "max_amount=100"


class RefundState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    decision: dict[str, bool] | None


def _build_graph() -> Any:
    model = traced_chat_model(RefundModel())
    tools = [traced_tool(lookup_customer), traced_tool(get_refund_policy)]

    def agent_node(state: RefundState) -> dict[str, Any]:
        return {"messages": [model.invoke(state["messages"])]}

    def route(state: RefundState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else "finalize"

    def finalize(state: RefundState) -> dict[str, Any]:
        last = state["messages"][-1]
        return {"decision": json.loads(str(last.content))}

    builder: StateGraph[RefundState] = StateGraph(RefundState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route, {"tools": "tools", "finalize": "finalize"}
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("finalize", END)
    return builder.compile()


def _run(prompt: str) -> dict[str, bool]:
    graph = _build_graph()
    result = graph.invoke(
        {
            "messages": [
                SystemMessage(content=prompt),
                HumanMessage(content="Refund Ada's $80 purchase?"),
            ]
        }
    )
    return dict(result["decision"] or {})


def run_buggy() -> dict[str, bool]:
    return _run(BUGGY_PROMPT)


def run_fixed() -> dict[str, bool]:
    return _run(FIXED_PROMPT)
