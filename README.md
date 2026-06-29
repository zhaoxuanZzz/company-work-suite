# NoeticAI 知识卡片

将 noeticai 项目中的企业知识卡片迁移为 Hermes Custom Desktop 可加载的专家套件插件。

> **免责声明：** 本套件输出仅用于研究和决策辅助，不替代正式尽职调查、法律意见或投资建议。

## 能力概览

| 卡片 | 说明 |
|------|------|
| 企业画像 | 汇总企业基本信息、经营状态与核心标签 |
| 股权结构分析 | 股东结构、实控人、持股链路与股权异常信号 |
| 司法风险分析 | 诉讼、执行、失信等司法风险研判 |
| 融资历史分析 | 融资轮次、投资方、估值与资本市场信号 |

## Workflow

| Workflow | 说明 |
|----------|------|
| 企业尽调 | 组合画像、股权、司法、融资，生成尽调摘要 |
| 投资分析 | 组合核心卡片，生成投资研判报告 |

## 开发

本仓库为独立开发目录。在 Hermes Custom Desktop 中调试时，可将本目录链接到桌面客户端的 `plugins/` 下：

```bash
ln -s /Users/zhaoxuan/code/noeticai-knowledge \
  /Users/zhaoxuan/code/hermes-custom-desktop/plugins/noeticai-knowledge
```

详细方案见 [docs/noeticai-knowledge-plugin-plan.md](./docs/noeticai-knowledge-plugin-plan.md)。

## 目录结构

```text
.
├── .claude-plugin/plugin.json   # Hermes expert suite manifest
├── .qoder-plugin/plugin.json    # Qoder 兼容 manifest
├── .mcp.json                    # MCP 配置（企查查预留）
├── skills/
│   ├── {卡片名}/SKILL.md        # 卡片执行说明
│   ├── {卡片名}/card.yaml       # 卡片结构化元数据
│   └── workflows/*.yaml         # 卡片编排关系
├── CONNECTORS.md
└── docs/noeticai-knowledge-plugin-plan.md
```
