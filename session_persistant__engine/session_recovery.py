"""
session_recovery.py
Session recovery engine with automatic and manual recovery modes.
Implements validation, conflict detection, and version compatibility checks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Awaitable

from session_models import (
    SessionState, SessionStatus, RecoveryType, RecoveryLog,
    SessionSnapshot, SubtaskStatus, AgentStatus
)
from session_events import (
    RecoveryInitiated, RecoveryCompleted, RecoveryValidated,
    EventBus
)


logger = logging.getLogger("session.recovery")


class RecoveryError(Exception):
    """Base recovery exception."""
    pass


class ValidationError(RecoveryError):
    """State validation failed."""
    pass


class VersionIncompatibleError(RecoveryError):
    """Session version incompatible with current code."""
    pass


class ConflictDetectedError(RecoveryError):
    """Conflicting changes detected during recovery."""
    pass


@dataclass
class RecoveryPlan:
    """Plan for recovering a session."""
    session_id: str
    from_version: int
    target_version: Optional[int]
    steps: List[str]
    validation_checks: List[str]
    expected_duration_seconds: float
    risk_level: str  # low, medium, high


@dataclass
class ValidationResult:
    """Result of recovery validation."""
    passed: bool
    checks: Dict[str, bool]
    errors: List[str]
    warnings: List[str]
    recovered_state: Optional[SessionState] = None


class StateValidator:
    """
    Validates session state integrity after recovery.
    Checks structural consistency, referential integrity, and business rules.
    """
    
    def __init__(self) -> None:
        self._checks: Dict[str, Callable[[SessionState], bool]] = {}
        self._register_default_checks()
    
    def _register_default_checks(self) -> None:
        """Register built-in validation checks."""
        self._checks = {
            "session_id_present": lambda s: bool(s.session_id),
            "tenant_id_present": lambda s: bool(s.tenant_id),
            "owner_id_present": lambda s: bool(s.owner_id),
            "agent_memory_valid": self._check_agent_memory,
            "execution_plan_consistent": self._check_execution_plan,
            "subtask_references_valid": self._check_subtasks,
            "vm_state_reachable": self._check_vm_state,
            "browser_state_reachable": self._check_browser_state,
            "terminal_state_reachable": self._check_terminal_state,
            "version_positive": lambda s: s.version > 0,
            "timestamps_valid": self._check_timestamps,
            "conversation_consistent": self._check_conversation,
            "workspace_devices_valid": self._check_workspace,
        }
    
    def _check_agent_memory(self, state: SessionState) -> bool:
        """Validate agent memory structure."""
        mem = state.agent_memory
        return (
            bool(mem.agent_id) and
            isinstance(mem.short_term, list) and
            isinstance(mem.working_memory, dict)
        )
    
    def _check_execution_plan(self, state: SessionState) -> bool:
        """Validate execution plan consistency."""
        plan = state.execution_plan
        if not plan.stages:
            return True  # Empty plan is valid
        
        # Check all stage dependencies exist
        stage_ids = {s.stage_id for s in plan.stages}
        for stage in plan.stages:
            for dep in stage.dependencies:
                if dep not in stage_ids:
                    return False
        
        return True
    
    def _check_subtasks(self, state: SessionState) -> bool:
        """Validate subtask references."""
        all_subtasks = set()
        for stage in state.execution_plan.stages:
            for subtask in stage.subtasks:
                all_subtasks.add(subtask.subtask_id)
        
        # Running and queued subtasks should exist in plan
        for subtask in state.running_subtasks:
            if subtask.subtask_id not in all_subtasks:
                return False
        
        return True
    
    def _check_vm_state(self, state: SessionState) -> bool:
        """Validate VM state reference if present."""
        if state.vm_state is None:
            return True
        return bool(state.vm_state.vm_id and state.vm_state.state_bucket)
    
    def _check_browser_state(self, state: SessionState) -> bool:
        """Validate browser state reference if present."""
        if state.browser_state is None:
            return True
        return bool(state.browser_state.browser_id)
    
    def _check_terminal_state(self, state: SessionState) -> bool:
        """Validate terminal state reference if present."""
        if state.terminal_state is None:
            return True
        return bool(state.terminal_state.terminal_id)
    
    def _check_timestamps(self, state: SessionState) -> bool:
        """Validate timestamp ordering."""
        return (
            state.created_at <= state.updated_at and
            state.updated_at >= state.last_activity_at
        )
    
    def _check_conversation(self, state: SessionState) -> bool:
        """Validate conversation state."""
        conv = state.conversation
        if not conv.messages:
            return True
        
        # Messages should be chronologically ordered
        for i in range(1, len(conv.messages)):
            if conv.messages[i].timestamp < conv.messages[i-1].timestamp:
                return False
        
        return True
    
    def _check_workspace(self, state: SessionState) -> bool:
        """Validate workspace device connections."""
        ws = state.workspace
        # Device IDs should be unique
        device_ids = [d.device_id for d in ws.active_devices]
        return len(device_ids) == len(set(device_ids))
    
    def add_check(
        self,
        name: str,
        check: Callable[[SessionState], bool]
    ) -> None:
        """Add custom validation check."""
        self._checks[name] = check
    
    async def validate(self, state: SessionState) -> ValidationResult:
        """
        Run all validation checks against recovered state.
        """
        checks: Dict[str, bool] = {}
        errors: List[str] = []
        warnings: List[str] = []
        
        for name, check in self._checks.items():
            try:
                # Run check with timeout
                result = await asyncio.wait_for(
                    asyncio.to_thread(check, state),
                    timeout=5.0
                )
                checks[name] = bool(result)
                if not result:
                    errors.append(f"Validation check failed: {name}")
            except asyncio.TimeoutError:
                checks[name] = False
                errors.append(f"Validation check timed out: {name}")
            except Exception as e:
                checks[name] = False
                errors.append(f"Validation check error '{name}': {str(e)}")
        
        # Additional heuristic checks
        if state.status == SessionStatus.RECOVERING:
            warnings.append("Session still in recovering state - may need manual intervention")
        
        # Check for stale subtasks
        stale_subtasks = [
            s for s in state.running_subtasks
            if s.started_at and (datetime.utcnow() - s.started_at).total_seconds() > 86400
        ]
        if stale_subtasks:
            warnings.append(f"Found {len(stale_subtasks)} stale running subtasks")
        
        passed = all(checks.values()) and not errors
        
        return ValidationResult(
            passed=passed,
            checks=checks,
            errors=errors,
            warnings=warnings,
            recovered_state=state if passed else None
        )


class RecoveryEngine:
    """
    Core recovery engine implementing multiple recovery strategies.
    """
    
    # Maximum version gap allowed for automatic recovery
    MAX_AUTO_RECOVERY_VERSION_GAP = 10
    
    # Maximum age for automatic recovery (7 days)
    MAX_AUTO_RECOVERY_AGE_DAYS = 7
    
    def __init__(
        self,
        event_bus: EventBus,
        validator: StateValidator,
        version_compatibility: Optional[Dict[int, str]] = None
    ) -> None:
        self.event_bus = event_bus
        self.validator = validator
        self.version_compatibility = version_compatibility or {}
        self._recovery_strategies: Dict[str, Callable] = {
            "latest_snapshot": self._recover_from_latest_snapshot,
            "version_rollback": self._recover_by_version_rollback,
            "state_rebuild": self._recover_by_state_rebuild,
            "minimal_boot": self._recover_minimal_boot,
        }
    
    async def create_recovery_plan(
        self,
        session: SessionState,
        recovery_type: RecoveryType
    ) -> RecoveryPlan:
        """
        Analyze session and create optimal recovery plan.
        """
        steps = []
        risk_level = "low"
        
        # Determine available snapshots
        available_snapshots = session.snapshots
        
        if available_snapshots:
            latest = max(available_snapshots, key=lambda s: s.version)
            from_version = latest.version
            steps.append(f"Restore from snapshot {latest.snapshot_id} (v{latest.version})")
        else:
            from_version = 1
            steps.append("No snapshots available - will attempt state rebuild")
            risk_level = "high"
        
        # Analyze gaps
        version_gap = session.version - from_version
        
        if version_gap > self.MAX_AUTO_RECOVERY_VERSION_GAP:
            steps.append(f"Large version gap ({version_gap}) - full state rebuild recommended")
            risk_level = "high"
        elif version_gap > 0:
            steps.append(f"Replay {version_gap} events to reach current")
        
        # Check component states
        if session.vm_state:
            steps.append(f"Reconnect VM: {session.vm_state.vm_id}")
        if session.browser_state:
            steps.append(f"Reconnect browser: {session.browser_state.browser_id}")
        if session.terminal_state:
            steps.append(f"Reconnect terminal: {session.terminal_state.terminal_id}")
        
        # Determine target
        target_version = session.version if recovery_type != RecoveryType.FORCED else None
        
        # Calculate expected duration
        expected_duration = 5.0 + (version_gap * 0.5)  # heuristic
        
        # Adjust risk for manual recovery
        if recovery_type == RecoveryType.MANUAL:
            risk_level = "medium" if risk_level == "low" else "high"
            steps.insert(0, "Manual recovery - operator review required")
        
        return RecoveryPlan(
            session_id=session.session_id,
            from_version=from_version,
            target_version=target_version,
            steps=steps,
            validation_checks=list(self.validator._checks.keys()),
            expected_duration_seconds=expected_duration,
            risk_level=risk_level
        )
    
    async def execute_recovery(
        self,
        session: SessionState,
        recovery_type: RecoveryType,
        plan: Optional[RecoveryPlan] = None
    ) -> Tuple[SessionState, RecoveryLog]:
        """
        Execute recovery for a session.
        """
        start_time = time.time()
        
        if plan is None:
            plan = await self.create_recovery_plan(session, recovery_type)
        
        # Emit recovery initiated event
        await self.event_bus.publish(RecoveryInitiated(
            event_type="recovery.initiated",
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            recovery_type=recovery_type.value,
            from_version=plan.from_version,
            target_version=plan.target_version,
            recovery_plan={"steps": plan.steps, "risk": plan.risk_level}
        ))
        
        # Pre-recovery validation
        if recovery_type == RecoveryType.AUTOMATIC and plan.risk_level == "high":
            raise RecoveryError(
                f"Automatic recovery refused for high-risk plan. "
                f"Use manual recovery for session {session.session_id}"
            )
        
        # Check version compatibility
        if not self._check_version_compatibility(session.version):
            raise VersionIncompatibleError(
                f"Session version {session.version} incompatible with current runtime"
            )
        
        # Execute recovery strategy
        strategy = self._select_strategy(plan)
        recovered_state = await strategy(session, plan)
        
        # Post-recovery validation
        validation = await self.validator.validate(recovered_state)
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Create recovery log
        log = RecoveryLog(
            session_id=session.session_id,
            recovery_type=recovery_type,
            started_at=datetime.utcfromtimestamp(start_time),
            completed_at=datetime.utcnow(),
            success=validation.passed,
            from_snapshot_id=plan.from_version if plan.from_version else None,
            to_version=recovered_state.version,
            errors=validation.errors,
            validation_results=validation.checks
        )
        
        # Update state
        recovered_state.recovery_logs.append(log)
        
        if validation.passed:
            recovered_state.status = SessionStatus.ACTIVE
            recovered_state.touch()
        else:
            recovered_state.status = SessionStatus.FAILED
            if recovery_type == RecoveryType.AUTOMATIC:
                # Escalate to manual
                logger.warning(
                    f"Auto-recovery failed for {session.session_id}, "
                    f"escalating to manual: {validation.errors}"
                )
        
        # Emit events
        await self.event_bus.publish(RecoveryCompleted(
            event_type="recovery.completed",
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            recovery_id=log.log_id,
            success=validation.passed,
            final_version=recovered_state.version,
            duration_ms=duration_ms
        ))
        
        await self.event_bus.publish(RecoveryValidated(
            event_type="recovery.validated",
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            recovery_id=log.log_id,
            validation_passed=validation.passed,
            checks=validation.checks
        ))
        
        return recovered_state, log
    
    def _select_strategy(
        self,
        plan: RecoveryPlan
    ) -> Callable[[SessionState, RecoveryPlan], Awaitable[SessionState]]:
        """Select best recovery strategy based on plan."""
        if plan.from_version == plan.target_version:
            return self._recovery_strategies["latest_snapshot"]
        elif plan.target_version and plan.from_version < plan.target_version:
            return self._recovery_strategies["version_rollback"]
        elif "state rebuild" in " ".join(plan.steps).lower():
            return self._recovery_strategies["state_rebuild"]
        else:
            return self._recovery_strategies["minimal_boot"]
    
    async def _recover_from_latest_snapshot(
        self,
        session: SessionState,
        plan: RecoveryPlan
    ) -> SessionState:
        """Recover from most recent snapshot."""
        if not session.snapshots:
            raise RecoveryError("No snapshots available for recovery")
        
        latest = max(session.snapshots, key=lambda s: s.created_at)
        
        # In production, load actual snapshot data from storage
        # For now, validate and return current state
        recovered = session.model_copy(deep=True)
        recovered.status = SessionStatus.RECOVERING
        recovered.version = latest.version
        
        # Reset transient runtime state
        for subtask in recovered.running_subtasks:
            subtask.status = SubtaskStatus.QUEUED
            subtask.started_at = None
        
        logger.info(f"Recovered session {session.session_id} from snapshot {latest.snapshot_id}")
        return recovered
    
    async def _recover_by_version_rollback(
        self,
        session: SessionState,
        plan: RecoveryPlan
    ) -> SessionState:
        """Recover by rolling back to specific version."""
        recovered = session.model_copy(deep=True)
        recovered.status = SessionStatus.RECOVERING
        
        # Mark incomplete subtasks for retry
        for subtask in recovered.running_subtasks:
            subtask.status = SubtaskStatus.RETRYING
            subtask.retry_count += 1
        
        # Re-queue failed subtasks
        for stage in recovered.execution_plan.stages:
            for subtask in stage.subtasks:
                if subtask.status == SubtaskStatus.FAILED:
                    subtask.status = SubtaskStatus.QUEUED
        
        logger.info(f"Rolled back session {session.session_id} to version {plan.from_version}")
        return recovered
    
    async def _recover_by_state_rebuild(
        self,
        session: SessionState,
        plan: RecoveryPlan
    ) -> SessionState:
        """Rebuild state from component references."""
        recovered = session.model_copy(deep=True)
        recovered.status = SessionStatus.RECOVERING
        
        # Reconnect to external systems
        if recovered.vm_state:
            recovered.metadata["vm_reconnect_pending"] = True
        if recovered.browser_state:
            recovered.metadata["browser_reconnect_pending"] = True
        if recovered.terminal_state:
            recovered.metadata["terminal_reconnect_pending"] = True
        
        # Reset agent to idle
        recovered.agent_memory.working_memory = {}
        
        logger.info(f"Rebuilt session {session.session_id} from component references")
        return recovered
    
    async def _recover_minimal_boot(
        self,
        session: SessionState,
        plan: RecoveryPlan
    ) -> SessionState:
        """Minimal recovery - preserve identity, reset execution."""
        recovered = session.model_copy(deep=True)
        recovered.status = SessionStatus.RECOVERING
        
        # Preserve identity and conversation
        # Reset execution state
        recovered.execution_plan = session.execution_plan.model_copy()
        for stage in recovered.execution_plan.stages:
            for subtask in stage.subtasks:
                if subtask.status not in {SubtaskStatus.COMPLETED, SubtaskStatus.FAILED}:
                    subtask.status = SubtaskStatus.QUEUED
        
        recovered.running_subtasks = []
        recovered.queued_subtasks = []
        
        logger.info(f"Minimal boot recovery for session {session.session_id}")
        return recovered
    
    def _check_version_compatibility(self, version: int) -> bool:
        """Check if session version is compatible with current runtime."""
        if not self.version_compatibility:
            return True  # No restrictions
        
        # Check if version in compatible range
        compatible_versions = set(self.version_compatibility.keys())
        if compatible_versions and version not in compatible_versions:
            # Check if version is within supported range
            min_ver = min(compatible_versions)
            max_ver = max(compatible_versions)
            return min_ver <= version <= max_ver
        
        return True
    
    async def detect_conflicts(
        self,
        original: SessionState,
        recovered: SessionState
    ) -> List[Dict[str, Any]]:
        """
        Detect conflicts between original and recovered state.
        Used when multiple recovery a
