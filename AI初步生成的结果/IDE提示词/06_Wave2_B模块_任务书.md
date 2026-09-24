# Wave 2：成员 B 故障预警与健康评估模块（kuy-3117）

## 前置条件

Wave 1 已合并（A 的 C-INT-01 可用，便于联调，但不阻塞开发——B 可先用契约示例报文做 stub）。

## 任务范围（cluster: apps/fault-warning/）

实现 v1.1.0 契约中 B 的职责：

1. 风险评估：接收/模拟监测数据 → 计算风险等级（LOW/MEDIUM/HIGH/CRITICAL，映射 P4-P1 优先级，以 shared-enums.json 为准）；
2. `WarningId` 生成：每个预警唯一；同一预警重发保持同一 WarningId（幂等）；
3. 发送 `WarningRaised` 事件到 C（POST 到 C-INT-02 的 `/api/v1/warnings`，B 是调用方）；
4. `POST /api/v1/maintenance-conclusions` —— C-INT-04 接收 C 发来的维修结论，关闭/修正/标注预警；
5. 预警状态机：OPEN → …（warningStatus 以 Wave 0 审定后契约为准；若 Wave 0 未合入 v2 的 warningStatus，则 B 模块内私有实现状态，不上公共契约）。

## 基于成员 C 实现的联调补充要求

成员 C 已提供幂等建单、工单状态机、备件流水以及 `MaintenanceConclusionReported`
回传能力。B 的实现必须按以下边界与 C 对接，不得把 C 的工单表或状态机复制到本模块：

### WarningRaised 发送（B → C，C-INT-02）

- 事件必须使用统一 envelope：`eventId`、`eventType=WarningRaised`、`schemaVersion`、
  `occurredAt`、`sourceMember=MEMBER_B`、`traceId` 和 `payload` 均不可缺失；payload 至少包含
  `warningId`、`equipmentId`、`riskLevel`、`healthScore`、`suspectedFault`、`warningAt`、
  `modelVersion`，字段名称和枚举值严格遵循
  `contracts/schemas/warning-raised.payload.schema.json` 与示例。
- 同一设备、同一疑似故障且预警尚未关闭时应复用 `WarningId`；风险升高只更新原预警并按
  原 `eventId` 重发，不能为连续采样创建多个工单。`LOW` 仅记录健康结果，不发送事件。
- `eventId` 必须在首次生成后持久化，HTTP 超时、连接失败或消息重试时复用原值；C 返回
  `202` 和 `orderId` 后记录投递成功。不得因为重试生成新的 `WarningId` 或事件编号。
- C 服务地址从 `MAINTENANCE_SERVICE_URL` 读取；连接超时、4xx/5xx 应区分可重试与不可重试，
  保留待发送状态、重试次数和最后错误，日志中带 `traceId`，不得吞掉异常。

### MaintenanceConclusionReported 接收（C → B，C-INT-04）

- 入口先校验 envelope、`eventId` UUID、`warningId`、`rootCause`、`maintenanceResult` 和
  `effective`；未知 `warningId` 返回明确的 404/业务错误，不得静默创建预警。
- 以 `eventId` 做幂等：同一结论重复投递必须返回第一次处理结果，不重复改变状态或产生副作用。
- 结论映射固定为：`RECOVERED` 且有效 → `CLOSED`；`PARTIALLY_RECOVERED` → `PROCESSING`；
  `NOT_RECOVERED` 或 `effective=false` → `FLAGGED`，同时保存真实 `rootCause` 供审计和下一次评估。
  已关闭预警不得被旧结论重新打开；冲突或过期结论需记录并返回可诊断错误。

### 可替换性、持久化与可观测性

- 保留当前领域层的风险优先级映射（`LOW→P4`、`MEDIUM→P3`、`HIGH→P2`、`CRITICAL→P1`）、
  健康分 0–100 校验、模型版本和时区感知的 `warningAt`；将内存字典封装为仓储接口，便于
  替换为带唯一约束的数据库（`warningId`、`eventId`）和 outbox 表。
- 事件应遵循“预警落库后再发送”的 outbox 顺序；消费者重启后可继续投递，成功后标记已发送，
  保留发送时间、响应码和重试历史。不得直接维护设备主档或维修工单权威数据。
- HTTP 层负责请求校验、统一错误体、健康检查和端口配置；应用层保持可被单元测试直接调用。
- 为 E2E 联调提供 `traceId` 贯穿 B→C→B，结构化记录 `warningId`、`eventId`、`orderId` 和
  状态迁移，敏感信息不得写日志。

## 验收（我审查时逐条检查）

- [ ] check_repo.py --strict 通过；模块 pytest 全绿
- [ ] 发送的 WarningRaised 报文与 contracts/examples/warning-raised.json 结构一致，能通过 warning-raised.payload.schema.json 校验
- [ ] 同一设备同一预警重复评估不产生重复 WarningId
- [ ] 收到维修结论后对应预警关闭，且 EventId 幂等
- [ ] 同一设备同一疑似故障连续采样复用 WarningId；风险升级不重复建单，LOW 不发 C-INT-02
- [ ] C-INT-02 失败可重试且复用原 eventId，成功后能记录 C 返回的 orderId；服务重启不丢待发送事件
- [ ] C-INT-04 对 RECOVERED/PARTIALLY_RECOVERED/NOT_RECOVERED 与 effective=false 的状态映射、
      已关闭预警保护和未知 warningId 错误均有测试
- [ ] payload/envelope 字段、UUID、时间时区、健康分范围和枚举非法值均有请求级校验测试
- [ ] README 更新（端口 8102、启动、演示方式：如何触发一次 HIGH 预警）

## 分支与提交

```bash
git switch main && git pull --ff-only
git switch -c feat/b-fault-warning
git commit -m "feat(b): 实现风险评估与 WarningRaised 事件发送"
git push -u origin feat/b-fault-warning
```

PR 标题：`feat(b): 实现故障预警模块`

## 给湛卢 IDE 的提示词要点（完整版结构同 Wave 1，可复制 05 文件改写）

- 骨架生成：同 Wave 1 的分层结构要求，端口 8102，C 调用方 URL 用环境变量 `MAINTENANCE_SERVICE_URL` `.env.example` 已有）；
- 契约自检：核对 C-INT-04 与 warning-raised schema、examples；
- 附加提示词：「写一个演示脚本 scripts/demo_raise_warning.py，构造一条 HIGH 风险的 WarningRaised 事件 POST 到 C 服务，展示 202 响应与返回的 orderId（C 未就绪时打印目标 URL 与报文即可）」；再补充
  `scripts/demo_maintenance_conclusion.py`，用同一 `eventId` 连续发送一次有效维修结论和一次重试，
  展示状态只迁移一次。
- 联调前用 C 模块 README 中的端口 8103/接口启动说明做 smoke test：先 POST 一条 HIGH 预警，
  保存返回的 `orderId`，再 POST 相同 `warningId` 验证返回原单；随后发送 C-INT-04 并检查 B 的
  `CLOSED`/`PROCESSING`/`FLAGGED` 状态。所有地址均通过环境变量配置，禁止写死 localhost。
