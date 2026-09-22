#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信源对账 —— 章程「信源铁律」第二步：每天校对我们与对标清单的信源差别。
（2026-09-22 建，Opus）

第一步「完全拷贝对标公开清单」的登记台账在这里生成：把对标站公开精选里出现过的
source.name 逐项登记，标出我们是否已接、接在哪一路、未接原因。第二步「每天校对」
复用 ~/ai-radar/养分吸收器.py 已有的条目级对账结果（养分台账.json），不重写第二套。

产出：
  信源/信源登记.json      机器可读登记表（唯一原件）
  信源/信源登记.md        人可看版（脚本生成，勿手改）
  data/信源登记.json      发布用副本（含当日差别摘要）→ 发布链 → /api/v1/sources.json
  data/信源差别.json      当日差别（撞上/漏网/独家/建议补源）
  产物/信源差别-YYYY-MM-DD.md   当日差别人读版

用法：
  python3 引擎/信源对账.py            # 全量重算并写出
  python3 引擎/信源对账.py --dry-run  # 只打印统计不写文件
"""
import argparse, ast, json, os, re, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import (PROJ, DATA_DIR, WORK, RADAR, write_json_atomic, utc_iso,
                  brand_violation)

RADAR_PY = os.path.join(RADAR, "抢跑雷达.py")
WECHAT_PY = os.path.join(RADAR, "公众号桥.py")
BENCHMARK = os.path.join(RADAR, "data", "AIHOT信源库.json")     # 对标站公开精选累积的 source.name
NUTRIENT_LEDGER = os.path.join(RADAR, "data", "养分台账.json")   # 条目级日对账（养分吸收器写）
REG_DIR = os.path.join(PROJ, "信源")
REG_JSON = os.path.join(REG_DIR, "信源登记.json")
REG_MD = os.path.join(REG_DIR, "信源登记.md")
PUB_REG = os.path.join(DATA_DIR, "信源登记.json")
DIFF_JSON = os.path.join(DATA_DIR, "信源差别.json")

STATUS = {"connected": "已接", "pending": "待接", "blocked": "不可接"}


# ---------- 我们这边的家底（从雷达源表直接读，不手抄第二份） ----------
def _literal(src, name):
    """从源码里取模块级常量（纯字面量/字符串拼接），不 import、不执行模块。"""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                # 字符串 + 拼接（X_OFFICIAL_QUERY 那种）
                parts = []

                def walk(n):
                    if isinstance(n, ast.Constant):
                        parts.append(n.value)
                    elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
                        walk(n.left)
                        walk(n.right)
                    else:
                        raise ValueError(f"{name} 不是纯字面量表达式")
                walk(node.value)
                return "".join(parts)
    raise KeyError(f"{RADAR_PY} 里找不到 {name}")


def our_inventory():
    src = open(RADAR_PY, encoding="utf-8").read()
    rss = [{"name": n, "url": u, "tag": t} for n, u, t in _literal(src, "RSS_FEEDS")]
    html = [{"name": n, "url": u} for n, u, _re in _literal(src, "HTML_CHANNELS")]
    x_handles = sorted({h.lower() for h in re.findall(r"from%3A([A-Za-z0-9_]+)",
                                                      _literal(src, "X_OFFICIAL_QUERY"))})
    try:
        wechat = [a for a, _q in _literal(open(WECHAT_PY, encoding="utf-8").read(), "ACCOUNTS")]
    except (OSError, KeyError, ValueError):
        wechat = []
    other = [
        {"name": "arXiv 官方 API", "lane": "雷达·论文", "note": "cs.AI/cs.CL/cs.LG 全摘要通道"},
        {"name": "HuggingFace Papers API", "lane": "雷达·论文", "note": "社区热门论文，不走 RSS"},
        {"name": "HuggingFace 模型库（全球 + 中国实验室）", "lane": "雷达·模型", "note": "CN_HF_AUTHORS 7 家"},
        {"name": "GitHub 组织 Release", "lane": "雷达·代码", "note": "GH_ORGS 5 家"},
        {"name": "Hacker News 热议", "lane": "雷达·社区", "note": "Algolia 热帖接口"},
        {"name": "X 哨兵", "lane": "雷达·X", "note": f"{len(x_handles)} 个账号合并查询，超时硬杀 + 频控"},
        {"name": "公众号桥", "lane": "雷达·公众号", "note": f"{len(wechat)} 个核心号，硬频控防风控"},
    ]
    return {"rss": rss, "html": html, "x_handles": x_handles, "wechat": wechat, "other": other}


# ---------- 对标清单 → 我们的哪一路 ----------
# 非 X / 非公众号的条目按别名表判定（逐条人工核过，可审计）。值 = (status, lane, note)
ALIAS = {
    "IT之家（RSS）": ("connected", "雷达 RSS·IT之家", ""),
    "TechCrunch：AI（RSS）": ("connected", "雷达 RSS·TechCrunch-AI", ""),
    "MarkTechPost（RSS）": ("connected", "雷达 RSS·MarkTechPost", ""),
    "The Verge：AI（RSS）": ("connected", "雷达 RSS·TheVerge-AI", ""),
    "Ars Technica：AI（RSS）": ("connected", "雷达 RSS·ArsTechnica-AI", ""),
    "The Decoder：AI News（RSS）": ("connected", "雷达 RSS·The Decoder", ""),
    "Simon Willison 博客": ("connected", "雷达 RSS·SimonWillison", ""),
    "NVIDIA Technical Blog：Agentic AI / Generative AI": ("connected", "雷达 RSS·NVIDIA生成式AI", ""),
    "Google Blog：AI（RSS）": ("connected", "雷达 RSS·Google AI", ""),
    "OpenAI：官网动态（RSS · 排除企业/客户案例）": ("connected", "雷达 RSS·OpenAI", "客户案例清洗闸在 共用.decide_selected"),
    "Claude Code：GitHub Releases（RSS）": ("connected", "雷达 RSS·Claude Code Release", ""),
    "Google Research：Blog（网页）": ("connected", "雷达 RSS·GoogleResearch", "我们走官方 RSS，比网页差分更稳"),
    "Latent Space（RSS）": ("connected", "雷达 RSS·LatentSpace", ""),
    "Anthropic：Newsroom（网页）": ("connected", "雷达 HTML 差分·Anthropic", ""),
    "Claude：Blog（网页）": ("connected", "雷达 HTML 差分·Anthropic", "同域 news 差分覆盖；独立 claude.ai/blog 待补"),
    "HuggingFace Daily Papers（社区热门论文）": ("connected", "雷达·HF Papers API", ""),
    "Hacker News 热门（buzzing.cc 中文翻译）": ("connected", "雷达·HN 热议", "我们取英文原帖，不走中文翻译站"),
    "Hacker News：AI 热帖": ("connected", "雷达·HN 热议", ""),
    "Apple Machine Learning Research（RSS）": ("pending", "雷达 RSS（待加）", "我们只有 Apple Newsroom；机器学习研究页另有 RSS，可加"),
    "Gary Marcus：The Road to AI We Can Trust（RSS）": ("pending", "雷达 RSS（待加）", "Substack RSS 可达，评论型内容待定级"),
    "Epoch AI：研究、数据与评测": ("pending", "雷达 RSS（待加）", "epoch.ai 有 RSS，属数据/评测一手源"),
    "LangChain：Blog（RSS）": ("pending", "雷达 RSS（待加）", "blog.langchain.dev 有 RSS"),
    "LlamaIndex：产品、工程与评测": ("pending", "雷达 RSS（待加）", "官方博客有 RSS"),
    "Midjourney：Updates（RSS）": ("pending", "雷达 RSS（待加）", ""),
    "404 Media（RSS）": ("pending", "雷达 RSS（待加）", "部分内容付费墙，只收摘要"),
    "Newcomer 新闻长文（RSS）": ("pending", "雷达 RSS（待加）", "Substack，长文为主"),
    "Trail of Bits：AI安全研究": ("pending", "雷达 RSS（待加）", "blog.trailofbits.com 有 RSS"),
    "Sakana AI：Blog（网页）": ("pending", "雷达 HTML 差分（待加）", "无 RSS，需写卡片正则"),
    "Artificial Intelligence News（网页）": ("pending", "雷达 RSS（待加）", "artificialintelligence-news.com 有 RSS"),
    "elsewhere：文章（RSS）": ("pending", "雷达 RSS（待加）", "聚合站，等级待评"),
}


def classify(name):
    """对标清单一项 → (type, status, lane, note)。"""
    n = name.strip()
    m = re.search(r"@([A-Za-z0-9_]+)", n)
    if n.startswith("X：") or (m and not n.startswith("公众号")):
        handle = (m.group(1) if m else "").lower()
        return ("X", handle)
    if n.startswith("公众号："):
        return ("公众号", n.split("：", 1)[1])
    if "（网页）" in n:
        return ("网页差分", None)
    if "（RSS）" in n or "RSS" in n:
        return ("RSS", None)
    return ("其他", None)


def build_registry(inv, benchmark):
    x_set = set(inv["x_handles"])
    wechat_set = {w for w in inv["wechat"]}
    rows = []
    for name, hits in sorted(benchmark.items(), key=lambda kv: (-kv[1], kv[0])):
        typ, key = classify(name)
        if typ == "X":
            if key and key in x_set:
                status, lane, note = "connected", "雷达·X 哨兵", f"@{key} 在合并查询里"
            else:
                status, lane, note = ("pending", "雷达·X 哨兵（待加）",
                                      f"@{key} 未入合并查询；X 查询有频控与超时硬杀，按热度分批加"
                                      if key else "清单里只有昵称无 handle，待人工补 handle")
        elif typ == "公众号":
            if any(key.startswith(w) or w in key for w in wechat_set):
                status, lane, note = "connected", "雷达·公众号桥", f"核心号 {key}"
            else:
                status, lane, note = ("pending", "雷达·公众号桥（待加）",
                                      "公众号无官方 RSS，只能走搜狗桥；桥有硬频控，按号逐个加，加不上就如实留待接")
        else:
            status, lane, note = ALIAS.get(name, ("pending", "未定", "对标清单新名字，待人工归类"))
        rows.append({"name": name, "type": typ, "benchmark_hits": hits,
                     "status": status, "status_zh": STATUS[status], "lane": lane, "note": note})
    return rows


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def daily_diff():
    """复用 养分吸收器.py 的条目级日对账结果（不重跑、不重写第二套逻辑）。"""
    led = load_json(NUTRIENT_LEDGER, []) or []
    if not isinstance(led, list) or not led:
        return {"status": "pending", "note": f"暂无条目级对账记录（{NUTRIENT_LEDGER} 为空）"}
    last = led[-1]
    return {
        "status": "ok",
        "source": "ai-radar/养分吸收器.py（条目级日对账，本脚本只引用不重算）",
        "day": last.get("day"),
        "benchmark_items": last.get("aihot"),
        "our_items": last.get("ours"),
        "overlap": last.get("hit"),
        "we_missed": last.get("miss"),
        "our_exclusive": last.get("exclusive"),
        "suggest_new_domains": last.get("new_doms") or [],
        "history_days": len(led),
    }


def render_md(reg):
    c = reg["counts"]
    d = reg["diff_vs_benchmark"]
    L = [f"# 信源登记表（对标清单逐项）",
         "",
         f"> 生成 {reg['generated_at_utc']}　由 `引擎/信源对账.py` 写出，**勿手改**。",
         f"> 对标清单来源：`{reg['benchmark']['path']}`（对标站公开精选里出现过的信源名累积 {c['total']} 项）。",
         "",
         "## 一、总账",
         "",
         "| 状态 | 数 | 含义 |",
         "|---|---|---|",
         f"| 已接 | {c['connected']} | 我们已有同一路（或更一手的）通道 |",
         f"| 待接 | {c['pending']} | 技术上可接，排期加 |",
         f"| 不可接 | {c['blocked']} | 付费墙/风控/无可用接口，如实登记不硬来 |",
         "",
         "按类型：" + "　".join(f"{k} {v}" for k, v in c["by_type"].items()),
         "",
         "## 二、当日条目级差别（引用 ai-radar/养分吸收器.py，不重算）",
         ""]
    if d.get("status") == "ok":
        L += [f"- 日期：{d['day']}（历史 {d['history_days']} 天）",
              f"- 对标当日收录 {d['benchmark_items']} 条；我们当日捕获 {d['our_items']} 条",
              f"- 撞上 {d['overlap']}　我们漏网 {d['we_missed']}　我们独家 {d['our_exclusive']}",
              "- 建议补源（按漏网域名频次）：" + ("、".join(d["suggest_new_domains"]) or "无"),
              ""]
    else:
        L += [f"- {d.get('note')}", ""]
    L += ["## 三、逐项登记", "",
          "| 对标信源 | 类型 | 它出现次数 | 我们 | 接在哪一路 | 说明 |", "|---|---|---|---|---|---|"]
    for r in reg["sources"]:
        L.append(f"| {r['name']} | {r['type']} | {r['benchmark_hits']} | {r['status_zh']} | "
                 f"{r['lane']} | {r['note']} |")
    L += ["", "## 四、我们的家底（雷达源表实读）", "",
          f"- RSS {len(reg['our_inventory']['rss'])} 路：" +
          "、".join(x["name"] for x in reg["our_inventory"]["rss"]),
          f"- 网页差分 {len(reg['our_inventory']['html'])} 路：" +
          "、".join(x["name"] for x in reg["our_inventory"]["html"]),
          f"- X 哨兵 {len(reg['our_inventory']['x_handles'])} 个：@" +
          "、@".join(reg["our_inventory"]["x_handles"]),
          f"- 公众号桥 {len(reg['our_inventory']['wechat'])} 个：" +
          "、".join(reg["our_inventory"]["wechat"]),
          "- 其余通道：" + "、".join(f"{o['name']}（{o['lane']}）" for o in reg["our_inventory"]["other"]),
          ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印统计不写文件")
    args = ap.parse_args()

    benchmark = load_json(BENCHMARK, {}) or {}
    if not benchmark:
        print(f"[信源对账] 对标清单不可读或为空：{BENCHMARK}", file=sys.stderr)
        return 2
    inv = our_inventory()
    rows = build_registry(inv, benchmark)
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    counts = {"total": len(rows),
              "connected": sum(1 for r in rows if r["status"] == "connected"),
              "pending": sum(1 for r in rows if r["status"] == "pending"),
              "blocked": sum(1 for r in rows if r["status"] == "blocked"),
              "by_type": by_type}
    now = datetime.now(timezone.utc)
    reg = {
        "generated_at_utc": utc_iso(now),
        "benchmark": {"path": os.path.relpath(BENCHMARK, os.path.expanduser("~")),
                      "note": "对标站公开精选里出现过的信源名累积（只拷公开清单，不取其代码与数据）",
                      "n": len(benchmark)},
        "counts": counts,
        "diff_vs_benchmark": daily_diff(),
        "sources": rows,
        "our_inventory": inv,
    }
    print(f"[信源对账] 对标 {counts['total']} 项 → 已接 {counts['connected']} / "
          f"待接 {counts['pending']} / 不可接 {counts['blocked']}；按类型 {by_type}")
    if args.dry_run:
        return 0
    os.makedirs(REG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    write_json_atomic(REG_JSON, reg)
    with open(REG_MD, "w", encoding="utf-8") as f:
        f.write(render_md(reg))
    # 发布副本（/api/v1/sources.json 的原料）：去掉 our_inventory 里的内部路径，只留公开事实
    pub = dict(reg)
    # 硬边界：对外产物不得出现对标站品牌字样，也不带本机路径 → 发布副本只留中性描述
    pub["benchmark"] = {"name": "对标站公开精选清单（累积出现过的信源名）",
                        "note": reg["benchmark"]["note"], "n": reg["benchmark"]["n"]}
    pub["our_inventory"] = {
        "rss": [x["name"] for x in inv["rss"]],
        "html_diff": [x["name"] for x in inv["html"]],
        "x_sentinel": inv["x_handles"],
        "wechat_bridge": inv["wechat"],
        "other": [o["name"] for o in inv["other"]],
    }
    blob = json.dumps(pub, ensure_ascii=False)
    if brand_violation(blob) or "/Users/" in blob or "/Volumes/" in blob:
        print("[信源对账] 发布副本命中品牌字样或本机路径 → 拒写（内部登记表已写）", file=sys.stderr)
        return 3
    write_json_atomic(PUB_REG, pub)
    write_json_atomic(DIFF_JSON, {"generated_at_utc": reg["generated_at_utc"],
                                  "counts": counts, "diff": reg["diff_vs_benchmark"]})
    day = now.strftime("%Y-%m-%d")
    with open(os.path.join(WORK, f"信源差别-{day}.md"), "w", encoding="utf-8") as f:
        f.write(render_md(reg))
    for p in (REG_JSON, REG_MD, PUB_REG, DIFF_JSON, os.path.join(WORK, f"信源差别-{day}.md")):
        print(f"[信源对账] 写出 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
