#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 翻译层 —— 2026-09-19 军令：每条资讯 中/德/英 三版 + 原文
# 设计：
#   - 对象 = 36h 内当日条目 ∪ 精选（成本收口：历史条目不翻，前端回退链兜底）
#   - 英文源条目 title_en 直接复用 title_src（不经模型回译，零损耗）；其余字段模型翻译
#   - 模型 = MODEL_FLASH（量大价廉）；每批 TRANSLATE_BATCH 条一次调用出双语 JSON
#   - 失败降级 = 字段留空 + degrade 留痕；前端回退链 zh → en → de → src 保证不空卡
import re
from 共用 import (MODEL_FLASH, call_json)

TRANSLATE_BATCH = 8
WINDOW_H = 36   # 当日+昨天两组都上三语

PROMPT_HEAD = """把下列 AI 新闻条目翻译成英文和德文。输入是 JSON 数组，每项 {"i":序号,"title":标题,"liner":一句话摘要,"why":为何值得看}。

要求：
- title：简洁新闻标题，英文 ≤12 词，德文 ≤12 词；忠实原意，不加原文没有的信息
- liner：一句话摘要，英文 ≤28 词，德文 ≤28 词
- why：若输入为空字符串，输出留空 ""；否则一句话，英文/德文 ≤24 词
- 公司/产品/模型/人名等专名保持原文不翻（如 OpenAI、Claude、Gemini）
- 只输出 JSON 数组，不多一个字：[{"i":0,"title_en":"","title_de":"","liner_en":"","liner_de":"","why_en":"","why_de":""}, ...]

输入：
"""

OUT_KEYS = ("title_en", "title_de", "liner_en", "liner_de", "why_en", "why_de")


def _entry_texts(e):
    """条目的翻译源文本：标题优先中文加工结果（过闸干净版），空则原文。"""
    title = e.get("title_zh") or e.get("title_src") or ""
    liner = e.get("one_liner_zh") or ""
    why = e.get("why_zh") or ""
    return title, liner, why


def _in_window(e, now):
    from 共用 import to_utc
    from datetime import timedelta
    for k in ("published_utc", "first_seen_utc"):
        t = to_utc(e.get(k))
        if t and (now - t) < timedelta(hours=WINDOW_H):
            return True
    return False


def translate_entries(entries, now, degrade_log=None):
    """对 36h 内 ∪ 精选条目补 title_en/title_de/one_liner_en/one_liner_de（精选加 why_en/why_de）。
    返回翻译成功条数。模型不可用时整层跳过（字段留空，不阻塞管线）。"""
    from 共用 import ModelUnavailable
    targets = [e for e in entries
               if (e.get("selected") or _in_window(e, now))
               and (e.get("title_zh") or e.get("title_src"))]
    if not targets:
        return 0
    ok = 0
    for s in range(0, len(targets), TRANSLATE_BATCH):
        chunk = targets[s:s + TRANSLATE_BATCH]
        payload = []
        for j, e in enumerate(chunk):
            title, liner, why = _entry_texts(e)
            # 精选卡才翻 why（量小）；时间线条目 why 不上前端，不翻省额度
            payload.append({"i": j, "title": title, "liner": liner,
                            "why": why if e.get("selected") else ""})
        try:
            arr = call_json(PROMPT_HEAD + __import__("json").dumps(payload, ensure_ascii=False),
                            model=MODEL_FLASH, max_tokens=12000, think=False)   # 短文本翻译关思考提速
        except ModelUnavailable as ex:
            if degrade_log is not None:
                degrade_log.append({"layer": "trilingual", "batch": s // TRANSLATE_BATCH,
                                    "reason": f"模型不可用：{str(ex)[:120]}"})
            break
        if not isinstance(arr, list):
            if degrade_log is not None:
                degrade_log.append({"layer": "trilingual", "batch": s // TRANSLATE_BATCH,
                                    "reason": "输出非 JSON 数组，本批留空"})
            continue
        for r in arr:
            try:
                j = int(r.get("i"))
            except Exception:
                continue
            if not (0 <= j < len(chunk)):
                continue
            e = chunk[j]
            title_en = str(r.get("title_en") or "").strip()
            # 英文源条目：title_en 以原文为准（模型回译版弃用）
            if not e.get("src_is_zh") and e.get("title_src"):
                title_en = e["title_src"]
            e["title_en"] = title_en
            e["title_de"] = str(r.get("title_de") or "").strip()
            e["one_liner_en"] = str(r.get("liner_en") or "").strip()
            e["one_liner_de"] = str(r.get("liner_de") or "").strip()
            if e.get("selected"):
                e["why_en"] = str(r.get("why_en") or "").strip()
                e["why_de"] = str(r.get("why_de") or "").strip()
            if e["title_en"] or e["title_de"]:
                ok += 1
    return ok
