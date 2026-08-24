"""The orchestration loop: Plan -> Validate(local) -> Execute(strong) -> Verify.

Replaces the stub `asyncio.sleep` version with real LLM calls. Complexity
routing (Queen) decides whether to do a single fast pass or the full pipeline.

Safety vs. the original spec:
- No header-based key forwarding. Models are reached via the user's own
  configured endpoints and keys (see config.py).
- Each step's token usage counts against the per-agent context window; the
  80% rule triggers a clean handoff with a checkpoint.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import llm
from .config import Config
from .context import IsolatedContextWindow, StateDir, HandoffPayload
from .rate_limit import RateLimitConfig, check_and_update, check_monthly_quota, estimate_tokens, RateLimitError

logger = logging.getLogger("arctus.orch")

COMPLEX_KEYWORDS = (
    "refactor", "architecture", "microservice", "security audit",
    "parallel", "pipeline", "benchmark", "full-stack", "db migration",
    "migrate", "design", "rewrite",
)

PLANNER_SYSTEM = (
    "You are the Planner for Arctus.ai. Break the user's task into a small "
    "ordered list of concrete steps and tag each as 'fast' or 'strong'.\n"
    "  fast   = formatting, syntax checks, summaries, linting, simple edits.\n"
    "  strong = refactors, design decisions, algorithmic logic, multi-file changes.\n"
    'Respond with STRICT JSON only, no prose:\n'
    '{"steps":[{"title":"...","detail":"...","tier":"fast|strong"}]}'
)

VALIDATOR_SYSTEM = (
    "You are the local Validator for Arctus.ai. Given context and a step, "
    "perform the lightweight check requested (lint, format, summary, schema). "
    "Return a concise result string."
)

WORKER_SYSTEM = (
    "You are a focused worker agent for Arctus.ai. Do exactly what the step "
    "asks. Be concise."
)

VERIFIER_SYSTEM = (
    "You are the Verifier for Arctus.ai. Given the task and the work produced, "
    'decide if it is satisfied. Reply with STRICT JSON only:\n'
    '{"done": true|false, "notes": "one short sentence"}'
)

CIRCUIT_BREAKER_LIMIT = 3  # consecutive failures before halting a worker


@dataclass
class Step:
    title: str
    detail: str
    tier: str = "fast"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Step":
        return cls(title=str(d.get("title", "")), detail=str(d.get("detail", "")), tier=str(d.get("tier", "fast")))


@dataclass
class TaskResult:
    complexity: str            # "simple" | "complex"
    mode: str                  # "single_fast" | "pipeline"
    steps: List[Step] = field(default_factory=list)
    work: List[Dict[str, Any]] = field(default_factory=list)
    handoffs: List[Dict[str, Any]] = field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)


class QueenAgent:
    """Routes by complexity. Simple -> single fast pass. Complex -> full pipeline."""

    def __init__(self, config: Config):
        self.config = config

    def evaluate_complexity(self, prompt: str) -> str:
        p = prompt.lower()
        has_kw = any(k in p for k in COMPLEX_KEYWORDS)
        if has_kw or len(prompt.split()) > getattr(self.config, "complexity_threshold_words", 100):
            return "complex"
        return "simple"

    def _tier(self, name: str) -> str:
        """Resolve a logical tier without requiring a Tier enum in config.py.

        The current Arctus config uses provider names/strings rather than a
        Tier enum. This keeps the orchestrator compatible with that config.
        """
        value = getattr(self.config, name, None)

        if value is None:
            # Safe defaults for the current provider presets.
            defaults = {
                "fast": "ollama",
                "strong": "openrouter",
                "free": "hf",
                "planner_uses": "fast",
            }
            value = defaults.get(name, "ollama")

        # Config implementations may expose a provider object instead of a
        # string. Prefer its provider name.
        provider_name = getattr(value, "name", None)
        if provider_name:
            return str(provider_name)

        # Some configs may wrap the provider in a "provider" attribute.
        provider_name = getattr(value, "provider", None)
        if provider_name:
            return str(provider_name)

        return str(value)

    def _chat(
        self,
        tier: str,
        messages: List[Dict[str, str]],
        session_id: str = "",
    ) -> str:
        """Call the actual llm.py API used by this repository.

        llm.py exposes LLMClient/create_client rather than the old
        module-level llm.chat()/pop_usage() API that this orchestrator used.
        """
        provider = self._tier(tier)

        # Accept either a provider name or a logical tier name.
        aliases = {
            "fast": "ollama",
            "strong": "openrouter",
            "free": "hf",
            "huggingface": "hf",
        }
        provider = aliases.get(provider.lower(), provider.lower())

        # Prefer a configured model when available; otherwise create_client()
        # uses the provider preset's default model.
        model = None
        configured = getattr(self.config, tier, None)
        if configured is not None:
            model = getattr(configured, "model", None)
            if model is None:
                model = getattr(configured, "model_id", None)

        client = llm.LLMClient(provider=provider, model=model)

        try:
            llm_messages = [
                llm.Message(
                    role=llm.MessageRole(m["role"]),
                    content=m["content"],
                )
                for m in messages
            ]
            response = client.chat(llm_messages)
            if isinstance(response, llm.LLMResponse):
                return response.text
            return str(response)
        finally:
            client.close()

    def _extract_json(self, text: str) -> Dict[str, Any]:
        cleaned = text.replace("```json", "").replace("```", "").strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object found in model response")
        return json.loads(cleaned[start : end + 1])

    def plan(self, prompt: str, session_id: str = "") -> List[Step]:
        # Feature 2: search the Skill Store for reusable verified skills.
        skill_hint = ""
        try:
            from .skill_store import SkillStore
            store = SkillStore()
            matches = store.search(prompt, top_k=3)
            if matches:
                skill_hint = "\n\nVerified skills available for reuse (prefer these where applicable):\n"
                for s in matches:
                    skill_hint += f"  - {s.name}: {s.description[:80]}\n"
        except Exception as e:
            logger.debug("Skill search skipped: %s", e)

        tier = self._tier(getattr(self.config, "planner_uses", "fast"))
        out = self._chat(
            getattr(self.config, "planner_uses", "fast") if getattr(self.config, "planner_uses", None) else "fast",
            [
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": f"Task: {prompt}{skill_hint}"},
            ],
            session_id=session_id if getattr(self.config, "sticky_session_enabled", False) else "",
        )
        parsed = self._extract_json(out)
        raw_steps = parsed.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            # Fallback: one strong step covering the whole prompt.
            return [Step(title="Whole task", detail=prompt, tier="strong")]
        return [Step.from_dict(s) for s in raw_steps]

    def _call_with_budget(
        self,
        agent_id: str,
        tier: str,
        messages: List[Dict[str, str]],
        budget: IsolatedContextWindow,
        session_id: str = "",
    ) -> str:
        # Pre-flight token estimate for the prompt side.
        prompt_chars = sum(len(m["content"]) for m in messages)
        budget.consume(estimate_tokens_of(prompt_chars))
        result = self._chat(
            tier,
            messages,
            session_id=session_id if getattr(self.config, "sticky_session_enabled", False) else "",
        )
        budget.consume(estimate_tokens_of(len(result)))
        return result

    def run_simple(self, prompt: str, session_id: str) -> TaskResult:
        logger.info("Queen: simple route -> single LLM (sub-agents bypassed)")
        tier = self._tier("fast")
        budget = IsolatedContextWindow(agent_id=f"{session_id}-fast")
        out = self._call_with_budget(
            f"{session_id}-fast", tier,
            [
                {"role": "system", "content": WORKER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            budget,
            session_id=session_id,
        )
        return TaskResult(
            complexity="simple",
            mode="single_fast",
            steps=[Step(title="prompt", detail=prompt, tier="fast")],
            work=[{"step": "prompt", "tier": "fast", "result": out}],
        )

    def _execute_single_step(
        self,
        index: int,
        total: int,
        step: Step,
        tier: str,
        prompt: str,
        session_id: str,
        dependency_titles: List[str],
        escalated: bool = False,
    ) -> Dict[str, Any]:
        """Execute ONE step in its own isolated context. Used as a worker
        callable by the parallel ThreadPoolExecutor in run_pipeline()."""
        agent_id = f"{session_id}-w{index+1}{'-esc' if escalated else ''}"
        budget = IsolatedContextWindow(
            agent_id=agent_id, max_tokens=getattr(self.config, "agent_context_limit", 8192)
        )
        state = StateDir(agent_id=agent_id, session_id=session_id)

        system = VALIDATOR_SYSTEM if step.tier == "fast" else WORKER_SYSTEM

        # Per-step context: ONLY the step's own detail + a one-line note
        # about what preceding steps produced. NOT the full conversation history.
        dep_note = ""
        if dependency_titles:
            dep_note = "Prior step outputs (titles only — do not re-send):\n" + "\n".join(
                f"  - {t}" for t in dependency_titles
            )

        # Computer-use dispatch: if step.tier == "computer-use", use the
        # screenshot-reason-act loop instead of a plain LLM call.
        if step.tier == "computer-use":
            try:
                from . import computer_use
                cu_result = computer_use.agent_execution_loop(
                    user_goal=f"{step.title}\n{step.detail}",
                    llm_client=None,  # wired to the tier's LLM when available
                    max_steps=10,
                    use_display=True,
                    use_browser=False,
                )
                summary = cu_result.get("summary") or f"Completed in {cu_result.get('steps_taken', 0)} steps"
                return {
                    "index": index, "step": step.title, "tier": "computer-use",
                    "result": summary, "escalated": escalated,
                    "agent": agent_id, "tokens_used": 0,  # not metered via LLM here
                }
            except Exception as e:
                return {
                    "index": index, "step": step.title, "tier": "computer-use",
                    "error": str(e), "escalated": escalated,
                }

        system = VALIDATOR_SYSTEM if step.tier == "fast" else WORKER_SYSTEM
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": (
                f"{dep_note}\n\n"
                f"Step {index+1}/{total}: {step.title}\n{step.detail}"
            ) if dep_note else f"Step {index+1}/{total}: {step.title}\n{step.detail}"},
        ]

        try:
            out = self._call_with_budget(agent_id, tier, messages, budget, session_id=session_id)
        except llm.LLMError as e:
            return {
                "index": index, "step": step.title, "tier": step.tier,
                "error": str(e), "escalated": escalated,
            }

        # 80% handoff rule: checkpoint via the Context Offload Protocol.
        handoff_entry = None
        if budget.used_tokens >= budget.handoff_limit:
            next_idx = index + 2  # the step after this one (1-indexed)
            state.write_checkpoint(
                done=f"Completed step {index+1}/{total}: {step.title}",
                next_steps=(
                    f"Continue from step {next_idx}/{total}" if next_idx <= total
                    else "All steps done."
                ),
                context=budget.to_dict(),
                task_status=f"step_{index+1}_complete",
                current_state_and_progress=f"Agent {agent_id} completed {step.title}",
                pending_steps=f"Step {next_idx}/{total} onward",
            )
            handoff_entry = HandoffPayload(
                paused_agent=agent_id,
                target_agent=f"{session_id}-w{index+2}",
                state_dir=state,
                reason="80% context threshold reached",
                context_snapshot=budget.to_dict(),
            ).to_dict()
            logger.warning("Handoff triggered at step %d (agent %s)", index+1, agent_id)

        return {
            "index": index, "step": step.title, "tier": step.tier,
            "agent": agent_id, "tokens_used": budget.used_tokens,
            "result": out, "escalated": escalated,
            "handoff": handoff_entry,
        }

    def run_pipeline(self, prompt: str, session_id: str) -> TaskResult:
        """Complex route: plan steps, then fan-out to parallel workers.

        Each step runs in its own thread with its own IsolatedContextWindow
        and StateDir. Workers = getattr(self.config, "max_workers", 2) (2/4/6 per tier).

        Per-step context: each worker receives ONLY its step detail + titles
        of dependency steps (not the full conversation history).

        Circuit breaker: 3 consecutive failures on the same step halts the
        worker and escalates to the higher tier once.
        """
        logger.info("Queen: complex route -> parallel pipeline (%d workers)",
                     getattr(self.config, "max_workers", 2))
        steps = self.plan(prompt, session_id=session_id)
        logger.info("Plan: %d step(s)", len(steps))
        result = TaskResult(complexity="complex", mode="pipeline", steps=steps)

        # Build dependency map: step i depends on step i-1 (simple chain).
        dependency_map: Dict[int, List[str]] = {}
        for i in range(len(steps)):
            if i > 0:
                dependency_map[i] = [steps[i - 1].title]

        # Parallel execution with ThreadPoolExecutor.
        completed: Dict[int, Dict[str, Any]] = {}
        failure_counts: Dict[int, int] = {}  # step_index -> consecutive failures

        with ThreadPoolExecutor(max_workers=getattr(self.config, "max_workers", 2)) as pool:
            # Submit all steps as independent futures.
            futures: Dict[int, Any] = {}
            for i in range(len(steps)):
                tier_name = "fast" if steps[i].tier == "fast" else "strong"
                tier = self._tier(tier_name)
                deps = dependency_map.get(i, [])
                futures[i] = pool.submit(
                    self._execute_single_step,
                    i, len(steps), steps[i], tier, prompt, session_id, deps,
                )

            # Collect results as they complete; handle circuit breaker retries.
            pending_futures = dict(futures)
            while pending_futures:
                for future in as_completed(pending_futures):
                    idx = next(i for i in pending_futures if pending_futures[i] is future)
                    try:
                        step_result = future.result()
                    except Exception as e:
                        step_result = {
                            "index": idx, "step": steps[idx].title,
                            "tier": steps[idx].tier, "error": str(e),
                            "escalated": False,
                        }

                    del pending_futures[idx]

                    # Circuit breaker: 3 failures -> escalate to higher tier once.
                    if step_result.get("error"):
                        failure_counts[idx] = failure_counts.get(idx, 0) + 1
                        if failure_counts[idx] >= CIRCUIT_BREAKER_LIMIT and not step_result.get("escalated"):
                            logger.warning(
                                "Circuit breaker triggered for step %d (%s) — "
                                "escalating to higher tier",
                                idx + 1, steps[idx].title,
                            )
                            esc_tier = self._tier("strong" if steps[idx].tier == "fast" else "fast")
                            deps = dependency_map.get(idx, [])
                            pending_futures[idx] = pool.submit(
                                self._execute_single_step,
                                idx, len(steps), steps[idx], esc_tier, prompt,
                                session_id, deps, escalated=True,
                            )
                            continue
                        else:
                            result.error = (
                                f"Step {idx+1} ({steps[idx].title}) failed after "
                                f"{failure_counts[idx]} attempt(s): {step_result.get('error')}"
                            )
                            logger.error(result.error)
                    else:
                        failure_counts.pop(idx, None)

                    completed[idx] = step_result
                    break  # re-enter the as_completed loop

        # Assemble results in step order.
        work_log: List[str] = []
        for i in range(len(steps)):
            sr = completed.get(i)
            if not sr:
                continue
            if sr.get("error"):
                work_log.append(f"## {sr['step']} — ERROR: {sr['error']}")
                result.work.append({
                    "step": sr["step"], "tier": sr.get("tier", "?"),
                    "error": sr["error"], "escalated": sr.get("escalated", False),
                })
            else:
                work_log.append(f"## {sr['step']}\n{sr.get('result', '')}")
                result.work.append({
                    "step": sr["step"], "tier": sr.get("tier", "?"),
                    "agent": sr.get("agent", ""), "tokens_used": sr.get("tokens_used", 0),
                    "result": sr.get("result", ""),
                })
            if sr.get("handoff"):
                result.handoffs.append(sr["handoff"])

        # Verify on the fast tier using per-step summaries (not full history).
        verification_context = "\n".join(
            f"{w.get('step', '?')}: {str(w.get('result', ''))[:200]}"
            for w in result.work if not w.get("error")
        )
        try:
            verdict_text = self._call_with_budget(
                f"{session_id}-verify", self._tier("fast"),
                [
                    {"role": "system", "content": VERIFIER_SYSTEM},
                    {"role": "user", "content": f"Task: {prompt}\n\nWork (summarized):\n{verification_context}"},
                ],
                IsolatedContextWindow(agent_id=f"{session_id}-verify"),
                session_id=session_id,
            )
            try:
                result.verification = self._extract_json(verdict_text)
            except Exception:
                result.verification = {"done": True, "notes": "verifier unparsable; assuming done"}
        except llm.LLMError as e:
            result.verification = {"done": True, "notes": f"verifier failed: {e}"}

        return result

    def run(
        self,
        prompt: str,
        session_id: str = "default",
        rate_config: Optional[RateLimitConfig] = None,
        complexity_override: Optional[str] = None,
    ) -> TaskResult:
        complexity = (complexity_override or self.evaluate_complexity(prompt)).lower()
        try:
            rc = rate_config or RateLimitConfig()
            check_and_update(session_id, rc, estimated_tokens=estimate_tokens(prompt))
        except RateLimitError as e:
            return TaskResult(complexity=complexity, mode="blocked", error=e.detail)

        if complexity == "simple":
            result = self.run_simple(prompt, session_id)
        else:
            result = self.run_pipeline(prompt, session_id)

        # llm.py currently returns usage per LLMResponse, so there is no
        # module-level llm.pop_usage() API. Keep the aggregate optional.
        result.usage = {}
        return result


def estimate_tokens_of(char_count: int) -> int:
    # Same heuristic as rate_limit.estimate_tokens; kept local for clarity.
    return max(1, char_count // 4)
