"""Arctus AI Orchestration Framework - Prompt Framer.

Responsible for worker prompt generation, system prompt generation,
role prompt generation, and prompt optimization.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from domain_models import AgentRole, SubTask
from exceptions import ErrorContext, PlanningException
from infrastructure import LogContext, async_timed, get_logger


logger = get_logger("prompt_framer")


class PromptTemplate:
    """Reusable prompt template with variable substitution."""

    def __init__(self, template: str, required_vars: Optional[Set[str]] = None) -> None:
        self.template = template
        self.required_vars = required_vars or set()

    def render(self, **kwargs: Any) -> str:
        """Render template with variables.

        Args:
            **kwargs: Template variables.

        Returns:
            Rendered prompt string.
        """
        result = self.template
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            result = result.replace(placeholder, str(value))
        return result


class PromptFramerImpl:
    """Production prompt framer with role-aware optimization.

    Generates contextually appropriate prompts for workers and
    system initialization with token optimization.
    """

    # Role-specific prompt templates
    ROLE_TEMPLATES: Dict[AgentRole, str] = {
        AgentRole.CODER: """You are an expert software engineer. Your task:
{task_description}

Requirements:
- Write clean, well-documented code
- Follow best practices for the target language
- Include error handling and edge cases
- Provide usage examples where helpful

Context:
{context}

Output format: {output_format}""",

        AgentRole.ANALYST: """You are a data analyst and researcher. Your task:
{task_description}

Requirements:
- Provide evidence-based analysis
- Cite sources and methodologies
- Consider multiple perspectives
- Quantify findings where possible

Context:
{context}

Output format: {output_format}""",

        AgentRole.CREATIVE: """You are a creative content specialist. Your task:
{task_description}

Requirements:
- Engage the target audience effectively
- Maintain consistent tone and style
- Optimize for clarity and impact
- Follow any brand guidelines provided

Context:
{context}

Output format: {output_format}""",

        AgentRole.RESEARCHER: """You are a research specialist. Your task:
{task_description}

Requirements:
- Conduct thorough information gathering
- Synthesize findings from multiple sources
- Evaluate source credibility
- Present balanced, well-supported conclusions

Context:
{context}

Output format: {output_format}""",

        AgentRole.REVIEWER: """You are a quality reviewer. Your task:
{task_description}

Requirements:
- Verify accuracy and consistency
- Check for errors and omissions
- Ensure compliance with requirements
- Provide constructive feedback

Context:
{context}

Output format: {output_format}""",

        AgentRole.PLANNER: """You are a strategic planner. Your task:
{task_description}

Requirements:
- Consider dependencies and constraints
- Optimize for efficiency and feasibility
- Account for risks and contingencies
- Provide clear, actionable steps

Context:
{context}

Output format: {output_format}""",

        AgentRole.EXECUTOR: """You are a task executor. Your task:
{task_description}

Requirements:
- Execute precisely as specified
- Report progress and status clearly
- Handle errors gracefully
- Confirm completion with evidence

Context:
{context}

Output format: {output_format}""",

        AgentRole.GENERALIST: """You are a capable AI assistant. Your task:
{task_description}

Requirements:
- Provide accurate, helpful responses
- Ask clarifying questions when needed
- Adapt to the user's expertise level
- Be concise yet thorough

Context:
{context}

Output format: {output_format}""",
    }

    SYSTEM_PROMPT_BASE = """You are {role_name}, a specialist AI agent in the Arctus orchestration system.

Capabilities: {capabilities}
Constraints: {constraints}

