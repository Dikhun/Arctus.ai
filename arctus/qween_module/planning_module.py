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

    async def _validate_dependencies(...):
    ...
    return violations
    def _validate_safety(self, plan: ExecutionPlan) -> List[str]:
    """Validate safety rules."""

    violations: List[str] = []

    if not plan.safety_rules:
        return violations

    for rule in plan.safety_rules:
        if not rule.enabled:
            continue

        if rule.rule_type.name == "MUTEX":
            task_ids = set(rule.parameters.get("tasks", []))
            running = [
                t for t in plan.subtasks
                if str(t.id) in task_ids and t.status.name == "RUNNING"
            ]

            max_concurrent = rule.parameters.get("max_concurrent", 1)

            if len(running) > max_concurrent:
                violations.append(
                    f"Mutex rule '{rule.name}' violated."
                )

        elif rule.rule_type.name == "SEQUENCE":
            sequence = rule.parameters.get("sequence", [])

            completed = [
                str(t.id)
                for t in sorted(
                    plan.subtasks,
                    key=lambda x: x.started_at or 0
                )
                if t.status.name == "COMPLETED"
            ]

            if completed[:len(sequence)] != sequence:
                violations.append(
                    f"Sequence rule '{rule.name}' violated."
                )

        elif rule.rule_type.name == "RESOURCE_CAP":
            resource = rule.parameters.get("resource")
            cap = rule.parameters.get("cap", 0)

            usage = sum(
                t.resource_usage.get(resource, 0)
                for t in plan.subtasks
                if hasattr(t, "resource_usage")
            )

            if usage > cap:
                violations.append(
                    f"Resource cap exceeded for {resource}."
                )

    return violations
    def _validate_budget(self, plan: ExecutionPlan) -> List[str]:
    violations: List[str] = []

    if not getattr(plan, "total_estimated_cost", None):
        return violations

    return violations

        if (
            plan.total_estimated_cost
            and plan.total_estimated_cost.estimated_cost_usd
            > self.max_estimated_cost_usd
        ):
            violations.append(
                f"Estimated cost "
                f"{plan.total_estimated_cost.estimated_cost_usd} "
                f"exceeds maximum allowed "
                f"{self.max_estimated_cost_usd}"
            )

        return violations
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

        # Check all tasks are reachable from the root task
        if plan.root_task_id in adj:
            reachable = await graph.reachable_from(plan.root_task_id, adj)

            unreachable = {
                task.id for task in plan.subtasks
            } - reachable

            if unreachable:
                violations.append(
                    f"Unreachable tasks detected: "
                    f"{', '.join(str(t) for t in unreachable)}"
                )

        return violations

Responsible for intent analysis, goal extraction, constraint analysis,
complexity analysis, risk analysis, priority analysis, parallelism
planning, dependency planning, execution strategy generation, task
decomposition, execution plan optimization, and plan validation.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
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
    UserRequest,
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

   from __future__ import annotations

"""
Arctus Framework - Domain Models (Single Source of Truth)

This module is the canonical source for all shared data models across the Arctus framework.
All modules MUST import shared models exclusively from this file to ensure consistency.

Migration Guide for Existing Code:
- Old: from planning_module import TaskNode, ExecutionPlan
- New: from domain_models import TaskNode, ExecutionPlan

Backward Compatibility:
- Import aliases are provided at the bottom of this file for common legacy import paths.
- These aliases will be deprecated in v2.0 and removed in v3.0.
"""

import enum
import uuid
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import (
    Any, Dict, List, Optional, Set, Tuple, Union, Callable, ClassVar,
    Literal, Protocol, runtime_checkable, Self, TypeVar, Generic,
    get_type_hints
)
from dataclasses import dataclass, field, asdict
from collections import defaultdict

