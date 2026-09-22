#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 大厂通道 —— D5 §2：大厂官方域被反爬熔断时的权威转述通道（Fable D5 裁决 v2-2，写死）
#
#   病根（D4 五审 ④）：openai.com 整域 403 → RSS 只有一句 teaser（128-156 字）→ body_source
#   = rss_teaser → 分级硬闸全拦 → 「GPT-6 发布日首页无 OpenAI」结构性清零。同域 RSS 大概率
#   同吃 403，「触发页面抽取」是绕回原路——真通道只有一条：
#
#   **权威转述源正文 + 卡片链官方原文**：
#   大厂官方域条目自身无正文（teaser/none）时，若 24h 内有 ≥2 个独立 host 的权威转述源
#   （T1/T1.5）拿到真正文，则卡片正文=最优转述正文（body_source 继承转述源的 page/rss_full），
#   卡片链接=官方原文 URL，major_event=true + body_relay 留痕（转述源名单落卡）。
#
#   关联器（relay_match）：与去重器（Jaccard ≥0.6，宁漏勿误杀的合并阈值）分离——跨语言标题
#   （官方英文题 vs 量子位中文题）J 只有 0.17，靠合并阈值永远关联不上，这正是 D4 结构性清零
#   的第二层病根。本关联器走英文 token 交集（产品名在中文标题里保留拉丁原文），判据：
#   共享特色 token ≥2（去常见词与厂商名）且（J≥0.30 或 含数字 token 如 gpt-6/3.8）。
#   实测台账校准：GPT-6 发布日（09-04）openai.com 条目 ↔ ARC/x.com/marktechpost 转述全部命中；
#   「Qwen3.8-Flash-Next ↔ Qwen3-Coder」类假关联被 J 门槛正确拒绝。
#
# 用法（管线在 预筛→enrich 之后、打分之前调用）：
#   events = 大厂通道.apply_relay(items, clusters, kept_rep_indexes, quick=False)
import re
from 共用 import (host_of, tokens_en, flat, BODY_SOURCE_PASS)
import 正文抽取器

# 大厂官方域（宪法 §五 D5 条款写死；子域命中也算）
MAJOR_VENDOR_HOSTS = {
    "openai.com", "anthropic.com", "claude.com",
    "deepmind.google", "deepmind.com", "blog.google", "ai.google", "googleblog.com",
    "microsoft.com", "news.microsoft.com", "meta.ai", "ai.meta.com",
    "developer.nvidia.com", "nvidia.com",
    "mistral.ai", "qwen.ai", "qwenlm.github.io", "github.blog", "huggingface.co",
    "cohere.com", "x.ai", "grok.com",
}

RELAY_TIERS = ("T1", "T1.5")        # 权威转述源等级（T2 区域源不算权威转述）
RELAY_WINDOW_HOURS = 24             # 转述覆盖窗口（Fable 裁决：24h 内 ≥2 独立源）
RELAY_MIN_HOSTS = 2                 # 独立 host 数下限
RELAY_MAX_FETCH = 8                 # 每事件转述候选抓页上限（礼节与成本控制）
RELAY_TOKEN_MIN = 3                 # D6 §3：关联特色 token 阈值（≥3 或产品名全称匹配——Fable 六审 ②-c）

# D6 §3 非媒体 host 永不算转述源（tier 过滤之外的 host 过滤——Fable 六审 ①「循环」病根：
# arxiv 论文页 / x.com 帖子 / fireworks 文档都是一手或碎片源，不是 T1/T1.5 意义上的「媒体转述」；
# github.com 是 release/仓库一手源（github.blog 官方博客不在此列），reddit/HN 是社区聚合）
RELAY_EXCLUDE_HOSTS = {
    "arxiv.org", "x.com", "twitter.com", "t.co", "fireworks.ai",
    "reddit.com", "news.ycombinator.com", "github.com",
}


def is_relay_source(url, tier):
    """转述源资格：tier ∈ T1/T1.5 媒体 且 host 不在非媒体排除表（含子域）。"""
    if tier not in RELAY_TIERS:
        return False
    h = host_of(url or "")
    if not h:
        return False
    return not any(h == x or h.endswith("." + x) for x in RELAY_EXCLUDE_HOSTS)


# D6 §3：台账条目的 src 是雷达通道名（官方RSS/arXiv论文/X官方哨…），不是信源名——
# tier 解析须按 URL host 走：FEEDS 信源 host → 信源名 → tiers；再补台账里常见但不在 FEEDS
# 的独立媒体 host。聚合器（news.google/arc.net）与厂商博客不算独立媒体转述。
_EXTRA_MEDIA_HOSTS = {
    "techcrunch.com": "T1.5", "arstechnica.com": "T1.5", "simonwillison.net": "T1.5",
    "latent.space": "T1.5", "venturebeat.com": "T1.5", "theinformation.com": "T1",
    "semafor.com": "T1.5", "cnbc.com": "T1.5", "reuters.com": "T1", "bloomberg.com": "T1",
    "zdnet.com": "T1.5", "computerbase.de": "T1.5", "wired.com": "T1.5",
}


