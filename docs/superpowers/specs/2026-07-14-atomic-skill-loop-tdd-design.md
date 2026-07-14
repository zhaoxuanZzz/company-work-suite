# 原子 Skill Loop 与 TDD 改进闭环设计

日期：2026-07-14

状态：设计已确认，待实现计划

## 1. 背景

CWS 当前通过 `card.yaml.gate`、`handoff.json`、`evidence.json`、确定性 semantic gate 和可选 LLM Judge 验证 skill 产物。现有 runner 能记录节点执行与 gate 结果，但失败后主要依赖人工修复产物并重新验收，尚未形成统一的原子 skill 自动修正循环，也没有把重复失败稳定转化为 skill 回归案例。

本设计把 loop 收缩到单个原子 skill。Workflow 继续保持无环 DAG；workflow 节点只是原子 skill loop 的调用者。非 workflow 场景也可以独立运行同一 loop。

## 2. 目标与非目标

### 2.1 目标

- 为声明了 gate 的原子 skill 提供显式启用的执行修正 loop。
- 在固定输入和评分标准下，允许 skill 根据结构化 findings 补数或修正当前产物。
- 将确定性门禁、语义评分和 runner 动作分离。
- 隔离每次 attempt，只有通过的 attempt 才提升为正式产物。
- 对重复失败设置明确上限，并保留完整审计记录。
- 将可复现的真实失败转成回归案例，以 RED → GREEN → regression 的方式改进 skill。
- 保证运行中的 skill revision 不发生变化。

### 2.2 非目标

- 不让 `workflow.yaml` 支持环或动态回跳。
- 不在当前 run 中自动修改 `SKILL.md`、`card.yaml` 或 checker。
- 不让总分覆盖主体串线、证据不一致等确定性错误。
- 不默认对所有 skill 启用 loop。
- 不在第一版引入知识图谱、独立建议池服务或新的通用编排引擎。

## 3. 核心模型

原子 skill loop 是一个无父节点的单节点运行：

```text
输入与 rubric 冻结
  -> 执行 skill
  -> Deterministic Gate
  -> Semantic Judge
  -> Runner Policy
       -> accept
       -> revise -> 下一 attempt
       -> needs_input
       -> human_review
       -> exhausted
```

Workflow 模式只在父产物全部通过后启动该节点的 loop；节点通过后才解锁下游。最终报告节点也是普通原子 skill，只是其输入包含全部父 handoff，并使用 final rubric 检查跨节点一致性。

如果最终节点发现已通过的父产物缺少其契约本应提供的信息，结果记为 `upstream_contract_gap` 并停止本次 run。该问题进入跨运行的 skill/card 改进闭环，不在运行期自动回跳上游。

## 4. 启用方式与复用边界

第一版仅对满足以下条件的原子 skill 显式启用：

- 存在 `card.yaml.gate`；
- 调用方明确请求 loop；
- 产物可以在提交外部副作用前接受 gate；
- 输入、rubric 和 skill revision 可以在 run 开始时冻结。

底层复用现有 node gate、delegate runner 状态和 `gate-result-N.json` 审计格式。独立原子 skill 在内部建模为只有一个节点、没有 parents 的 run，不新增第二套状态机。

## 5. Attempt 与产物提交

每次尝试写入独立目录：

```text
artifacts/<run-id>/<skill-id>/
├── attempts/
│   ├── 1/
│   │   ├── handoff.json
│   │   ├── evidence.json
│   │   └── gate-result.json
│   └── 2/
│       ├── handoff.json
│       ├── evidence.json
│       └── gate-result.json
├── handoff.json
├── evidence.json
└── gate-result.json
```

只有通过的 attempt 才提升到 skill 目录顶层。失败 attempt 永不覆盖，供审计和回归案例提取。

每次 attempt 使用同一份冻结输入、rubric 和 skill revision。Maker 接收原始输入、当前产物和最新 findings，不继承完整历史对话，避免上下文随循环腐化。

## 6. 副作用边界

原子 skill 必须区分可重复的准备阶段和不可逆提交阶段：

```text
prepare -> evaluate -> revise -> passed -> commit once
```

- 邮件、消息、任务和审批必须先生成草稿，通过后只提交一次。
- 外部写入使用 `run_id` 作为幂等键。
- raw 数据可以按来源和时间确定性保存。
- wiki 正式写回应在 gate 通过后执行或保证幂等。
- 无法把准备与提交分开的 skill 不进入自动 loop，只允许先检查后人工提交。

## 7. 三层判定体系

### 7.1 Deterministic Gate

硬门禁只返回通过或失败，不参与加权评分。至少覆盖：

- handoff/evidence 结构和必要产物；
- run 与主体一致性；
- evidence 路径、claim 引用和值一致性；
- 跨公司、跨 run 串数据；
- 否定结论的查询覆盖；
- 明确虚构、直接矛盾和禁止副作用。

确定性 gate 失败时不调用 Semantic Judge。Runner 根据稳定 reason code 判断该问题是否可以在当前 skill 内修正。

### 7.2 Semantic Judge

Judge 使用 0–4 五档评分：

| 分数 | 定义 |
| ---: | --- |
| 0 | 缺失、完全错误或与证据冲突 |
| 1 | 存在重大缺陷，无法使用 |
| 2 | 部分满足，必须修正 |
| 3 | 达到交付标准 |
| 4 | 明显高于交付标准 |

所有原子 skill 共享五个基础维度：

