# Gate 双层数据集设计

日期：2026-07-13

状态：设计已确认

范围：`cws-company-profile` 节点 gate 与 `cws-due-diligence` final gate 的首批验证数据集

## 1. 背景

仓库现有 `tests/fixtures/gates/company-profile/` 主要验证 `handoff.json` 的结构、必填字段、输出类型、`run_id` 和少量行为规则。`scripts/check_artifact_gate.py` 的 final 模式主要验证本次 run 的父 handoff 与报告 handoff 是否存在、可解析且 `run_id` 一致。

这些测试能够证明 gate 检查器按当前契约工作，但不能证明 gate 对真实企业数据质量做出了正确判断。例如，字段内容互相冲突、数据已经过期或父产物来自另一家公司时，只要结构仍然合法，当前 gate 仍可能放行。

因此需要建立两层数据集：

1. 契约数据集：确定性验证 gate 检查器本身，进入常规 CI。
2. 真实业务快照数据集：离线回放复杂企业数据场景，识别语义误放行、误拦截和数据源漂移。

真实业务层采用“离线冻结快照作为基准集 + 定期在线刷新”。在线数据只生成候选快照和漂移报告，不直接改写基准答案。

## 2. 目标与非目标

### 2.1 目标

- 同时覆盖 node gate 与 final gate。
- 区分“当前 gate 实际行为”和“业务上正确的预期行为”。
- 能稳定复现缺字段、主体歧义、来源冲突、数据过期、跨 run 串线和跨公司串线等场景。
- 能量化误放行、误拦截、已知能力缺口和数据漂移。
- 基准快照的更新必须经过可审计的人工确认。

### 2.2 首批范围

- 节点：`cws-company-profile`。
- 终局：`cws-due-diligence`。
- 结构异常使用基准 handoff 加 patch 生成。
- 真实业务场景保存完整、最小化的离线快照 bundle。

### 2.3 非目标

- 首批不覆盖所有业务 skill 和投资分析 workflow。
- 不在数据集建设阶段直接实现 LLM 主观评分器。
- 不把在线数据源的实时结果作为 CI 的通过条件。
- 不自动接受在线刷新产生的新标签或新基准。
- 不把受限原文、访问令牌、请求头或企业内部数据提交到仓库。

## 3. 判定政策

核心原则：**真实但不完整可以通过；虚构、隐瞒、不一致或串数据必须拦截。**

每个案例同时记录 gate 决策和数据质量状态：

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `expected_gate` | `passed` / `blocked` | 业务上期望的硬门禁结果 |
| `quality_state` | `complete` / `degraded` / `invalid` | 数据完整、真实但有缺口、或不可接受 |
| `waivable` | `true` / `false` | 是否允许人工带原因放行 |
| `expected_reasons` | 字符串列表 | 稳定、机器可比较的原因码 |

`degraded` 不等于失败。无法取得部分数据但已在 `evidence_gaps` 中如实披露时，`expected_gate` 可以是 `passed`。主体无法确认、来源冲突未披露、虚构结论或混入其他任务数据时，`expected_gate` 必须是 `blocked`。

数据集还必须记录当前实现的实际结果：

```json
{
  "expected_gate": "blocked",
  "quality_state": "invalid",
  "expected_reasons": ["source_conflict_not_disclosed"],
  "current_gate_decision": "passed",
  "capability_gap": true,
  "waivable": true
}
```

这样可以保留已知失败案例，而不把当前误放行错误地固化为业务预期。

## 4. 方案选择

考虑过三种组织方式：

1. 每个场景保存完整 `handoff.json`：直观，但结构异常案例会大量复制相同数据。
2. 单一基准快照加 patch：维护成本低，但真实业务案例难以独立阅读和审计。
3. 混合式：真实业务场景保存完整快照，纯结构异常由基准 handoff 加 patch 生成。

采用第三种。它兼顾真实场景的可审计性和契约测试的低维护成本。

## 5. 数据集目录

```text
tests/fixtures/gate-dataset/
├── schema/
│   ├── base/
│   │   ├── company-profile.handoff.json
│   │   └── due-diligence-run/
│   ├── patches/
│   └── cases.json
├── business/
│   ├── normal-active-company/
│   ├── ambiguous-company-name/
│   ├── partially-missing-data/
│   ├── conflicting-sources/
│   ├── stale-data/
│   ├── no-public-data/
│   └── high-risk-company/
├── manifests/
│   ├── node-cases.json
│   └── final-cases.json
└── refresh/
    └── companies.json
```