def make_host_tier_lookup(tiers):
    """构造 (src, url) → tier 的解析函数（参数序与 discover_events 的 tier_of 调用一致）。
    先信源名直映（管线 items 的 src 就是信源名），台账通道名不中时按 URL host 走 FEEDS/扩展媒体表。"""
    feed_hosts = {}

    def lookup(src, url=""):
        if src in tiers:                       # 信源名直映（管线 items 的 src 就是信源名）
            return tiers[src]
        h = host_of(url or "")
        if not feed_hosts:
            try:
                import 摘要抓取器
                for name, feed_url in 摘要抓取器.FEEDS:
                    fh = host_of(feed_url)
                    if fh:
                        feed_hosts[fh] = tiers.get(name, "T2")
            except Exception:
                pass
        if h in feed_hosts:
            return feed_hosts[h]
        for host, tier in _EXTRA_MEDIA_HOSTS.items():
            if h == host or h.endswith("." + host):
                return tier
        return "T2"
    return lookup



# 关联器停用词：常见英文虚词 + 厂商名（厂商名当天所有事件都共享，不具备区分度——
# 「OpenAI 发布 A」与「OpenAI 发布 B」只靠厂商名绝不能互相关联）
_RELAY_COMMON = {
    "the", "a", "an", "and", "or", "for", "with", "new", "how", "why", "what", "when",
    "in", "on", "of", "to", "its", "is", "are", "as", "at", "by", "from", "this", "that",
    "using", "use", "used", "can", "will", "not", "but", "all", "your", "you", "we", "our",
    "more", "most", "best", "first", "next", "over", "under", "out", "about", "into",
    "than", "then", "them", "they", "their", "has", "have", "had", "be", "been", "was",
    "were", "it", "ai", "model", "models", "launch", "launches", "launched", "released",
    "release", "announces", "announced", "ann", "introducing", "introduces", "expand",
    "expands", "expanded", "update", "updates", "openai", "anthropic", "google",
    "microsoft", "meta", "nvidia", "deepmind", "gemini", "chatgpt", "claude", "copilot",
}


def is_major_vendor(url):
    """URL 是否大厂官方域（含子域）。"""
    h = host_of(url)
    return any(h == v or h.endswith("." + v) for v in MAJOR_VENDOR_HOSTS)


# 产品名×版本号合并（Claude 5.1 / Gemini 3.8 / o5 → claude-5.1 单 token）：
# 厂商名在停用词表（同日多事件都共享），但「产品名+版本号」合起来是强身份信号
_PRODUCTIZE = re.compile(
    r"\b(gpt|claude|gemini|llama|qwen|glm|deepseek|kimi|grok|ernie|hunyuan|doubao|seed|nova|o)"
    r"\s*[-.]?\s*(\d+(?:\.\d+)*)", re.I)

# D6 §3 产品名全称匹配（Fable 六审 ②-c：token 阈值 ≥3 或产品名全称匹配）。
# 产品家族词起头 + 后续产品词/版本号连成的短语，例：
#   "Introducing GPT-6 Astra for work" → ("gpt-6","astra")；"AlphaGenome Atlas: ..." → ("alphagenome","atlas")
# 全称在转述标题里逐 token 连续出现才算覆盖该产品（"只提到 gpt-6 没提 astra"不算覆盖 Astra 事件）。
_PROD_FAMILY = {
    "gpt", "claude", "gemini", "llama", "qwen", "glm", "deepseek", "kimi", "grok", "ernie",
    "hunyuan", "doubao", "seed", "nova", "codex", "agents", "alphagenome", "alphafold",
    "alphaproteo", "chatgpt", "copilot", "grok-4", "granite", "nemotron",
}
_PROD_SUFFIX = {
    "astra", "live", "api", "apis", "mini", "pro", "ultra", "nano", "atlas", "plus", "max",
    "flash", "next", "turbo", "omni", "coder", "vl", "thinking", "extended", "desktop",
    "search", "voice", "vision", "reasoning", "computer", "hub", "studio", "apps", "app",
    "enterprise", "work", "thinking", "long", "context", "pro", "max",
}
_PHRASE_MAX_LEN = 2    # 产品短语最多吸收 2 个 token（"gpt-6 astra"、"gemini-3.8 live"、"alphagenome atlas"）


