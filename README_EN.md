# NoeticAI Knowledge Cards

Expert suite plugin that migrates NoeticAI enterprise knowledge cards into Hermes Custom Desktop.

> **Disclaimer:** Outputs are for research and decision support only. They do not replace formal due diligence, legal opinions, or investment advice.

## Cards

| Card | Description |
|------|-------------|
| 企业画像 | Company profile, operating status, and key tags |
| 股权结构分析 | Shareholder structure, control chain, and equity risk signals |
| 司法风险分析 | Litigation, enforcement, and credit risk analysis |
| 融资历史分析 | Funding rounds, investors, valuation, and capital market signals |

## Workflows

| Workflow | Description |
|----------|-------------|
| 企业尽调 | Due diligence report combining profile, equity, legal, and financing |
| 投资分析 | Investment analysis report from core knowledge cards |

## Development

Link this repo into Hermes Custom Desktop `plugins/` for local testing:

```bash
ln -s /Users/zhaoxuan/code/noeticai-knowledge \
  /Users/zhaoxuan/code/hermes-custom-desktop/plugins/noeticai-knowledge
```

See [docs/noeticai-knowledge-plugin-plan.md](./docs/noeticai-knowledge-plugin-plan.md) for the full migration plan.
