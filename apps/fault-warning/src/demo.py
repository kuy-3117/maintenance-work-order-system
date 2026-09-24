"""命令行演示：输出一次可复制到 C 服务联调的完整 JSON。"""
import json
from .application.service import WarningService
from .domain.evaluation import HealthInput, RuleBasedHealthEvaluator

service = WarningService()
assessment = RuleBasedHealthEvaluator().evaluate(HealthInput("EQ-123456", 100, 8, 15))
warning = service.record_assessment(assessment, event_id="123e4567-e89b-12d3-a456-426614174000")
print(json.dumps(service.warning_raised_event(warning.warning_id, "demo-trace-001"), ensure_ascii=False, indent=2))