# Pydantic imports with version compatibility
try:
    from pydantic import (
        BaseModel, Field, field_validator, model_validator,
        ConfigDict, computed_field, PrivateAttr,
        ValidationError as PydanticValidationError
    )
    from pydantic.fields import FieldInfo
    PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseModel, Field, validator, root_validator, PrivateAttr
    from pydantic.fields import ModelField
    PYDANTIC_V2 = False

# Optional imports for enhanced functionality
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

try:
    from bson import ObjectId
    HAS_BSON = True
except ImportError:
    HAS_BSON = False


# ============================================================================
# ENUMERATIONS
# ============================================================================

class TaskStatus(str, enum.Enum):
    """
    Lifecycle states for a task execution.
    
    Transitions: PENDING -> READY -> RUNNING -> (COMPLETED | FAILED | CANCELLED)
    """
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"

    @classmethod
    def terminal_states(cls) -> Set[TaskStatus]:
        """Return states from which no further transitions occur."""
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED, cls.SKIPPED, cls.TIMEOUT}

    @classmethod
    def active_states(cls) -> Set[TaskStatus]:
        """Return states representing active execution."""
        return {cls.READY, cls.RUNNING, cls.PAUSED}

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in self.terminal_states()

    @property
    def is_active(self) -> bool:
        """Check if this represents active execution."""
        return self in self.active_states()


class PlanStatus(str, enum.Enum):
    """Lifecycle states for an execution plan."""
    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"

    @property
    def is_mutable(self) -> bool:
        """Check if plan can still be modified in this state."""
        return self in {self.DRAFT, self.READY}


class DependencyType(str, enum.Enum):
    """Types of dependencies between tasks."""
    REQUIRES_COMPLETION = "requires_completion"
    REQUIRES_START = "requires_start"
    REQUIRES_OUTPUT = "requires_output"
    REQUIRES_RESOURCE = "requires_resource"
    SOFT_DEPENDENCY = "soft_dependency"
    TEMPORAL = "temporal"
    EXCLUSIVE = "exclusive"


class SafetyRuleType(str, enum.Enum):
    """Categories of safety constraints."""
    MUTEX = "mutex"
    SEQUENCE = "sequence"
    TIME_WINDOW = "time_window"
    RESOURCE_CAP = "resource_cap"
    RATE_LIMIT = "rate_limit"
    GEO_FENCE = "geo_fence"
    DATA_RESIDENCY = "data_residency"


class OptimizationStrategy(str, enum.Enum):
    """Available optimization strategies for plan execution."""
    NONE = "none"
    CRITICAL_PATH = "critical_path"
    RESOURCE_LEVELING = "resource_leveling"
    COST_MINIMIZATION = "cost_minimization"
    TIME_MINIMIZATION = "time_minimization"
    BALANCED = "balanced"
    CUSTOM = "custom"


class ComplexityLevel(str, enum.Enum):
    """Task complexity classification for resource estimation."""
    TRIVIAL = "trivial"      # < 1 minute, no dependencies
    SIMPLE = "simple"        # < 5 minutes, few dependencies
    MODERATE = "moderate"    # < 1 hour, moderate dependencies
    COMPLEX = "complex"      # < 4 hours, many dependencies
    COMPLICATED = "complicated"  # < 1 day, complex dependency graph
    HARD = "hard"            # > 1 day, critical path sensitive


