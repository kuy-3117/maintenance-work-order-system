from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from ..domain.models import MaintenanceResult, RiskLevel, Warning, WarningStatus, utc_now


class WarningService:
    """预警生命周期服务；内存存储便于替换为数据库或消息适配器。"""

    def __init__(self) -> None:
        self._warnings: dict[str, Warning] = {}
        self._events: dict[str, str] = {}

    def raise_warning(self, *, equipment_id: str, risk_level: RiskLevel, suspected_fault: str,
                      model_version: str, warning_at: datetime | None = None,
                      health_score: float | None = None, event_id: str | None = None,
                      warning_id: str | None = None) -> Warning:
        if event_id:
            try:
                UUID(event_id)
            except ValueError as exc:
                raise ValueError("event_id 必须是 UUID") from exc
            existing_id = self._events.get(event_id)
            if existing_id:
                return self._warnings[existing_id]
        warning_id = warning_id or f"WARN-{uuid4().hex[:24].upper()}"
        existing = self._warnings.get(warning_id)
        if existing:
            return existing
        warning = Warning(warning_id, equipment_id, risk_level, suspected_fault,
                          warning_at or utc_now(), model_version, health_score, _event_id=event_id)
        self._warnings[warning_id] = warning
        if event_id:
            self._events[event_id] = warning_id
        return warning

    def get(self, warning_id: str) -> Warning:
        try:
            return self._warnings[warning_id]
        except KeyError as exc:
            raise KeyError(f"预警不存在: {warning_id}") from exc

    def mark_processing(self, warning_id: str) -> Warning:
        warning = self.get(warning_id)
        if warning.status not in (WarningStatus.CLOSED,):
            warning.status = WarningStatus.PROCESSING
        return warning

    def apply_maintenance_conclusion(self, *, warning_id: str, root_cause: str,
                                     result: MaintenanceResult, effective: bool) -> Warning:
        warning = self.get(warning_id)
        if not root_cause:
            raise ValueError("root_cause 不能为空")
        warning.root_cause = root_cause
        if not effective or result is MaintenanceResult.NOT_RECOVERED:
            warning.status = WarningStatus.FLAGGED
        elif result is MaintenanceResult.PARTIALLY_RECOVERED:
            warning.status = WarningStatus.PROCESSING
        else:
            warning.status = WarningStatus.CLOSED
        return warning

    def warning_raised_event(self, warning_id: str, trace_id: str) -> dict:
        warning = self.get(warning_id)
        return {"eventId": warning._event_id or str(uuid4()), "eventType": "WarningRaised",
                "schemaVersion": "1.0", "occurredAt": warning.warning_at.isoformat(),
                "sourceMember": "MEMBER_B", "traceId": trace_id,
                "payload": {"warningId": warning.warning_id, "equipmentId": warning.equipment_id,
                            "riskLevel": warning.risk_level.value, "healthScore": warning.health_score,
                            "suspectedFault": warning.suspected_fault,
                            "warningAt": warning.warning_at.isoformat(), "modelVersion": warning.model_version}}