`schema/` 只表达确定性契约变体。`business/` 表达真实业务语义。`manifests/` 是测试发现和期望判定的入口。`refresh/companies.json` 只保存允许在线刷新的主体标识、场景用途和刷新频率，不保存密钥。

## 6. 真实案例 bundle

每个业务案例是一个可独立回放的 bundle：

```text
business/conflicting-sources/
├── case.json
├── raw/
│   ├── qcc-company.json
│   └── public-source.json
├── input.json
├── artifacts/
│   └── run-case-001/
│       ├── cws-company-profile/
│       │   ├── handoff.json
│       │   └── report.md
│       └── cws-due-diligence/
│           └── handoff.json
└── expected/
    └── decision.json
```

职责分离：

- `raw/`：冻结且最小化的原始来源数据。
- `input.json`：输入主体、统一社会信用代码（如有）、模拟运行时间和固定 `run_id`。
- `artifacts/`：待 gate 回放的标准化产物。
- `case.json`：场景标签、快照时间、适用 gate 和数据来源摘要。
- `expected/decision.json`：业务期望、当前实际结果和能力缺口。

`case.json` 最小形状：

```json
{
  "case_id": "conflicting-sources",
  "subject": "示例公司",
  "tags": ["source-conflict", "node", "semantic"],
  "snapshot_at": "2026-07-13",
  "evaluation_at": "2026-07-13",
  "applicable_gates": ["cws-company-profile:node"],
  "source_hashes": {
    "qcc-company.json": "sha256:4f34c65a67790b3f89b5834cc1f1ce0ddf2e9ab82f211d265f34a55af8ef8629",
    "public-source.json": "sha256:7e702493db039a275202805704e500524a7e5f3f48d4ac21d2c61f254608c2a4"
  }
}
```

`snapshot_at` 表示抓取时间；`evaluation_at` 表示回放时模拟的当前时间。两者分开后，可以稳定复现“数据已过期”场景，而不依赖测试执行当天的系统时间。

## 7. 首批场景矩阵

### 7.1 Node gate

| 类别 | 场景 | `expected_gate` | `quality_state` |
| --- | --- | --- | --- |
| 基线 | 主体唯一、数据完整、来源一致 | `passed` | `complete` |
| 主体 | 公司简称能唯一解析到法人主体 | `passed` | `complete` |
| 主体 | 同名企业，无法确定具体主体 | `blocked` | `invalid` |
| 主体 | 名称与统一社会信用代码不一致 | `blocked` | `invalid` |
| 缺失 | 非关键字段缺失，已写 `evidence_gaps` | `passed` | `degraded` |
| 缺失 | 核心画像缺失，未写缺口 | `blocked` | `invalid` |
| 空数据 | 完全查不到公开数据，如实说明 | `passed` | `degraded` |
| 空数据 | 查不到数据却填充确定性结论 | `blocked` | `invalid` |
| 来源 | 多来源结论一致 | `passed` | `complete` |
| 来源 | 多来源冲突，已披露冲突和取舍依据 | `passed` | `degraded` |
| 来源 | 多来源冲突，直接选择其一且不说明 | `blocked` | `invalid` |
| 时效 | 数据较旧，明确标注时间和时效风险 | `passed` | `degraded` |
| 时效 | 使用过期数据却声明为当前状态 | `blocked` | `invalid` |
| 状态 | 注销、吊销或经营异常，风险如实进入 `risk_flags` | `passed` | `complete` |
| 角色 | data handoff 携带最终尽调结论 | `blocked` | `invalid` |
| 文件 | handoff 缺失、JSON 损坏或根节点类型错误 | `blocked` | `invalid` |
| 隔离 | handoff `run_id` 与本次运行不一致 | `blocked` | `invalid` |

### 7.2 Final gate

| 场景 | `expected_gate` | `quality_state` |
| --- | --- | --- |
| 父 handoff 和报告齐全，来自同一 run 和同一主体 | `passed` | `complete` |
| 任一父 handoff 缺失或损坏 | `blocked` | `invalid` |
| 混入其他 run 的父产物 | `blocked` | `invalid` |
| 混入另一家公司的父产物 | `blocked` | `invalid` |
| 父节点结构合格，但其 gate 实际被阻断 | `blocked` | `invalid` |
| 报告遗漏父节点披露的重大风险或关键缺口 | `blocked` | `invalid` |

首批案例应覆盖每一行至少一个样本。结构型案例可由 patch 生成；主体、来源、时效和报告遗漏必须使用完整业务 bundle。

## 8. 原因码

原因码用于稳定断言，不直接依赖易变化的中文错误文本。首批至少包括：

