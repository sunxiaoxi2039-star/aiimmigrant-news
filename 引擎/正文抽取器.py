#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 正文抽取器 —— D4 主件：页面层正文供给（readability 式简化版，纯标准库自研，不装第三方包）
#   病根（Fable D3 四审 ③「最重要一件事」）：正文供给=RSS description，闸建在空壳上——
#   openai.com 一句 teaser 就过硬闸，量子位/HF 全灭，首屏等于「谁的 RSS 带摘要」。
# 与摘要抓取器的分工（Fable D4 审单 ③）：摘要抓取器管 RSS 层（feed 摘要），
#   本模块管页面层（抓原文页面抽正文），缓存分离（摘要缓存.json / 页面正文缓存.json）。
# 抽取顺序（Fable D4 审单 ①）：&lt;article&gt; → JSON-LD articleBody → og:description → 密度启发；
#   每条落 extract_len 与 method。
# 分级（管线消费）：classify_body_source(rss_len, page_len) → page|rss_full|rss_teaser|none；
#   page 需 ≥PAGE_MIN(400) 字，与 rss_full 同为精选硬闸门票。
# 抓取礼节（规格书 §3 + Fable D4 审单 ①）：自定义 UA、ETag/Last-Modified 条件请求、
#   失败 2s/8s 退避、单条失败不拖全轮、每域名 ≥DOMAIN_INTERVAL(30s) 频控（轮转调度）、
#   403/401 域名熔断+负缓存 TTL(24h)、每轮抓取条数/总时长上限。
# 编码探测（Fable D4 审单 ①，Golem 变音符病根）：response Content-Type charset
#   → BOM 探测 → meta charset → 声明编码严格解 → utf-8 严格 → utf-8 替换兜底。
#   不再 utf-8 ignore 硬解 latin-1。
# 用法：
#   /opt/homebrew/bin/python3 正文抽取器.py --prefill   # 为回填库当前条目预热页面缓存
#   /opt/homebrew/bin/python3 正文抽取器.py --regress   # 固定回归集 10 URL/5+ 域（单测引用同一张表）
import json, os, re, sys, time
import urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

from 共用 import (WORK, norm_url, flat, host_of, strip_html_stable,
                  classify_body_source, RSS_FULL_MIN, PAGE_MIN)

CACHE_FILE = os.path.join(WORK, "页面正文缓存.json")
BODY_STORE_MAX = 3000      # 单页正文入库上限（防缓存膨胀；条目消费再截 1500）
# M6（Fable 9-21 v2 审）：进仓缓存体积上界——pages 按 fetched_at 48h TTL 剪枝。
# 页面缓存省的是时间与被封风险（过期后同 URL 走礼貌条件请求重抓），非模型钱。
PAGE_TTL_H = 48
DOMAIN_INTERVAL = 30.0     # 同域名两次请求最小间隔（秒）
NEG_TTL_HOURS = 24         # 403/401 域名熔断时长
MAX_FETCH_PER_ROUND = 80   # 每轮抓取条数上限
MAX_ROUND_SECONDS = 420.0  # 每轮抓取总时长上限（秒）
TIMEOUT = 25

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Accept": "text/html,application/xhtml+xml",
      "Accept-Language": "en,zh;q=0.8,de;q=0.6"}

# ---------- 编码探测 ----------
_BOMS = ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"),
         (b"\xfe\xff", "utf-16-be"), (b"\xff\xfe\x00\x00", "utf-32-le"),
         (b"\x00\x00\xfe\xff", "utf-32-be"))

