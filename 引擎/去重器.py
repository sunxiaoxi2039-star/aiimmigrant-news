#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 去重器 —— 两层聚类：URL 规范化（同链合并）+ 标题 Jaccard 相似度（同事件合并）
# 设计原则：宁漏勿误杀（漏合并只损失一次"多源报道"计数，误杀会把两个事件合成一个假事件）
# 语言适配：英文/德文用词 token 集，中文用字符 bigram 集（中文没有天然分词）
import re
from 共用 import norm_url, tokens_en, tokens_zh, versions_of, jaccard, host_of, flat
from datetime import datetime, timezone

TIER_ORDER = {"T1": 0, "T1.5": 1, "T2": 2, "DROP": 3}

def _lang_of(title):
    cjk = sum(1 for c in title or "" if "\u4e00" <= c <= "\u9fff")
    return "zh" if cjk >= max(2, len(title or "") * 0.15) else "en"

def _tok(title):
    return tokens_zh(title) if _lang_of(title) == "zh" else tokens_en(title)

def cluster(items, jaccard_threshold=0.6, window_hours=48):
    """items: [{title,url,src,tier,pub_utc(datetime),...}] → list of clusters
    cluster = {rep(代表条目), members[...]}，代表=T1 最优先 → pub 最新。
    合并条件（两条之间，满足其一）：
      A. norm_url 相同（同链）
      B. 标题 Jaccard ≥ 阈值 且 |pub 差| ≤ 窗口 且 不同 host（同 host 不同 URL 视为不同文章，防误杀）
    pub 缺失时只走 A（保守）。"""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # A 层：URL 规范化
    by_url = {}
    for i, it in enumerate(items):
        u = norm_url(it.get("url", ""))
        if u in by_url:
            union(i, by_url[u])
        else:
            by_url[u] = i

    # B 层：标题相似（先按 URL 簇取代表文本再比，减少 O(n²) 里的重复计算）
    reps = {}
    for i in range(n):
        reps.setdefault(find(i), []).append(i)
    rep_list = sorted(reps.keys())
    toks = {r: _tok(flat(items[r].get("title", ""))) for r in rep_list}
    pubs = {r: items[r].get("pub_utc") for r in rep_list}
    for a_pos in range(len(rep_list)):
        ra = rep_list[a_pos]
        for b_pos in range(a_pos + 1, len(rep_list)):
            rb = rep_list[b_pos]
            ha, hb = host_of(items[ra].get("url", "")), host_of(items[rb].get("url", ""))
            if not ha or not hb or ha == hb:
                continue  # 同 host 不做标题合并（防误杀）；无 host 的条目跳过 B 层
            pa, pb = pubs[ra], pubs[rb]
            if pa is not None and pb is not None and abs((pa - pb).total_seconds()) > window_hours * 3600:
                continue
            # 版本号互斥（防误杀硬规则）：两个标题都带版本号但无一相同 → 必是不同事件
            va, vb = versions_of(items[ra].get("title", "")), versions_of(items[rb].get("title", ""))
            if va and vb and not (va & vb):
                continue
            # 中英跨语标题 token 几乎不重叠，额外用数字指纹比对（版本号/关键数字相同才近似）
            ja = jaccard(toks[ra], toks[rb])
            if ja >= jaccard_threshold or _num_fingerprint_match(items[ra], items[rb]):
                union(ra, rb)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    clusters = []
    for members in groups.values():
        # 代表：tier 最小值优先，同 tier 取 pub 最新
        def rank(i):
            it = items[i]
            return (TIER_ORDER.get(it.get("tier", "T2"), 2),
                    -(it.get("pub_utc") or datetime.min.replace(tzinfo=timezone.utc)).timestamp())
        rep = min(members, key=rank)
        clusters.append({"rep": rep, "members": sorted(members)})
    return clusters

def _num_fingerprint_match(a, b):
    """跨语言同事件兜底：标题中的数字集合（版本号/参数量/金额）≥2 个相同数字，
    且存在共享的版本样式数字（x.y）。门槛刻意苛刻：单一数字相同太容易误杀。"""
    def nums(t):
        return set(re.findall(r"\d+(?:\.\d+)?", t or ""))
    def ver(t):
        return set(re.findall(r"\d+\.\d+", t or ""))
    na, nb = nums(a.get("title", "")), nums(b.get("title", ""))
    if len(na & nb) < 2:
        return False
    return bool(ver(a.get("title", "")) & ver(b.get("title", "")))

def merge_info(items, members):
    """簇属性：最早 published、最早 first_seen、去重后源列表。"""
    pubs = [items[i]["pub_utc"] for i in members if items[i].get("pub_utc")]
    firsts = [items[i].get("first_seen_utc") for i in members if items[i].get("first_seen_utc")]
    return {
        "published_utc": min(pubs) if pubs else None,
        "first_seen_utc": min(firsts) if firsts else None,
        "n_sources": len({items[i].get("src") for i in members}),
    }
