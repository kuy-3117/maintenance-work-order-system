"""故障预警模块的领域与应用服务。"""

from .src.application.service import WarningService
from .src.domain.models import MaintenanceResult, RiskLevel, Warning

__all__ = ["MaintenanceResult", "RiskLevel", "Warning", "WarningService"]
