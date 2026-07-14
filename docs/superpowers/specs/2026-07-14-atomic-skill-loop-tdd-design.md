# 原子 Skill Loop 与 TDD 改进闭环设计

日期：2026-07-14

状态：设计已完善，待评审

## 1. 背景

CWS 当前通过 `card.yaml.gate`、`handoff.json`、`evidence.json`、确定性 semantic gate 和可选 LLM Judge 验证 skill 产物。现有 delegate runner 能记录节点执行与 gate 结果，但 gate 失败后主要依赖父 agent 或人工修复顶层产物并再次验收：失败产物会占用正式路径，重试输入和 skill revision 没有冻结，重复失败也没有稳定转化为回归案例。

本设计把 loop 收缩到单个原子 skill。Workflow 继续保持无环 DAG；workflow 节点只是原子 skill loop 的调用者。独立 skill 和 workflow 节点复用同一状态机、attempt 布局和 gate，不新增通用编排引擎。

## 2. 已确认决策

1. Loop 只发生在原子 skill 内，不让 `workflow.yaml` 支持环或回跳上游。
2. Runner 只维护状态、验收和决策，不内置 Agent SDK，也不负责生成内容。
3. Maker 由当前宿主或父 agent 调用；Runner 通过结构化命令返回 attempt 路径、冻结输入和最新 findings。
4. 每次 attempt 隔离保存，node gate 与 final gate 都通过后才原子提升为正式产物。
5. 第一版复用现有 Judge v1 协议，以 `passed | needs_review`、confidence 和结构化 findings 决策；五维评分延后到 v1.1。
6. 第一版只覆盖无不可逆外部副作用的分析 skill；邮件、消息、任务、审批等提交型 skill 不进入自动 loop。
7. 运行内 loop 只修正当前产物；`SKILL.md`、`card.yaml`、rubric 和 checker 的改进发生在跨运行 TDD 闭环，并保留人工批准。

## 3. 目标与非目标

### 3.1 目标

- 为声明了 gate 的原子 skill 提供显式启用的执行修正 loop。
- 在固定输入、rubric 和 skill revision 下，根据结构化 findings 修正当前产物。
- 隔离每次 attempt，失败产物永不占用正式产物路径。
- 复用 node gate、final gate、delegate runner 状态和现有 Judge adapter。
- 对次数、无进展、低置信度、缺输入和人工审查设置确定的停止条件。
- 支持进程中断后的安全恢复，并阻止同一节点被两个执行者同时领取。
- 将可复现的真实失败转成回归案例，以 RED → GREEN → regression 改进 skill。

### 3.2 第一版非目标

- 不在 workflow 图上引入环、动态分支或自动回跳上游。
- 不在当前 run 中自动修改或发布 skill、card、rubric、checker。
- 不实现新的 Agent runtime、通用建议池、知识图谱或独立编排服务。
- 不实现五维加权评分作为通过门槛。
- 不承诺无法提供幂等键的外部系统 exactly-once。
- 不对 `planned`、`auto` 模式自动注入宿主 hook；第一版先接独立 skill 和 `delegate` 模式。

## 4. 第一版适用范围

原子 skill 只有同时满足以下条件才允许启用 loop：

- 存在合法的 `card.yaml.gate`；
- 调用方显式请求 loop；
- 输入可以在 run 开始时完整冻结；
- `SKILL.md`、`card.yaml`、rubric 和运行时 gate revision 可记录；
- Maker 可以把候选产物写入 Runner 指定的 attempt 目录；
- gate 能在任何正式写回或不可逆提交前执行；
- 本次运行没有邮件、消息、任务、审批、付款等不可逆外部副作用。

首个垂直切片只支持：

```text
skill: cws-company-profile
mode: standalone + delegate
input: frozen fixture
max_attempts: 3
external_commit: disabled
```

生产数据补数、wiki 正式写回、Hermes planned/auto 接入和提交型 skill 在 tracer case 跑通后分别评估，不阻塞第一版。

## 5. 运行架构与宿主边界

### 5.1 核心流程