class Priority(int, enum.Enum):
    """Execution priority levels with numeric ordering."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4

    def __lt__(self, other: Priority) -> bool:
        return self.value < other.value

    def __gt__(self, other: Priority) -> bool:
        return self.value > other.value

    def __le__(self, other: Priority) -> bool:
        return self.value <= other.value

    def __ge__(self, other: Priority) -> bool:
        return self.value >= other.value


class RiskLevel(str, enum.Enum):
    """Risk classification for tasks and plans."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionMode(str, enum.Enum):
    """Execution environment modes."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DISTRIBUTED = "distributed"
    ADAPTIVE = "adaptive"


class AgentRole(str, enum.Enum):
    """Roles that agents can fulfill in the workflow."""
    ORCHESTRATOR = "orchestrator"
    EXECUTOR = "executor"
    VALIDATOR = "validator"
    MONITOR = "monitor"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"
    BACKUP = "backup"


class MemoryType(str, enum.Enum):
    """Types of memory entries for provenance tracking."""
    OBSERVATION = "observation"
    DECISION = "decision"
    ACTION = "action"
    RESULT = "result"
    ERROR = "error"
    STATE_CHANGE = "state_change"
    COMMUNICATION = "communication"


# ============================================================================
# BASE MIXINS AND UTILITIES
# ============================================================================

class SerializableMixin:
    """
    Mixin providing serialization capabilities to both dataclasses and Pydantic models.
    """
    
    def to_dict(self, exclude_none: bool = True, exclude_unset: bool = False) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        if isinstance(self, BaseModel):
            if PYDANTIC_V2:
                return self.model_dump(
                    mode="json",
                    exclude_none=exclude_none,
                    exclude_unset=exclude_unset,
                    by_alias=True
                )
            else:
                return json.loads(self.json(exclude_none=exclude_none, exclude_unset=exclude_unset))
        
        # Handle dataclass
        result = asdict(self)
        if exclude_none:
            result = {k: v for k, v in result.items() if v is not None}
        return self._serialize_values(result)
    
    def to_json(self, indent: Optional[int] = None, sort_keys: bool = False) -> str:
        """Serialize to JSON string."""
        data = self.to_dict()
        if HAS_ORJSON:
            option = orjson.OPT_SORT_KEYS if sort_keys else 0
            if indent:
                option |= orjson.OPT_INDENT_2
            return orjson.dumps(data, option=option).decode("utf-8")
        return json.dumps(data, indent=indent, sort_keys=sort_keys, default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Self:
        """Create instance from dictionary."""
        if issubclass(cls, BaseModel):
            if PYDANTIC_V2:
                return cls.model_validate(data)
            return cls.parse_obj(data)
        # For dataclasses, use direct construction
        field_names = {f.name for f in field(cls) if f.init}
        filtered = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered)
    
    @classmethod
    def from_json(cls, json_str: str) -> Self:
        """Create instance from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def _serialize_values(self, obj: Any) -> Any:
        """Recursively serialize special types."""
        if isinstance(obj, dict):
            return {k: self._serialize_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_values(v) for v in obj]
        elif isinstance(obj, (datetime, timedelta)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, enum.Enum):
            return obj.value
        elif isinstance(obj, uuid.UUID):
            return str(obj)
        elif HAS_BSON and isinstance(obj, ObjectId):
            return str(obj)
        return obj


class TimestampedMixin:
    """Mixin adding created_at and updated_at timestamps."""
    
    def __post_init__(self):
        if not hasattr(self, 'created_at') or self.created_at is None:
            object.__setattr__(self, 'created_at', datetime.now())
        object.__setattr__(self, 'updated_at', datetime.now())
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        if hasattr(self, 'updated_at'):
            self.updated_at = datetime.now()


