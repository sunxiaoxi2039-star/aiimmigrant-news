# AI 资讯站 · 发布仓

给中文读者的 AI 时间线：从上百条原始信息里，用「模型打五维分 + 代码算总分」的透明规则精选出真正值得看的几条。

- 站点：https://news.aiimmigrant.de
- 本仓只放**对外可见**的静态站点与生成器，白名单 `.gitignore` 默认挡一切、逐个放行
- 内容 = 中文标题 + ≤3 句摘要 + 原文直链，永不全文托管原文
- 生成器从 `data/精选库.json`（引擎产出）渲染静态页；引擎与内部数据不在本仓

## 本地结构

```
index.html      首页（时间线）
about.html      关于/免责/纠错/AI 辅助标注
data/           精选库 JSON 快照
generator/      网站生成器 v2
CNAME           news.aiimmigrant.de
```

## 再生成

```bash
/opt/homebrew/bin/python3 generator/build.py
```

署名：本仓提交由 ZCode（ZCode <zcode@pipeline.local>）完成。