```text
调用方初始化 run
  -> Runner 冻结输入和 revision
  -> Runner 领取 attempt，返回 lease + MakerContext
  -> 宿主/父 agent 调用 Maker
  -> Maker 写 attempt/handoff.json 与 evidence.json
  -> Runner 执行 Deterministic Gate
  -> 通过后执行 Semantic Judge
  -> Runner Policy 计算 next_action
       -> accept -> final gate（如有）-> 原子提升 -> passed
       -> revise -> 创建下一 attempt
       -> needs_input
       -> human_review
       -> exhausted
```

Runner 不接收自由文本控制指令。宿主只根据 `next_action` 调用下一条命令，Maker 只接收 Runner 生成的 `maker-context.json`。

### 5.2 CLI 契约

独立原子 skill 使用 `workflow_cli.py loop` 子命令，作为现有 delegate runner 的单节点薄入口：

```bash
python skills/cws-workflow/scripts/workflow_cli.py loop init \
  --skill cws-company-profile \
  --company "<company-name>" \
  --run-id "run-<stable-id>" \
  --input <frozen-input.json>

python skills/cws-workflow/scripts/workflow_cli.py loop next \
  --run-id "run-<stable-id>"

python skills/cws-workflow/scripts/workflow_cli.py loop complete \
  --run-id "run-<stable-id>" \
  --lease-id "<lease-id>"

python skills/cws-workflow/scripts/workflow_cli.py loop status \
  --run-id "run-<stable-id>"

python skills/cws-workflow/scripts/workflow_cli.py loop cancel \
  --run-id "run-<stable-id>" \
  --reason "<reason>"
```

`loop next` 只在节点可执行时发放 lease，并返回：

```json
{
  "run_id": "run-example",
  "skill": "cws-company-profile",
  "attempt": 1,
  "action": "execute",
  "lease_id": "lease-...",
  "attempt_dir": ".../artifacts/run-example/attempts/cws-company-profile/1",
  "maker_context_path": ".../maker-context.json"
}
```

修正轮的 `action` 为 `revise`。`loop complete` 验收当前 lease 对应的 attempt，返回 `next_action` 和稳定状态，不直接调用 Maker。

Workflow delegate 模式继续使用 `delegate start/complete/status/ready`；这些命令内部调用同一 node-loop helper。`planned` 和 `auto` 第一版保持现状，避免把宿主特有的任务生命周期塞进插件状态机。

### 5.3 MakerContext

每次 attempt 生成独立的 `maker-context.json`，只包含：

- `run_id`、`skill_id`、`attempt`；
- 冻结输入路径及其 SHA-256；
- 冻结的 skill/card 路径及 revision；
- 当前 attempt 的输出目录；
- 上一 attempt 的只读产物路径；
- 最新一次结构化 findings；
- 必须生成的输出文件和禁止的副作用。

Maker 不继承完整历史对话。finding 的 `detail` 只作为数据展示，不作为系统指令；宿主必须把冻结输入、skill 指令和 findings 分区传入，防止来源数据或 Judge 文本覆盖执行约束。

## 6. 冻结输入与 Revision Manifest

初始化时写入：

```text
artifacts/<run-id>/
├── run-manifest.json
└── frozen/
    ├── input.json
    └── skills/
        └── <skill-id>/
            ├── SKILL.md
            └── card.yaml
```

`run-manifest.json` 至少包含：

```json
{
  "schema_version": 1,
  "run_id": "run-example",
  "subject": {"name": "示例公司"},
  "created_at": "2026-07-14T00:00:00Z",
  "max_attempts": 3,
  "input_sha256": "...",
  "skill_revision": {
    "SKILL.md": "...",
    "card.yaml": "..."
  },
  "gate_revision": {
    "checker_version": "...",
    "rubric_id": "company-profile-v1",
    "judge_protocol": "cws-gate-judge/v1"
  }
}
```

SHA-256 用于校验，`frozen/` 中的实际文件用于重放。Runner 每次发放 lease 和验收前重新计算哈希；任一冻结文件变化则进入 `human_review`，不得继续 loop。