| 维度 | 权重 | 关键维度 |
| --- | ---: | --- |
| `evidence_sufficiency` | 30% | 是 |
| `task_completeness` | 25% | 是 |
| `gap_conflict_disclosure` | 20% | 是 |
| `reasoning_discipline` | 15% | 是 |
| `clarity_usability` | 10% | 否 |

总分计算：

```text
total_score = sum(dimension_score / 4 * weight)
```

基础维度的业务解释通过版本化 rubric ID 注册，例如 `company-profile-v1`。第一版不允许每个 `card.yaml` 自由修改权重。

通过条件固定为：

```text
Deterministic Gate 全部通过
AND 无 fatal finding
AND 所有关键维度 >= 3
AND total_score >= 80
AND Judge confidence >= 0.75
```

Judge 保持 `passed | needs_review` 的简单决策。其输出还必须包含 `confidence`、`total_score`、各维度评分、rubric/model 版本和结构化 findings。分数用于衡量，findings 用于修正。

### 7.3 Runner Policy

Runner 将 gate/judge 结果映射为运行动作：

| 条件 | 动作 |
| --- | --- |
| 全部通过 | `accept` |
| 存在可修复 finding 且仍有次数 | `revise` |
| 缺少必要用户输入 | `needs_input` |
| 低置信度、policy 或不可自动修复问题 | `human_review` |
| 达到次数上限或无进展 | `exhausted` |

第一版固定：

- 首次执行加最多 2 次修正；
- 相同 finding fingerprint 连续 2 轮出现则提前停止；
- 每轮至少解决一个 major finding，且不得新增 fatal/major finding；
- confidence 低于 0.75 时不继续自动追分。

Finding fingerprint 由稳定 reason code、artifact path 和 field 生成。总分缓慢上升不能覆盖 finding 没有变化的事实。

## 8. Finding 契约

Gate 与 Judge 输出统一的结构化 finding：

```json
{
  "reason": "source_conflict_not_disclosed",
  "dimension": "gap_conflict_disclosure",
  "severity": "major",
  "repairable": true,
  "artifact_path": "artifacts.operating_status",
  "field": "operating_status",
  "evidence_refs": ["e1", "e2"]
}
```

Checker 只描述问题，不指定 workflow 节点。对于原子 skill，Runner 只需判断当前 skill 能否修正、是否缺输入或是否必须人工介入。

## 9. Skill 改进 TDD 闭环

运行内 loop 只修正本次产物。Skill 定义的修改发生在跨运行闭环：

```text
生产失败
  -> 冻结并脱敏候选案例
  -> 判断问题层级
  -> RED：旧 revision 可重现
  -> 最小修改
  -> GREEN：同一案例通过
  -> 全量相关回归
  -> 人工批准
  -> 新 revision 供新 run 使用
```

### 9.1 问题分层

| 现象 | 修改位置 |
| --- | --- |
| 错误产物被 Gate 放过 | gate、rubric 或 checker |
| Gate 已指出问题但 Maker 重复失败 | `SKILL.md` |
| 指令正确但工具输出不稳定 | tool adapter 或 harness |
| 下游需要但 card 未声明 | `card.yaml` gate 契约 |
| 数据源没有该信息 | capability gap，不改 skill |
| Judge 结果不稳定 | rubric、Judge 或评估数据 |
| 副作用早于验收 | runner prepare/commit 边界 |

### 9.2 RED 案例

候选案例必须冻结最小输入、原始来源摘要、失败产物、gate 结果和预期可观察行为。测试不比较生成文本是否逐字相同。

RED 必须同时证明：

- 固定错误 handoff 能被 Gate 稳定拦截；
- 旧 skill revision 在冻结输入下可以重现目标失败。

无法重现的生产观察只进入待分析记录，不直接驱动 skill 修改。

### 9.3 GREEN 与回归

一次只修改一个行为。GREEN 要求：

- 目标 hard gate 和 semantic rubric 通过；
- 目标 finding 消失；
- 没有新增严重 finding；
- 相关 skill 案例没有新回归。

验收优先级固定为：目标案例修复、无新硬门禁失败、关键维度达标、案例通过率不下降，最后才比较总分。平均分提高不能抵消通过率下降。

Gate fixture 进入普通 CI。依赖模型的 skill replay 在普通 PR 中对相关案例运行一次；发布 skill revision 前，目标案例运行 3 次且至少 2 次通过，不得出现 fatal false-accept。完整重复评估进入定期任务。

### 9.4 Revision 发布

每个 run 记录相关 skill 文件的 SHA-256 revision。已开始的 run 不切换 revision。修改通过评估并人工批准后，只对新的 run 生效；需要验证原生产输入时，使用新的 run-id 重放。

## 10. 首个 Tracer Case

第一条垂直切片使用：

```text
skill: cws-company-profile
case: conflicting-operating-status
finding: source_conflict_not_disclosed
expected: 披露两个来源的冲突，不自行选择其一
```

该案例复用现有来源冲突 gate fixture，先证明错误 handoff 被拦截，再重放原子 skill，最后以最小 `SKILL.md` 修改使同一冻结案例通过。

## 11. 验收标准

- 原子 skill 不依赖 workflow YAML 即可显式启动 loop。
- Workflow 节点复用同一单节点 loop，不引入图上的环。
- 每次 attempt 的输入、skill revision、评分和产物可追溯。
- 失败 attempt 不会成为正式产物或重复提交外部副作用。
- 确定性错误不能被语义总分抵消。
- Loop 能根据 findings 自动修正，但在次数上限、无进展或低置信度时停止。
- 可复现生产失败能够形成 RED 案例，并通过最小 skill 修改达到 GREEN。
- 新 skill revision 通过相关回归和人工批准后才供新 run 使用。
