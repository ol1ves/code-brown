"""Per-run state passed through every pipeline stage.

Holds the run id, a pre-bound logger adapter (so log lines auto-include
``run_id``), and accumulating counters/timings/warnings that the presenter
and structured logs both read from. Stages mutate the context via
``record_stage`` and ``add_warning`` — no other state lives outside.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from time import monotonic


@dataclass
class RunContext:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=monotonic)
    timings_ms: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    logger: logging.LoggerAdapter = field(init=False)

    def __post_init__(self) -> None:
        self.logger = logging.LoggerAdapter(
            logging.getLogger("backend"),
            {"run_id": self.run_id},
        )

    def record_stage(self, stage: str, *, duration_ms: int, **counts: int) -> None:
        self.timings_ms[stage] = duration_ms
        for key, value in counts.items():
            self.counts[f"{stage}.{key}"] = value

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def total_ms(self) -> int:
        return int((monotonic() - self.started_at) * 1000)
