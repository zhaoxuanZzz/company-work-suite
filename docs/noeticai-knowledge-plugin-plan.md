# NoeticAI 知识卡片 Plugin 化方案

> 版本：v0.1 · 更新日期：2026-06-26  
> 目标：将 noeticai 项目中的知识卡片迁移为 Hermes Custom Desktop 可加载的专家套件插件。  
> 原则：卡片独立、workflow 编排、数据库函数先自然语言化，企查查 MCP 后接入。

---

## 1. 背景与目标

noeticai 现有知识卡片具备两类能力：

1. **知识分析能力**：卡片定义输入、分析逻辑、输出结构。
2. **数据获取能力**：部分卡片通过数据库函数取数，并存在子卡调用关系。

本方案将知识卡片迁移为 `plugins/noeticai-knowledge/` 下的 expert suite。迁移后：

- 每张卡片都是一个相对独立的 `skill`
- 卡片之间不直接互相调用
- 原子卡片依赖关系放入 `workflows/*.yaml`
- 原数据库函数替换为自然语言 `data_needs`
- 后续企查查 MCP 接入后，再将 `data_needs` 映射到真实 MCP 工具

不在本阶段做 workflow runtime。`workflow.yaml` 先作为 agent 可读的编排说明使用。

---

## 2. 目标目录结构

```text
plugins/noeticai-knowledge/
├── .claude-plugin/
│   └── plugin.json
├── .qoder-plugin/
│   └── plugin.json
├── .mcp.json
├── README.md
├── README_EN.md
├── CONNECTORS.md
└── skills/
    ├── 企业画像/
    │   ├── SKILL.md
    │   └── card.yaml
    ├── 股权结构分析/
    │   ├── SKILL.md
    │   └── card.yaml
    ├── 司法风险分析/
    │   ├── SKILL.md
    │   └── card.yaml
    ├── 融资历史分析/
    │   ├── SKILL.md
    │   └── card.yaml
    └── workflows/
        ├── 企业尽调.yaml
        └── 投资分析.yaml
```

说明：

- `.claude-plugin/plugin.json`：Hermes expert suite 读取的主 manifest。
- `.qoder-plugin/plugin.json`：保留当前插件兼容格式。
- `.mcp.json`：预留企查查 MCP 配置；未接入前可为空对象。
- `skills/*/SKILL.md`：卡片执行说明。
- `skills/*/card.yaml`：卡片的结构化元数据。
- `skills/workflows/*.yaml`：卡片编排关系。

---

## 3. Plugin Manifest 草案

`.claude-plugin/plugin.json`：

```json
{
  "name": "noeticai-knowledge",
  "version": "0.1.0",
  "description": "NoeticAI 企业知识卡片套件：围绕企业画像、股权结构、司法风险、融资历史和投资分析生成结构化研判。",
  "author": {
    "name": "NoeticAI"
  },
  "keywords": ["expert-suite", "knowledge-card", "company-research"],
  "hermes": {
    "displayName": "NoeticAI 知识卡片",
    "icon": "blocks",
    "iconBg": "bg-sky-50",
    "iconColor": "text-sky-600",
    "longDescription": "将企业研究、尽调和投研中的知识卡片拆分为独立技能，并通过 workflow yaml 组合为企业尽调、投资分析等流程。接入企查查 MCP 后可自动增强工商、股权、司法、融资等数据获取能力。",
    "disclaimer": "本套件输出仅用于研究和决策辅助，不替代正式尽职调查、法律意见或投资建议。",
    "capabilityOverview": "• 企业画像\n• 股权结构分析\n• 司法风险分析\n• 融资历史分析\n• 企业尽调 workflow\n• 投资分析 workflow",
    "dataConnections": [{ "id": "qichacha", "name": "企查查 MCP" }]
  }
}
```

`.qoder-plugin/plugin.json`：

```json
{
  "name": "noeticai-knowledge",
  "displayName": "NoeticAI 知识卡片",
  "version": "0.1.0",
  "description": "NoeticAI 企业知识卡片套件：企业画像、股权结构、司法风险、融资历史、企业尽调和投资分析。",
  "author": {
    "name": "NoeticAI"
  },
  "skills": [
    "企业画像",
    "股权结构分析",
    "司法风险分析",
    "融资历史分析"
  ]
}
```

---

## 4. 单卡设计

每张卡片保持独立，只声明输入、数据需求、输出和分析规则。不要在卡片内部调用其他卡片。

`skills/股权结构分析/card.yaml`：

```yaml
id: shareholder-structure
name: 股权结构分析
description: 分析目标企业股东结构、实控人、持股链路和股权异常信号。

inputs:
  - company_name
  - unified_social_credit_code

data_needs:
  - 查询企业工商基本信息
  - 查询当前股东列表及持股比例
  - 查询历史股权变更
  - 查询实际控制人
  - 查询对外投资和关联企业

outputs:
  - shareholder_summary
  - control_chain
  - related_entities
  - risk_flags
  - evidence_gaps

rules:
  - 不要编造工商、股权或关联企业数据
  - 数据缺失时输出 evidence_gaps
  - 所有结论必须说明依据字段
  - 企查查 MCP 可用时优先使用 MCP 查询
```

`skills/股权结构分析/SKILL.md`：

