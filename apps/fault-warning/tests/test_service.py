"""成员 B 的领域、契约和 HTTP 冒烟测试；不依赖仓库外部父包。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from src.application.service import WarningService
from src.domain.evaluation import HealthInput, RuleBasedHealthEvaluator
from src.domain.models import MaintenanceResult, RiskLevel, WarningStatus
from src.http_server import Handler, Api


def test_warning_event_matches_contract_shape() -> None:
    service = WarningService()
    warning = service.raise_warning(equipment_id="EQ-123456", risk_level=RiskLevel.HIGH,
                                    suspected_fault="振动异常", model_version="model-1",
                                    warning_at=datetime.now(timezone.utc))
    first = service.warning_raised_event(warning.warning_id, "trace-1")
    second = service.warning_raised_event(warning.warning_id, "trace-2")
    assert first["eventId"] == second["eventId"]
    assert first["payload"]["warningId"].startswith("WARN-")
    assert {"recommendedAction", "metricSnapshot"} <= first["payload"].keys()


@pytest.mark.parametrize(("result", "effective", "status"), [
    (MaintenanceResult.RECOVERED, True, WarningStatus.CLOSED),
    (MaintenanceResult.PARTIALLY_RECOVERED, True, WarningStatus.PROCESSING),
    (MaintenanceResult.NOT_RECOVERED, True, WarningStatus.FLAGGED),
    (MaintenanceResult.RECOVERED, False, WarningStatus.FLAGGED),
])
def test_maintenance_result_mapping(result, effective, status) -> None:
    service = WarningService()
    warning = service.raise_warning(equipment_id="EQ-123456", risk_level=RiskLevel.CRITICAL,
                                    suspected_fault="过热", model_version="model-1")
    service.apply_maintenance_conclusion(warning_id=warning.warning_id, root_cause="冷却系统",
                                         result=result, effective=effective)
    assert warning.status is status


def test_low_sample_does_not_raise_warning() -> None:
    evaluator = RuleBasedHealthEvaluator()
    assessment = evaluator.evaluate(HealthInput("EQ-123456", 20, 1, 5))
    assert assessment.risk_level is RiskLevel.LOW
    assert WarningService().record_assessment(assessment) is None


def test_http_health_and_assessment_endpoints() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port)
        conn.request("GET", "/health"); response = conn.getresponse()
        assert response.status == 200 and json.loads(response.read())["status"] == "UP"
        conn.request("POST", "/api/v1/assessments", body=json.dumps({
            "equipmentId": "EQ-123456", "temperatureC": 100, "vibrationMmS": 8, "currentA": 15,
            "traceId": "test-trace"}), headers={"Content-Type": "application/json"})
        response = conn.getresponse(); body = json.loads(response.read())
        assert response.status == 201 and body["event"]["eventType"] == "WarningRaised"
        conn.request("GET", "/")
        response = conn.getresponse()
        assert response.status == 200 and "成员 B" in response.read().decode()
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()
