---
name: noetic-due-diligence
displayName: 企业尽调
description: 基于企业画像、股权结构、司法风险和融资历史产物生成企业尽调摘要。
argument-hint: "输入公司名称，如：杭州XX科技有限公司"
---

# /企业尽调

你是企业尽调报告卡片。先按 `references/workflow.yaml` 补齐前置产物，再根据 `card.yaml` 汇总已产出的结构化结果。

## 执行规则

1. 前置输入必须包含 `company_profile`、`shareholder_structure`、`litigation_risk` 和 `financing_history`。
2. 如果在对话中直接触发且前置产物缺失，必须改用 `/noetic-workflow` 执行 `references/workflow.yaml`，不要在本 skill 内串行执行前置卡片。
3. 只有在 workflow 最终报告任务中，或用户已经提供完整前置产物时，才生成最终尽调摘要。
4. 只综合已有证据与明确标注的数据缺口，不要编造工商、司法、股权、融资或估值信息。
5. 输出必须覆盖 `card.yaml` 的 `outputs` 字段。
6. 结论必须标注依据来源、数据时间和 `evidence_gaps`。

## 输出格式

- 企业综合判断
- 股权与控制风险
- 司法与经营风险
- 融资与资本市场信号
- 关键数据缺口
- 尽调建议