def _tokens(title):
    """标题 → 特色 token 集（产品名×版本号先合并，再去停用词/短词）。"""
    t = _PRODUCTIZE.sub(lambda m: f"{m.group(1)}-{m.group(2)}", title or "").lower()
    return tokens_en(t)


def _raw_tokens(title):
    """标题 → 有序 token 列表（产品名×版本号先合并，再按连接符整词切）。"""
    t = _PRODUCTIZE.sub(lambda m: f"{m.group(1)}-{m.group(2)}", title or "").lower()
    return re.findall(r"[a-z0-9][a-z0-9._\-+]*[a-z0-9]|[a-z0-9]", t)


def product_phrases(title):
    """标题里的产品名全称候选（有序 token 短语）。家族词起头，向后吸收产品词/版本号 token；
    停用词与普通词截断。返回 [tuple(tokens)]。"""
    toks = _raw_tokens(title)
    phrases, i = [], 0
    while i < len(toks):
        base = re.split(r"[-.]", toks[i])[0]
        if toks[i] in _PROD_FAMILY or base in _PROD_FAMILY:
            j = i + 1
            while j < len(toks) and j - i < _PHRASE_MAX_LEN:
                b2 = re.split(r"[-.]", toks[j])[0]
                if (toks[j] in _PROD_SUFFIX or b2 in _PROD_FAMILY or b2 in _PROD_SUFFIX
                        or any(c.isdigit() for c in toks[j])):
                    j += 1
                else:
                    break
            phrases.append(tuple(toks[i:j]))
            i = j
        else:
            i += 1
    return phrases


def _phrase_in(phrase, toks):
    n = len(phrase)
    return any(tuple(toks[k:k + n]) == tuple(phrase) for k in range(len(toks) - n + 1))


def relay_match(title_a, title_b):
    """转述关联判定（D6 §3 v2，Fable 六审 ②-c）：返回 (是否关联, 共享特色 token 集)。
    特色 token = 非停用词且（长度 ≥4 或含数字）；产品名×版本号合并成单 token（claude-5.1）。
    接受条件（满足其一）：
    ① 特色共享 ≥ RELAY_TOKEN_MIN(3)——实质性主题重合；
    ② 产品名全称匹配：a 侧产品短语（≥2 token，或带版本号的单 token 如 gpt-6）在 b 侧逐 token 连续出现
       ——治「共享 {gpt-6, astra} 两 token 即关联」（Perplexity 客户稿病样：只提 gpt-6 不提 astra → 拒）。"""
    A, B = _tokens(title_a), _tokens(title_b)
    if not A or not B:
        return False, set()
    shared = A & B
    dist = {t for t in shared
            if t not in _RELAY_COMMON and (len(t) >= 4 or any(c.isdigit() for c in t))}
    if not dist:
        return False, dist
    if len(dist) >= RELAY_TOKEN_MIN:
        return True, dist
    toks_b = _raw_tokens(title_b)
    phs = product_phrases(title_a)
    if phs:
        # 只用最长短语参与全称匹配：厂商题说「GPT-6 Astra」时，转述只提 gpt-6 不提 astra = 不算覆盖
        maxlen = max(len(p) for p in phs)
        for ph in (p for p in phs if len(p) == maxlen):
            if len(ph) >= 2 or (len(ph) == 1 and any(c.isdigit() for c in ph[0])):
                if _phrase_in(ph, toks_b):
                    return True, dist
    return False, dist


def _t(it):
    """条目时间锚（pub 优先，first_seen 兜底）。"""
    return it.get("pub_utc") or it.get("first_seen_utc")


def find_relays(rep, items, quick=False):
    """对一个无正文的大厂 rep 找转述候选并补正文。返回达标的转述条目列表（≥2 独立 host），
    不达标返回 []。候选条件：非同 host、转述源资格（D6 §3：tier T1/T1.5 媒体 + host 不在
    非媒体排除表）、24h 窗、relay_match 关联。"""
    rep_t = _t(rep)
    rep_host = host_of(rep.get("url", ""))
    cands = []
    for it in items:
        h = host_of(it.get("url", ""))
        if not h or h == rep_host:
            continue
        if not is_relay_source(it.get("url", ""), it.get("tier")):
            continue
        if rep_t and _t(it):
            dh = abs((_t(it) - rep_t).total_seconds()) / 3600.0
            if dh > RELAY_WINDOW_HOURS:
                continue
        ok, _dist = relay_match(rep.get("title", ""), it.get("title", ""))
        if ok:
            cands.append(it)
    if len({host_of(c["url"]) for c in cands}) < RELAY_MIN_HOSTS:
        return []
    正文抽取器.enrich(cands, quick=quick, max_fetch=RELAY_MAX_FETCH, verbose=False)
    good = [c for c in cands if c.get("body_source") in BODY_SOURCE_PASS]
    if len({host_of(c["url"]) for c in good}) < RELAY_MIN_HOSTS:
        return []
    return good