模型名称、endpoint 标识和推理参数写入每次 `gate-result.json`，用于审计但不作为 skill revision。密钥和完整 endpoint 凭据不得落盘。

## 7. Attempt 布局与原子提升

Attempt 放在 run 级目录，避免候选产物被现有 final gate 当作正式节点扫描：

```text
artifacts/<run-id>/
├── attempts/
│   └── <skill-id>/
│       ├── 1/
│       │   ├── maker-context.json
│       │   ├── handoff.json
│       │   ├── evidence.json
│       │   └── gate-result.json
│       └── 2/
│           └── ...
├── <skill-id>/                 # 仅通过后出现
│   ├── handoff.json
│   ├── evidence.json
│   └── gate-result.json
├── run-manifest.json
└── workflow-state.json
```

失败 attempt 永不覆盖、删除或移动。通过时 Runner：

1. 校验 node gate；
2. 若为报告节点，以“正式父产物 + 当前 candidate 目录”构造 final gate 视图；
3. 将通过的 candidate 复制到同一文件系统的临时目录；
4. `fsync` 必要文件后，用 `os.replace` 把完整临时目录原子提升为 `artifacts/<run-id>/<skill-id>/`；
5. 最后更新 `workflow-state.json` 为 `passed`。

一个 run 中正式 skill 目录只允许从“不存在”变为“已提升”。若目标目录已存在且 revision 或 attempt 不一致，Runner 进入 `human_review`，不得覆盖。

### 7.1 Final gate 候选视图

`check_final` 增加可选 `candidate_skill_dir`：

- 父节点 handoff 和 `gate-result.json` 仍从正式顶层目录读取；
- 当前报告节点的 handoff、evidence 和 report 从 candidate 目录读取；
- subject/run 一致性检查同时覆盖父产物和 candidate；
- candidate 未通过 final gate 前不复制到正式路径。

这消除“必须先提升才能验 final、但通过前又不能提升”的循环依赖。

## 8. 状态机、Lease 与恢复

### 8.1 节点状态

```text
pending
  -> running
  -> validating
       -> retryable -> running
       -> needs_input
       -> needs_review
       -> exhausted
       -> promoting -> passed
  -> cancelled
```

`blocked` 保留给不启用 loop 的旧 delegate 行为。启用 loop 后，确定性失败先由 Runner Policy 映射为 `retryable | needs_input | needs_review | exhausted`，不会直接重新出现在 ready 列表。

`needs_input`、`needs_review`、`exhausted`、`passed` 和 `cancelled` 在第一版都是终态：

- `needs_input` 不允许修改冻结输入后原地继续；调用方补齐输入后必须创建新 run-id；
- `needs_review` 不提供绕过确定性 gate 的 waiver；人工修复或批准后使用新 run 重放；
- `cancelled` 保留全部 attempt 和审计记录，不提升候选产物；
- `exhausted` 只能由新 run 重试，防止无限增加 attempt。

### 8.2 Lease

`loop next` / `delegate start` 在一次带锁事务中写入：

- `lease_id`；
- `lease_owner`（宿主提供的非敏感标识，可省略）；
- `lease_started_at`；
- `lease_expires_at`；
- `attempt`。

`complete` 必须提交匹配的 `lease_id`。过期 lease 不能验收；Runner 把节点恢复为 `retryable`，保留原 attempt，并为下一轮创建新的 attempt 编号。旧执行者迟到提交时返回稳定错误，不修改状态。

所有 `workflow-state.json` 读改写通过 run 级锁文件和 Python 标准库 `fcntl.flock` 串行化；临时文件加 `os.replace` 只解决落盘原子性，不能替代并发锁。

### 8.3 恢复规则

- `running` 且 lease 未过期：等待当前执行者；
- `running` 且 lease 已过期：转 `retryable`；
- `validating`：重新运行 gate，gate 必须无外部副作用；
- `promoting` 且正式目录不存在：重新执行原子提升；
- `promoting` 且正式目录与记录的 attempt hash 一致：补写 `passed`；
- 状态与目录无法对应：进入 `needs_review`，不猜测、不覆盖。

## 9. 三层判定体系

### 9.1 Deterministic Gate

