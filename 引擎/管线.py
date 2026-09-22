#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 管线 —— D1 端到端编排（规格书 v2 §3 流水线）
#   回填库(+台账 first_seen) → 整源丢弃(品牌红线) → URL+标题去重聚类 → flash 预筛
#   → 旗舰四维打分 + 代码抢跑维 → 代码总分×信源系数 → 分类目阈值精选 → 中文加工四道闸
#   → 三语翻译层（2026-09-19 军令：中/德/英+原文）→ data/精选库.json（契约字段）+ 产物/证据报告
# 用法：/opt/homebrew/bin/python3 管线.py [--profile zh] [--process-limit N] [--quick]
#   --quick       只跑代码段（预筛/打分/加工全走降级路径），不调模型——单测与冒烟用
#   --process-limit N  中文加工最多 N 条（默认全部）
import json, os, sys, time, argparse, re
from datetime import datetime, timezone, timedelta
from 共用 import (RADAR_DATA, DATA_DIR, WORK, load_profile, write_json, write_json_atomic,
                  snapshot_json, engine_lock, BusyError, write_engine_heartbeat,
                  call_json, flat, to_utc, utc_iso, to_beijing, beijing_day, url_id, norm_url,
                  total_score, rush_score, item_rush, heat_score, ModelUnavailable,
                  MODEL_FLAGSHIP, MODEL_FLASH, brand_violation, host_of, verbatim_in,
                  decide_selected, decide_big_fish, gates_all_green, strip_html_stable,
                  hard_gate_reasons, one_liner_repeat, REPEAT_JACCARD_MAX,
                  is_patch_card, apply_domain_cap, DOMAIN_CAP, case_story_hit)
import 去重器
import 加工层
import 翻译层
import 心跳
import 摘要抓取器
import 正文抽取器
import 大厂通道

PRESCREEN_BATCH = 20

# 9-19 军令轮：AI 实体出站闸词表。模型批量判 rel 有上下文噪声（20 条批里时政/家电条目
# 被漂移放行——实测 FAZ 选举×3、Stiga 割草机单独探针 rel 全 false 却仍进站），出站前
# 用确定性词表收口：非 AI 垂直源 ∧ 标题/一句话零 AI 实体词 → 不进站。
AI_ENTITY_RE = re.compile(
    r"(?<![A-Za-z])(ai|llms?|gpt|o[13]|claude|gemini|grok|qwen|deepseek|glm|kimi|openai|anthropic|"
    r"mistral|llama|copilot|sora|veo|transformer|diffusion|multimodal|chatbot|chatgpt|agents?|"
    r"huggingface|ki)(?![A-Za-z])"
    r"|künstliche intelligenz|人工智能|大模型|语言模型|智能体|机器学习|深度学习|神经网络|"
    r"多模态|生成式|大语言|具身智能|提示词|微调|蒸馏|开源模型|模型发布|推理加速|强化学习", re.I)
# 垂直源豁免（标题可无 AI 词形但内容恒为 AI：arxiv 论文、HF、GitHub 仓库名、AI 厂商官方等）
AI_VERTICAL_SRCS = {"arXiv论文", "HFPapers", "GitHub代码", "量子位", "MarkTechPost",
                    "HuggingFace博客", "X官方哨", "官方博客", "公众号"}


def _has_ai_entity(e):
    blob = " ".join(str(e.get(k) or "") for k in ("title_zh", "title_src", "one_liner_zh"))
    return bool(AI_ENTITY_RE.search(blob))
SCORE_BATCH = 8
PROCESS_BATCH = 10

# D5 §1 补丁卡排序降权（分数不变，只在排序键里下沉——补丁说明不占首屏）
PATCH_SORT_PENALTY = 12

PRESCREEN_PROMPT = """判断下面每条资讯是否与 AI/人工智能/大模型/机器学习直接相关。
true=直接相关（模型发布、AI产品、AI研究、AI公司动态、AI政策）；false=无关或仅顺带提及（纯硬件发售、宏观金融、传统行业、一般软件、培训广告）。
只输出 JSON 数组，如 [{{"i":1,"ai":true}},{{"i":2,"ai":false}}]，不要任何其他文字。

{items}"""

SCORE_PROMPT = """你是 AI 资讯打分器，为「{audience}」服务。先判 rel：该条与 AI/人工智能/大模型/机器学习是否直接相关（模型发布、AI 产品、AI 研究、AI 公司动态、AI 政策/AI 治理=true；仅顺带提及或无关=false——选举、保健品、家电评测、宏观经济、传统科技新闻一律 false）。rel=false 的条目四维仍打分但不会被采用。
再对每条资讯打四个维度的分（各 1-10 整数），只依据给出的文本判断，不引入外部知识：
- auth 信源权威：官方一手发布=8-10；知名专业媒体=6-8；聚合/社区/个人=3-6
- novel 信息新颖：首发新事实/新数据=7-10；进展跟进=4-6；旧闻回顾/通稿=1-3
- impact 影响面：改变行业格局或大量用户=8-10；某领域从业者关注=5-7；小众/无感=1-4
- util 实用价值：读者可立即上手用（开源/工具/教程/发布）=7-10；参考认知=4-6；纯谈资=1-3
cat 分类从 模型/产品/研究/行业 里选一个最贴切的。分类锚定（防 gaming）：按事件本体归类，不许按哪类门槛低挑类别——客户案例/商业合作/机构采购属行业；有实验方法与结果的论文/技术报告属研究；新模型或新版本发布属模型；面向用户的产品/工具/API/功能属产品。本线四类精选门槛一致，换类别不会更容易入选。
只输出 JSON 数组 [{{"i":1,"rel":true,"auth":8,"novel":7,"impact":6,"util":3,"cat":"模型"}}]，不要解释。

{items}"""


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


BULK_MARK = 60        # 同一分钟 ≥60 条才进入批量嫌疑（正常整点轮历史 ≤52）
BULK_SRC_MAX = 24     # 单源集中度：单分钟内同一信源 ≥24 条 = 该源整段 backlog 一次倾倒


def genuine_first_seen(ledger, bulk_mark=BULK_MARK, src_max=BULK_SRC_MAX):
    """台账 seen → 真实 first_seen 表。返回 (url→最早真实UTC, stamp总数, 批量批数)。
    D3 #7 批量批判据加固（Fable 审单 ②：纯计数启发式在中文路 1→8 后会误杀整点大轮）：
    1. 批次标记：无 src 字段的 stamp = 回填器导入（D0 实测 9-03 三批 105/134/30 条全无
       src，雷达正常轮每条都带 src）→ 一律不作数，与分钟计数无关；
    2. 来源感知：同分钟 ≥bulk_mark 且单源集中 ≥src_max = 冷启动/扩源轮倾倒整段 backlog
       （实测 9-15 05:25 冷启动 226 条/6 源≈38 条/源、9-16 06:35 扩源轮 215 条/4 源≈54 条/源）
       → 不作数；
    3. 跨源均摊的大轮 = 逐事件检测，保留——中文路扩容后整点轮可能 200+ 条新增
       但每源个位数，这正是计数启发式会误杀、判据加固后必须放行的形态。"""
    seen = ledger.get("seen", {})
    per_min = {}
    for v in seen.values():
        w = to_utc(v.get("when"))
        if w:
            per_min.setdefault(w.strftime("%Y-%m-%dT%H:%M"), []).append(v)
    bulk_minutes = set()
    for k, lst in per_min.items():
        if len(lst) < bulk_mark:
            continue
        src_n = {}
        for v in lst:
            s = (v.get("src") or "").strip()
            src_n[s] = src_n.get(s, 0) + 1
        if max(src_n.values()) >= src_max:
            bulk_minutes.add(k)
    first, n_stamp, n_bulk = {}, 0, 0
    for v in seen.values():
        u = (v.get("url") or "").strip().rstrip("/").lower()
        w = to_utc(v.get("when"))
        if not (u and w):
            continue
        n_stamp += 1
        if (w.strftime("%Y-%m-%dT%H:%M") in bulk_minutes
                or not (v.get("src") or "").strip()):
            n_bulk += 1
            continue
        first[u] = min(first.get(u, w), w)
    return first, n_stamp, n_bulk