class IdentifiableMixin:
    """Mixin ensuring all entities have a unique identifier."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    @property
    def short_id(self) -> str:
        """Return first 8 characters of ID for display."""
        return self.id[:8]


# ============================================================================
# SHARED PYDANTIC BASE
# ============================================================================

class ArctusBaseModel(BaseModel, SerializableMixin):
    """
    Base model for all Arctus Pydantic models.
    Provides consistent configuration, serialization, and validation.
    """
    
    if PYDANTIC_V2:
        model_config = ConfigDict(
            populate_by_name=True,
            str_strip_whitespace=True,
            use_enum_values=True,
            validate_assignment=True,
            arbitrary_types_allowed=True,
            json_encoders={
                datetime: lambda v: v.isoformat(),
                timedelta: lambda v: v.total_seconds(),
                Decimal: str,
                uuid.UUID: str,
                set: list,
                frozenset: list,
            }
        )
    else:
        class Config:
            populate_by_name = True
            str_strip_whitespace = True
            use_enum_values = True
            validate_assignment = True
            arbitrary_types_allowed = True
            json_encoders = {
                datetime: lambda v: v.isoformat(),
                timedelta: lambda v: v.total_seconds(),
                Decimal: str,
                uuid.UUID: str,
                set: list,
                frozenset: list,
            }


# ============================================================================
# CORE VALUE OBJECTS
# ============================================================================

class TokenCount(ArctusBaseModel):
    """
    Token usage tracking for LLM operations.
    Supports multiple model providers with unified accounting.
    """
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    
    # Provider-specific breakdowns
    breakdown: Dict[str, int] = Field(default_factory=dict)
    
    if PYDANTIC_V2:
        @model_validator(mode="after")
        def validate_total(self) -> Self:
            expected = self.prompt_tokens + self.completion_tokens
            if self.total_tokens != expected:
                self.total_tokens = expected
            return self
    else:
        @root_validator
        def validate_total(cls, values):
            prompt = values.get("prompt_tokens", 0)
            completion = values.get("completion_tokens", 0)
            values["total_tokens"] = prompt + completion
            return values
    
    def __add__(self, other: TokenCount) -> TokenCount:
        """Add two token counts together."""
        return TokenCount(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            breakdown={
                k: self.breakdown.get(k, 0) + other.breakdown.get(k, 0)
                for k in set(self.breakdown) | set(other.breakdown)
            }
        )


class CostEstimate(ArctusBaseModel):
    """
    Detailed cost breakdown for task or plan execution.
    Supports multiple currencies with USD as default.
    """
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    total: Decimal = Field(default=Decimal("0"), ge=0)
    
    # Component breakdowns
    compute: Decimal = Field(default=Decimal("0"), ge=0)
    storage: Decimal = Field(default=Decimal("0"), ge=0)
    network: Decimal = Field(default=Decimal("0"), ge=0)
    api_calls: Decimal = Field(default=Decimal("0"), ge=0)
    tokens: Decimal = Field(default=Decimal("0"), ge=0)
    human_review: Decimal = Field(default=Decimal("0"), ge=0)
    other: Decimal = Field(default=Decimal("0"), ge=0)
    
    # Usage metrics
    token_count: Optional[TokenCount] = None
    
    @property
    def is_zero(self) -> bool:
        """Check if cost is effectively zero."""
        return self.total <= Decimal("0")
    
    def __add__(self, other: CostEstimate) -> CostEstimate:
        """Combine two cost estimates."""
        if self.currency != other.currency:
            raise ValueError(f"Cannot add costs in different currencies: {self.currency} vs {other.currency}")
        return CostEstimate(
            currency=self.currency,
            total=self.total + other.total,
            compute=self.compute + other.compute,
            storage=self.storage + other.storage,
            network=self.network + other.network,
            api_calls=self.api_calls + other.api_calls,
            tokens=self.tokens + other.tokens,
            human_review=self.human_review + other.human_review,
            other=self.other + other.other,
            token_count=(self.token_count + other.token_count) if self.token_count and other.token_count else None
        )


class ResourceUsage(ArctusBaseModel):
    """
    Resource consumption metrics for a task or plan.
    """
    cpu_seconds: float = Field(default=0.0, ge=0)
    memory_mb: float = Field(default=0.0, ge=0)
    disk_mb: float = Field(default=0.0, ge=0)
    network_egress_mb: float = Field(default=0.0, ge=0)
    network_ingress_mb: float = Field(default=0.0, ge=0)
    gpu_seconds: float = Field(default=0.0, ge=0)
    custom_metrics: Dict[str, float] = Field(default_factory=dict)


# ============================================================================
# BUDGET AND RESOURCE MODELS
# ============================================================================

class Budget(ArctusBaseModel):
    """
    Budget constraints for plan execution.
    Supports overall limits and per-category allocations.
    """
    budget_id: str = Field(default_factory=lambda: f"budget_{uuid.uuid4().hex[:8]}")
    name: Optional[str] = None
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    
    # Overall limits
    limit: Decimal = Field(..., gt=0, description="Maximum total spend")
    alert_threshold: Decimal = Field(default=Decimal("0.8"), ge=0, le=1, description="Fraction of limit triggering alerts")
    
    # Category allocations (category -> limit)
    allocation: Dict[str, Decimal] = Field(default_factory=dict)
    
    # Time bounds
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    
    # Tracking
    spent: Decimal = Field(default=Decimal("0"), ge=0)
    reserved: Decimal = Field(default=Decimal("0"), ge=0)
    
    @property
    def remaining(self) -> Decimal:
        """Calculate remaining budget."""
        return max(self.limit - self.spent - self.reserved, Decimal("0"))
    
    @property
    def utilization(self) -> float:
        """Calculate budget utilization as fraction."""
        if self.limit <= 0:
            return 0.0
        return float((self.spent + self.reserved) / self.limit)
    
    @property
    def is_alert_triggered(self) -> bool:
        """Check if alert threshold is exceeded."""
        return self.utilization >= float(self.alert_threshold)
    
    @property
    def is_exhausted(self) -> bool:
        """Check if budget is fully consumed."""
        return self.remaining <= 0
    
    def can_spend(self, amount: Decimal) -> bool:
        """Check if amount can be spent within budget."""
        return (self.spent + self.reserved + amount) <= self.limit
    
    def spend(self, amount: Decimal, category: Optional[str] = None) -> None:
        """Record spending against budget."""
        if not self.can_spend(amount):
            raise BudgetExceededError(f"Cannot spend {amount}: only {self.remaining} remaining")
        self.spent += amount
        if category and category in self.allocation:
            # Track per-category spending implicitly through nested budgets
            pass
    
    def reserve(self, amount: Decimal) -> None:
        """Reserve budget for pending operations."""
        if not self.can_spend(amount):
            raise BudgetExceededError(f"Cannot reserve {amount}: only {self.remaining} remaining")
        self.reserved += amount
    
    def release(self, amount: Decimal) -> None:
        """Release reserved budget."""
        self.reserved = max(self.reserved - amount, Decimal("0"))


class Resource(ArctusBaseModel):
    """
    Represents a consumable or reusable resource in the system.
    """
    resource_id: str = Field(default_factory=lambda: f"res_{uuid.uuid4().hex[:8]}")
    name: str
    resource_type: str = Field(..., description="E.g., 'gpu', 'cpu', 'storage', 'api_key'")
    
    # Capacity
    capacity: Optional[float] = Field(default=None, gt=0)
    unit: str = Field(default="unit", description="Unit of measurement")
    
    # Cost
    hourly_rate: Optional[Decimal] = Field(default=None, ge=0)
    per_use_rate: Optional[Decimal] = Field(default=None, ge=0)
    
    # Constraints
    availability_schedule: Optional[str] = None  # Cron expression
    max_concurrent_usage: int = Field(default=1, ge=1)
    geographic_region: Optional[str] = None
    
    # Metadata
    provider: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# SAFETY AND RETRY MODELS
# ============================================================================

class SafetyRule(ArctusBaseModel):
    """
    Safety constraint for plan execution.
    """
    rule_id: str = Field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:8]}")
    name: str
    description: Optional[str] = None
    rule_type: SafetyRuleType = SafetyRuleType.MUTEX
    enabled: bool = True
    severity: RiskLevel = RiskLevel.MEDIUM
    
    # Rule-specific parameters
    parameters: Dict[str, Any] = Field(default_factory=dict)
  