硬门禁只返回通过或失败，不参与评分。至少覆盖：

- handoff/evidence 结构和必要产物；
- run 与主体一致性；
- evidence 路径、claim 引用和值一致性；
- 跨公司、跨 run 串数据；
- 否定结论的查询覆盖；
- 明确虚构、直接矛盾和禁止副作用。

确定性 gate 失败时不调用 Judge。现有字符串错误在 GateOutcome 边界统一转换为 finding；checker 内部仍可继续返回稳定 reason code，避免第一版重写所有 checker。

### 9.2 Semantic Judge v1

第一版沿用 `cws-gate-judge/v1`：

- `decision`: `passed | needs_review`；
- `confidence`；
- `model`；
- `rubric_version`；
- `findings`。

通过条件为：

```text
Deterministic Gate 全部通过
AND Judge decision == passed
AND Judge confidence >= 0.75
AND 无 fatal finding
```

Judge 缺失、禁用、超时、协议错误或 confidence 低于 0.75 均映射为 `human_review`，不自动追分。

### 9.3 五维评分 v1.1

五维评分保留为后续可选扩展，不阻塞第一版：

| 维度 | 权重 | 关键维度 |
| --- | ---: | --- |
| `evidence_sufficiency` | 30% | 是 |
| `task_completeness` | 25% | 是 |
| `gap_conflict_disclosure` | 20% | 是 |
| `reasoning_discipline` | 15% | 是 |
| `clarity_usability` | 10% | 否 |

启用 v1.1 后由 Runner 根据维度分数计算总分，不信任模型直接给出的 `total_score`：

```text
total_score = sum(dimension_score / 4 * weight)
```

额外通过条件为所有关键维度 `>= 3` 且 `total_score >= 80`。第一版 tracer 不实现、不测试该分支。

## 10. Finding 与 Runner Policy

### 10.1 统一 Finding

Gate 与 Judge 在进入 Runner Policy 前统一成：

```json
{
  "reason": "source_conflict_not_disclosed",
  "dimension": "gap_conflict_disclosure",
  "severity": "major",
  "repairable": true,
  "action": "revise",
  "artifact_path": "artifacts.operating_status",
  "field": "operating_status",
  "evidence_refs": ["e1", "e2"],
  "detail": "..."
}
```

其中 `reason`、`severity`、`repairable`、`action` 由仓库内版本化 reason-policy 表决定，不接受模型自行提升权限。Judge 可提供 `artifact_path`、`field`、`evidence_refs` 和 `detail`；未知 reason 默认映射为 `human_review`。

允许的 action：

- `revise`：当前 skill 可在冻结输入内修正；
- `needs_input`：缺少调用方必须提供的事实或授权；
- `human_review`：低置信度、未知原因、policy 或不可自动修复问题；
- `upstream_contract_gap`：final 节点确认父 card 契约应提供但正式父产物缺失；
- `stop`：fatal、安全或主体串线问题。

`upstream_contract_gap` 只能由确定性 final checker 或白名单 reason-policy 产生。Judge 单独提出时一律进入 `human_review`，避免把报告节点自身遗漏误判为上游契约问题。

### 10.2 Fingerprint

Finding fingerprint 由以下字段的规范化 JSON 计算 SHA-256：

```text
reason + artifact_path + field + sorted(evidence_refs)
```

`detail` 不参与 fingerprint，避免措辞变化掩盖重复失败。缺失字段使用空值，不允许根据自由文本猜字段。

### 10.3 Runner Policy

固定策略：

| 条件 | next_action |
| --- | --- |
| node/final gate 全部通过 | `accept` |
| 有 `repairable=true` finding，输入充足且仍有次数 | `revise` |
| reason-policy 为 `needs_input` | `needs_input` |
| Judge 低置信度、不可用、未知 reason 或 policy 问题 | `human_review` |
| fatal、主体串线或禁止副作用 | `human_review` |
| 达到次数上限或无进展 | `exhausted` |

