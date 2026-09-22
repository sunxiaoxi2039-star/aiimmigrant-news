#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 摘要抓取器 —— D2 必修1：从雷达既有 RSS 信源拉「摘要正文」，喂给打分与中文加工
#   病根（Fable 二审）：模型只见标题，卡片只能复述标题。本模块补正文侧供给。
#   信源清单同步自 ~/ai-radar/抢跑雷达.py RSS_FEEDS + 回填器.py TRIAL_FEEDS（2026-09-16 快照，
#   只读镜像不 import 雷达本体——雷达归另一路 agent，扩源后这里跟着加即可）。
# 抓取礼节（规格书 §3）：自定义 UA、ETag/Last-Modified 条件请求、失败指数退避（2s/8s）、
#   单源失败不拖全轮、源间 0.4s 间隔。全部免费公开 RSS，零 Key。
# 产物：产物/摘要缓存.json
#   {"generated_at":..., "feeds":{feed_url:{etag,last_modified,fetched_at,n}},
#    "urls":{norm_url: 摘要正文(≤SUMMARY_MAX)}, "failures":[...]}
# 用法：
#   /opt/homebrew/bin/python3 摘要抓取器.py            # 刷新缓存（条件请求，304 不重解析）
#   /opt/homebrew/bin/python3 摘要抓取器.py --fresh    # 无视 ETag 全量重拉
# 管线消费：load() 只读（绝不联网），body_for() 给出 条目→正文 的统一出口。
import json, os, re, sys, time, html
import urllib.request, urllib.error
from datetime import datetime, timedelta

from 共用 import WORK, norm_url, flat, norm_for_match, strip_html_stable

CACHE_FILE = os.path.join(WORK, "摘要缓存.json")
SUMMARY_MAX = 1500          # 防爆上下文：正文截前 1500 字符（军令口径）
MIN_USEFUL = 40             # 比这还短的"摘要"基本是标题复读，不进缓存
# M6（Fable 9-21 v2 审）：进仓缓存的体积上界——urls 条目 48h TTL 剪枝，防 state-in-repo 无限增长。
# 摘要缓存省的是解析时间不是钱，过期重拉只是普通 HTTP 条件请求，零模型花费。
URL_TTL_H = 48

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Accept-Language": "en,zh;q=0.8"}

# (信源名, feed URL) —— 只含雷达既有 RSS 路；HTML 差分通道（Anthropic/Mistral 等）无摘要可拉，不在此列
FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("HuggingFace博客", "https://huggingface.co/blog/feed.xml"),
    ("通义Qwen博客", "https://qwenlm.github.io/blog/index.xml"),
    ("DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("微软AI", "https://news.microsoft.com/source/topics/ai/feed/"),
    ("GitHub官方博客", "https://github.blog/ai-and-ml/feed/"),
    ("NVIDIA生成式AI", "https://developer.nvidia.com/blog/category/generative-ai/feed/"),
    ("宝玉博客", "https://baoyu.io/feed.xml"),
    ("Claude Code Release", "https://github.com/anthropics/claude-code/releases.atom"),
    ("OpenAI Skills动态", "https://github.com/openai/skills/commits/main.atom"),
    ("IT之家", "https://www.ithome.com/rss/"),
    ("TheVerge-AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("heise", "https://www.heise.de/rss/heise-atom.xml"),
    ("t3n", "https://t3n.de/rss.xml"),
    ("Golem", "https://www.golem.de/rss.php"),
    ("Tech.eu", "https://tech.eu/feed/"),
    ("TheRegister", "https://www.theregister.com/headlines.atom"),
    ("Sifted", "https://sifted.eu/feed/"),
    ("欧洲央行ECB", "https://www.ecb.europa.eu/rss/press.html"),
    ("SAP新闻室", "https://news.sap.com/feed/"),
    ("Bosch新闻室", "https://www.bosch-presse.de/pressblog/de/rss.xml"),
    ("Bitkom协会", "https://www.bitkom.org/rss.xml"),
    ("FAZ财经", "https://www.faz.net/rss/aktuell/"),
    # 回填器 TRIAL_FEEDS（D0 试用源）
    ("机器之心", "https://www.jiqizhixin.com/rss"),
    ("量子位", "https://www.qbitai.com/feed"),
    ("MarkTechPost", "https://www.marktechpost.com/feed/"),
    ("The Decoder", "https://the-decoder.com/feed/"),
]


def _strip_html(s):
    """CDATA/HTML → 纯文本。D3 #2 顺序修复 + D4 修复包升级：
    剥标签/解实体循环至稳定（≤3 轮，多重转义收口）+ 行内标签替空串/块标签替空格
    （治「( ANTHROPIC_BASE_URL )」空格伪迹）+ 反例保护（「a &lt; b」类合法裸 < 不被剥）。
    实现收口在 共用.strip_html_stable（正文抽取器同用一套规则）。"""
    return strip_html_stable(s)


def parse_feed(xml):
    """RSS/Atom → [(url, title, 摘要正文)]。摘要取 description/content/summary 中最长者。"""
    out = []

    def _link_of(block, atom):
        if atom:
            pairs = []
            for attrs in re.findall(r"<link([^>]*)(?:/>|>)", block):
                href = re.search(r'href="([^"]+)"', attrs)
                rel = re.search(r'rel="([^"]+)"', attrs)
                if href:
                    pairs.append((href.group(1).strip(), rel.group(1) if rel else ""))
            alt = [h for h, r in pairs if r == "alternate"]
            return (alt or [h for h, _ in pairs] or [""])[0]
        m = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.S)
        if m:
            return m.group(1).strip()
        m = re.search(r"<guid[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</guid>", block, re.S)
        return m.group(1).strip() if m else ""

    def _text(block, tag):
        m = re.search(rf"<{tag}(?: [^>]*)?>(.*?)</{tag}>", block, re.S | re.I)
        return m.group(1) if m else ""

    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        b = m.group(1)
        title = _strip_html(_text(b, "title"))
        desc = max((_strip_html(_text(b, "description")),
                    _strip_html(_text(b, "content:encoded")),
                    _strip_html(_text(b, "encoded"))), key=len)
        out.append((_link_of(b, False), title, desc))
    if not out:  # Atom
        for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.S):
            b = m.group(1)
            title = _strip_html(_text(b, "title"))
            summ = max((_strip_html(_text(b, "summary")),
                        _strip_html(_text(b, "content"))), key=len)
            out.append((_link_of(b, True), title, summ))
    return out


