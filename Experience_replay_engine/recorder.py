"""
Experience Recorder — Captures complete execution history from the Arctus pipeline.
"""

import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import json
import copy


@dataclass
class ExecutionSnapshot:
    """Point-in-time snapshot during execution."""
    step_number: int
    timestamp: float
    event_type: str  # 'decision', 'tool_call', 'agent_message', 'verification', etc.
    data: Dict[str, Any]
    context_hash: Optional[str] = None


class ExperienceRecorder:
    """
    Records complete execution experiences from the Arctus pipeline.
    Integrates with Reasoning, Planning, and Execution engines.
    """
    
    CAPTURE_FIELDS = [
        'user_intent', 'execution_plan', 'execution_dag', 'agent_decisions',
        'model_selection', 'tool_invocations', 'capability_usage', 'context_assembly',
        'memory_retrieval', 'prompt_versions', 'execution_timeline',
        'intermediate_results', 'verification_results', 'performance_metrics',
        'resource_usage', 'final_outcome'
    ]
    
    def __init__(self, storage, config):
        self.storage = storage
        self.config = config
        self._active_sessions: Dict[str, Dict] = {}
        self._snapshots: Dict[str, List[ExecutionSnapshot]] = {}
        self._hooks: Dict[str, List[Callable]] = {}
    
    def start_session(self, user_intent: str, context: Optional[Dict] = None) -> str:
        """
        Begin recording a new execution session.
        Called when user request enters the Reasoning Engine.
        """
        session_id = str(uuid.uuid4())
        
        self._active_sessions[session_id] = {
            'session_id': session_id,
            'start_time': datetime.now(),
            'user_intent': user_intent,
            'context': context or {},
            'status': 'recording',
            'capture': {field: None for field in self.CAPTURE_FIELDS}
        }
        
        self._snapshots[session_id] = []
        
        # Initialize capture fields
        self._active_sessions[session_id]['capture']['user_intent'] = user_intent
        self._active_sessions[session_id]['capture']['execution_timeline'] = []
        
        return session_id
    
    def record_planning(self, session_id: str, execution_plan: Dict, execution_dag: Dict):
        """Record planning phase output."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['execution_plan'] = execution_plan
        self._active_sessions[session_id]['capture']['execution_dag'] = execution_dag
        
        self._add_snapshot(session_id, 'planning_complete', {
            'plan': execution_plan,
            'dag': execution_dag
        })
    
    def record_decision(self, session_id: str, decision: Dict):
        """Record an agent decision."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['agent_decisions'] is None:
            self._active_sessions[session_id]['capture']['agent_decisions'] = []
        
        self._active_sessions[session_id]['capture']['agent_decisions'].append({
            'timestamp': datetime.now().isoformat(),
            **decision
        })
        
        self._add_snapshot(session_id, 'agent_decision', decision)
    
    def record_model_selection(self, session_id: str, selection: Dict):
        """Record model selection decision."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['model_selection'] = selection
    
    def record_tool_invocation(self, session_id: str, tool_call: Dict):
        """Record a tool/function invocation."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['tool_invocations'] is None:
            self._active_sessions[session_id]['capture']['tool_invocations'] = []
        
        invocation_record = {
            'timestamp': datetime.now().isoformat(),
            'tool_name': tool_call.get('name'),
            'arguments': tool_call.get('arguments'),
            'result': tool_call.get('result'),
            'latency_ms': tool_call.get('latency_ms'),
            'success': tool_call.get('success', True),
            'error': tool_call.get('error')
        }
        
        self._active_sessions[session_id]['capture']['tool_invocations'].append(invocation_record)
        self._add_snapshot(session_id, 'tool_invocation', invocation_record)
    
    def record_capability_usage(self, session_id: str, capabilities: List[str]):
        """Record which system capabilities were used."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['capability_usage'] = capabilities
    
    def record_context_assembly(self, session_id: str, context: Dict):
        """Record how context was assembled for the execution."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['context_assembly'] = context
    
    def record_memory_retrieval(self, session_id: str, memories: List[Dict]):
        """Record memories retrieved during execution."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['memory_retrieval'] = memories
    
    def record_prompt_version(self, session_id: str, prompt_name: str, version: str, content: str):
        """Record prompt version used."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['prompt_versions'] is None:
            self._active_sessions[session_id]['capture']['prompt_versions'] = {}
        
        self._active_sessions[session_id]['capture']['prompt_versions'][prompt_name] = {
            'version': version,
            'hash': hash(content) & 0xFFFFFFFF,
            'length': len(content)
        }
    
    def record_intermediate_result(self, session_id: str, step: int, result: Dict):
        """Record intermediate execution result."""
        self._ensure_session(session_id)
        
        if self._active_sessions[session_id]['capture']['intermediate_results'] is None:
            self._active_sessions[session_id]['capture']['intermediate_results'] = []
        
        self._active_sessions[session_id]['capture']['intermediate_results'].append({
            'step': step,
            'timestamp': datetime.now().isoformat(),
            'result': result
        })
    
    def record_verification(self, session_id: str, verification: Dict):
        """Record verification engine results."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['verification_results'] = verification
        
        self._add_snapshot(session_id, 'verification', verification)
    
    def record_performance_metrics(self, session_id: str, metrics: Dict):
        """Record performance metrics."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['performance_metrics'] = metrics
    
    def record_resource_usage(self, session_id: str, usage: Dict):
        """Record resource consumption."""
        self._ensure_session(session_id)
        self._active_sessions[session_id]['capture']['resource_usage'] = usage
    
    def finalize_session(
        self,
        session_id: str,
        final_outcome: Dict,
        classification: Optional[str] = None
    ):
        """
        Finalize recording and create an ExperienceRecord.
        Called after Execution Engine completes.
        """
        self._ensure_session(session_id)
        session = self._active_sessions[session_id]
        
        session['capture']['final_outcome'] = final_outcome
        session['end_time'] = datetime.now()
        session['status'] = 'completed'
        
        # Calculate execution timeline from snapshots
        session['capture']['execution_timeline'] = [
            {
                'step': s.step_number,
                'timestamp': s.timestamp,
                'event_type': s.event_type,
                'data_summary': self._summarize_snapshot_data(s.data)
            }
            for s in self._snapshots.get(session_id, [])
        ]
        
        # Build the experience record
        experience_id = str(uuid.uuid4())
        
        # NOTE: ExperienceRecord needs to be imported/defined depending on your project structure
        experience = ExperienceRecord(
            experience_id=experience_id,
            session_id=session_id,
            timestamp=session['start_time'],
            version=1,
            **session['capture']
        )
        
        # Store in database
        self.storage.save_experience(experience)
        
        # Clean up
        del self._active_sessions[session_id]
        del self._snapshots[session_id]
        
        # Notify hooks
        self._notify_hooks('experience_recorded', experience)
        
        return experience
    
    def _ensure_session(self, session_id: str):
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")
    
    def _add_snapshot(self, session_id: str, event_type: str, data: Dict):
        snapshots = self._snapshots[session_id]
        snapshot = ExecutionSnapshot(
            step_number=len(snapshots),
            timestamp=time.time(),
            event_type=event_type,
            data=copy.deepcopy(data),
            context_hash=self._hash_context(data)
        )
        snapshots.append(snapshot)
    
    def _hash_context(self, data: Dict) -> str:
        """Create hash of context for deduplication."""
        return str(hash(json.dumps(data, sort_keys=True, default=str)) & 0xFFFFFFFF)
    
    def _summarize_snapshot_data(self, data: Dict) -> Dict:
        """Create a summary of snapshot data for timeline."""
        return {
            'keys': list(data.keys()),
            'size': len(json.dumps(data, default=str)),
            'has_result': 'result' in data,
            'has_error': 'error' in data
        }
    
    def register_hook(self, event: str, callback: Callable):
        """Register a callback for recording events."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)
    
    def _notify_hooks(self, event: str, data: Any):
        """Notify registered hooks."""
        for callback in self._hooks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                print(f"Hook error for {event}: {e}")
    
    def get_active_sessions(self) -> List[str]:
        """Get list of currently recording session IDs."""
        return list(self._active_sessions.keys())
