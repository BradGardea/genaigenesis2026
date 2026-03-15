"""Pydantic models for agent orchestration, metadata, messaging, and tracing."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Agent registry / metadata ────────────────────────────────────────

class AgentMetadata(BaseModel):
    """Describes an agent's identity, configuration, and place in the graph."""

    agent_id: str = Field(description="Unique key, e.g. 'meteorologist', 'decision'")
    display_name: str = Field(description="Human-readable name")
    description: str = Field(description="What this agent does")
    model_id: str = "meta-llama/llama-3-3-70b-instruct"
    max_tokens: int = 500
    temperature: float = 0.1
    capabilities: list[str] = Field(
        default_factory=list,
        description="Tags like 'weather_analysis', 'risk_assessment', 'route_evaluation'",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="agent_ids this agent requires input from",
    )


# ── Orchestration plan (declarative DAG) ─────────────────────────────

class AgentStep(BaseModel):
    """A single step in an orchestration plan."""

    agent_id: str = Field(description="Which agent to run")
    depends_on: list[str] = Field(
        default_factory=list,
        description="agent_ids that must complete before this step runs",
    )
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Maps context keys: {local_key: 'upstream_agent_id.output_key'}",
    )
    timeout_seconds: float = Field(default=10.0, gt=0)
    required: bool = Field(
        default=True,
        description="If False, failure does not block downstream steps",
    )


class OrchestrationPlan(BaseModel):
    """Declarative DAG describing how agents are composed."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="e.g. 'evacuation_decision', 'full_briefing'")
    steps: list[AgentStep]
    max_parallel: int = Field(default=5, ge=1, description="Concurrency cap for parallel steps")


# ── Inter-agent messaging ────────────────────────────────────────────

class AgentMessage(BaseModel):
    """Typed message passed between agents during orchestration."""

    from_agent: str
    to_agent: str
    message_type: Literal["briefing", "request", "result", "error"]
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Execution trace / audit ──────────────────────────────────────────

class AgentExecutionTrace(BaseModel):
    """Audit record for a single agent invocation."""

    agent_id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: Literal["success", "fallback", "error"]
    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(ge=0)
    used_llm: bool
    model_id: str = ""
    input_context_keys: list[str] = Field(default_factory=list)
    output_summary: str = ""
    error_message: str | None = None


class OrchestrationResult(BaseModel):
    """Full result of a multi-agent orchestration run."""

    plan_id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: Literal["completed", "partial", "failed"]
    traces: list[AgentExecutionTrace] = Field(default_factory=list)
    final_output: dict[str, Any] = Field(default_factory=dict)
    total_duration_ms: float = Field(ge=0)
    agents_used_llm: int = Field(default=0, ge=0)
    agents_used_fallback: int = Field(default=0, ge=0)