```markdown
---
name: 股权结构分析
displayName: 股权结构分析
description: 输入公司名称，分析股东结构、实控人、持股链路和股权异常信号。
argument-hint: "输入公司名称，如：杭州XX科技有限公司"
---

# /股权结构分析

你是股权结构分析卡片。根据 `card.yaml` 的输入、数据需求、输出字段和规则执行分析。

## 执行规则

1. 先确认目标企业主体，必要时要求用户补充统一社会信用代码。
2. 如企查查 MCP 可用，优先查询 `data_needs` 中列出的数据。
3. 如 MCP 不可用，不要编造数据；列出需要查询的字段，并基于用户提供资料分析。
4. 输出结论时必须标注依据和数据缺口。

## 输出格式

- 企业主体确认
- 股东概览
- 实控人与控制链路
- 关联企业与对外投资
- 股权异常信号
- 数据缺口
- 下一步建议
```

---

## 5. Workflow 设计

workflow 只负责编排，不承载具体分析逻辑。

`skills/workflows/企业尽调.yaml`：

```yaml
id: due-diligence
name: 企业尽调
description: 组合企业画像、股权结构、司法风险和融资历史，生成企业尽调摘要。

inputs:
  - company_name
  - unified_social_credit_code
  - purpose

steps:
  - id: profile
    card: 企业画像

  - id: shareholder_structure
    card: 股权结构分析
    needs: [profile]

  - id: litigation_risk
    card: 司法风险分析
    needs: [profile]

  - id: financing_history
    card: 融资历史分析
    needs: [profile]

  - id: final_report
    combine:
      - profile
      - shareholder_structure
      - litigation_risk
      - financing_history
    output: due_diligence_report

output_format:
  - 企业基本判断
  - 股权与控制风险
  - 司法与经营风险
  - 融资与资本市场信号
  - 数据缺口
  - 尽调建议
```

约束：

- `needs` 表示上下文依赖，不表示函数调用。
- `combine` 表示最终报告需要汇总的中间结果。
- workflow 文件先给 agent 读取执行；不开发解析器。

---

## 6. 数据函数迁移规则

| noeticai 现状 | Plugin 化后 |
|---|---|
| 知识卡片 | `skills/{卡片名}/SKILL.md` |
| 卡片元数据 | `skills/{卡片名}/card.yaml` |
| 子卡调用 | `skills/workflows/*.yaml` 的 `needs` |
| DB function | `card.yaml` 的 `data_needs` |
| DB 返回字段 | `outputs` 和 `rules` 中的依据字段要求 |
| 页面渲染模板 | `SKILL.md` 的输出格式 |
| 固定分析链路 | workflow yaml |

示例：

```text
getCompanyBasicInfo(company_id)
```

迁移为：

```yaml
data_needs:
  - 查询企业工商基本信息，包括企业名称、统一社会信用代码、法定代表人、注册资本、成立日期、经营状态、注册地址、经营范围
```

```text
getLitigationCases(company_id, years=3)
```

迁移为：

```yaml
data_needs:
  - 查询近三年司法案件，区分原告、被告、案由、涉案金额、审理阶段和裁判结果
```

---

## 7. MCP 接入策略

`.mcp.json` 先保留最小占位：

```json
{
  "mcpServers": {}
}
```

企查查 MCP 接入后再补充真实 server 配置，并更新各卡片 `SKILL.md`：

```markdown
如企查查 MCP 可用：
- 工商基本信息使用企查查企业基本信息查询能力
- 股东结构使用企查查股东及股权穿透查询能力
- 司法风险使用企查查司法案件、被执行人、失信信息查询能力
- 所有 MCP 结果需在输出中标注数据来源和查询时间
```

不要在 v0.1 中写死不存在的 MCP 工具名。

---

## 8. 迁移步骤

### Phase 1：样板卡片

1. 新建 `plugins/noeticai-knowledge/` 基础结构。
2. 迁移 1 张卡片，例如 `企业画像`。
3. 编写 `SKILL.md` 和 `card.yaml`。
4. 在专家套件页面确认插件元数据可展示。

### Phase 2：核心卡片

优先迁移 4 张卡片：

- 企业画像
- 股权结构分析
- 司法风险分析
- 融资历史分析

每张卡片只保留独立输入、数据需求和输出结构。

### Phase 3：Workflow

新增两个 workflow：

- 企业尽调
- 投资分析

将旧系统中的子卡依赖关系迁移到 `needs`。

### Phase 4：企查查 MCP 增强

1. 补充 `.mcp.json`。
2. 将 `data_needs` 映射到真实 MCP 能力。
3. 更新 `CONNECTORS.md`。
4. 增加数据来源、查询时间、数据缺口输出要求。

---

## 9. 验收标准

- [ ] `noeticai-knowledge` 出现在专家套件列表中
- [ ] 每张卡片可作为独立 skill 被触发
- [ ] 卡片不依赖其他卡片即可给出结果或数据缺口
- [ ] workflow yaml 能表达旧系统主要子卡依赖
- [ ] 未接入企查查 MCP 时不会编造企业数据
- [ ] 接入企查查 MCP 后，卡片可按 `data_needs` 使用外部数据增强

---

## 10. 暂不实现

- workflow runtime
- 卡片 DAG 可视化
- 数据库 schema 迁移
- noeticai 后端函数兼容层
- MCP 工具名自动映射

这些都等卡片结构稳定后再加。
