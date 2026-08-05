"""
Experience Ranking — Importance scoring and prioritization of experiences.
"""

import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np

from .storage import ExperienceRecord


class ExperienceRanker:
    """
    Calculates importance scores for experiences to prioritize replay.
    Uses multiple signals: outcome, rarity, recency, user feedback.
    """
    
    def __init__(self, config):
        self.config = config
        self.decay_factor = 0.995  # Daily decay
    
    def score_experience(self, experience: ExperienceRecord) -> float:
        """
        Calculate comprehensive importance score for an experience.
        Score range: 0.0 to 1.0
        """
        scores = {
            'outcome': self._outcome_score(experience),
            'rarity': self._rarity_score(experience),
            'recency': self._recency_score(experience),
            'complexity': self._complexity_score(experience),
            'feedback': self._feedback_score(experience),
            'learning_potential': self._learning_potential(experience)
        }
        
        # Weighted combination
        weights = {
            'outcome': 0.25,
            'rarity': 0.20,
            'recency': 0.15,
            'complexity': 0.15,
            'feedback': 0.15,
            'learning_potential': 0.10
        }
        
        total_score = sum(scores[k] * weights[k] for k in scores)
        return min(1.0, max(0.0, total_score))
    
    def _outcome_score(self, exp: ExperienceRecord) -> float:
        """Score based on execution outcome."""
        if exp.classification == 'Successful Execution':
            return 0.7 + (exp.success_score * 0.3)
        elif exp.classification == 'Partial Success':
            return 0.4 + (exp.success_score * 0.3)
        elif exp.classification == 'Failure':
            return 0.8  # High importance for failures (learning opportunity)
        elif exp.classification == 'User Correction':
            return 0.9  # Very high - direct feedback
        elif exp.classification == 'Security Violation':
            return 1.0  # Critical
        else:
            return 0.5
    
    def _rarity_score(self, exp: ExperienceRecord) -> float:
        """Score based on how unusual/rare this experience is."""
        # Higher score for rare/unusual experiences
        # Would be calculated against full corpus in practice
        tool_count = len(exp.tool_invocations or [])
        decision_count = len(exp.agent_decisions or [])
        
        # Unusual tool usage patterns get higher scores
        if tool_count > 10 or decision_count > 20:
            return 0.8
        
        return 0.5
    
    def _recency_score(self, exp: ExperienceRecord) -> float:
        """Score based on how recent the experience is."""
        age_days = (datetime.now() - exp.timestamp).days
        return self.decay_factor ** age_days
    
    def _complexity_score(self, exp: ExperienceRecord) -> float:
        """Score based on execution complexity."""
        scores = []
        
        # Plan complexity
        if exp.execution_plan:
            scores.append(min(1.0, len(str(exp.execution_plan)) / 10000))
        
        # DAG complexity
        if exp.execution_dag:
            node_count = len(exp.execution_dag.get('nodes', []))
            scores.append(min(1.0, node_count / 50))
        
        # Tool variety
        if exp.tool_invocations:
            unique_tools = len(set(t.get('tool_name') for t in exp.tool_invocations))
            scores.append(min(1.0, unique_tools / 10))
        
        # Decision count
        if exp.agent_decisions:
            scores.append(min(1.0, len(exp.agent_decisions) / 20))
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _feedback_score(self, exp: ExperienceRecord) -> float:
        """Score based on explicit or implicit feedback."""
        metadata = exp.metadata or {}
        feedback = metadata.get('feedback', {})
        
        if not feedback:
            return 0.5
        
        user_rating = feedback.get('user_rating', 0.5)
        verification_pass = feedback.get('verification_pass', True)
        
        score = user_rating
        if not verification_pass:
            score *= 0.7
        
        return score
    
    def _learning_potential(self, exp: ExperienceRecord) -> float:
        """Estimate how much can be learned from this experience."""
        # Failures have high learning potential
        if exp.classification in ['Failure', 'Timeout', 'Performance Regression']:
            return 0.9
        
        # New capabilities discovered
        if exp.classification == 'Capability Discovery':
            return 0.95
        
        # User corrections indicate learning opportunity
        if exp.classification == 'User Correction':
            return 0.85
        
        # Optimization opportunities
        if exp.classification == 'Optimization Opportunity':
            return 0.8
        
        return 0.5
    
    def rank_experiences(
        self,
        experiences: List[ExperienceRecord],
        top_k: Optional[int] = None
    ) -> List[Tuple[ExperienceRecord, float]]:
        """Rank experiences by importance score."""
        scored = [(exp, self.score_experience(exp)) for exp in experiences]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        if top_k:
            return scored[:top_k]
        return scored
    
    def update_scores(self, storage):
        """Recalculate and update all experience scores."""
        for batch in storage.iterate_all(batch_size=100):
            for exp in batch:
                new_score = self.score_experience(exp)
                storage.update_experience(exp.experience_id, {
                    'importance_score': new_score
                })