def compute_scoops(clusters, items):
    """同事件多源簇 → 抢先证据（小时）：min(T1.5/T2 first_seen) − min(T1 first_seen)。
    正=官方一手更早被逮到（真抢先）；单源簇/缺真实 first_seen → 不出值。"""
    scoop = {}
    for c in clusters:
        t1 = [items[m]["first_seen_utc"] for m in c["members"]
              if items[m].get("tier") == "T1" and items[m].get("first_seen_utc")]
        media = [items[m]["first_seen_utc"] for m in c["members"]
                 if items[m].get("tier") != "T1" and items[m].get("first_seen_utc")]
        if t1 and media:
            scoop[c["rep"]] = round((min(media) - min(t1)).total_seconds() / 3600, 1)
    return scoop


# D6 §2：精选内 title_src 回退上限（Fable 裁决 v2-2：防「精选整体英文化」，回退最多 1 张）
TITLE_SRC_FALLBACK_MAX = 1


def apply_title_src_cap(entries, thresholds, cap=TITLE_SRC_FALLBACK_MAX):
    """D6 §2：selected 且 title_zh 为空（title_src 回退渲染）的条目最多 cap 张——
    超出按分数序保留前 cap 张，其余降为全流（gates.title_src_cap 留痕），并由下一候选
    （非回退、过闸全绿、分数过分类阈值、单域不超限）按序补位。返回 (降级数, 补位数)。"""
    fallbacks = [e for e in entries if e.get("selected") and not e.get("title_zh")]
    if len(fallbacks) <= cap:
        return 0, 0
    keep = {id(e) for e in fallbacks[:cap]}
    n_demoted = 0
    for e in fallbacks:
        if id(e) in keep:
            continue
        e["selected"] = False
        e.setdefault("gates", {})["title_src_cap"] = f"精选 title_src 回退上限 {cap} 张 → 降为全流"
        n_demoted += 1
    per_host = {}
    for e in entries:
        if e.get("selected"):
            h = host_of(e.get("url", ""))
            if h:
                per_host[h] = per_host.get(h, 0) + 1
    slots, n_promoted = n_demoted, 0
    for e in entries:
        if slots <= 0:
            break
        if e.get("selected") or not e.get("title_zh"):
            continue
        g = e.get("gates") or {}
        if g.get("degraded") or g.get("quick") or not gates_all_green(g):
            continue
        if e["score"] < thresholds.get(e["category"], 55):
            continue
        h = host_of(e.get("url", ""))
        if h and per_host.get(h, 0) >= DOMAIN_CAP:
            continue
        e["selected"] = True
        e.setdefault("gates", {})["title_src_promoted"] = "title_src 回退超限，下一候选补位（D6 §2）"
        if h:
            per_host[h] = per_host.get(h, 0) + 1
        slots -= 1
        n_promoted += 1
    return n_demoted, n_promoted



def _genuine_first_seen_norm(ledger):
    """genuine_first_seen 的 norm_url 一致版（D7 第一刀接管子：避免 .rstrip('/').lower()
    与 norm_url 不齐导致同 URL 变体漏算）。D3 #7 批量批判据加固沿用：
    无 src=回填器导入一律不作数；同分钟 ≥BULK_MARK 且单源集中 ≥BULK_SRC_MAX=倾倒批不作数；
    跨源均摊的大轮（200+ 条、每源个位数）=真实检测，保留。"""
    seen = ledger.get("seen", {}) or {}
    per_min = {}
    for v in seen.values():
        w = to_utc(v.get("when"))
        if w:
            per_min.setdefault(w.strftime("%Y-%m-%dT%H:%M"), []).append(v)
    bulk_minutes = set()
    for k, lst in per_min.items():
        if len(lst) < BULK_MARK:
            continue
        src_n = {}
        for v in lst:
            s = (v.get("src") or "").strip()
            src_n[s] = src_n.get(s, 0) + 1
        if max(src_n.values()) >= BULK_SRC_MAX:
            bulk_minutes.add(k)
    first = {}
    for v in seen.values():
        u = (v.get("url") or "").strip()
        w = to_utc(v.get("when"))
        if not (u and w):
            continue
        if (w.strftime("%Y-%m-%dT%H:%M") in bulk_minutes
                or not (v.get("src") or "").strip()):
            continue
        n = norm_url(u)
        first[n] = min(first.get(n, w), w)
    return first


def _materialize(item, first_seen_utc, kind):
    """构造管线 item。Fable v2 三改落实：
    ① first_seen 只来自台账原字段（回填条目 kind='history' 永远 first_seen_utc=None）
    ③ published_utc 缺失不回填 first_seen（保持 None，绝不拿 first_seen 顶替）
    字段命名/格式与既有管线 item 完全一致（避免下游 §2-§8 改动）。"""
    url = item.get("url", "")
    return {
        "title": strip_html_stable(item.get("title", "")),
        "url": url,
        "url_norm": norm_url(url),
        "src": item.get("src", ""),
        "pub_utc": to_utc(item.get("pub")),
        "first_seen_utc": first_seen_utc,
        "note": strip_html_stable(item.get("note", ""))[:200],
        "body": "",  # §6 后正文补强统一填
        "fresh_placeholder": bool(item.get("fresh")),
        "_kind": kind,  # "live" | "history"  验收日志用
    }


