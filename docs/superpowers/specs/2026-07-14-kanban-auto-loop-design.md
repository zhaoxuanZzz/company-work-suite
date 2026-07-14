# Kanban 与 Auto 原子 Loop 接入设计

日期：2026-07-14

状态：待用户复核

## 1. 决策

Loop 只发生在原子 skill 内，workflow 继续保持无环 DAG。`planned` 和
`auto` 不实现新的 loop 引擎，统一复用现有 `atomic_loop.py` 的 attempt、
lease、Gate、findings、停止条件和产物提升。

`auto` 只负责生成候选执行计划；计划通过 CWS 静态校验后，交给与
`planned` 相同的 Kanban 提交与 loop 适配路径执行。

## 2. 目标与非目标

目标：

- 支持 `execute --mode planned --loop`；
- 同一 Kanban 卡片可对应多个隔离的 attempt；
- 只有 Runner 验收通过才能完成卡片并解锁下游；
- 支持 `passed | revise | needs_input | needs_review | exhausted`；
- Auto 生成的计划经校验后获得与 Planned 相同的运行保证。

非目标：

- 不在 `workflow.yaml` 中增加环、回边或循环语法；
- 不让 Maker 根据提示词自行决定重试或通过；
- 不复制 `atomic_loop.py` 状态机；
- 不支持有不可逆外部副作用的 skill 自动重试；
- 不承诺未通过结构化计划校验的 Auto 任务具备 Gate 或 Loop 保证。

## 3. 统一执行模型

```text
planned -> validated execution plan ----+
                                        +-> Kanban loop adapter -> atomic_loop
auto -> candidate plan -> validation ---+
```

每个执行节点保存：

- `run_id`；
- `node_id`；
- `skill_id`；
- `kanban_task_id`；
- `loop_enabled`；
- 当前 `attempt` 和 `lease_id`。

这些字段写入 CWS 的 `workflow-state.json`。Kanban 任务正文只携带稳定的
CWS 上下文标记，不作为状态真相源。

## 4. Planned Loop

`execute --mode planned --loop` 的提交顺序：

1. 编译并验证静态 workflow；
2. 初始化共享的 loop-enabled workflow state；
3. 创建带显式父依赖的 Kanban 任务；
4. 将实际 `kanban_task_id` 回写到对应节点状态；
5. dispatcher 领取任务时为该节点领取下一 attempt；
6. Worker 只读取 `maker-context.json`，并写入指定 attempt 目录；
7. `kanban_complete` 前由插件调用 `complete_attempt`；
8. `passed` 才允许完成卡片；`revise` 重新排队同一卡片；其他终态暂停。

失败 attempt 永不覆盖正式产物。下游仍只依赖原 Kanban 卡片，因此重试不
创建新的业务 DAG 节点。

## 5. Hermes 适配边界

现有 `pre_tool_call(kanban_complete)` 可作为硬验收边界，但不足以单独完成
自动 loop。干净实现还需要 Hermes 提供两个明确能力：

1. 任务领取后、Worker 启动前注入 attempt 上下文；
2. 将当前运行安全结束并把同一卡片重新置为 `ready` 的 `retry_task` 或
   `requeue_task` API。

不使用 `block_task` 加 `unblock_task` 模拟正常重试，因为 Hermes 的重复
阻塞熔断会把确定性的 loop attempt 误判为阻塞风暴。

如果上述能力暂时不可用，`planned --loop` 必须 fail closed，并明确报告
缺失能力；不退化为提示词自循环。

## 6. Auto 计划归一化

Auto decomposer 不直接提交自由形态的执行卡片，而是输出候选计划：

```json
{
  "nodes": [
    {
      "id": "profile",
      "skill": "cws-company-profile",
      "parents": [],
      "outputs": ["company_profile"]
    }
  ]
}
```

提交前复用现有 workflow 契约完成以下校验：

- `skill` 可发现且名称唯一；
- 节点 ID 唯一；
- 父节点存在且图无环；
- 输入 artifact 能由父节点输出满足；
- 报告节点和 final Gate 上下文可确定；
- loop skill 声明合法 Gate，且无不可逆外部副作用。

校验通过后转换成与 Planned 相同的 execution plan，并调用同一 Kanban
提交函数。校验失败时保留在 triage，不创建执行卡片。

## 7. 状态映射

| Atomic loop 结果 | Kanban 动作 |
|---|---|
| `passed` | 允许完成当前卡片 |
| `revise` | 结束当前 task run，重新排队同一卡片 |
| `needs_input` | `blocked`，等待新 run 补齐冻结输入 |
| `needs_review` | `review` 或 `blocked`，等待人工处理 |
| `exhausted` | `blocked`，禁止继续增加 attempt |

第一版默认首次执行加最多两次修正，共三个 attempts。次数由现有 Runner
状态约束，不由 Kanban 自己计算。

## 8. 恢复与并发

- CWS lease 是节点 attempt 的唯一执行权；Kanban claim 不能替代它；
- 重复 claim 只能恢复过期 lease，不得并行创建两个 attempt；
- 过期 Worker 的 completion 因 lease 不匹配而被拒绝；
- Kanban task ID 与 CWS node ID 的映射必须幂等回写；
- 插件重启后以 `workflow-state.json` 和 Kanban durable task 状态恢复；
- 状态不一致时进入 `needs_review`，不得猜测或覆盖正式产物。

## 9. 最小实施顺序

1. 为 Planned 提取共享 execution-plan 提交函数；
2. 增加 `planned --loop` 初始化和 task/node 映射；
3. 增加 Hermes claim/requeue 能力探测，并先完成 tracer test；
4. 将 `kanban_complete` Gate 接到 `complete_attempt`；
5. 验证同一卡片两次运行后通过并解锁下游；
6. 增加 Auto 候选计划 schema 与校验；
7. Auto 校验成功后调用同一提交函数。

## 10. 验收标准

- Planned 节点第一次 Gate 失败后保留 attempt 1，并自动产生 attempt 2；
- attempt 2 通过后才出现正式产物并完成原 Kanban 卡片；
- 下游在上游通过前保持不可领取；
- 达到三次上限后稳定进入 `exhausted`；
- Auto 非法或有环计划不创建任何执行卡片；
- Auto 合法计划与等价 Planned 计划产生相同的 Runner 状态和 Kanban DAG；
- 未提供 Hermes 安全 requeue 能力时 fail closed。