def detect_encoding(raw, content_type=""):
    """响应字节 → (解码文本, 使用的编码)。顺序：Content-Type charset → BOM →
    前 4KB 里的 meta charset/xml 声明 → 声明编码严格解 → utf-8 严格 → utf-8 替换。"""
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            try:
                return raw.decode(enc), enc
            except (UnicodeDecodeError, LookupError):
                break
    cand = []
    m = re.search(r"charset=([\w.:()-]+)", content_type or "", re.I)
    if m:
        cand.append(m.group(1).strip("\"'"))
    head = raw[:4096].decode("ascii", "replace")
    for pat in (r'<meta[^>]+charset=["\']?([\w.:()-]+)', r'encoding=["\']?([\w.:()-]+)'):
        m = re.search(pat, head, re.I)
        if m:
            cand.append(m.group(1))
    cand.append("utf-8")
    for enc in cand:
        try:
            return raw.decode(enc), enc           # 严格解：错码即换下一个
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace"), "utf-8-replace"   # 最后兜底（替换非法字节）

# ---------- 抽取 ----------
_KILL = re.compile(
    r"<(script|style|noscript|svg|iframe|form|template|nav|header|footer|aside|button|select)\b[^>]*>.*?</\1\s*>",
    re.S | re.I)
_COMMENTS = re.compile(r"<!--.*?-->", re.S)
_ARTICLE = re.compile(r"<article\b[^>]*>(.*?)</article\s*>", re.S | re.I)
_P_BLOCK = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.S | re.I)
_LI_BLOCK = re.compile(r"<li\b[^>]*>(.*?)</li\s*>", re.S | re.I)
_A_IN = re.compile(r"<a\b[^>]*>(.*?)</a\s*>", re.S | re.I)
_JSONLD = re.compile(r'<script[^>]+ld\+json[^>]*>(.*?)</script\s*>', re.S | re.I)
_META_OG = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]*>', re.I)
_META_CONTENT = re.compile(r'content=["\']([^"\']*)["\']', re.I)


def _clean(html_frag):
    return strip_html_stable(html_frag)

def _from_article(html):
    best = ""
    for m in _ARTICLE.finditer(html):
        t = _clean(m.group(1))
        if len(t) > len(best):
            best = t
    return best

def _from_jsonld(html):
    for m in _JSONLD.finditer(html):
        s = re.sub(r"^<!\[CDATA\[|\]\]>$", "", m.group(1).strip())
        s = s.strip().rstrip(";").rstrip(",")
        try:
            data = json.loads(s)
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                ab = cur.get("articleBody")
                if isinstance(ab, list):
                    ab = " ".join(str(x) for x in ab)
                if isinstance(ab, str) and ab.strip():
                    return _clean(ab)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    return ""

def _from_og(html):
    m = _META_OG.search(html)
    if not m:
        return ""
    c = _META_CONTENT.search(m.group(0))
    return _clean(c.group(1)) if c else ""

def _density_blocks(html, block_re, min_len=40, max_link_ratio=0.35):
    out = []
    for m in block_re.finditer(html):
        raw = m.group(1)
        link_len = sum(len(_clean(a)) for a in _A_IN.findall(raw))
        t = _clean(raw)
        if len(t) >= min_len and len(t) and link_len / max(1, len(t) + link_len) <= max_link_ratio:
            out.append(t)
    return out

def _from_density(html):
    parts = _density_blocks(html, _P_BLOCK)
    if sum(len(p) for p in parts) < PAGE_MIN:
        parts += _density_blocks(html, _LI_BLOCK)
    return " ".join(parts)

def extract_body(html_text):
    """页面 HTML → (正文, 方法, 长度)。顺序：article → JSON-LD articleBody →
    og:description → 密度启发（&lt;p&gt; 块按长度+链接密度过滤）。
    返回第一个达到可用长度的结果；og:description 无长度门槛（天然短，作最后兜底）。
    注意：JSON-LD 必须在 _KILL 杀 script 之前从原文取（它自己就在 script 里）。"""
    raw = html_text or ""
    jsonld_text = _from_jsonld(raw)
    html = _COMMENTS.sub(" ", _KILL.sub(" ", raw))
    t = _from_article(html)
    if len(t) >= PAGE_MIN:
        return t[:BODY_STORE_MAX], "article", min(len(t), BODY_STORE_MAX)
    if len(jsonld_text) >= PAGE_MIN:
        return jsonld_text[:BODY_STORE_MAX], "jsonld", min(len(jsonld_text), BODY_STORE_MAX)
    og = _from_og(html)
    dens = _from_density(html)
    if len(dens) >= PAGE_MIN:
        return dens[:BODY_STORE_MAX], "density", min(len(dens), BODY_STORE_MAX)
    if len(og) > len(dens):
        return og, "og", len(og)
    return dens, "density-fallback", len(dens)

