from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from ..domain.models import MaintenanceResult, RiskLevel, Warning, WarningStatus, utc_now
from ..domain.evaluation import HealthAssessment


class WarningService:
    """预警生命周期服务。

    当前以字典充当仓储，适合本地演示和单元测试；生产实现应把两个字典
    替换成事务性数据库表，并保留 event_id 唯一约束，避免服务重启后重复建警。
    """

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

    def record_assessment(self, assessment: HealthAssessment, *, event_id: str | None = None) -> Warning | None:
        """将评估结果转为预警；LOW 仅记录为无预警，不创建工单事件。

        同设备、同疑似故障且仍未关闭的预警会复用原 WarningId；只有风险升高
        时才更新风险等级，从而避免连续采样为同一故障创建大量工单。
        """
        if assessment.risk_level is RiskLevel.LOW:
            return None
        for warning in self._warnings.values():
            if warning.equipment_id == assessment.equipment_id and warning.suspected_fault == assessment.suspected_fault and warning.status is not WarningStatus.CLOSED:
                rank = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
                if rank[assessment.risk_level] > rank[warning.risk_level]:
                    warning.risk_level = assessment.risk_level
                warning.health_score = assessment.health_score
                return warning
        return self.raise_warning(equipment_id=assessment.equipment_id, risk_level=assessment.risk_level,
                                  suspected_fault=assessment.suspected_fault, model_version=assessment.model_version,
                                  health_score=assessment.health_score, event_id=event_id)

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
        """构造发送给成员 C 的 C-INT-02 事件。

        调用方负责把返回值序列化为 JSON 并投递到消息系统或 C 的 HTTP 接口；
        重试时必须复用返回对象中的 eventId，不能重新生成事件编号。
        """
        warning = self.get(warning_id)
        return {"eventId": warning._event_id or str(uuid4()), "eventType": "WarningRaised",
                "schemaVersion": "1.0", "occurredAt": warning.warning_at.isoformat(),
                "sourceMember": "MEMBER_B", "traceId": trace_id,
                "payload": {"warningId": warning.warning_id, "equipmentId": warning.equipment_id,
                            "riskLevel": warning.risk_level.value, "healthScore": warning.health_score,
                            "suspectedFault": warning.suspected_fault,
                            "warningAt": warning.warning_at.isoformat(), "modelVersion": warning.model_version}}
