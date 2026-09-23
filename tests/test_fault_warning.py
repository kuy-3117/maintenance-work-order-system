from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps" / "fault-warning"
sys.path.insert(0, str(PACKAGE))


from src.application.service import WarningService  # noqa: E402
from src.domain.models import MaintenanceResult, RiskLevel, WarningStatus  # noqa: E402
from src.domain.evaluation import HealthInput, RuleBasedHealthEvaluator  # noqa: E402


class WarningServiceTest(unittest.TestCase):
    def test_idempotent_raise_and_priority(self) -> None:
        service = WarningService()
        args = dict(equipment_id="EQ-1", risk_level=RiskLevel.HIGH,
                    suspected_fault="振动异常", model_version="model-1",
                    warning_at=datetime.now(timezone.utc), event_id="123e4567-e89b-12d3-a456-426614174000")
        first = service.raise_warning(**args)
        second = service.raise_warning(**args)
        self.assertIs(first, second)
        self.assertEqual(first.priority, "P2")

    def test_conclusion_lifecycle(self) -> None:
        service = WarningService()
        warning = service.raise_warning(equipment_id="EQ-1", risk_level=RiskLevel.CRITICAL,
                                         suspected_fault="过热", model_version="model-1")
        service.apply_maintenance_conclusion(warning_id=warning.warning_id, root_cause="冷却故障",
                                              result=MaintenanceResult.RECOVERED, effective=True)
        self.assertEqual(warning.status, WarningStatus.CLOSED)

    def test_rule_based_assessment_creates_warning(self) -> None:
        assessment = RuleBasedHealthEvaluator().evaluate(
            HealthInput("EQ-1", temperature=100, vibration=8, current=15)
        )
        self.assertEqual(assessment.risk_level, RiskLevel.CRITICAL)
        service = WarningService()
        warning = service.record_assessment(assessment)
        self.assertIsNotNone(warning)
        self.assertEqual(warning.health_score, assessment.health_score)


if __name__ == "__main__":
    unittest.main()