```text
handoff_missing
handoff_invalid_json
required_output_missing
required_output_empty
run_id_mismatch
subject_ambiguous
subject_identity_mismatch
missing_data_not_disclosed
unsupported_claim
source_conflict_not_disclosed
stale_data_not_disclosed
data_role_contains_final_report
parent_handoff_missing
parent_gate_blocked
cross_run_artifact
cross_subject_artifact
material_risk_omitted
```

一个案例可以有多个原因码。测试断言至少要求实际原因集合包含 `expected_reasons`，允许检查器附加更具体的诊断信息。

## 9. 离线评估

离线 runner 的职责是：

1. 从 manifest 发现案例。
2. 为结构案例复制基准 handoff 并应用 patch。
3. 为业务案例构造隔离的临时 company-kb 目录。
4. 使用案例固定的 `run_id` 调用现有 node 或 final gate。
5. 记录 `expected_gate`、实际 exit code、标准化原因码和能力缺口。
6. 输出 JSON 明细与终端摘要。

指标至少包含：

- 总案例数与按标签覆盖率。
- 误放行：预期拦截但实际通过。
- 误拦截：预期通过但实际拦截。
- 已知能力缺口：`capability_gap: true` 的案例。
- 非预期回归：原本一致的案例产生新偏差。

CI 分层执行：

- 常规 CI：全部契约案例和不依赖外部访问的业务快照。
- 定期评估：同一离线基准集的完整报告，可容纳已登记的能力缺口，但不能新增未登记偏差。
- 在线刷新：独立任务，不作为普通 PR 的通过条件。

## 10. 在线刷新

在线刷新遵循以下流程：

```text
定期抓取
  -> 写入 staging 快照
  -> 与当前基准做字段级 diff
  -> 生成候选 handoff
  -> 运行现有 gate
  -> 比较 expected 与 actual
  -> 生成漂移报告
  -> 人工审核
  -> 提升为新的版本化基准
```

约束：

- 在线任务不得直接覆盖 `tests/fixtures/gate-dataset/business/`。
- 原始响应、标准化 handoff 与预期判定必须分开保存。
- 刷新产物先进入仓库外 staging 目录；只有审核后的最小化快照才能进入 fixture。
- 对来源响应做字段白名单和敏感信息扫描。
- 保存最小必要字段及摘要哈希，不保存 token、cookie、授权头或受限全文。
- 语义标签必须人工审核；刷新脚本只能提出候选变化。
- 基准更新应在 PR 中同时展示来源 diff、handoff diff、gate 决策 diff 和标签变化。

## 11. 当前能力缺口的处理

数据集先表达正确业务期望，不迁就当前检查器能力。预期会首先暴露以下误放行：

- 主体歧义或名称与信用代码不一致。
- 来源冲突未披露。
- 数据过期未披露。
- 父 handoff 属于同一 run，但实际是另一家公司。
- final 报告遗漏父节点的重大风险或 `evidence_gaps`。
- final 只检查父 handoff 存在，却没有验证父 gate 是否通过。

这些案例标记为 `capability_gap: true`。后续增强 gate 时逐项转为普通回归案例；不能删除失败样本来提高通过率。

## 12. 分阶段落地

### 阶段一：数据集骨架与现有规则回归

- 建立目录、manifest 和案例元数据格式。
- 迁移现有 company-profile fixture。
- 增加结构 patch 与 final run fixture。
- runner 复用现有 `check_artifact_gate.py`。

### 阶段二：首批真实业务快照

- 为主体歧义、部分缺失、来源冲突、数据过期、无公开数据和高风险主体建立 bundle。
- 人工标注业务期望和原因码。
- 生成首次误放行与误拦截报告。

### 阶段三：在线刷新与漂移报告

- 配置刷新主体和频率。
- 输出 staging 快照与多层 diff。
- 建立人工提升基准的 PR 流程。

### 阶段四：扩大覆盖

- 按能力缺口优先级增强 gate。
- 扩展到股权结构、司法风险、融资历史和投资分析。
- 保持 node 与 final 案例分层，不把所有场景塞进单一端到端测试。

## 13. 验收标准

- 首批场景矩阵每一行至少有一个案例。
- 所有案例均有稳定 `case_id`、标签、预期 gate、质量状态和原因码。
- 离线执行不访问网络，结果可重复。
- 当前已有结构规则全部通过回归。
- 当前语义能力缺口被明确列出，且不会导致普通回归被误判为成功。
- 在线刷新不能直接修改基准；基准提升需要人工审核。
- 测试报告能分别展示误放行、误拦截、能力缺口和数据漂移。