无进展定义为：连续两个已完成 attempt 的 fingerprint 集合完全相同。分数上升或 `detail` 变化不能覆盖 finding 集合未变化。每次修正若新增 fatal finding，立即 `human_review`；新增 major finding 时允许保留本轮结果，但不得继续自动修正。

第一版固定首次执行加最多 2 次修正，共 3 个 attempt。次数、无进展和 finding 集合均写入状态与 gate result。

Run manifest 同时记录固定 `max_elapsed_seconds`。每次 `next` 和 `complete` 都检查总运行时长，超限映射为 `exhausted`。Judge 单次超时继续使用现有 `CWS_JUDGE_TIMEOUT_SECONDS` 上限；Maker 的 token/费用预算由宿主执行层控制，Runner 只接受宿主主动 `cancel`，不伪造无法观测的成本保证。

## 11. 副作用与提交边界

理想协议为：

```text
prepare -> evaluate -> revise -> accept -> promote -> commit once
```

第一版只实现到 `promote`，不执行不可逆外部 `commit`。允许进入 loop 的写入必须满足以下之一：

- 写入 attempt/staging 目录；
- 以确定性路径覆盖同一 run 的临时数据；
- 有外部系统提供的幂等键和可查询 commit receipt。

邮件、消息、任务、审批、付款等无法可靠查询提交结果的操作直接判定为不具备 loop 资格。后续若支持提交型 skill，必须先定义 `commit-receipt.json`、provider 幂等键和“外部成功但本地未落盘”的恢复规则，不能仅凭 `run_id` 宣称 exactly-once。

首个 `cws-company-profile` tracer 使用冻结 fixture 和 staging 输出，不执行生产 wiki 写回。生产 wiki 接入必须在 canonical path 覆盖或 staging merge 的幂等性被单独验证后启用。

## 12. 审计与错误处理

每个 `gate-result.json` 至少包含：

- `run_id`、`skill_id`、`attempt`、`lease_id`；
- `status`、`decision`、`next_action`；
- deterministic gate 结果；
- Judge 原始结果及归一化 findings；
- finding fingerprints；
- 输入、skill、card、rubric revision；
- `checked_at`、candidate hash；
- promotion 或停止原因。

错误分层：

| 类型 | 行为 |
| --- | --- |
| 候选产物不合法 | 按 reason-policy 决定 revise/needs_input/human_review |
| Judge 不可用或协议错误 | `human_review`，fail closed |
| Runner 状态或磁盘不一致 | `human_review`，不覆盖 |
| 冻结文件 hash 变化 | `human_review` |
| lease 过期 | 保留 attempt，创建下一 attempt |
| promotion 中断 | 按 candidate hash 恢复 |
| 未知 reason | `human_review` |

日志和审计文件不得包含 secret。冻结生产案例前必须脱敏；无法安全脱敏的案例只记录 reason、schema 和最小可观察行为，不进入仓库 fixture。

## 13. 跨运行 Skill TDD 闭环

运行内 loop 只修正本次产物。Skill 定义改进继续走人工批准的跨运行流程：

```text
生产失败
  -> 冻结并脱敏候选案例
  -> 判断问题层级
  -> RED：固定错误产物被 gate 稳定拦截
  -> REPLAY：旧 skill revision 可重现目标失败
  -> 最小修改
  -> GREEN：同一案例通过
  -> 相关回归
  -> 人工批准
  -> 新 revision 仅供新 run 使用
```

### 13.1 问题分层

| 现象 | 修改位置 |
| --- | --- |
| 错误产物被 Gate 放过 | gate、rubric 或 checker |
| Gate 已指出问题但 Maker 重复失败 | `SKILL.md` |
| 指令正确但工具输出不稳定 | tool adapter 或 harness |
| 下游需要但 card 未声明 | `card.yaml` gate 契约 |
| 数据源没有该信息 | capability gap，不改 skill |
| Judge 结果不稳定 | rubric、Judge 或评估数据 |
| 副作用早于验收 | runner prepare/commit 边界 |

### 13.2 RED 与 Replay

候选案例必须冻结最小输入、来源摘要、失败产物、gate 结果、旧 skill/card 内容和预期可观察行为。测试不比较生成文本是否逐字相同。