def _http_conditional(url, etag=None, last_modified=None, timeout=25):
    """条件请求。返回 (status, body, etag, last_modified)；status 200/304/失败抛异常。"""
    headers = dict(UA)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "ignore"), r.headers.get("ETag"), r.headers.get("Last-Modified")


def refresh(force=False):
    """刷新摘要缓存。逐源条件请求；失败退避重试 2 次后放弃该源（不拖全轮）。"""
    cache = load()
    feeds_meta = cache.get("feeds", {})
    urls = cache.get("urls", {})
    url_times = dict(cache.get("url_times") or {})   # M6：TTL 剪枝的时间账
    round_keys = set()
    failures = []
    for name, feed_url in FEEDS:
        meta = feeds_meta.get(feed_url, {})
        status = body = etag = lm = None
        for attempt in range(3):
            try:
                kw = {} if force or not meta else {"etag": meta.get("etag"), "last_modified": meta.get("last_modified")}
                status, body, etag, lm = _http_conditional(feed_url, **kw)
                break
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    status = 304
                    break
                last = f"HTTP {e.code}"
                if e.code in (404, 410):
                    break  # 永久死链不重试（礼节：别轰炸）
                time.sleep([2, 8][min(attempt, 1)])
            except Exception as e:
                last = str(e)[:90]
                time.sleep([2, 8][min(attempt, 1)])
        else:
            failures.append(f"{name}: {last}")
            print(f"  {name}: 失败（跳过，用旧缓存） {last}", flush=True)
            continue
        if status == 304:
            feeds_meta[feed_url] = dict(meta, fetched_at=datetime.now().isoformat(timespec="seconds"))
            print(f"  {name}: 304 未变（{meta.get('n', '?')} 条缓存沿用）", flush=True)
        else:
            items = parse_feed(body or "")
            n = 0
            for u, title, desc in items:
                if not u or len(desc) < MIN_USEFUL:
                    continue
                if desc == title or norm_for_eq(desc) == norm_for_eq(title):
                    continue  # 摘要=标题复读，喂了等于没喂
                key = norm_url(u)
                if key:
                    urls[key] = desc[:SUMMARY_MAX]
                    round_keys.add(key)
                    n += 1
            feeds_meta[feed_url] = {"etag": etag, "last_modified": lm, "fetched_at":
                                    datetime.now().isoformat(timespec="seconds"), "n": n}
            print(f"  {name}: {len(items)} 条 → 有效摘要 {n}", flush=True)
        time.sleep(0.4)
    # M6：本轮活跃条目时间戳刷新 + 48h TTL 剪枝（进仓体积上界；过期条目下轮需要时重拉）
    _now = datetime.now()
    for k in round_keys:
        url_times[k] = _now.isoformat(timespec="seconds")
    urls, url_times = _prune_urls(urls, url_times, _now)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"),
               "feeds": feeds_meta, "urls": urls, "url_times": url_times, "failures": failures}
    os.makedirs(WORK, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"摘要缓存 → {CACHE_FILE}（可匹配 URL {len(urls)} 个；失败 {len(failures)} 路）")
    return payload


def norm_for_eq(s):
    return norm_for_match(s)


def _prune_urls(urls, times, now=None):
    """M6（Fable 9-21 v2 审）：urls 按 url_times 48h TTL 剪枝（进仓缓存体积上界）。
    无时间戳的旧条目按 now 记——迁移宽限一轮，下一轮起自然到期。返回 (kept_urls, kept_times)。"""
    now = now or datetime.now()
    cutoff = now - timedelta(hours=URL_TTL_H)
    kept, kept_times = {}, {}
    for k, v in urls.items():
        try:
            dt = datetime.fromisoformat(times[k]) if times.get(k) else now
        except (ValueError, TypeError):
            dt = now
        if dt >= cutoff:
            kept[k] = v
            kept_times[k] = dt.isoformat(timespec="seconds")
    return kept, kept_times


def load():
    """只读加载缓存（管线用；绝不联网）。坏文件/缺文件返回空结构。"""
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            c = json.load(f)
        if isinstance(c, dict) and isinstance(c.get("urls"), dict):
            return c
    except Exception:
        pass
    return {"generated_at": None, "feeds": {}, "urls": {}, "failures": []}


def body_for(item):
    """条目 → 正文出口：优先抓到的 RSS 摘要，回填 note 兜底，≤SUMMARY_MAX。
    （取不到正文的条目返回空串，管线行为同 D1——军令：取不到的保持现状）"""
    u = norm_url(item.get("url", ""))
    summ = (u and load()["urls"].get(u)) or ""
    if summ:
        return summ[:SUMMARY_MAX]
    return flat(item.get("note", ""))[:SUMMARY_MAX]


if __name__ == "__main__":
    refresh(force="--fresh" in sys.argv)