def discover_events(ledger_items, tier_of, now=None):
    """D6 §3 hold-out 事件发现（去循环——Fable 六审 ①：tier 过滤进发现逻辑，与生产 find_relays
    同一资格判据；不再「用 relay_match 自己发现事件就算数」）。ledger_items: [{title,url,when,src}]，
    tier_of: (src, url) → tier（台账 src 是雷达通道名，须按 host 解析——用 make_host_tier_lookup 构造）。
    返回候选事件名单（供人工核验，落文件），不做任何抓取/正文判定。"""
    from datetime import datetime, timezone, timedelta
    now = now or datetime.now(timezone.utc)
    recent = [v for v in ledger_items
              if v.get("when") and abs((now - v["when"]).days) <= 30]
    by_time = sorted(recent, key=lambda v: v["when"])
    candidates = []
    for v in by_time:
        if not is_major_vendor(v.get("url", "")):
            continue
        relays = []
        for c in by_time:
            if host_of(c.get("url", "")) == host_of(v.get("url", "")):
                continue
            if abs((c["when"] - v["when"]).total_seconds()) > RELAY_WINDOW_HOURS * 3600:
                continue
            if not is_relay_source(c.get("url", ""), tier_of(c.get("src", ""), c.get("url", ""))):
                continue
            ok, dist = relay_match(v.get("title", ""), c.get("title", ""))
            if ok:
                relays.append({"host": host_of(c.get("url", "")), "src": c.get("src", ""),
                               "title": c.get("title", "")[:90],
                               "shared": sorted(dist)[:4]})
        hosts = sorted({r["host"] for r in relays})
        if len(hosts) >= RELAY_MIN_HOSTS:
            candidates.append({
                "vendor": host_of(v.get("url", "")), "url": v.get("url", ""),
                "title": v.get("title", ""), "when_utc": v["when"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "n_hosts": len(hosts), "hosts": hosts,
                "relays": relays[:8],
                "note": "候选事件（D6 §3 去循环发现）：tier+host 过滤后 ≥2 独立媒体转述关联，供人工核验",
            })
    # 同 vendor×日 去重（一天多条同事件条目取转述源最多的一条）
    best = {}
    for h in candidates:
        key = (h["vendor"], h["when_utc"][:10])
        if key not in best or h["n_hosts"] > best[key]["n_hosts"]:
            best[key] = h
    return sorted(best.values(), key=lambda h: h["when_utc"], reverse=True)



def apply_relay(items, clusters, kept_rep_indexes, quick=False, verbose=True):
    """管线钩子：对预筛保留的大厂 rep 无正文者走转述通道。
    就地修改 rep（body/body_source/extract_len/_major_event/_body_relay）；
    返回事件记录列表 [{rep_i, relays:[{src,url}], best:{src,url,body_source}}]。
    卡片 URL 保持官方原文（管线组装读 rep 自身 url，不改动）。"""
    events = []
    kept = set(kept_rep_indexes)
    for rep_i in sorted(kept):
        rep = items[rep_i]
        if not is_major_vendor(rep.get("url", "")):
            continue
        if rep.get("body_source") in BODY_SOURCE_PASS:
            continue                      # 自身有真正文，无需通道
        good = find_relays(rep, items, quick=quick)
        if not good:
            continue                      # 转述覆盖不足（<2 独立源）→ 如实留 teaser，硬闸兜底
        best = max(good, key=lambda c: c.get("extract_len", 0))
        rep["body"] = best.get("body", "")
        rep["body_source"] = best.get("body_source", "page")
        rep["extract_len"] = best.get("extract_len", len(best.get("body", "")))
        rep["extract_method"] = f"relay:{best.get('src', '')}"
        rep["_major_event"] = True
        rep["_body_relay"] = {
            "src": best.get("src", ""),
            "url": best.get("url", ""),
            "body_source": best.get("body_source", ""),
            "relays": [{"src": c.get("src", ""), "url": c.get("url", ""),
                        "host": host_of(c.get("url", ""))} for c in good],
        }
        events.append({"rep_i": rep_i, "best": {"src": best.get("src", ""), "url": best.get("url", "")},
                       "relays": rep["_body_relay"]["relays"]})
        if verbose:
            rh = host_of(rep.get("url", ""))
            hosts = ", ".join(sorted({r["host"] for r in rep["_body_relay"]["relays"]}))
            print(f"  [大厂通道] {rh} 无正文 → 转述正文({best.get('body_source')}) via {hosts}；卡片链官方原文",
                  flush=True)
    return events
