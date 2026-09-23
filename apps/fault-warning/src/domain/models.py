from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def order_priority(self) -> str:
        return {self.LOW: "P4", self.MEDIUM: "P3", self.HIGH: "P2", self.CRITICAL: "P1"}[self]


class WarningStatus(str, Enum):
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    CLOSED = "CLOSED"
    FLAGGED = "FLAGGED"


class MaintenanceResult(str, Enum):
    RECOVERED = "RECOVERED"
    PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"


@dataclass
class Warning:
    warning_id: str
    equipment_id: str
    risk_level: RiskLevel
    suspected_fault: str
    warning_at: datetime
    model_version: str
    health_score: float | None = None
    status: WarningStatus = WarningStatus.OPEN
    root_cause: str | None = None
    _event_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.warning_id or not self.equipment_id or not self.suspected_fault or not self.model_version:
            raise ValueError("warning_id、equipment_id、suspected_fault 和 model_version 不能为空")
        if self.health_score is not None and not 0 <= self.health_score <= 100:
            raise ValueError("health_score 必须在 0 到 100 之间")
        if self.warning_at.tzinfo is None:
            raise ValueError("warning_at 必须包含时区")

    @property
    def priority(self) -> str:
        return self.risk_level.order_priority


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