# ---------- 缓存 ----------
def load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            c = json.load(f)
        if isinstance(c, dict) and isinstance(c.get("pages"), dict):
            return c
    except Exception:
        pass
    return {"generated_at": None, "pages": {}, "negative_hosts": {}, "failures": []}

def save_cache(c):
    os.makedirs(WORK, exist_ok=True)
    c["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prune_pages(c)      # M6：落盘前按 fetched_at 48h TTL 剪枝（进仓体积上界）
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


def prune_pages(cache, now=None):
    """M6（Fable 9-21 v2 审）：pages 条目 fetched_at 超 48h 丢弃；无 fetched_at 按 now
    宽限一轮（迁移兼容）；status=dead 的负结果同样过期（域名熔断另有 24h until_ts 独立 TTL）。"""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=PAGE_TTL_H)
    pages = cache.get("pages") or {}
    if not isinstance(pages, dict):
        return 0
    kept = {}
    for k, rec in pages.items():
        fa = (rec or {}).get("fetched_at") if isinstance(rec, dict) else None
        try:
            dt = datetime.strptime(fa, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if fa else now
        except (ValueError, TypeError):
            dt = now
        if dt >= cutoff:
            kept[k] = rec
    dropped = len(pages) - len(kept)
    if dropped:
        cache["pages"] = kept
    return dropped

def _neg_ok(cache, host, now_ts):
    rec = cache.get("negative_hosts", {}).get(host)
    return not rec or now_ts >= rec.get("until_ts", 0)

# ---------- 抓取 ----------
def _fetch(url, etag=None, last_modified=None):
    """条件请求。返回 (status, text, etag, last_modified, encoding)。异常向上抛。"""
    headers = dict(UA)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        text, enc = detect_encoding(raw, r.headers.get("Content-Type", ""))
        return r.status, text, r.headers.get("ETag"), r.headers.get("Last-Modified"), enc


# ---------- arxiv 官方 API 通道 ----------
# 9-19 军令轮：density 抓 abs 页只拿到 ~455 字符半篇摘要（打分器看到的事实不全，
# 好论文擦线掉分）。export.arxiv.org 官方 API 给完整摘要（~1300+ 字符），批量 id_list 一次 50 条。
ARXIV_ABS_RE = re.compile(r"^https?://arxiv\.org/abs/([^/?#]+)", re.I)


def _arxiv_id_of(url):
    m = ARXIV_ABS_RE.match(url or "")
    return m.group(1) if m else None


def _arxiv_api_batch(pairs, cache, verbose=True):
    """pairs=[(cache_key, arxiv_id)]。成功写 pages[key] method="arxiv_api"；返回成功条数。
    API 失败的条目不压栈（留待 HTML 路径兜底/下轮再试）。"""
    import xml.etree.ElementTree as ET
    done = 0
    for off in range(0, len(pairs), 50):
        chunk = pairs[off:off + 50]
        api = ("https://export.arxiv.org/api/query?max_results=50&id_list="
               + ",".join(aid for _, aid in chunk))
        try:
            with urllib.request.urlopen(urllib.request.Request(api, headers=UA), timeout=40) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            if verbose:
                print(f"  arxiv API 批失败：{type(e).__name__} {str(e)[:60]}", flush=True)
            continue
        ns = {"a": "http://www.w3.org/2005/Atom"}
        got = {}
        for entry in root.findall("a:entry", ns):
            eid = (entry.findtext("a:id", "", ns) or "").rsplit("/abs/", 1)[-1]
            summ = " ".join((entry.findtext("a:summary", "", ns) or "").split())
            if eid and summ:
                got[eid] = summ[:4000]
        now_s = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for key, aid in chunk:
            body = got.get(aid) or got.get(aid.split("v")[0])   # 缓存带 v 号、API 不带时的互配
            if body:
                cache["pages"][key] = {"body": body, "len": len(body), "method": "arxiv_api",
                                       "status": "ok", "fetched_at": now_s,
                                       "last_check": f"api@{now_s}"}
                done += 1
        if off + 50 < len(pairs):
            time.sleep(3)   # arxiv API 礼节（官方建议 ≤1 次/3s）
    return done

def fetch_pages(urls, cache=None, max_fetch=MAX_FETCH_PER_ROUND,
                max_seconds=MAX_ROUND_SECONDS, verbose=True):
    """按域名轮转逐条抓页面并抽正文，写回 cache（pages/negative_hosts）。
    礼节：同域名间隔 ≥DOMAIN_INTERVAL；403/401 → 域名熔断记负缓存；
    404/410 → 该 URL 记 dead 永不再抓；瞬时错误 2s/8s 退避两次后放弃该条。"""
    cache = cache or load_cache()
    pages = cache.setdefault("pages", {})
    neg = cache.setdefault("negative_hosts", {})
    by_host = {}
    arxiv_pairs = []
    for u in urls:
        key, host = norm_url(u), host_of(u)
        if not (key and host):
            continue
        aid = _arxiv_id_of(u) if host == "arxiv.org" else None
        if aid:
            arxiv_pairs.append((key, aid))      # abs 页走官方 API 批量（完整摘要）
        else:
            by_host.setdefault(host, []).append((u, key))
    hosts = sorted(by_host)
    t0 = time.monotonic()
    n_done = n_skip_neg = 0
    if arxiv_pairs:
        n_api = _arxiv_api_batch(arxiv_pairs, cache, verbose)
        if verbose:
            print(f"  arxiv API 通道：{n_api}/{len(arxiv_pairs)} 条拿到完整摘要", flush=True)
    last_hit = {}
    while hosts and n_done < max_fetch and (time.monotonic() - t0) < max_seconds:
        host = hosts[0]
        u, key = by_host[host].pop(0)
        if not by_host[host]:
            hosts.remove(host)
        now_ts = time.time()
        if not _neg_ok(cache, host, now_ts):
            n_skip_neg += 1
            continue
        rec = pages.get(key) or {}
        if rec.get("status") == "dead":
            continue
        gap = DOMAIN_INTERVAL - (time.monotonic() - last_hit.get(host, -999))
        if gap > 0:
            time.sleep(min(gap, max(1.0, max_seconds - (time.monotonic() - t0))))
        last_hit[host] = time.monotonic()
        status = text = etag = lm = enc = None
        last_err = None
        for attempt in range(3):
            try:
                kw = {}
                if rec.get("etag"):
                    kw["etag"] = rec["etag"]
                if rec.get("last_modified"):
                    kw["last_modified"] = rec["last_modified"]
                status, text, etag, lm, enc = _fetch(u, **kw)
                break
            except urllib.error.HTTPError as e:
                status, last_err = e.code, f"HTTP {e.code}"
                if e.code in (403, 401):
                    until = datetime.now(timezone.utc) + timedelta(hours=NEG_TTL_HOURS)
                    neg[host] = {"until": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 "until_ts": until.timestamp(), "code": e.code}
                    if verbose:
                        print(f"  [熔断] {host}: HTTP {e.code}，{NEG_TTL_HOURS}h 内不再请求", flush=True)
                    break
                if e.code in (404, 410):
                    pages[key] = {"body": "", "len": 0, "method": "none", "status": "dead",
                                  "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                    last_err = f"HTTP {e.code}"
                    break
                time.sleep([2, 8][min(attempt, 1)])
            except Exception as e:
                last_err = f"{type(e).__name__}:{str(e)[:80]}"
                time.sleep([2, 8][min(attempt, 1)])
        n_done += 1
        now_s = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if status == 304:
            rec["fetched_at"] = now_s
            rec["last_check"] = f"304@{now_s}"     # D6 §4：304=服务器确认未变（过，但记 fresh=304）
            pages[key] = rec
            if verbose:
                print(f"  304 {host} {u[:70]}", flush=True)
        elif status == 200 and text:
            body, method, ln = extract_body(text)
            pages[key] = {"body": body, "len": ln, "method": method, "status": "ok",
                          "etag": etag, "last_modified": lm, "encoding": enc,
                          "fetched_at": now_s, "last_check": f"200@{now_s}"}
            if verbose:
                print(f"  200 {host} len={ln} method={method} enc={enc} {u[:60]}", flush=True)
        else:
            cache.setdefault("failures", []).append(
                {"url": u, "err": last_err, "at": now_s})
            if verbose:
                print(f"  失败 {u[:70]} → {last_err}", flush=True)
    save_cache(cache)
    if verbose:
        print(f"页面正文缓存：本轮抓取 {n_done} 条（负缓存跳过 {n_skip_neg}），"
              f"耗时 {round(time.monotonic()-t0)}s，库内 {len(pages)} URL", flush=True)
    return cache

# ---------- 管线入口 ----------
def enrich(items, quick=False, max_fetch=MAX_FETCH_PER_ROUND, verbose=True):
    """对条目做页面层正文补强（打分前调用——Fable D4 审单 ①：打分吃 body）。
    items: 簇代表列表（含 url/body/tier）。逐条设 body / body_source / extract_len /
    extract_method。
    D5 §1 规则制（Fable D5 裁决 v2-1，废除白名单）：非熔断域一律先抓页——即使 RSS ≥400 字
    也抓（D4 病根：NVIDIA 403-406 字截断 teaser 擦线当 rss_full 且「≥400 不抓页」）；
    熔断域（negative_hosts 生效中，如 openai.com 403）不抓，走 rss_full 兜底。
    尾「…」截断的 RSS 永不算 rss_full（共用.rss_is_truncated）。
    缓存过的 URL（ok/dead）不重抓；quick 模式零联网。"""
    from 共用 import rss_is_truncated
    cache = load_cache()
    now_ts = time.time()
    need = []
    for it in items:
        it["rss_len"] = len((it.get("body") or "").strip())
        it["_rss_text"] = it.get("body") or ""          # 截断检测用原始 RSS 文本（替换前）
        host = host_of(it.get("url", ""))
        if host and not _neg_ok(cache, host, now_ts):   # 熔断域：不抓页（rss_full 兜底）
            continue
        if norm_url(it.get("url", "")) not in cache.get("pages", {}):
            need.append(it)
    if need and not quick:
        urls = [it["url"] for it in need]
        if urls:
            fetch_pages(urls, cache=cache, max_fetch=max_fetch, verbose=verbose)
        cache = load_cache()
    pages = cache.get("pages", {})
    stats = {"page": 0, "rss_full": 0, "rss_teaser": 0, "none": 0}
    for it in items:
        rec = pages.get(norm_url(it.get("url", ""))) or {}
        page_body = rec.get("body") or ""
        page_len = rec.get("len") or len(page_body)
        if page_len > it["rss_len"]:
            it["body"], it["extract_len"] = page_body[:1500], page_len
            it["extract_method"] = rec.get("method", "")
        else:
            it["body"], it["extract_len"] = (it.get("body") or "")[:1500], max(it["rss_len"], page_len)
            it["extract_method"] = "rss" if it["rss_len"] >= page_len else rec.get("method", "")
        truncated = rss_is_truncated(it.pop("_rss_text", ""))
        it["body_source"] = classify_body_source(it["rss_len"], page_len, rss_truncated=truncated)
        stats[it["body_source"]] += 1
    if verbose:
        print(f"正文分级：{stats}（页面缓存 {len(pages)} URL）", flush=True)
    return stats

# ---------- 固定回归集（Fable D4 审单 ④：10 URL 覆盖 ≥5 域，≥8 条抽出 ≥400 字） ----------
REGRESSION_URLS = [
    "https://www.qbitai.com/2026/09/489460.html",
    "https://www.qbitai.com/2026/09/489389.html",
    "https://www.ithome.com/1/002/755.htm",
    "https://deepmind.google/blog/alphagenome-atlas-a-predictive-map-of-every-possible-dna-letter-change-in-the-human-genome/",
    "https://huggingface.co/blog/asyncgrpo-lora-hfjobs",
    "https://www.marktechpost.com/2026/09/14/agent-net-open-sources-webagent-a-go-harness-that-turns-any-website-into-a-guarded-ai-agent/",
    "https://github.blog/ai-and-ml/github-copilot/github-copilot-app-for-beginners-using-the-diff-terminal-and-browser/",
    "https://developer.nvidia.com/blog/how-full-stack-nim-optimizations-deliver-2-5x-more-users-on-nemotron-3-ultra/",
    "https://www.theregister.com/ai-ml/2026/09/15/sponsored-how-everpure-plans-to-stop-ai-from-starving-without-data/5295812",
    "https://t3n.de/news/ki-kritik-anthropic-biowaffen-1763507/",
]

def run_regression(use_cache=True):
    """跑固定回归集（D6 §4 fail-closed，Fable 六审 ①：抓失败不回读缓存记录——旧记录不顶数；
    304=服务器确认未变，视为过但记 fresh=304）。返回 [(url, len, method, encoding, fresh)]，
    fresh ∈ {"cache","200","304","fail"}；use_cache=False 时抓取未被本轮确认 → ("fail", len=0)。"""
    cache = load_cache()
    out = []
    for u in REGRESSION_URLS:
        key = norm_url(u)
        if use_cache:
            rec = (cache.get("pages", {}) or {}).get(key) or {}
            if rec.get("body"):
                out.append((u, rec.get("len") or 0, rec.get("method") or "?",
                            rec.get("encoding") or "?", "cache"))
                continue
        t0 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        fetch_pages([u], cache=cache, max_fetch=1, max_seconds=90, verbose=False)
        cache = load_cache()
        rec = (cache.get("pages", {}) or {}).get(key) or {}
        check = rec.get("last_check") or ""
        confirmed = check.endswith(rec.get("fetched_at") or "") and check[:4] in ("200@", "304@") \
            and (rec.get("fetched_at") or "") >= t0
        if confirmed:
            fresh = check[:3]           # "200" 或 "304"
            out.append((u, rec.get("len") or 0, rec.get("method") or "?",
                        rec.get("encoding") or "?", fresh))
        elif use_cache and rec.get("body"):
            # 宽松模式（非验收路径）：fetch 未确认但有旧记录 → 记 cache（不冒充 fresh）
            out.append((u, rec.get("len") or 0, rec.get("method") or "?",
                        rec.get("encoding") or "?", "cache"))
        else:
            out.append((u, 0, "fetch-fail", "?", "fail"))   # fail-closed：断网=FAIL，不回读旧缓存
    return out


def _prefill():
    """为回填库当前条目预热页面缓存（D5 规则制：非熔断域一律抓页，不再只抓 <400 的）。只读雷达数据。"""
    from 共用 import RADAR_DATA
    from 摘要抓取器 import body_for
    from 共用 import snapshot_json
    bf = snapshot_json(os.path.join(RADAR_DATA, "回填库.json"))
    urls = [it["url"] for it in bf.get("items", []) if it.get("url")]
    print(f"预热目标 {len(urls)} URL", flush=True)
    fetch_pages(urls)


if __name__ == "__main__":
    if "--regress" in sys.argv:
        for u, ln, method, enc, fresh in run_regression(use_cache="--fresh" not in sys.argv):
            mark = "PASS" if (ln >= PAGE_MIN and fresh != "fail") else "short"
            print(f"{mark:5s} fresh={fresh:5s} len={ln:5d} {method:17s} {enc:14s} {u}")
        sys.exit(0)
    if "--prefill" in sys.argv:
        _prefill()
        sys.exit(0)
    print(__doc__)