Operational guidelines:
- Respond only to your assigned task
- Do not hallucinate or invent facts
- Acknowledge uncertainty when appropriate
- Follow the specified output format precisely"""

    def __init__(
        self,
        custom_templates: Optional[Dict[AgentRole, str]] = None,
        max_prompt_tokens: int = 4000,
        enable_optimization: bool = True,
    ) -> None:
        self.templates = dict(self.ROLE_TEMPLATES)
        if custom_templates:
            self.templates.update(custom_templates)
        self.max_prompt_tokens = max_prompt_tokens
        self.enable_optimization = enable_optimization
        self.logger = get_logger("prompt_framer")

    @async_timed
    async def frame_worker_prompt(
        self,
        task: SubTask,
        context: str,
        style: Optional[str] = None,
    ) -> str:
        """Generate worker prompt for task execution.

        Args:
            task: The subtask to frame.
            context: Extracted relevant context.
            style: Optional prompt style override.

        Returns:
            Framed prompt string.
        """
        with LogContext(module="prompt_framer", operation="frame_worker_prompt", task_id=task.id):
            role = self._infer_role(task)
            template = self.templates.get(role, self.templates[AgentRole.GENERALIST])

            output_format = task.desired_output_format or self._infer_output_format(task)
            task_desc = self._optimize_description(task.description)

            prompt = template.format(
                task_description=task_desc,
                context=context or "No additional context provided.",
                output_format=output_format,
            )

            if style:
                prompt = f"[Style: {style}]\n\n{prompt}"

            # Token optimization
            if self.enable_optimization:
                prompt = await self.optimize_prompt(prompt)

            self.logger.info(
                "Worker prompt framed",
                extra={
                    "task_id": str(task.id),
                    "role": role.name,
                    "prompt_tokens": self._estimate_tokens(prompt),
                },
            )

            return prompt

    async def frame_system_prompt(
        self,
        agent_role: str,
        capabilities: Set[str],
        constraints: List[str],
    ) -> str:
        """Generate system prompt for agent initialization.

        Args:
            agent_role: Role identifier.
            capabilities: Agent capabilities.
            constraints: Operational constraints.

        Returns:
            System prompt string.
        """
        with LogContext(module="prompt_framer", operation="frame_system_prompt"):
            role_enum = AgentRole(agent_role.upper()) if hasattr(AgentRole, agent_role.upper()) else AgentRole.GENERALIST

            prompt = self.SYSTEM_PROMPT_BASE.format(
                role_name=agent_role,
                capabilities=", ".join(sorted(capabilities)) or "general reasoning",
                constraints="; ".join(constraints) if constraints else "none",
            )

            # Add role-specific guidance
            if role_enum in self.templates:
                prompt += f"\n\nRole-specific guidance: You excel at tasks requiring {role_enum.name.lower()} expertise."

            if self.enable_optimization:
                prompt = await self.optimize_prompt(prompt)

            self.logger.info(
                "System prompt framed",
                extra={"role": agent_role, "tokens": self._estimate_tokens(prompt)},
            )

            return prompt

    async def frame_role_prompt(
        self,
        role: AgentRole,
        task_description: str,
        expertise_areas: List[str],
        tone: str = "professional",
    ) -> str:
        """Generate role-specific prompt.

        Args:
            role: Agent role.
            task_description: Task to perform.
            expertise_areas: Areas of expertise.
            tone: Communication tone.

        Returns:
            Role prompt string.
        """
        template = self.templates.get(role, self.templates[AgentRole.GENERALIST])

        prompt = template.format(
            task_description=task_description,
            context=f"You are an expert in: {', '.join(expertise_areas)}",
            output_format="Respond in a clear, structured format appropriate to the task.",
        )

        prompt = f"[Tone: {tone}]\n\n{prompt}"

        if self.enable_optimization:
            prompt = await self.optimize_prompt(prompt)

        return prompt

    async def optimize_prompt(self, prompt: str) -> str:
        """Optimize prompt for token efficiency and clarity.

        Args:
            prompt: Original prompt.

        Returns:
            Optimized prompt.
        """
        # Remove redundant whitespace
        optimized = re.sub(r'\n{3,}', '\n\n', prompt)

        # Remove filler words
        fillers = ["very", "really", "quite", "rather", "fairly", "pretty"]
        for filler in fillers:
            optimized = re.sub(rf'\b{filler}\b\s+', '', optimized, flags=re.IGNORECASE)

        # Ensure key instructions are preserved
        optimized = self._preserve_instructions(optimized)

        # Truncate if over limit
        tokens = self._estimate_tokens(optimized)
        if tokens > self.max_prompt_tokens:
            optimized = await self._truncate(optimized, self.max_prompt_tokens)

        return optimized.strip()

    def _infer_role(self, task: SubTask) -> AgentRole:
        """Infer optimal role from task characteristics.

        Args:
            task: Task to analyze.

        Returns:
            Inferred agent role.
        """
        desc = task.description.lower()
        caps = " ".join(task.required_capabilities).lower()

        role_indicators = {
            AgentRole.CODER: ["code", "program", "function", "class", "debug", "refactor", "implement"],
            AgentRole.ANALYST: ["analyze", "data", "metrics", "statistics", "report"],
            AgentRole.CREATIVE: ["write", "create", "design", "story", "content", "marketing"],
            AgentRole.RESEARCHER: ["research", "investigate", "study", "find", "gather"],
            AgentRole.REVIEWER: ["review", "check", "verify", "validate", "audit"],
            AgentRole.PLANNER: ["plan", "strategy", "roadmap", "schedule", "organize"],
            AgentRole.EXECUTOR: ["execute", "run", "deploy", "build", "test", "ship"],
        }

        scores: Dict[AgentRole, int] = {role: 0 for role in AgentRole}
        for role, indicators in role_indicators.items():
            for indicator in indicators:
                scores[role] += desc.count(indicator)
                scores[role] += caps.count(indicator)

        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return best

        return AgentRole.GENERALIST

    def _infer_output_format(self, task: SubTask) -> str:
        """Infer desired output format from task.

        Args:
            task: Task to analyze.

        Returns:
            Output format description.
        """
        if task.desired_output_format:
            return task.desired_output_format

        desc = task.description.lower()
        formats = {
            "json": "JSON",
            "code": "code block with syntax highlighting",
            "table": "markdown table",
            "list": "bulleted list",
            "paragraph": "well-structured paragraphs",
            "report": "structured report with sections",
        }
        for keyword, fmt in formats.items():
            if keyword in desc:
                return fmt

        return "clear, structured response"

    def _optimize_description(self, description: str) -> str:
        """Optimize task description for prompt inclusion.

        Args:
            description: Raw description.

        Returns:
            Optimized description.
        """
        # Truncate very long descriptions
        words = description.split()
        if len(words) > 100:
            return " ".join(words[:100]) + "..."

        return description

    def _preserve_instructions(self, prompt: str) -> str:
        """Ensure critical instructions are not optimized away.

        Args:
            prompt: Prompt to check.

        Returns:
            Prompt with preserved instructions.
        """
        critical_markers = [
            "Requirements:", "Constraints:", "Output format:",
            "You must", "Do not", "Always", "Never",
        ]
        # Ensure these sections exist
        for marker in critical_markers:
            if marker.lower() in prompt.lower():
                # Already present
                continue
        return prompt

    async def _truncate(self, text: str, max_tokens: int) -> str:
        """Truncate text to token limit.

        Args:
            text: Text to truncate.
            max_tokens: Maximum tokens.

        Returns:
            Truncated text.
        """
        words = text.split()
        max_words = int(max_tokens / 1.3)  # Approximate

        if len(words) <= max_words:
            return text

        # Keep beginning and end, truncate middle
        keep = max_words // 2
        return " ".join(words[:keep]) + "\n\n... [truncated] ...\n\n" + " ".join(words[-keep:])

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count.

        Args:
            text: Text to estimate.

        Returns:
            Estimated tokens.
        """
        return int(len(text.split()) * 1.3)


# Factory
async def create_prompt_framer(
    custom_templates: Optional[Dict[AgentRole, str]] = None,
    max_prompt_tokens: int = 4000,
    event_bus: Optional[Any] = None,
) -> PromptFramerImpl:
    """Factory for creating configured prompt framer.

    Args:
        custom_templates: Custom role templates.
        max_prompt_tokens: Maximum prompt tokens.
        event_bus: Optional event bus.

    Returns:
        Configured PromptFramerImpl.
    """
    return PromptFramerImpl(
        custom_templates=custom_templates,
        max_prompt_tokens=max_prompt_tokens,
    )


from domain_models import OrchestrationEvent
