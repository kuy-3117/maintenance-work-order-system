# 成员 B：故障预警与健康评估

## 模块职责

- 计算或模拟设备健康分、风险等级和疑似故障；
- 生成稳定且唯一的 `WarningId`；
- 向成员 C 发送 `WarningRaised` 事件；
- 接收成员 C 的 `MaintenanceConclusionReported`；
- 根据真实根因和维修效果关闭、修正或标注预警。
- 使用成员 D 的统一身份/通知能力，并配合契约与端到端测试。

## 对外契约

- 发送：`WarningRaised`（C-INT-02）；
- 接收：`MaintenanceConclusionReported`（C-INT-04）；
- 公共定义：`contracts/schemas/`、`contracts/examples/` 和风险等级映射。

## 实现前必须确定

- 风险等级到工单优先级的唯一映射；
- 同一设备连续预警的去重、合并或升级规则；
- 模型版本与每条预警的关联方式；
- 维修结论怎样进入后续评估或模型反馈。

## 建议内部结构

```text
src/
├── domain/          # 预警、健康结果、规则
├── application/     # 评估、发布、关闭用例
├── interfaces/      # 数据输入、事件入口
└── infrastructure/  # 模型、数据库、消息适配
tests/
```

不要在本模块复制设备主档或直接修改维修工单数据库。

## 已实现的业务规则

- 风险等级与工单优先级固定映射：`LOW → P4`、`MEDIUM → P3`、`HIGH → P2`、`CRITICAL → P1`。
- `eventId` 是重试幂等键；重复投递返回第一次创建的同一 `Warning`，不会生成新的 `WarningId`。
- 维修结论：`RECOVERED` 关闭预警；`PARTIALLY_RECOVERED` 保持处理中；`NOT_RECOVERED` 或无效结论标记为需关注（`FLAGGED`）。
- 每条预警保存模型版本、健康分和疑似故障，便于后续模型评估与审计。

实现位于 `src/domain` 和 `src/application`，仅使用内存仓储，生产环境可替换为持久化和消息适配器。

## 当前任务进展（成员 B）

| 板块 | 状态 | 说明 |
| --- | --- | --- |
| 领域模型与风险优先级 | 已完成 | `Warning`、状态、维修结果和 P1-P4 映射 |
| 健康评估基线 | 已完成（规则版） | `RuleBasedHealthEvaluator` 根据温度、振动、电流计算健康分 |
| 预警去重与风险更新 | 已完成（内存版） | 同设备同疑似故障的未关闭预警复用记录 |
| 维修结论处理 | 已完成（应用层） | 支持关闭、处理中和需关注状态 |
| C-INT-02/C-INT-04 HTTP 服务 | 待完成 | 需要补充 Web 框架、请求校验和错误响应 |
| 数据库与消息发布 | 待完成 | 当前仍为内存仓储和事件字典 |
| 身份、通知、可观测性 | 待联调 | 依赖成员 D 的统一服务 |
| E2E-01 至 E2E-04 | 待联调 | 需要 A、C、D 提供运行中的服务 |

## 本地调用示例

当前模块是纯 Python 应用服务，调用方可先把模块目录加入 `PYTHONPATH`：

```bash
PYTHONPATH=apps/fault-warning python -c '
from src.domain.evaluation import HealthInput, RuleBasedHealthEvaluator
from src.application.service import WarningService

assessment = RuleBasedHealthEvaluator().evaluate(
    HealthInput("EQ-000001", temperature=100, vibration=8, current=15)
)
service = WarningService()
warning = service.record_assessment(assessment,
                                    event_id="123e4567-e89b-12d3-a456-426614174000")
if warning:
    event = service.warning_raised_event(warning.warning_id, "trace-local-001")
    print(event)
'
```

也可以在 Python 代码中直接调用：

```python
from src.application.service import WarningService
from src.domain.evaluation import HealthInput, RuleBasedHealthEvaluator

assessment = RuleBasedHealthEvaluator("health-model-1.0").evaluate(
    HealthInput("EQ-000001", temperature=72, vibration=3, current=11)
)
service = WarningService()
warning = service.record_assessment(assessment)
```

`record_assessment()` 返回 `None` 表示健康等级为 `LOW`，返回 `Warning` 表示已经产生或复用了预警。`warning_raised_event()` 返回符合 `WarningRaised` 包络的字典。

## 可执行 HTTP 服务

本模块不依赖仓库外部父包，可直接启动内置标准库 HTTP 服务：

```bash
PYTHONPATH=apps/fault-warning B_SERVICE_PORT=8102 python -m src.http_server
```

- `GET /health`：健康检查；
- `GET /`：浏览器控制台，可提交采样并直接查看格式化 JSON；
- `GET /api/v1/status`：查看当前进程内全部预警及状态；
- `POST /api/v1/assessments`：提交 `equipmentId`、`temperatureC`、`vibrationMmS`、`currentA`，返回评估和预警事件；
- `POST /api/v1/warnings`：兼容 C-INT-02 的预警入口；
- `POST /api/v1/maintenance-conclusions`：提交包含 `warningId`、`rootCause`、`result`、`effective` 的维修结论。

服务仅使用模块内 `src.*` 导入，便于测试、容器启动和后续替换数据库/消息适配器。

## 如何完成并查看测试

在仓库根目录执行：

```bash
pytest -q apps/fault-warning
```

看到 `10 passed`（或更高数量）即表示 B 模块单元、契约和 HTTP 冒烟测试通过。需要网页结果时先启动服务，
然后浏览器打开 <http://127.0.0.1:8102/>，点击“评估”即可看到包含 `warningId`、风险等级和事件 envelope 的 JSON；
打开 <http://127.0.0.1:8102/api/v1/status> 可查看当前预警列表。命令行也可运行：

```bash
PYTHONPATH=apps/fault-warning python -m src.demo
```

该命令会输出一份可复制保存的 `WarningRaised` JSON，便于与成员 C 做联调。