RED 的确定性部分必须证明固定错误 handoff 被 Gate 稳定拦截。Maker replay 属于概率性验证：旧 revision 在相同冻结输入下运行 3 次，至少 2 次出现目标 finding，才认为可以稳定重现。无法达到该标准的生产观察只进入待分析记录，不自动驱动 skill 修改。

### 13.3 GREEN 与回归

一次只修改一个行为。GREEN 要求：

- 目标 hard gate 和 semantic rubric 通过；
- 目标 finding 消失；
- 没有新增 fatal/major finding；
- 相关 skill 案例没有新回归。

Gate fixture 进入普通 CI。依赖模型的相关案例在普通 PR 中运行一次；发布 skill revision 前，目标案例运行 3 次且至少 2 次通过，负例不得出现 fatal false-accept。完整重复评估进入定期任务。

新 revision 只对新 run 生效。验证原生产输入必须创建新 run-id；运行中的 manifest 和 frozen skill 文件不得替换。

## 14. 首个 Tracer Case

```text
skill: cws-company-profile
case: conflicting-operating-status
finding: source_conflict_not_disclosed
expected: 披露两个来源的冲突，不自行选择其一
```

Tracer 顺序：

1. 复用现有来源冲突 fixture，证明错误 handoff 被确定性 gate 拦截；
2. 初始化 standalone 单节点 run，验证 frozen manifest 和 attempt 目录；
3. attempt 1 产生目标 finding，Runner 返回 `revise`；
4. attempt 2 使用相同冻结输入和最新 findings，生成修正候选；
5. node gate 与 Judge 通过后原子提升；
6. 验证 attempt 1 仍存在、正式目录只包含通过产物；
7. 再模拟重复 finding、低置信度、lease 过期和 promotion 中断。

第一条切片不修改 `SKILL.md`；先用确定性测试 Maker/harness 证明运行内状态机。状态机稳定后，再单独执行真实 skill replay 和跨运行 TDD 修改，避免把 runner 缺陷与模型行为混在一起。

## 15. 测试边界

最小测试集：

| 层级 | 必测行为 |
| --- | --- |
| reason-policy | 已知 reason 映射、未知 reason fail closed、fingerprint 稳定 |
| loop state | init、next、complete、最多 3 次、无进展停止 |
| attempt isolation | 失败产物不进入正式路径，通过后完整提升 |
| final candidate | 正式父产物 + candidate 报告验收，不提前提升 |
| concurrency | 两个 start 只有一个获得 lease，迟到 complete 被拒绝 |
| recovery | lease 过期、validating 重跑、promotion 中断恢复 |
| revision | frozen hash 变化停止，manifest 可重放 |
| Judge | passed、needs_review、低置信度、不可用、协议错误 |
| compatibility | 未启用 loop 的 delegate 行为和现有 gate CLI 不变 |

不为 v1.1 五维评分、planned/auto hook、生产 wiki merge 或外部 commit 编写占位实现和测试。

## 16. 验收标准

- 原子 skill 不依赖 workflow YAML 即可显式初始化和运行 loop。
- Workflow delegate 节点复用同一 node-loop helper，不引入图上的环。
- Runner 不直接调用 Agent；宿主能仅凭结构化输出完成 execute/revise 协议。
- 每次 attempt 的输入、lease、skill/card revision、gate 结果和产物可追溯。
- node gate 与 final gate 都能验 candidate，失败 candidate 不会进入正式路径。
- 通过产物以完整目录原子提升，恢复时不会覆盖不一致的正式产物。
- 确定性错误不能被 Judge 决策或未来语义分数抵消。
- Loop 在次数上限、无进展、低置信度、未知 reason、缺输入或 lease 冲突时稳定停止。
- 同一节点不能被两个执行者同时领取或由过期执行者提交。
- 第一版不重复提交不可逆外部副作用。
- 未启用 loop 的 skill、现有 gate CLI 和 delegate 行为保持兼容。
- 可复现生产失败能形成脱敏 RED 案例，并通过最小修改达到 GREEN。
- 新 skill revision 通过相关回归和人工批准后才供新 run 使用。
