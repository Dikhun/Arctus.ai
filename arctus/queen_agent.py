"""
Queen Agent
Python 3.13+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

import asyncio
from pydantic import BaseModel, Field
from arctus.queen_module import (
    ModelRouter,
    PlanningModule,
    CapabilitiesRouter,
    AgentAllocator,
    WorkflowPlanner,
    ContextManager,
    ContextExtractor,
    MemoryRouter,
    Dispatcher,
    CommunicationModule,
    VerificationManager,
    Synthesizer,
    LearningManager,
    ProviderHealthMonitor,
    RetryManager,
    CostOptimizer,
)


# ==========================================================
# Models
# ==========================================================

class ExecutionMode(str, Enum):
    FAST_PATH = "fast_path"
    PARALLEL = "parallel"


class UserRequest(BaseModel):
    prompt: str
    history: list[str] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    title: str
    role: str
    domain: str
    action: str
    context: str


class TaskResult(BaseModel):
    task_id: str
    output: str


# ==========================================================
# Interfaces
# ==========================================================

LLMCallable = Callable[[str], Awaitable[str]]

@dataclass(slots=True)
class QueenAgent:

    llm: LLMCallable

    model_router: ModelRouter = field(default_factory=ModelRouter)
    planning_module: PlanningModule = field(default_factory=PlanningModule)
    capabilities_router: CapabilitiesRouter = field(default_factory=CapabilitiesRouter)
    agent_allocator: AgentAllocator = field(default_factory=AgentAllocator)
    workflow_planner: WorkflowPlanner = field(default_factory=WorkflowPlanner)
    context_manager: ContextManager = field(default_factory=ContextManager)
    context_extractor: ContextExtractor = field(default_factory=ContextExtractor)
    memory_router: MemoryRouter = field(default_factory=MemoryRouter)
    dispatcher: Dispatcher = field(default_factory=Dispatcher)
    communication_module: CommunicationModule = field(default_factory=CommunicationModule)
    verification_manager: VerificationManager = field(default_factory=VerificationManager)
    synthesizer: Synthesizer = field(default_factory=Synthesizer)
    learning_manager: LearningManager = field(default_factory=LearningManager)
    provider_health: ProviderHealthMonitor = field(default_factory=ProviderHealthMonitor)
    retry_manager: RetryManager = field(default_factory=RetryManager)
    cost_optimizer: CostOptimizer = field(default_factory=CostOptimizer)

    async def run(
        self,
        request: UserRequest,
    ) -> str:

        tasks = await self.planning_module.plan(request)

        # -----------------------------
        # Fast Path
if mode == ExecutionMode.FAST_PATH:  # or `if mode is ExecutionMode.FAST_PATH:`
    return await self.llm(request.prompt)

        # -----------------------------
        # Planning
        # -----------------------------

        results = await self.dispatcher.dispatch(tasks)
        return await self.synthesizer.merge(
            results,
            self.llm,
        )