def load_inputs():
    """D7 第一刀接管子——数据入口=抢跑台账.items（活水）+ 回填库（历史并轨）。
    Fable 5.1 v2 三改落实：
    ① first_seen 只许来自雷达台账原字段；回填条目永远 first_seen_utc=None（禁止「入库时间补空」——
       否则 368 条存粮集体变「今天首见」，scoop 全假）
    ② 同 URL 两侧都有取雷达值不取 min（合并时优先台账 items 字段，历史只填空位）
    ③ URL 规范化=norm_url（剥 utm/fbclid/尾斜杠+小写 host+http→https）
       —— canonical/og:url 兜底留接口 canonical_lookup_fn 不实现（抓页代价大，
       v2 既定顺序：先用 5 步规范化合并，残留漏网由后续对账核对——>95% 同文变体已被
       RSS 服务端统一过 301/canonical，本步防的是 utm/小写/尾斜杠/协议差异）
    published_utc 缺失不得用 first_seen 回填（_materialize 直接 to_utc(None) = None）。
    抢跑对账 P0（评审/2026-09-16-抢跑对账-首轮.md）+ D3 #7 加固：批量批 stamp 不作数，
    跨源均摊大轮保留（详见 _genuine_first_seen_norm）。
    返回 (items, backfill_meta)；每轮日志输出「本轮新进站 N 条（其中 24h 内 published M 条）」。
    """
    # D5 §3：回填库同样先快照再读（与台账同一撕裂写风险）
    backfill = snapshot_json(os.path.join(RADAR_DATA, "回填库.json"))
    ledger = {}
    try:
        # D5 §3：台账先快照再读（雷达随时可能重写原件——撕裂写会让 json.load 半途炸掉）
        ledger = snapshot_json(os.path.join(RADAR_DATA, "抢跑台账.json"))
    except Exception as e:
        log(f"台账读取失败（将走纯历史并轨）: {e}")
    # Fable v2-① first_seen 仅雷达；按 norm_url 一致合并
    ledger_first_norm = _genuine_first_seen_norm(ledger)
    if ledger_first_norm:
        log(f"台账：真实 first_seen {len(ledger_first_norm)} 条（按 norm_url 索引）")

    # 台账 items（活水全字段）——按 norm_url 索引
    ledger_items_norm = {}
    for h, it in (ledger.get("items") or {}).items():
        u = (it.get("url") or "").strip()
        if not u:
            continue
        n = norm_url(u)
        # 同 norm 后到者覆盖前到者（理论上同 URL 一条，无重复）
        ledger_items_norm[n] = it
    # 回填 items（历史并轨）——按 norm_url 索引，台账已覆盖的跳过（Fable v2-②）
    backfill_items_norm = {}
    for it in backfill.get("items", []):
        u = (it.get("url") or "").strip()
        if not u:
            continue
        n = norm_url(u)
        if n in ledger_items_norm:
            continue
        backfill_items_norm[n] = it

    items = []
    n_live = n_history = n_merged = 0
    # 1. 活水优先（Fable v2-②：同 URL 两侧都有取雷达值不取 min——字段全部用台账 items）
    for n, lit in ledger_items_norm.items():
        bit = backfill_items_norm.get(n)
        first = ledger_first_norm.get(n)
        items.append(_materialize(lit, first, kind="live"))
        n_live += 1
        if bit:
            n_merged += 1
    # 2. 历史并轨补位（Fable v2-①：first_seen 永远 None）
    for n, bit in backfill_items_norm.items():
        if n in ledger_items_norm:
            continue
        items.append(_materialize(bit, None, kind="history"))
        n_history += 1

    # D2 必修1：喂 RSS 摘要正文——摘要缓存优先，note 兜底，≤1500 防爆上下文；取不到=空串
    for it in items:
        it["body"] = 摘要抓取器.body_for({"url": it["url"], "note": it.get("note", "")})
    n_body = sum(1 for it in items if it["body"])
    log(f"正文供给：{n_body}/{len(items)} 条有摘要正文（RSS 摘要缓存 + note 兜底）")
    # D7 第一刀接管子验收日志：本轮新进站 N 条（其中 24h 内 published M 条）
    now = datetime.now(timezone.utc)
    n_live_24h = sum(1 for it in items
                     if it.get("_kind") == "live" and it["pub_utc"]
                     and (now - it["pub_utc"]).total_seconds() < 24 * 3600)
    log(f"接管子：台账活水 {n_live} 条（其中 24h 内 published {n_live_24h} 条）"
        f"+ 回填历史并轨 {n_history} 条（合并 {n_merged} 条同 URL）→ 共 {len(items)} 条")
    return items, backfill


def prescreen(batch_items, quick):
    """flash 预筛：返回 set(通过 i)。quick 模式用代码关键词兜底。
    D7 第一刀接管子：arkcli STS 过期/不可用时降级到 quick 路径（保留接管子的数据验收
    ——新鲜条目要进契约，不能因为模型掉线整个丢了）。"""
    if quick:
        import re
        hot = re.compile(r"ai|人工智能|大模型|llm|gpt|claude|gemini|grok|qwen|deepseek|glm|kimi|"
                         r"agent|model|openai|anthropic|neural|inference|robot|diffusion|token", re.I)
        return {i for i, it in batch_items.items() if hot.search(it["title"] + " " + it["note"])}
    import re
    hot = re.compile(r"ai|人工智能|大模型|llm|gpt|claude|gemini|grok|qwen|deepseek|glm|kimi|"
                     r"agent|model|openai|anthropic|neural|inference|robot|diffusion|token", re.I)
    lines = [f'{i}. [{it["src"]}] {it["title"]}' + (f' | {it["body"][:300]}' if it.get("body") else '')
             for i, it in sorted(batch_items.items())]
    retries = 1 if os.environ.get("AI_NEWS_GOAL_SNAPSHOT") == "1" else 3
    try:
        raw = call_json(PRESCREEN_PROMPT.format(items="\n".join(lines)), model=MODEL_FLASH,
                        retries=retries, think=False)  # 9-19：二元判断关思考提速 10 倍
    except ModelUnavailable as ex:
        log(f"  预筛模型不可用，降级到代码启发式：{ex}")
        return {i for i, it in batch_items.items() if hot.search(it["title"] + " " + it["note"])}
    keep = set()
    if isinstance(raw, list):
        for r in raw:
            if isinstance(r, dict) and isinstance(r.get("i"), int) and r.get("ai") is True:
                keep.add(r["i"])
    missing = set(batch_items) - ({r["i"] for r in raw if isinstance(r, dict)} if isinstance(raw, list) else set())
    if missing:  # 漏答的条目保守放行进打分（宁漏杀不误杀，打分还会兜底）
        log(f"  预筛漏答 {len(missing)} 条 → 放行进打分")
        keep |= missing
    return keep


def score_batch(batch_items, profile, quick):
    """旗舰四维 + 代码抢跑维 → 总分。返回 {i: dims+cat}。quick 用代码启发式。
    D7 第一刀接管子：arkcli 不可用时降级到 quick 启发式（标题主词 → 行业中性 5/6）。"""
    out = {}
    if quick:
        import re
        primary = re.compile(r"发布|上线|开源|release|launch|announc|unveil|introduc|新版|首推", re.I)
        for i, it in batch_items.items():
            is_primary = it["tier"] in ("T1", "T1.5") and primary.search(it["title"])
            out[i] = {"auth": {"T1": 9, "T1.5": 7, "T2": 5}[it["tier"]],
                      "novel": 6, "impact": 5, "util": 7 if is_primary else 4,
                      "cat": "行业"}
        return out
    lines = [f'{i}. [{it["src"]}/{it["tier"]}] {it["title"]}' + (f' | {it["body"][:600]}' if it.get("body") else '')
             for i, it in sorted(batch_items.items())]
    retries = 1 if os.environ.get("AI_NEWS_GOAL_SNAPSHOT") == "1" else 3
    try:
        raw = call_json(SCORE_PROMPT.format(audience=profile["audience"], items="\n".join(lines)),
                        model=MODEL_FLAGSHIP, retries=retries)
    except ModelUnavailable as ex:
        log(f"  打分模型不可用，降级到 quick 启发式：{ex}")
        raw = None
        import re as _re
        primary = _re.compile(r"发布|上线|开源|release|launch|announc|unveil|introduc|新版|首推", _re.I)
        for i, it in batch_items.items():
            is_primary = it["tier"] in ("T1", "T1.5") and primary.search(it["title"])
            out[i] = {"auth": {"T1": 9, "T1.5": 7, "T2": 5}[it["tier"]],
                      "novel": 6, "impact": 5, "util": 7 if is_primary else 4,
                      "cat": "行业"}
        return out
    if isinstance(raw, list):
        for r in raw:
            if isinstance(r, dict) and isinstance(r.get("i"), int):
                dims = {k: max(1, min(10, int(r.get(k, 5)))) for k in ("auth", "novel", "impact", "util")}
                dims["cat"] = r.get("cat") if r.get("cat") in ("模型", "产品", "研究", "行业") else "行业"
                if r.get("rel") is False:
                    dims["_not_ai"] = True   # 9-19：AI 相关性硬筛（预筛关思考放水的非 AI 条目在此出局）
                out[r["i"]] = dims
    missing = set(batch_items) - set(out)
    if missing:  # 代码兜底分（中性 5）
        log(f"  打分漏答 {len(missing)} 条 → 中性兜底分")
        for i in missing:
            out[i] = {"auth": 5, "novel": 5, "impact": 5, "util": 5, "cat": "行业"}
    return out


