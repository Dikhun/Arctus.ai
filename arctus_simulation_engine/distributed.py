"""Distributed orchestration for multi-node simulation coordination."""

from __future__ import annotations

import multiprocessing
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

@dataclass
class Node:
    node_id: str
    address: str = ""
    last_heartbeat: float = field(default_factory=time.time)
    status: str = "active"
    capacity: int = 1
    current_load: int = 0

    def is_alive(self, timeout: float = 30.0) -> bool:
        return (time.time() - self.last_heartbeat) < timeout

@dataclass
class Task:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    payload: Dict[str, Any] = field(default_factory=dict)
    assigned_node: Optional[str] = None
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None

@dataclass
class Partition:
    partition_id: str
    node_ids: List[str] = field(default_factory=list)
    state_range: Tuple[int, int] = (0, 0)

class DistributedOrchestrator:
    def __init__(self, node_id: Optional[str] = None, local_mode: bool = False):
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.local_mode = local_mode
        self._nodes: Dict[str, Node] = {}
        self._tasks: Dict[str, Task] = {}
        self._results: Dict[str, Any] = {}
        self._task_queue: List[Task] = []
        self._lock = multiprocessing.Lock() if not local_mode else None
        self._barriers: Dict[str, set] = defaultdict(set)
        self._callbacks: Dict[str, Callable[[Any], None]] = {}

    def register_node(self, node: Node) -> None:
        if self.local_mode:
            return
        self._nodes[node.node_id] = node

    def heartbeat(self, node_id: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].last_heartbeat = time.time()

    def submit_task(self, payload: Dict[str, Any], callback: Optional[Callable[[Any], None]] = None) -> str:
        task = Task(payload=payload)
        self._tasks[task.task_id] = task
        self._task_queue.append(task)
        if callback:
            self._callbacks[task.task_id] = callback
        return task.task_id

    def distribute_task(self, task_id: str) -> Optional[str]:
        if task_id not in self._tasks:
            return None
        task = self._tasks[task_id]
        available = [n for n in self._nodes.values() if n.is_alive() and n.current_load < n.capacity]
        if not available:
            if not self.local_mode:
                return None
            target_id = self.node_id
        else:
            target = min(available, key=lambda n: n.current_load)
            target_id = target.node_id
            target.current_load += 1
        task.assigned_node = target_id
        task.status = "assigned"
        return target_id

    def execute_local(self, task_id: str, executor: Callable[[Dict[str, Any]], Any]) -> Any:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found")
        task = self._tasks[task_id]
        task.status = "running"
        try:
            result = executor(task.payload)
            task.result = result
            task.status = "completed"
            self._results[task_id] = result
            if task_id in self._callbacks:
                self._callbacks[task_id](result)
            if task.assigned_node and task.assigned_node in self._nodes:
                self._nodes[task.assigned_node].current_load -= 1
            return result
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            if task.assigned_node and task.assigned_node in self._nodes:
                self._nodes[task.assigned_node].current_load -= 1
            raise

    def collect_results(self, task_ids: Sequence[str], timeout: Optional[float] = None) -> Dict[str, Any]:
        deadline = time.time() + timeout if timeout else None
        collected: Dict[str, Any] = {}
        pending = set(task_ids)
        while pending:
            for tid in list(pending):
                if tid in self._results:
                    collected[tid] = self._results[tid]
                    pending.remove(tid)
                elif tid in self._tasks and self._tasks[tid].status == "failed":
                    collected[tid] = {"error": self._tasks[tid].error}
                    pending.remove(tid)
            if not pending:
                break
            if deadline and time.time() > deadline:
                break
            time.sleep(0.01)
        return collected

    def sync_barrier(self, barrier_id: str, participants: int, timeout: float = 60.0) -> bool:
        self._barriers[barrier_id].add(self.node_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self._barriers[barrier_id]) >= participants:
                return True
            time.sleep(0.05)
        return False

    def get_cluster_status(self) -> Dict[str, Any]:
        nodes = list(self._nodes.values())
        alive = sum(1 for n in nodes if n.is_alive())
        total_capacity = sum(n.capacity for n in nodes if n.is_alive())
        total_load = sum(n.current_load for n in nodes if n.is_alive())
        return {
            "total_nodes": len(nodes),
            "alive_nodes": alive,
            "total_capacity": total_capacity,
            "total_load": total_load,
            "pending_tasks": len([t for t in self._tasks.values() if t.status == "pending"]),
            "completed_tasks": len([t for t in self._tasks.values() if t.status == "completed"])
        }

    def rebalance(self) -> List[Tuple[str, str]]:
        moved = []
        overloaded = [n for n in self._nodes.values() if n.is_alive() and n.current_load > n.capacity]
        available = [n for n in self._nodes.values() if n.is_alive() and n.current_load < n.capacity]
        for src in overloaded:
            while src.current_load > src.capacity and available:
                tgt = min(available, key=lambda n: n.current_load)
                tasks_to_move = [t for t in self._tasks.values() if t.assigned_node == src.node_id and t.status == "pending"]
                if not tasks_to_move:
                    break
                task = tasks_to_move[0]
                task.assigned_node = tgt.node_id
                src.current_load -= 1
                tgt.current_load += 1
                moved.append((task.task_id, tgt.node_id))
                if tgt.current_load >= tgt.capacity:
                    available.remove(tgt)
        return moved
