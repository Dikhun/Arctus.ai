"""Arctus AI Orchestration Framework - Planning Module.

Responsible for intent analysis, goal extraction, constraint analysis,
complexity analysis, risk analysis, priority analysis, parallelism
planning, dependency planning, execution strategy generation, task
decomposition, execution plan optimization, and plan validation.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from domain_models import (
    AgentRole,
    ComplexityLevel,
    ExecutionMode,
    ExecutionPlan,
    Priority,
    RiskLevel,
    SubTask,
    TaskIntent,
    TokenCount,
)
from exceptions import (
    ConstraintViolationException,
    DecompositionException,
    ErrorContext,
    PlanValidationException,
    PlanningException,
)
from infrastructure import LogContext, async_timed, get_logger
from protocols import ExecutionPlanner, IntentAnalyzer, PlanValidator


logger = get_logger("planning_module")


class IntentAnalyzerImpl(IntentAnalyzer):
    """Extracts structured intent from natural language using heuristic analysis.

    Analyzes raw user input to identify goals, constraints, tools,
    complexity indicators, and domain hints.
    """

    # Complexity indicators
    COMPLEXITY_MARKERS: Dict[ComplexityLevel, List[str]] = {
        ComplexityLevel.TRIVIAL: ["hello", "hi", "hey", "what is", "who is", "simple"],
        ComplexityLevel.SIMPLE: ["list", "summarize", "brief", "short", "quick"],
        ComplexityLevel.MODERATE: ["explain", "compare", "analyze", "describe", "how to"],
        ComplexityLevel.COMPLEX: ["design", "implement", "build", "create", "architect", "integrate"],
        ComplexityLevel.VERY_COMPLEX: ["optimize", "refactor", "scale", "enterprise", "distributed", "microservices"],
    }

    CONSTRAINT_PATTERNS: List[Tuple[str, str]] = [
        (r"\b(?:under|within|less than|at most)\s+(\d+)\s*(?:tokens?|words?|characters?|chars?)\b", "length_limit"),
        (r"\b(?:must|should|need to|required to)\s+(?:use|utilize|employ)\s+(\w+)\b", "tool_requirement"),
        (r"\b(?:budget|cost|spend|under)\s+\$?(\d+(?:\.\d+)?)\b", "budget_limit"),
        (r"\b(?:before|by|deadline|due)\s+(\w+(?:\s+\w+){0,5})\b", "time_constraint"),
        (r"\b(?:confidential|private|internal|sensitive|secure)\b", "security_constraint"),
        (r"\b(?:compliance|regulatory|GDPR|HIPAA|SOX)\b", "compliance_constraint"),
    ]

    URGENCY_MARKERS: List[str] = [
        "urgent", "asap", "immediately", "critical", "deadline", "emergency",
        "rush", "priority", "important", "blocking",
    ]

    DOMAIN_HINTS: Dict[str, List[str]] = {
        "code": ["code", "program", "function", "class", "bug", "debug", "refactor", "git", "repo"],
        "data": ["data", "csv", "database", "sql", "pandas", "analysis", "visualization"],
        "infrastructure": ["docker", "kubernetes", "deploy", "server", "cloud", "aws", "azure"],
        "research": ["research", "paper", "study", "academic", "citation", "literature"],
        "creative": ["write", "story", "blog", "article", "creative", "marketing", "copy"],
        "legal": ["contract", "legal", "clause", "regulation", "compliance", "law"],
    }

    def __init__(self, custom_patterns: Optional[Dict[str, List[str]]] = None) -> None:
        self.custom_patterns = custom_patterns or {}

    @async_timed
    async def analyze(self, raw_input: str, context: Optional[Dict[str, Any]] = None) -> TaskIntent:
        """Analyze raw user input and extract structured intent.

        Args:
            raw_input: The user's natural language request.
            context: Optional conversation or session context.

        Returns:
            Structured TaskIntent with extracted goals, constraints, etc.
        """
        with LogContext(module="intent_analyzer", operation="analyze"):
            logger.info("Analyzing intent", extra={"input_length": len(raw_input)})

            goals = self._extract_goals(raw_input)
            constraints = self._extract_constraints(raw_input)
            tools = self._extract_tools(raw_input, constraints)
            complexity = self._assess_complexity(raw_input, goals)
            urgency = self._extract_urgency(raw_input)
            domains = self._extract_domains(raw_input)

            intent = TaskIntent(
                raw_input=raw_input,
                goals=goals,
                constraints=constraints,
                explicit_tools=tools,
                desired_output_format=self._detect_output_format(raw_input),
                urgency_indicators=urgency,
                domain_hints=domains,
                estimated_complexity=complexity,
            )

            logger.info(
                "Intent analysis complete",
                extra={
                    "goals_count": len(goals),
                    "constraints_count": len(constraints),
                    "complexity": complexity.name,
                },
            )
            return intent

    def _extract_goals(self, text: str) -> List[str]:
        """Extract primary goals from input text.

        Uses imperative sentence detection and goal-oriented phrasing.
        """
        goals: List[str] = []
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            sentence = sentence.strip().lower()
            # Imperative starts
            if re.match(r'^(please\s+)?(create|build|make|generate|write|design|implement|develop|find|get|show|explain|compare|analyze|summarize|list|calculate|solve|fix|refactor|optimize|test|deploy|integrate|configure|set up)', sentence):
                # Clean up
                goal = sentence.strip()
                if len(goal) > 5:
                    goals.append(goal)
        if not goals:
            # Fallback: treat whole input as single goal
            goals.append(text.strip())
        return goals[:5]  # Cap at 5 goals

    def _extract_constraints(self, text: str) -> List[str]:
        """Extract explicit and implicit constraints."""
        constraints: List[str] = []
        text_lower = text.lower()
        for pattern, constraint_type in self.CONSTRAINT_PATTERNS:
            for match in re.finditer(pattern, text_lower):
                constraints.append(f"{constraint_type}: {match.group(0)}")
        return constraints

    def _extract_tools(self, text: str, constraints: List[str]) -> List[str]:
        """Extract explicitly requested tools from constraints and text."""
        tools: Set[str] = set()
        tool_keywords = ["python", "javascript", "typescript", "docker", "kubernetes",
                        "sql", "pandas", "numpy", "react", "vue", "angular",
                        "fastapi", "django", "flask", "aws", "gcp", "azure"]
        text_lower = text.lower()
        for tool in tool_keywords:
            if tool in text_lower:
                tools.add(tool)
        # Also check constraint tool requirements
        for c in constraints:
            if "tool_requirement" in c:
                parts = c.split(":")
                if len(parts) > 1:
                    tools.add(parts[-1].strip())
        return sorted(tools)

    def _assess_complexity(self, text: str, goals: List[str]) -> ComplexityLevel:
        """Assess task complexity based on markers and goal structure."""
        text_lower = text.lower()
        scores: Dict[ComplexityLevel, int] = {level: 0 for level in ComplexityLevel}

        for level, markers in self.COMPLEXITY_MARKERS.items():
            for marker in markers:
                scores[level] += text_lower.count(marker)

        # Boost for multiple goals
        goal_count = len(goals)
        if goal_count > 3:
            scores[ComplexityLevel.VERY_COMPLEX] += goal_count
        elif goal_count > 1:
            scores[ComplexityLevel.COMPLEX] += goal_count

        # Length heuristic
        word_count = len(text.split())
        if word_count > 200:
            scores[ComplexityLevel.VERY_COMPLEX] += 2
        elif word_count > 100:
            scores[ComplexityLevel.COMPLEX] += 1

        return max(scores, key=lambda k: scores[k])

    def _extract_urgency(self, text: str) -> List[str]:
        """Extract urgency indicators."""
        text_lower = text.lower()
        return [marker for marker in self.URGENCY_MARKERS if marker in text_lower]

    def _extract_domains(self, text: str) -> List[str]:
        """Extract domain hints from text."""
        text_lower = text.lower()
        domains: Set[str] = set()
        for domain, markers in self.DOMAIN_HINTS.items():
            for marker in markers:
                if marker in text_lower:
                    domains.add(domain)
        return sorted(domains)

    def _detect_output_format(self, text: str) -> Optional[str]:
        """Detect desired output format from request."""
        formats = {
            "json": r"\bjson\b",
            "markdown": r"\bmarkdown\b|\bmd\b",
            "code": r"\bcode\b|\bsyntax\b",
            "table": r"\btable\b|\bcsv\b|\btabular\b",
            "diagram": r"\bdiagram\b|\bmermaid\b|\bflowchart\b",
            "report": r"\breport\b|\bdocument\b|\bwhitepaper\b",
        }
        text_lower = text.lower()
        for fmt, pattern in formats.items():
            if re.search(pattern, text_lower):
                return fmt
        return None


class TaskDecomposer:
    """Decomposes complex tasks into atomic subtasks with dependencies.

    Uses recursive decomposition based on complexity and domain analysis.
    """

    def __init__(self, max_depth: int = 3, min_subtask_words: int = 5) -> None:
        self.max_depth = max_depth
        self.min_subtask_words = min_subtask_words

    @async_timed
    async def decompose(
        self,
        intent: TaskIntent,
        parent_id: Optional[uuid.UUID] = None,
        depth: int = 0,
    ) -> List[SubTask]:
        """Decompose intent into subtasks.

        Args:
            intent: Analyzed task intent.
            parent_id: Parent task ID for hierarchical decomposition.
            depth: Current recursion depth.

        Returns:
            List of subtasks.
        """
        with LogContext(module="task_decomposer", operation="decompose"):
            if depth >= self.max_depth:
                # Stop decomposition, create single task
                return [self._create_leaf_task(intent, parent_id)]

            subtasks = self._generate_subtasks(intent, parent_id, depth)

            # Recursively decompose complex subtasks
            final_tasks: List[SubTask] = []
            for task in subtasks:
                if self._should_decompose(task):
                    child_intent = TaskIntent(
                        raw_input=task.description,
                        goals=[task.name],
                        constraints=list(intent.constraints),
                        estimated_complexity=ComplexityLevel.MODERATE,
                    )
                    children = await self.decompose(child_intent, task.id, depth + 1)
                    final_tasks.extend(children)
                else:
                    final_tasks.append(task)

            return final_tasks

    def _generate_subtasks(
        self,
        intent: TaskIntent,
        parent_id: Optional[uuid.UUID],
        depth: int,
    ) -> List[SubTask]:
        """Generate initial subtasks from intent goals."""
        subtasks: List[SubTask] = []
        base_priority = self._urgency_to_priority(intent.urgency_indicators)

        for i, goal in enumerate(intent.goals):
            task = SubTask(
                id=uuid.uuid4(),
                parent_id=parent_id,
                name=f"task_{depth}_{i}",
                description=goal,
                required_capabilities=self._infer_capabilities(goal, intent.domain_hints),
                priority=base_priority,
                dependencies=set(),
                execution_mode=ExecutionMode.SEQUENTIAL,
                max_retries=3,
                timeout_seconds=60.0,
            )
            subtasks.append(task)

        # Add planning/analysis subtask for complex goals
        if intent.estimated_complexity in (ComplexityLevel.COMPLEX, ComplexityLevel.VERY_COMPLEX):
            analysis_task = SubTask(
                id=uuid.uuid4(),
                parent_id=parent_id,
                name="analysis",
                description=f"Analyze requirements and approach for: {intent.raw_input[:100]}",
                required_capabilities={"analysis", "planning"},
                priority=Priority.HIGH,
                dependencies={t.id for t in subtasks},  # Depends on initial understanding
                execution_mode=ExecutionMode.SEQUENTIAL,
                max_retries=2,
                timeout_seconds=45.0,
            )
            subtasks.append(analysis_task)

        return subtasks

    def _should_decompose(self, task: SubTask) -> bool:
        """Determine if a task needs further decomposition."""
        word_count = len(task.description.split())
        complexity_markers = ["and then", "followed by", "subsequently", "after",
                             "first", "second", "third", "step", "phase", "stage"]
        has_markers = any(m in task.description.lower() for m in complexity_markers)
        return word_count > 50 or has_markers

    def _create_leaf_task(self, intent: TaskIntent, parent_id: Optional[uuid.UUID]) -> SubTask:
        """Create atomic leaf task from intent."""
        return SubTask(
            id=uuid.uuid4(),
            parent_id=parent_id,
            name="execute",
            description=intent.raw_input,
            required_capabilities=self._infer_capabilities(intent.raw_input, intent.domain_hints),
            priority=self._urgency_to_priority(intent.urgency_indicators),
            dependencies=set(),
            execution_mode=ExecutionMode.SEQUENTIAL,
            max_retries=3,
            timeout_seconds=60.0,
        )

    def _infer_capabilities(self, text: str, domains: List[str]) -> Set[str]:
        """Infer required capabilities from text and domains."""
        caps: Set[str] = set()
        text_lower = text.lower()

        capability_map = {
            "code": {"coding", "programming", "software_engineering"},
            "data": {"data_analysis", "statistics", "visualization"},
            "infrastructure": {"devops", "cloud", "deployment"},
            "research": {"research", "synthesis", "citation"},
            "creative": {"writing", "creative", "content_generation"},
            "legal": {"legal_analysis", "compliance", "contract_review"},
        }

        for domain in domains:
            if domain in capability_map:
                caps.update(capability_map[domain])

        # Heuristic from text
        if any(w in text_lower for w in ["code", "program", "function", "class", "debug"]):
            caps.add("coding")
        if any(w in text_lower for w in ["data", "csv", "sql", "analysis", "chart"]):
            caps.add("data_analysis")
        if any(w in text_lower for w in ["design", "architecture", "system"]):
            caps.add("system_design")
        if any(w in text_lower for w in ["test", "verify", "validate", "check"]):
            caps.add("verification")

        if not caps:
            caps.add("general")

        return caps

    def _urgency_to_priority(self, urgency: List[str]) -> Priority:
        """Map urgency indicators to priority level."""
        if not urgency:
            return Priority.NORMAL
        if any(u in ["critical", "emergency", "blocking"] for u in urgency):
            return Priority.CRITICAL
        if any(u in ["urgent", "asap", "immediately", "deadline"] for u in urgency):
            return Priority.HIGH
        return Priority.NORMAL


class PlanValidatorImpl(PlanValidator):
    """Validates execution plans for correctness, feasibility, and safety."""

    def __init__(self, max_subtasks: int = 100, max_estimated_cost_usd: float = 100.0) -> None:
        self.max_subtasks = max_subtasks
        self.max_estimated_cost_usd = max_estimated_cost_usd

    @async_timed
    async def validate(self, plan: ExecutionPlan) -> Tuple[bool, List[str]]:
        """Validate execution plan comprehensively.

        Args:
            plan: The execution plan to validate.

        Returns:
            Tuple of (is_valid, list_of_violation_messages).
        """
        with LogContext(module="plan_validator", operation="validate", plan_id=str(plan.id)):
            violations: List[str] = []

            # Structural validation
            violations.extend(self._validate_structure(plan))
            # Constraint validation
            violations.extend(self._validate_constraints(plan))
            # Dependency validation
            violations.extend(await self._validate_dependencies(plan))
            # Budget validation
            violations.extend(self._validate_budget(plan))
            # Safety validation
            violations.extend(self._validate_safety(plan))

            is_valid = len(violations) == 0
            if is_valid:
                logger.info("Plan validation passed", extra={"plan_id": str(plan.id), "subtasks": len(plan.subtasks)})
            else:
                logger.warning(
                    "Plan validation failed",
                    extra={"plan_id": str(plan.id), "violations_count": len(violations)},
                )

            return is_valid, violations

    def _validate_structure(self, plan: ExecutionPlan) -> List[str]:
        """Validate plan structural integrity."""
        violations: List[str] = []
        if not plan.subtasks:
            violations.append("Plan contains no subtasks")
            return violations

        task_ids = {t.id for t in plan.subtasks}
        if plan.root_task_id not in task_ids:
            violations.append(f"Root task {plan.root_task_id} not found in subtasks")

        if len(plan.subtasks) > self.max_subtasks:
            violations.append(f"Too many subtasks: {len(plan.subtasks)} > {self.max_subtasks}")

        for task in plan.subtasks:
            if task.parent_id and task.parent_id not in task_ids:
                violations.append(f"Task {task.id} has invalid parent {task.parent_id}")
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    violations.append(f"Task {task.id} has unknown dependency {dep_id}")

        return violations

    def _validate_constraints(self, plan: ExecutionPlan) -> List[str]:
        """Validate that plan satisfies original constraints."""
        violations: List[str] = []
        constraints = plan.original_intent.constraints

        for constraint in constraints:
            if "length_limit" in constraint:
                # Would check total estimated output length
                pass
            if "budget_limit" in constraint:
                match = re.search(r"\d+(?:\.\d+)?", constraint)
                if match:
                    budget = float(match.group())
                    if plan.total_estimated_cost and plan.total_estimated_cost.estimated_cost_usd > budget:
                        violations.append(f"Estimated cost exceeds budget: {plan.total_estimated_cost.estimated_cost_usd} > {budget}")

        return violations

    async def _validate_dependencies(self, plan: ExecutionPlan) -> List[str]:
        """Validate dependency graph for cycles and reachability."""
        from dependency_graph import DependencyGraphImpl
        graph = DependencyGraphImpl()
        violations: List[str] = []

        # Build adjacency list
        adj: Dict[uuid.UUID, set] = {}
        for task in plan.subtasks:
            adj[task.id] = task.dependencies

        # Check cycles
        cycle = await graph.detect_cycles(adj)
        if cycle:
            violations.append(f"Circular dependency detected: {' -> '.join(str(n) for n in cycle)}")

        # Check all tasks reachable from r
