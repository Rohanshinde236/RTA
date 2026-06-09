"""
core/models.py
Data models for RTA per-skill monitoring system.
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional
from pydantic import BaseModel

# ── Thresholds ────────────────────────────────────────────────────────────────
OCW_ALERT_THRESHOLD_SEC = 60   # 1 minute
SL_BAND_HEALTHY         = 90.0
SL_BAND_WARNING         = 80.0
SL_BAND_CRITICAL        = 70.0

# ── SLA Bands ─────────────────────────────────────────────────────────────────
def get_band(sla: float) -> str:
    if sla >= SL_BAND_HEALTHY:  return "HEALTHY"
    if sla >= SL_BAND_WARNING:  return "WARNING"
    if sla >= SL_BAND_CRITICAL: return "CRITICAL"
    return "SEVERE"


# ── Per-skill metric (one poll) ───────────────────────────────────────────────
class SkillMetric(BaseModel):
    """Single skill snapshot from one poll."""
    skill_name:       str
    service_level:    float
    calls_offered:    int
    calls_acceptable: int
    calls_waiting:    int
    agents_available: int
    agents_on_calls:  int
    agents_on_aux:    int
    headcount:        int
    projected_sl:     float
    ocw:              str = "00:00"
    timestamp:        datetime

    @property
    def band(self) -> str:
        return get_band(self.service_level)

    @property
    def ocw_seconds(self) -> int:
        try:
            p = self.ocw.split(':')
            return int(p[0]) * 60 + int(p[1])
        except Exception:
            return 0

    @property
    def is_ocw_critical(self) -> bool:
        return self.ocw_seconds >= OCW_ALERT_THRESHOLD_SEC

    @property
    def is_queue_critical(self) -> bool:
        return self.calls_waiting > 0 and self.calls_waiting > self.agents_available

    @property
    def has_aux_opportunity(self) -> bool:
        return self.calls_waiting > 0 and self.agents_on_aux > 0


# ── Per-skill history (rolling last 10 polls) ─────────────────────────────────
@dataclass
class SkillHistory:
    """Rolling history for one skill — last 10 polls."""
    skill_name:    str
    sla_history:   List[float] = field(default_factory=list)   # last 10 SLA values
    queue_history: List[int]   = field(default_factory=list)   # last 10 queue values
    last_band:     str         = "HEALTHY"
    MAX_HISTORY:   int         = 10

    def update(self, metric: SkillMetric):
        self.sla_history.append(metric.service_level)
        self.queue_history.append(metric.calls_waiting)
        if len(self.sla_history)   > self.MAX_HISTORY:
            self.sla_history   = self.sla_history[-self.MAX_HISTORY:]
        if len(self.queue_history) > self.MAX_HISTORY:
            self.queue_history = self.queue_history[-self.MAX_HISTORY:]

    # ── Breach conditions ─────────────────────────────────────────────────────
    def check_band_changed(self, current_band: str) -> bool:
        """C1: band changed from last poll."""
        changed = self.last_band != current_band and self.last_band != ""
        return changed

    def check_falling_3_polls(self) -> bool:
        """C2: SLA falling 3 polls in a row."""
        if len(self.sla_history) < 3:
            return False
        last3 = self.sla_history[-3:]
        return last3[0] > last3[1] > last3[2]

    def check_queue_doubled(self) -> bool:
        """C3: calls waiting doubled from last poll."""
        if len(self.queue_history) < 2:
            return False
        prev = self.queue_history[-2]
        curr = self.queue_history[-1]
        # Must have meaningful queue (>=2) and doubled
        return prev >= 2 and curr >= prev * 2

    def get_breach_reasons(self, current_band: str) -> List[str]:
        """Returns list of breach reasons — empty means no breach."""
        reasons = []
        if self.check_band_changed(current_band):
            reasons.append(f"BAND_CHANGED:{self.last_band}->{current_band}")
        if self.check_falling_3_polls():
            last3 = self.sla_history[-3:]
            reasons.append(f"FALLING_3_POLLS:{last3[0]:.1f}->{last3[1]:.1f}->{last3[2]:.1f}")
        if self.check_queue_doubled():
            prev = self.queue_history[-2]
            curr = self.queue_history[-1]
            reasons.append(f"QUEUE_DOUBLED:{prev}->{curr}")
        return reasons
