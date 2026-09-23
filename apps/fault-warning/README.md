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
