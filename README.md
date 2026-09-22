# AI 资讯站 · 发布仓

给中文读者的 AI 时间线：从上百条原始信息里，用「模型打五维分 + 代码算总分」的透明规则精选出真正值得看的几条。

- 站点：https://news.aiimmigrant.de
- 本仓只放**对外可见**的静态站点与生成器，白名单 `.gitignore` 默认挡一切、逐个放行
- 内容 = 中文标题 + ≤3 句摘要 + 原文直链，永不全文托管原文
- 生成器从 `data/精选库.json`（引擎产出）渲染静态页

## 本地结构

```
index.html      首页（时间线）
about.html      关于/免责/纠错/AI 辅助标注
data/           精选库 JSON 快照 + CI 状态件（台账/缓存，见下）
generator/      网站生成器 v2
引擎/           引擎仓内副本（十件，见下「同步纪律」）
雷达/           抢跑雷达 CI 副本（原件零触碰）
CNAME           news.aiimmigrant.de
.github/        Actions workflow + CI_MODE 模式开关
```

## 再生成

```bash
/opt/homebrew/bin/python3 generator/build.py
```

署名：本仓 Mac 侧提交由 ZCode（ZCode <zcode@pipeline.local>）经 agent-git wrapper 完成；GitHub Actions 内由 `github-actions[bot]`（Actions 自身主体）提交，台账 `author`/`trigger` 字段分账。

## GitHub Actions 云端化（Phase 1 影子期，2026-09-21 Fable 有条件 GO）

目标：Mac 关机时网站仍自动更新。当前模式看 `.github/CI_MODE`（内容一行 `shadow` 或 `live`）——
shadow = 只推 `ci/shadow-<ts>` 分支 + 开 PR，**不碰 main**；切 live = 改这一行一个 commit。

- 触发：`workflow_dispatch` 手动 + cron 每 6 小时（`17 */6 * * *`，影子期节奏，Phase 2 再议）
- 链路：雷达（纯 RSS/HTML 零凭据）→ 摘要 → 引擎（条件）→ 发布链五门禁原样 → 影子 PR
- **烧钱纪律**：DeepSeek 是按量付费。**影子期不配 Secret**——引擎层在 workflow 里 SKIP（打印
  三步指引退出 0），零双烧。Phase 2 切 live 前须按实账单报价（近 3 天日均 ÷ 轮数）并经站主点头。
- **配 Secret 三步**（Phase 2 时才做）：① 仓库页 Settings → Secrets and variables → Actions →
  New secret ② Name 填 `DEEPSEEK_API_KEY`，Value 粘 DeepSeek 平台的 API key ③ 保存后手动
  Run workflow 验证引擎层变绿。
- **CI 不做回滚**：`--revert` 只在 Mac 上做（发布链 revert 硬编码 agent-git/ZCode 署名）。
- 通知：Actions 自带失败邮件，不接新服务。

## 状态文件与体积上界（M6）

| 文件 | 上界规则 |
|---|---|
| data/雷达/抢跑台账.json | seen/items 各 8000 条封顶（雷达自身截断） |
| data/引擎产物/摘要缓存.json | 条目 48h TTL 剪枝（每轮落盘前） |
| data/引擎产物/页面正文缓存.json | 条目按 fetched_at 48h TTL 剪枝（落盘前） |
| data/引擎产物/发布-台账.jsonl / 告警-日志.jsonl | 追加型小台账，月度复盘 |

## 同步纪律（防双份漂移）

- **引擎**：Mac 原件在 `ZCodeProject/AI资讯站/引擎/`。改原件必须同步本仓 `引擎/` 副本（十件：
  管线/共用/加工层/去重器/摘要抓取器/正文抽取器/大厂通道/发布链/翻译层/scoring.zh+de.json）。
  Phase 2 后建议以本仓为源。
- **雷达**：`雷达/抢跑雷达.py` 是 `~/ai-radar/抢跑雷达.py` 的 CI 副本（2026-09-21 快照，delta
  仅 3 处 env 钩，见副本头注）。改原件必须重新快照。
