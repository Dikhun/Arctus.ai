"""Forward modeling and state prediction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

@dataclass
class Prediction:
    horizon: int
    predicted_state: Dict[str, Any]
    confidence_interval: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    model_name: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PredictionHorizon:
    steps: int
    step_size: float = 1.0

class Predictor:
    def __init__(self, world_model: Optional[Callable[[Dict[str, Any], float], Dict[str, Any]]] = None):
        self._world_model = world_model
        self._models: Dict[str, Callable[[Dict[str, Any], int], Dict[str, Any]]] = {}
        self._history: List[Dict[str, Any]] = []

    def register_model(self, name: str, model: Callable[[Dict[str, Any], int], Dict[str, Any]]) -> None:
        self._models[name] = model

    def record_state(self, state: Dict[str, Any]) -> None:
        self._history.append(state.copy())
        if len(self._history) > 10000:
            self._history = self._history[-5000:]

    def predict(
        self,
        current_state: Dict[str, Any],
        horizon: PredictionHorizon,
        model_name: Optional[str] = None
    ) -> Prediction:
        steps = horizon.steps
        model = self._get_model(model_name)
        predicted = model(current_state, steps)
        ci = {}
        for key, val in predicted.items():
            if isinstance(val, (int, float)):
                est = abs(val * 0.1)
                ci[key] = (val - est, val + est)
        return Prediction(
            horizon=steps,
            predicted_state=predicted,
            confidence_interval=ci,
            model_name=model_name or "default",
            metadata={"step_size": horizon.step_size}
        )

    def _get_model(self, name: Optional[str]) -> Callable[[Dict[str, Any], int], Dict[str, Any]]:
        if name and name in self._models:
            return self._models[name]
        if self._world_model is not None:
            return lambda s, h: self._world_model(s, float(h)) if self._world_model else s
        return self._naive_model

    def _naive_model(self, state: Dict[str, Any], steps: int) -> Dict[str, Any]:
        if not self._history or steps == 0:
            return state.copy()
        velocity = self._estimate_velocity()
        predicted = state.copy()
        for key, vel in velocity.items():
            if key in predicted and isinstance(predicted[key], (int, float)):
                predicted[key] = predicted[key] + vel * steps
        return predicted

    def _estimate_velocity(self) -> Dict[str, float]:
        if len(self._history) < 2:
            return {}
        recent = self._history[-10:]
        velocity = {}
        keys = set(recent[0].keys())
        for key in keys:
            if not all(isinstance(s.get(key), (int, float)) for s in recent):
                continue
            vals = [s[key] for s in recent]
            n = len(vals)
            mean_v = (vals[-1] - vals[0]) / max(n - 1, 1)
            velocity[key] = mean_v
        return velocity

    def ensemble_predict(
        self,
        current_state: Dict[str, Any],
        horizon: PredictionHorizon,
        model_names: Sequence[str],
        weights: Optional[Sequence[float]] = None
    ) -> Prediction:
        names = list(model_names)
        w = list(weights) if weights else [1.0 / len(names)] * len(names)
        predictions: List[Dict[str, Any]] = []
        for name in names:
            pred = self.predict(current_state, horizon, name).predicted_state
            predictions.append(pred)
        keys = set(predictions[0].keys())
        for p in predictions[1:]:
            keys |= set(p.keys())
        ensemble: Dict[str, Any] = {}
        for key in keys:
            weighted_sum = 0.0
            total_w = 0.0
            for i, p in enumerate(predictions):
                v = p.get(key, 0.0)
                if isinstance(v, (int, float)):
                    weight = w[i] if i < len(w) else 1.0
                    weighted_sum += v * weight
                    total_w += weight ensemble[key] = weighted_sum / total_w if total_w > 0 else 0.0
        return Prediction(
            horizon=horizon.steps,
            predicted_state=ensemble,
            model_name="ensemble",
            metadata={"models": names, "weights": w}
        )

    def forecast_error(self, actual: Dict[str, Any], predicted: Dict[str, Any]) -> Dict[str, float]:
        errors = {}
        for key in set(actual.keys()) | set(predicted.keys()):
            a = actual.get(key, 0.0)
            p = predicted.get(key, 0.0)
            if isinstance(a, (int, float)) and isinstance(p, (int, float)):
                errors[key] = abs(a - p)
            else:
                errors[key] = 0.0 if a == p else 1.0
        return errors