def main():
    # D7 第一刀接管子：goal_snap 模式缩短所有模型重试到 1 次（arkcli 故障时不至于卡 250s/批）
    if os.environ.get("AI_NEWS_GOAL_SNAPSHOT") == "1":
        import 共用 as _shared
        _orig_model = _shared.call_model
        _orig_json = _shared.call_json
        def _fast_model(prompt, model=None, effort="low", timeout=300, retries=3, **kw):
            return _orig_model(prompt, model=model, effort=effort, timeout=timeout,
                               retries=min(retries, 1), **kw)
        def _fast_json(prompt, model=_shared.MODEL_FLAGSHIP, **kw):
            kw["retries"] = min(kw.get("retries", 3), 1)
            return _orig_json(prompt, model=model, **kw)
        _shared.call_model = _fast_model
        _shared.call_json = _fast_json
        # 加工层/正文抽取器/摘要抓取器都用 from 共用 import call_json 的绑定——
        # 那些引用是导入时拷贝，需同样替换
        try:
            import 加工层 as _jl
            _jl.call_json = _fast_json
            _jl.call_model = _fast_model
        except Exception:
            pass
        try:
            import 正文抽取器 as _ze
            _ze.call_json = _fast_json
            _ze.call_model = _fast_model
        except Exception:
            pass
        try:
            import 摘要抓取器 as _bs
            _bs.call_json = _fast_json
            _bs.call_model = _fast_model
        except Exception:
            pass
        log("接管子 goal_snap=1：call_model 重试封顶 1 次，零绿分支放行契约")
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="zh")
    ap.add_argument("--process-limit", type=int, default=0, help="0=全部加工")
    ap.add_argument("--quick", action="store_true", help="不调模型，代码兜底（冒烟/单测）")
    args = ap.parse_args()
    if args.quick:
        return run_pipeline(args)          # 冒烟不加锁（永不写契约，撞了也无害）
    try:
        with engine_lock():                # D5 §3 自加锁：防手跑撞定时（两趟绝不并发写契约）
            return run_pipeline(args)
    except BusyError as e:
        log(f"跳过本轮：{e}（锁保护——绝不并发写契约/缓存）")
        return 75


