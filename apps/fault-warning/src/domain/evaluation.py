from __future__ import annotations

from dataclasses import dataclass

from .models import RiskLevel


@dataclass(frozen=True)
class HealthInput:
    equipment_id: str
    temperature: float
    vibration: float
    current: float


@dataclass(frozen=True)
class HealthAssessment:
    equipment_id: str
    health_score: float
    risk_level: RiskLevel
    suspected_fault: str
    model_version: str


class RuleBasedHealthEvaluator:
    """可审计的基线评估器；后续可替换为模型适配器。

    这里故意使用确定性的规则而不是随机模拟：相同输入永远产生相同结果，
    便于联调、回放和审计。生产环境可保持 ``HealthAssessment`` 输出协议，
    只替换本类的实现为机器学习模型适配器。
    """

    def __init__(self, model_version: str = "rule-health-1.0") -> None:
        self.model_version = model_version

    def evaluate(self, sample: HealthInput) -> HealthAssessment:
        """将一次设备采样转换为健康评估结果。

        惩罚项是演示用基线，不代表真实工业算法；上线前应由领域专家校准
        权重和阈值，并通过模型版本标识保证历史结果可追溯。
        """
        if not sample.equipment_id:
            raise ValueError("equipment_id 不能为空")
        if min(sample.temperature, sample.vibration, sample.current) < 0:
            raise ValueError("设备指标不能为负数")
        penalty = min(100.0, max(0.0, (sample.temperature - 60) * 0.8)
                      + sample.vibration * 4 + max(0.0, sample.current - 10) * 2)
        score = round(max(0.0, min(100.0, 100.0 - penalty)), 2)
        if score < 30:
            level, fault = RiskLevel.CRITICAL, "设备综合健康指标严重异常"
        elif score < 60:
            level, fault = RiskLevel.HIGH, "设备综合健康指标异常"
        elif score < 80:
            level, fault = RiskLevel.MEDIUM, "设备综合健康指标轻度异常"
        else:
            level, fault = RiskLevel.LOW, "设备运行指标正常"
        return HealthAssessment(sample.equipment_id, score, level, fault, self.model_version)
