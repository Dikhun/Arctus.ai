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
# Planner
# ==========================================================


    SIMPLE_KEYWORDS = {
        "what",
        "who",
        "when",
        "where",
        "define",
        "meaning",
        "translate",
        "weather",
    }

    def decide(self, prompt: str) -> ExecutionMode:

        words = prompt.lower().split()

        if (
            len(words) < 40
            and any(w in self.SIMPLE_KEYWORDS for w in words)
            and "build" not in prompt.lower()
            and "architecture" not in prompt.lower()
        ):
            return ExecutionMode.FAST_PATH

        return ExecutionMode.PARALLEL


# ==========================================================
# Context Isolation
# ==========================================================

class ContextExtractor:

    def extract(self, history: list[str], task: Task) -> str:

        """
        Only pass relevant context.

        Never send the entire conversation.
        """

        relevant = []

        for item in history[-8:]:

            if task.title.lower() in item.lower():
                relevant.append(item)

        return "\n".join(relevant)


# ==========================================================
# Prompt Framing
# ==========================================================

class PromptFramer:

    def build(self, task: Task) -> str:

        return (
            f"You are an expert {task.role}. "
            f"According to {task.domain}, "
            f"your task is to {task.action}.\n\n"
            f"{task.context}"
        )


# ==========================================================
# Interfaces
# ==========================================================

LLMCallable = Callable[[str], Awaitable[str]]


# ==========================================================
# Dispatcher
# ==========================================================

class Dispatcher:

    def __init__(self, llm: LLMCallable):

        self.llm = llm

    async def dispatch(self, tasks: list[Task]) -> list[TaskResult]:

        results: list[TaskResult] = []

        async with asyncio.TaskGroup() as tg:

            future_map = {}

            for task in tasks:

                future = tg.create_task(
                    self.llm(
                        PromptFramer().build(task)
                    )
                )

                future_map[future] = task

        for future, task in future_map.items():

            results.append(
                TaskResult(
                    task_id=task.id,
                    output=future.result(),
                )
            )

        return results


# ==========================================================
# Synthesizer
# ==========================================================

class Synthesizer:

    async def merge(
        self,
        results: list[TaskResult],
        llm: LLMCallable,
    ) -> str:

        joined = "\n\n".join(
            f"{r.task_id}\n{r.output}"
            for r in results
        )

        prompt = f"""
You are Queen Agent.

Combine all worker outputs into one coherent response.

Requirements:

- Remove duplicates
- Resolve contradictions
- Preserve technical accuracy
- Produce one final answer

Worker Results

{joined}
"""

        return await llm(prompt)


# ==========================================================
# Queen Agent
# ==========================================================

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

        tasks = await self.plan(request)

        # -----------------------------
        # Fast Path
        # -----------------------------

        if mode is ExecutionMode.FAST_PATH:

            return await self.llm(request.prompt)

        # -----------------------------
        # Planning
        # -----------------------------

        tasks = await self.plan(request)

        dispatcher = Dispatcher(self.llm)

        results = await dispatcher.dispatch(tasks)

        return await self.synthesizer.merge(
            results,
            self.llm,
        )