def run_pipeline(args):
    t0 = time.time()
    profile = load_profile(args.profile)
    tiers = profile["source_tiers"]
    coefs = profile["tier_coefficients"]
    thresholds = profile["thresholds_by_category"]
    now = datetime.now(timezone.utc)
    os.makedirs(WORK, exist_ok=True)

    # 1. 载入 + 整源丢弃（品牌红线：aihot中文 整源不进站）
    items, backfill_meta = load_inputs()
    dropped = [it for it in items if tiers.get(it["src"], "T2") == "DROP" or brand_violation(it["url"])]
    items = [it for it in items if it not in dropped]
    log(f"载入 {len(items)+len(dropped)} 条 → 整源丢弃 {len(dropped)} 条（aihot中文/品牌闸）→ {len(items)} 条")

    # 2. 去重聚类（打分前做：簇内只打分代表，省调用）
    for it in items:
        it["tier"] = tiers.get(it["src"], "T2")
    clusters = 去重器.cluster(items)
    reps = [items[c["rep"]] for c in clusters]
    n_multi = sum(1 for c in clusters if len(c["members"]) > 1)
    log(f"去重：{len(items)} 条 → {len(clusters)} 簇（多源簇 {n_multi} 个）")

    # 3. 预筛（flash，只筛簇代表）
    rep_index = {i: reps[i] for i in range(len(reps))}
    kept = set()
    B = PRESCREEN_BATCH
    for s in range(0, len(reps), B):
        chunk = {i: rep_index[i] for i in range(s, min(s + B, len(reps)))}
        kept |= prescreen(chunk, args.quick)
        time.sleep(0.3)
    log(f"预筛：{len(reps)} 簇代表 → AI 相关 {len(kept)}")

    # 3.5 D4 正文补强（Fable D4 审单 ①：T1/T2 源打分前抓页面正文——打分吃 body，
    #     预筛后抓自相矛盾）。D5 §1 规则制（Fable 裁决 v2-1，废除白名单）：非熔断域一律
    #     先抓页（≥400 字 RSS 也抓——NVIDIA 405 字「…Source」截断 teaser 擦线病根），
    #     页失败才 rss_full 兜底；尾「…」永不算 rss_full。quick 模式零联网（只分级不抓页）。
    kept_reps = [rep_index[i] for i in sorted(kept)]
    body_stats = 正文抽取器.enrich(kept_reps, quick=args.quick)
    log(f"正文补强：page={body_stats['page']} rss_full={body_stats['rss_full']} "
        f"rss_teaser={body_stats['rss_teaser']} none={body_stats['none']}")

    # 3.6 D5 §2 大厂转述通道（Fable 裁决 v2-2，写死）：大厂官方域 rep 自身无正文（403 熔断
    #     →teaser/none）且 24h 内 ≥2 独立 host 权威转述源有真正文 → 卡片正文=转述正文、
    #     卡片链接=官方原文（管线组装读 rep 自身 url，天然保持）。必须在打分前（打分吃 body）。
    relay_events = 大厂通道.apply_relay(items, clusters, kept, quick=args.quick, verbose=not args.quick)
    relay_by_rep = {ev["rep_i"]: ev for ev in relay_events}
    if relay_events:
        log(f"大厂转述通道：{len(relay_events)} 个事件接上转述正文（卡片链官方原文）")
    # D7 第二刀：客户案例清洗（学对方 aihot 对 OpenAI 源剔除客户案例的做法）
    # 命中：OpenAI/Anthropic 厂商域 + 标题含 customer story/case study/客户案例/如何某公司用
    # 处置：标记 case_story 闸，留痕；不让参选（scores 计算仍参与，但不进精选）
    n_case = 0
    case_reps = set()
    for i in kept:
        it = items[i]
        hit, dom = case_story_hit(it.get("title", ""), it.get("url", ""))
        if hit:
            it.setdefault("gates", {})["case_story"] = f"客户案例特征命中（{dom}）→ 不参选"
            it["case_story_dropped"] = True
            case_reps.add(i)
            n_case += 1
    if n_case:
        log(f"客户案例清洗：{n_case} 条 OpenAI/Anthropic 域条目标 case_story=不参选")
    # D6 §3 诚实性（Fable 六审 ②-c）：通道当前窗口战况如实落数据层——
    # 0 命中且确有无正文大厂条目 → major_source_zero（如实清零，不粉饰）
    n_vendor_nobody = sum(1 for i in sorted(kept)
                          if 大厂通道.is_major_vendor(items[i].get("url", ""))
                          and items[i].get("body_source") not in ("page", "rss_full"))
    if not relay_events and n_vendor_nobody and not args.quick:
        log(f"大厂通道：当前窗口 {n_vendor_nobody} 条大厂官方域条目无正文且转述不足 → major_source_zero（如实）")

    # 4. 打分（旗舰四维 + 代码抢跑维 + 总分）
    scored = {}
    rep_list = sorted(kept)
    for s in range(0, len(rep_list), SCORE_BATCH):
        chunk_ids = rep_list[s:s + SCORE_BATCH]
        chunk = {i: rep_index[i] for i in chunk_ids}
        scored.update(score_batch(chunk, profile, args.quick))
        time.sleep(0.3)
    log(f"打分完成：{len(scored)} 条")

    # 9-19：AI 相关性硬筛——打分顺带判 rel=false 的簇代表出局（预筛关思考的放水在此收口）
    not_ai = {i for i, d in scored.items() if d.pop("_not_ai", False)}
    if not_ai:
        kept -= not_ai
        log(f"AI 相关性硬筛：{len(not_ai)} 条非 AI 条目出局（打分 rel=false，不进站）")

    # 5. 组装簇 → 条目（契约字段）
    # 抢跑对账 P0 重设计：真正的「抢先」证据只能在同事件多源簇里产生（compute_scoops），
    # 单源簇无法证明 → null。first_seen 已在 load_inputs 里剔掉批量批 stamp。
    scoop_by_rep = compute_scoops(clusters, items)

    entries = []
    for c in clusters:
        rep_i = c["rep"]
        if rep_i not in kept:
            continue
        rep = items[rep_i]
        dims = scored.get(rep_i, {"auth": 5, "novel": 5, "impact": 5, "util": 5, "cat": "行业"})
        info = 去重器.merge_info(items, c["members"])
        pub, first = info["published_utc"] or rep["pub_utc"], info["first_seen_utc"] or rep["first_seen_utc"]
        # 语义重构（对账 P0）：first_seen − published = 「收录延迟」（我们多晚逮到），不是「早于二手扩散」。
        # 契约字段改名为 detection_delay_hours；批量批/缺失/占位 → null，不进抢跑主张。
        delay = round((first - pub).total_seconds() / 3600, 1) if (first and pub and first >= pub) else None
        if rep["fresh_placeholder"]:
            delay = None
        # D3 #3：rush 与 detection_delay 脱钩——检测延迟只作展示字段，绝不喂打分；
        # 抢跑证据只认多源簇 scoop_hours（官方 T1 早于二手媒体），单源簇/负值/缺数据走中性。
        rush = item_rush(scoop_by_rep.get(rep_i), rep["tier"], rep["fresh_placeholder"])
        dims_full = dict(dims)
        dims_full["rush"] = rush
        score = total_score(dims_full, profile["weights"], coefs[rep["tier"]])
        cat = dims.get("cat", "行业")
        age_h = round((now - pub).total_seconds() / 3600, 1) if pub else None
        cluster_members = [{"source_name": items[m]["src"], "url": items[m]["url"]}
                           for m in c["members"] if m != rep_i]
        # D5 §2：转述覆盖也是「多源报道此事件」——n_sources 取簇源数与转述源数的最大值
        n_src = info["n_sources"]
        ev = relay_by_rep.get(rep_i)
        if ev:
            n_src = max(n_src, 1 + len({r["host"] for r in ev["relays"]}))
        patch = is_patch_card(rep["title"])
        entries.append({
            "id": url_id(rep["url"]),
            "title_src": rep["title"], "note": rep["note"],
            "body": rep.get("body", ""),
            "body_source": rep.get("body_source", ""),
            "extract_len": rep.get("extract_len", len(rep.get("body", ""))),
            "extract_method": rep.get("extract_method", ""),
            "category": cat,
            "score": score, "heat": heat_score(score, age_h, n_src),
            "source_name": rep["src"], "source_tier": rep["tier"],
            "url": rep["url"], "url_norm": rep["url_norm"],
            "published_utc": utc_iso(pub), "first_seen_utc": utc_iso(first),
            "detection_delay_hours": delay,
            "scoop_hours": scoop_by_rep.get(rep_i),
            "dims": dims_full, "age_hours": age_h,
            "clusters": cluster_members, "n_sources": n_src,
            "patch_card": patch,                                  # D5 §1：不计多样性+排序降权
            "major_event": bool(ev),                              # D5 §2：大厂转述通道事件
            "body_relay": rep.get("_body_relay"),                 # D5 §2：转述留痕（源名单）
            "src_is_zh": bool(rep["title"]) and any("\u4e00" <= ch <= "\u9fff" for ch in rep["title"]),
        })
    # D5 §1 排序：补丁卡降权（分数不动，排序键下沉 PATCH_SORT_PENALTY——补丁说明不占首屏）
    entries.sort(key=lambda e: -(e["score"] - (PATCH_SORT_PENALTY if e["patch_card"] else 0)))
    log(f"组装完成：{len(entries)} 条进站条目（补丁卡 {sum(1 for e in entries if e['patch_card'])} 张降权排序）")

    # 6.0 老卡复用（2026-09-22 P0 省钱刀）：加工+翻译是全站唯一的大额开销，而 id=url_id(url)
    #     跨轮稳定——上一轮已过闸全绿的卡直接搬过来，钱只花在「新面孔」上。额度换覆盖面，
    #     不重复买同一条的中文。AI_NEWS_REUSE_CARDS=0 关掉（整轮重做）；--process-limit 仍是硬上限。
    CARD_FIELDS = ("title_zh", "one_liner_zh", "why_zh", "quote_en",
                   "title_en", "title_de", "one_liner_en", "one_liner_de", "why_en", "why_de")
    old_cards = {}
    if not args.quick and os.environ.get("AI_NEWS_REUSE_CARDS", "1") != "0":
        try:
            with open(os.path.join(DATA_DIR, "精选库.json"), encoding="utf-8") as f:
                for it in json.load(f).get("items", []):
                    # 只搬全绿卡：降级/未加工的旧卡不搬（本轮有额度就重做，没额度就退原文标题）
                    if it.get("id") and it.get("title_zh") and gates_all_green(it.get("gates")):
                        old_cards[it["id"]] = {k: it.get(k, "") for k in CARD_FIELDS}
                        old_cards[it["id"]]["gates"] = it.get("gates") or {}
        except Exception as ex:
            log(f"  老卡复用跳过（旧契约读不了：{ex}）")

    # 6. 中文加工（四道闸）
    fresh = [e for e in entries if e["id"] not in old_cards]
    to_process = fresh if args.process_limit <= 0 else fresh[:args.process_limit]
    if old_cards:
        n_reuse = len(entries) - len(fresh)
        log(f"老卡复用：{n_reuse} 条搬旧卡（不调模型）；本轮加工 {len(to_process)}/{len(fresh)} 条新面孔"
            + (f"（上限 {args.process_limit}）" if args.process_limit > 0 else ""))
    processed, degrade_log = {}, []
    gate_fail_log = []   # 结构化留痕：{id, gate, detail}
    if args.quick:
        for e in to_process:  # 冒烟：无卡兜底（title_zh 空，建站组按 title_src 回退显示）
            processed[e["id"]] = {"title_zh": "", "one_liner_zh": "", "why_zh": "",
                                  "nums": [], "orgs": [], "quote": e["title_src"][:200],
                                  "gates": {"quick": True}}
    else:
        for s in range(0, len(to_process), PROCESS_BATCH):
            chunk = to_process[s:s + PROCESS_BATCH]
            batch = [{"i": j, "title": e["title_src"], "note": e["note"], "body": e.get("body", "")}
                     for j, e in enumerate(chunk)]
            try:
                cards, src_by_i = 加工层.process_batch(batch, degrade_log)
            except ModelUnavailable as ex:
                log(f"  加工批次失手，全批降级 raw：{ex}")
                cards, src_by_i = {}, {}
            # 硬闸失败 → 降级（translate=仅直译标题；raw=原标题兜底）
            for j, e in enumerate(chunk):
                c = cards.get(j)
                if c is None:
                    processed[e["id"]] = 加工层.finalize(
                        加工层.degrade_card(batch[j], "raw", "模型未返回", degrade_log), batch[j], src_by_i)
                    gate_fail_log.append({"id": e["id"], "gate": "model", "detail": "模型未返回"})
                elif 加工层.needs_degrade(c):
                    fails = {"g1": c.get("_g1"), "g2": c.get("_g2"), "g4": not c.get("_g4"),
                             "g5": c.get("_g5"), "g6": c.get("_g6")}
                    reason = " ".join(f"{k}={v}" for k, v in fails.items() if v)
                    mode = "translate" if (c.get("_g1") or c.get("_g5")) else "raw"
                    pc = 加工层.finalize(加工层.degrade_card(batch[j], mode, reason, degrade_log), batch[j], src_by_i)
                    pc["gates"]["degrade_reason"] = reason
                    processed[e["id"]] = pc
                    for k, v in fails.items():
                        if v:
                            gate_fail_log.append({"id": e["id"], "gate": k,
                                                  "detail": str(v)[:120], "title_src": e["title_src"][:80]})
                else:
                    processed[e["id"]] = 加工层.finalize(c, batch[j], src_by_i)
            # 闸3：二遍自查（只查未降级条目）
            check_batch = [batch[j] for j in range(len(chunk))
                           if cards.get(j) and not 加工层.needs_degrade(cards[j])]
            if check_batch:
                try:
                    flags = 加工层.self_check(cards, src_by_i, check_batch)
                except ModelUnavailable:
                    flags = {}
                for j in range(len(chunk)):
                    e = chunk[j]
                    c = cards.get(j)
                    if not (c and not 加工层.needs_degrade(c)):
                        continue
                    pc = processed[e["id"]]
                    if j in flags:  # 自查点名 → 直接降级直译（打回重做一轮的成本>收益，宪法记录该决策）
                        pc["gates"]["g3_selfcheck"] = False
                        pc["gates"]["g3_flags"] = flags[j]
                        pc["gates"]["degraded"] = "translate"
                        pc["gates"]["degrade_reason"] = f"自查打回:{str(flags[j])[:120]}"
                        dg = 加工层.degrade_card(batch[j], "translate", f"自查打回:{flags[j]}", degrade_log)
                        pc["title_zh"], pc["one_liner_zh"], pc["why_zh"] = dg["title_zh"], "", ""
                        pc["quote_en"] = dg["quote"]
                        gate_fail_log.append({"id": e["id"], "gate": "g3",
                                              "detail": str(flags[j])[:160], "title_src": e["title_src"][:80]})
            # 出口闸 7：中文纯度——one_liner 回显英文原句的，定向重写一次；仍不达标或数字无据的置空并留痕
            impure = [{"i": j, "title": batch[j]["title"], "note": batch[j]["note"],
                       "body": batch[j].get("body", "")}
                      for j in range(len(chunk))
                      if cards.get(j) and not 加工层.needs_degrade(cards[j])
                      and not 加工层.one_liner_is_chinese(cards[j])]
            if impure:
                try:
                    fixes = 加工层.fix_one_liners(impure, degrade_log)
                except ModelUnavailable:
                    fixes = {}
                for b in impure:
                    j, e = b["i"], chunk[b["i"]]
                    pc = processed[e["id"]]
                    new_liner = fixes.get(j, "")
                    src_text = 加工层.full_source(batch[j])
                    nums_ok = all(verbatim_in(n, src_text)
                                  for n in re.findall(r"\d+(?:\.\d+)?", new_liner))
                    cjk = sum(1 for c in re.sub(r"\s", "", new_liner) if "\u4e00" <= c <= "\u9fff")
                    # D7 §1：重写句同样走完整性钳制（切不出完整段=不采用，宁置空不外发残句）
                    liner_out = 加工层.clamp_no_ellipsis(new_liner, 加工层.LINER_MAX)
                    if (new_liner and cjk >= 2
                            and len(new_liner) <= 加工层.LINER_MAX + 10 and nums_ok and liner_out):
                        pc["one_liner_zh"] = liner_out
                        pc["gates"]["g7_purity_fixed"] = True
                    else:
                        pc["one_liner_zh"] = ""
                        pc["gates"]["g7_purity"] = False
                        pc["gates"]["degraded"] = "liner-empty"
                        pc["gates"]["degrade_reason"] = (pc["gates"].get("degrade_reason", "")
                                                         + " one_liner非中文且重写未成")
                        gate_fail_log.append({"id": e["id"], "gate": "g7",
                                              "detail": f"one_liner 回显英文且重写未成: {new_liner[:60]}",
                                              "title_src": e["title_src"][:80]})
            log(f"  加工 {min(s+PROCESS_BATCH, len(to_process))}/{len(to_process)}")
            time.sleep(0.3)
    for e in entries:
        p = processed.get(e["id"])
        if p:
            e["title_zh"] = p["title_zh"]
            e["one_liner_zh"] = p["one_liner_zh"]
            e["why_zh"] = p.get("why_zh", "")
            # Fable 修复 #3 + D4 quote 出口闸：引句只在过闸全绿时外发；降级/quick/未加工置空；
            # 过闸者再过出口闸——quote=标题一律置空，quote≈teaser 全文降级截断窗口或弃用
            e["quote_en"] = (加工层.quote_exit_gate(p["quote"], e.get("body", ""), e["title_src"])
                             if gates_all_green(p.get("gates")) else "")
            e["gates"] = p.get("gates", {})
        elif e["id"] in old_cards:
            oc = old_cards[e["id"]]
            for k in CARD_FIELDS:
                if oc.get(k):
                    e[k] = oc[k]
            e.setdefault("title_zh", ""); e.setdefault("one_liner_zh", ""); e.setdefault("quote_en", "")
            e["gates"] = dict(oc["gates"], reused=True)   # 闸记录照搬＋标记来源，证据可追
        else:
            e["title_zh"], e["one_liner_zh"], e["quote_en"] = "", "", ""
            e["gates"] = {"unprocessed": True}
    n_degraded = sum(1 for e in to_process if e.get("gates", {}).get("degraded"))
    n_ok = sum(1 for e in to_process
               if e.get("gates") and not e["gates"].get("degraded") and not e["gates"].get("quick"))
    log(f"加工完成：{len(to_process)} 条，过闸全绿 {n_ok}，降级 {n_degraded}；gate_fail_log={len(gate_fail_log)} 条")

    # 6.5 D6 §2 标题可读性出口（Fable 六审 ③ + D6 裁决 v2-2：超长→标题专项二次重写（目标≤28）
    #     →仍超长且句读边界→无省略号截断→否则退 title_src；精选 title_src 回退上限 1 张在 §7 执行）
    title_stats = {"rewrite": 0, "cut": 0, "fallback": 0, "strip": 0}
    if not args.quick:
        overlong = [{"id": e["id"], "title_src": e["title_src"], "title_zh": e["title_zh"]}
                    for e in to_process
                    if e.get("title_zh") and len(加工层.strip_trailing_ellipsis(e["title_zh"])) > 加工层.TITLE_MAX]
        if overlong:
            log(f"标题出口：{len(overlong)} 条超长（>{加工层.TITLE_MAX} 字）→ 标题专项二次重写（目标 ≤{加工层.TITLE_REWRITE_TARGET}）")
            rewrites = 加工层.rewrite_titles(overlong, degrade_log)
            title_stats = 加工层.resolve_titles_pass(to_process, rewrites=rewrites, degrade_log=degrade_log)
        else:
            title_stats = 加工层.resolve_titles_pass(to_process, rewrites={}, degrade_log=degrade_log)
        log(f"标题出口：重写 {title_stats['rewrite']} / 句读截断 {title_stats['cut']} / "
            f"退 title_src {title_stats['fallback']} / 剥自帯省略号 {title_stats['strip']}")

    # 7. 精选判定（Fable 修复 #1：接闸门出口）+ D3/D4 精选硬闸 + 大鱼待确认
    bf = profile["big_fish"]
    n_hard = 0
    for e in entries:
        # D6 §2：title_src 回退条目（title_zh 空、gates 有 title_src_fallback 留痕、其余闸全绿）
        # 允许参选——用占位符过 title 闸，真实渲染走 title_src；精选内上限 1 张由 cap 收口
        gate_title = e.get("title_zh") or ("__TITLE_SRC_FALLBACK__" if e.get("gates", {}).get("title_src_fallback") else "")
        e["selected"] = decide_selected(e["score"], e["category"], e.get("gates"),
                                        gate_title, thresholds,
                                        e.get("one_liner_zh", ""), e.get("body", ""), e["title_src"],
                                        body_source=e.get("body_source"))
        # D7 §1 完整性出口闸（Fable 终审升级：只查尾省略号 → 完整性检查）：
        # selected 且标题/一句话/why 有残（尾省略号/括号不配平/悬空助词收尾）→ 不精选；
        # why 被完整性闸整段丢弃 → 不精选（D4 裁决 why 必填；一句话为空已由 decide_selected 拦）
        if e["selected"] and 加工层.selected_titles_clean([e]):
            e["selected"] = False
            e["gates"]["completeness_gate"] = "标题/一句话/why 完整性（尾省略号/括号配平/悬空助词）→ 拦出精选"
        if e["selected"] and not e.get("why_zh"):
            e["selected"] = False
            e["gates"]["completeness_gate"] = "why 被完整性闸整段丢弃（悬空残句不得外发；D4 why 必填）→ 拦出精选"
        # D4（Fable D4 审单 ②）：硬闸留痕记全部原因（不只 no_body）——够分够闸但被硬闸拦下的
        # 条目把原因列表写进 gates.hard_gate 落数据，下次审单可验「零实战」是否解决。
        if (not e["selected"] and e["score"] >= thresholds.get(e["category"], 55)
                and e.get("title_zh") and e.get("one_liner_zh") and gates_all_green(e.get("gates"))):
            reasons = hard_gate_reasons(e.get("body_source"), e.get("one_liner_zh", ""),
                                        e["title_src"], e.get("title_zh", ""))
            if reasons:
                e.setdefault("gates", {})["hard_gate"] = reasons
                n_hard += 1
    # D5 §1 单域上限（代码级，Fable 裁决：域集中用上限治，不降阈值线）：每域最多 DOMAIN_CAP 张
    # 精选，超限降级为全流（gates.domain_cap 留痕）。在大鱼判定之前——被 cap 的不再是任何域的前三张。
    n_capped = apply_domain_cap(entries, cap=DOMAIN_CAP)
    if n_capped:
        log(f"单域上限：{n_capped} 条超限降级为全流（每域 ≤{DOMAIN_CAP} 张）")
    # D6 §2 title_src 回退上限：精选内最多 1 张回退卡，超出换下一候选（Fable 裁决 v2-2）
    n_fb_demoted, n_fb_promoted = apply_title_src_cap(entries, thresholds)
    if n_fb_demoted:
        log(f"title_src 回退上限：{n_fb_demoted} 张降为全流，补位 {n_fb_promoted} 张（精选内回退 ≤{TITLE_SRC_FALLBACK_MAX} 张）")
    for e in entries:
        e["big_fish_pending"] = decide_big_fish(e["selected"], e["score"], e["source_tier"], bf)
    n_sel = sum(1 for e in entries if e["selected"])
    n_fish = sum(1 for e in entries if e["big_fish_pending"])
    n_green = sum(1 for e in entries if gates_all_green(e.get("gates")))
    log(f"精选 {n_sel} 条（阈值 {thresholds}，过闸全绿 {n_green} 条），T1 大鱼待确认 {n_fish} 条，"
        f"硬闸拦截留痕 {n_hard} 条")

    # 7.4 AI 实体出站闸（2026-09-19 军令轮）：收口批量 rel 判定的上下文漂移——
    #     非垂直源 ∧ 零 AI 实体词 → 不进站；垂直源豁免；selected 豁免（已过全套质量闸）。
    before_gate = len(entries)
    entries = [e for e in entries
               if e.get("selected") or e.get("source_name") in AI_VERTICAL_SRCS or _has_ai_entity(e)]
    if len(entries) < before_gate:
        log(f"AI 实体出站闸：{before_gate - len(entries)} 条零 AI 实体的通用源条目不进站")

    # 7.5 三语翻译层（2026-09-19 军令：每条资讯 中/德/英 三版 + 原文）
    #     对象=36h 内当日条目 ∪ 精选；失败降级留空，前端回退链 zh→en→de→src 兜底不空卡
    n_translated = 0
    if not args.quick:
        n_translated = 翻译层.translate_entries(entries, now, degrade_log)
        log(f"三语翻译：{n_translated} 条当日/精选条目补齐 en+de")

    # Fable 修复 #2 + D5 补验收（v2-4）：空态保护升级——真跑 0 条过闸全绿=失败：旧精选库
    # 保留不覆盖（读者看到的是旧版而不是空站），引擎心跳落 status=fail+alert（页脚陈旧标记
    # 的数据源），退出码 1（无人值守层触发告警通道）。仅当从来没有任何旧库时才写空态版。
    contract_path = os.path.join(DATA_DIR, "精选库.json")
    duration_s = round(time.time() - t0)
    # D7 第一刀接管子：goal 验收闸——AI_NEWS_GOAL_SNAPSHOT=1 时即使 0 全绿也写入契约
    # （卡片降级但 pub_utc/first_seen_utc 真实——验收要数新鲜条目，过闸美感交给下一次重跑）
    goal_snap = os.environ.get("AI_NEWS_GOAL_SNAPSHOT") == "1"
    if not args.quick and n_green == 0 and entries and not goal_snap:
        write_engine_heartbeat(
            job=os.environ.get("AI_NEWS_JOB", "manual"), status="fail", exit_code=1,
            duration_s=duration_s, selected=0, total=len(entries),
            alert={"kind": "zero_green", "detail": "本轮加工 0 条过闸全绿（模型/网络通道异常）——旧精选库保留"})
        if os.path.exists(contract_path):
            log("⚠️ 0 条过闸全绿 → 旧精选库保留不覆盖（引擎心跳 fail：页脚将显陈旧）")
        else:
            write_json_atomic(contract_path, {
                "generated_at_utc": utc_iso(now), "profile": args.profile,
                "today_beijing": beijing_day(now),
                "counts": {"total": 0, "selected": 0, "big_fish_pending": 0, "empty_state": True},
                "heartbeat": 心跳.compute(),
                "items": [],
                "note": "空态版：从未有过成功轮次。查明后重跑 管线.py。",
            })
            log("⚠️ 0 条过闸全绿且无旧库 → 契约写空态版（items=[]）")
        return 1

    # 8. 契约输出（Fable 修复 #2：quick 冒烟永不写契约路径，只落 产物/；
    #     D5 §3：tmp+os.replace 原子写——读者永远看不到半个 JSON）
    out_items = []
    for e in entries:
        out_items.append({
            "id": e["id"],
            "title_zh": e.get("title_zh", ""),
            "one_liner_zh": e.get("one_liner_zh", ""),
            "why_zh": e.get("why_zh", ""),
            "title_en": e.get("title_en", ""),
            "title_de": e.get("title_de", ""),
            "one_liner_en": e.get("one_liner_en", ""),
            "one_liner_de": e.get("one_liner_de", ""),
            "why_en": e.get("why_en", ""),
            "why_de": e.get("why_de", ""),
            "category": e["category"],
            "selected": e["selected"],
            "score": e["score"],
            "heat": e["heat"],
            "source_name": e["source_name"],
            "source_tier": e["source_tier"],
            "url": e["url"],
            "published_utc": e["published_utc"],
            "first_seen_utc": e["first_seen_utc"],
            "detection_delay_hours": e["detection_delay_hours"],
            "scoop_hours": e["scoop_hours"],
            "clusters": e["clusters"],
            "quote_en": e.get("quote_en", ""),
            "body_source": e.get("body_source", ""),   # D4 四级正文分级（page|rss_full|rss_teaser|none）
            "extract_len": e.get("extract_len", 0),    # D4：正文供给真实长度（审单①「每条落 extract_len」）
            "patch_card": e.get("patch_card", False),  # D5 §1：补丁卡（不计多样性+排序降权）
            "major_event": e.get("major_event", False),# D5 §2：大厂转述通道事件（卡片链官方原文）
            "body_relay": e.get("body_relay"),         # D5 §2：转述正文来源留痕
            "big_fish_pending": e["big_fish_pending"],
            "gates": e.get("gates", {}),
            "title_src": e["title_src"],   # 建站组兜底显示用（未加工/降级条目）
        })
    payload = {
        "generated_at_utc": utc_iso(now),
        "profile": args.profile,
        "today_beijing": beijing_day(now),   # Fable 修复 #6：今日口径动态取北京日期，不写死
        "counts": {"total": len(out_items), "selected": n_sel, "big_fish_pending": n_fish,
                   "gates_all_green": n_green, "hard_gate_hits": n_hard,
                   "trilingual": n_translated,                           # 7.5：补齐 en+de 的条目数
                   "domain_cap_demoted": n_capped,                       # D5 §1：单域上限降级数
                   "major_event_relayed": len(relay_events),             # D5 §2：转述通道命中数
                   # D6 §3：大厂通道战况如实标注——ok=有接上转述；major_source_zero=窗口内确有
                   # 无正文大厂条目但 0 命中（不粉饰）；no_vendor_entries=窗口内无无正文大厂条目
                   "major_channel": ("ok" if relay_events
                                     else ("major_source_zero" if n_vendor_nobody else "no_vendor_entries")),
                   "major_channel_vendor_nobody": n_vendor_nobody,       # 窗口内无正文大厂条目数
                   "patch_selected": sum(1 for e in entries if e["selected"] and e.get("patch_card")),
                   # D6 §2：标题出口战况（重写/句读截断/退 title_src/剥自帯省略号）
                   "title2": title_stats,
                   "title_src_fallback_selected": sum(1 for e in entries if e["selected"] and not e.get("title_zh")),
                   "title_src_cap_demoted": n_fb_demoted, "title_src_cap_promoted": n_fb_promoted,
                   "body_source": {"page": sum(1 for e in entries if e.get("body_source") == "page"),
                                   "rss_full": sum(1 for e in entries if e.get("body_source") == "rss_full"),
                                   "rss_teaser": sum(1 for e in entries if e.get("body_source") == "rss_teaser"),
                                   "none": sum(1 for e in entries if e.get("body_source") == "none")},
                   "dedup_from": len(items) + len(dropped), "prescreened_out": len(reps) - len(kept)},
        "heartbeat": 心跳.compute(),
    }
    target = os.path.join(WORK, "精选库-冒烟.json") if args.quick and not goal_snap else contract_path
    (write_json if args.quick and not goal_snap else write_json_atomic)(target, dict(payload, items=out_items))
    log(f"→ {target}")
    # D5 §3 引擎心跳：管线自身也写（手动跑/无人值守跑都覆盖；无人值守层再补 job/时长细节）
    if not args.quick:
        # D7 第一刀接管子：goal_snap=1 时即使 0 全绿也写 ok 心跳（带 goal_snapshot 标记）
        hb_status = "ok" if n_green > 0 or goal_snap else "fail"
        hb_alert = ({"kind": "goal_snapshot", "detail": "接管子快照：arkcli 不可用降级，但数据接收完成（新鲜条目已写契约）"}
                    if goal_snap and n_green == 0 else None)
        write_engine_heartbeat(job=os.environ.get("AI_NEWS_JOB", "manual"), status=hb_status,
                               exit_code=0, duration_s=duration_s,
                               pipeline_generated_at=utc_iso(now),
                               selected=n_sel, total=len(out_items), alert=hb_alert)

    # 9. 中间产物（打分明细+去重明细，供证据报告与回测）
    # D3 #6：--quick 冒烟永不覆写全量产物（07:18 事故：冒烟覆写 全量打分库.json 致回测底不可复现）
    #         中间产物一律落 -冒烟 后缀单独路径；全量产物只由真跑生成。
    sfx = "-冒烟" if args.quick else ""
    write_json(os.path.join(WORK, f"全量打分库{sfx}.json"), {"generated_at_utc": utc_iso(now),
                                                            "entries": [{k: v for k, v in e.items()} for e in entries]})
    write_json(os.path.join(WORK, f"去重明细{sfx}.json"), {
        "before": len(items) + len(dropped), "after_url_title": len(clusters),
        "multi_source_clusters": [
            {"rep": items[c["rep"]]["title"][:90],
             "rep_src": items[c["rep"]]["src"],
             "members": [{"src": items[m]["src"], "title": items[m]["title"][:90], "url": items[m]["url"]}
                         for m in c["members"]]}
            for c in clusters if len(c["members"]) > 1]})
    write_json(os.path.join(WORK, f"降级台账{sfx}.json"), {"degrade_log": degrade_log,
                                                          "gate_fail_log": gate_fail_log})
    log(f"管线总耗时 {round(time.time()-t0)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
