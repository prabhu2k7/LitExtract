"""Thread-safe token + cost accumulator. One singleton per process."""
import threading
from typing import Optional

import config
from init_db import _MODEL_PRICING


class TokenTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._input = 0
        self._output = 0
        self._cost = 0.0
        self._by_model: dict[str, dict[str, float]] = {}

    def add(self, input_tokens: int, output_tokens: int,
            model_name: Optional[str] = None) -> None:
        model = model_name or config.active_model_name()
        price = _MODEL_PRICING.get(model, _MODEL_PRICING["gpt-4o-mini"])
        cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
        with self._lock:
            self._input  += input_tokens
            self._output += output_tokens
            self._cost   += cost
            slot = self._by_model.setdefault(
                model, {"input": 0, "output": 0, "cost": 0.0}
            )
            slot["input"]  += input_tokens
            slot["output"] += output_tokens
            slot["cost"]   += cost

    def get_totals(self) -> dict:
        with self._lock:
            return {
                "input_tokens":  self._input,
                "output_tokens": self._output,
                "total_tokens":  self._input + self._output,
                "cost_usd":      round(self._cost, 6),
                "by_model":      {k: dict(v) for k, v in self._by_model.items()},
            }

    def get_cost(self) -> float:
        with self._lock:
            return round(self._cost, 6)

    def reset(self) -> None:
        with self._lock:
            self._input = 0
            self._output = 0
            self._cost = 0.0
            self._by_model = {}


tracker = TokenTracker()
