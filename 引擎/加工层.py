#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 中文加工层 —— 把信源条目加工成中文资讯卡，四道防幻觉闸门全上（规格书 v2 §3）
#   闸1 槽位填充：结构化输出 + 长度/句数上限（schema 约束，不做自由写作）
#   闸2 实体回验：关键数字/涉及主体逐字回原文比对（零 LLM 成本，代码强制）
#   闸3 二遍自查：同模型二次调用只问「哪些中文陈述在原文无依据」，被点名→重做一次→仍点名→降级
#   闸4 原文引句：quote 必须是原文逐字子串（留痕即信任）
# 出口附加闸：
#   闸5 禁用词表（标题党词命中→重写一次→再命中→直译兜底）
#   闸6 品牌红线（对外字段零 aihot 字样）
# 降级链：完整卡 → 直译标题卡（仅 title_zh+quote=原标题） → 原标题卡（模型不可用时兜底）
import json
import re
from 共用 import (call_model, call_json, extract_json, flat, verbatim_in, norm_for_match,
                  banned_hits, brand_violation, BANNED_WORDS, MODEL_FLAGSHIP)

TITLE_MAX = 32          # 中文字
TITLE_REWRITE_TARGET = 28   # D6 §2：标题专项二次重写目标（≤28 留余量，Fable 裁决 v2-2）
LINER_MAX = 60          # 一句话是什么
WHY_MAX = 60
QUOTE_MAX = 200
SENT_MAX = 3            # 摘要句数上限（版权红线：≤3 句）
QUOTE_LEN_HARD = 600    # 超过此值才判「引句超长」废卡；≤此值由出口钳制在词边界收口

PROCESS_PROMPT = """你是 AI 资讯站的中文加工员。把下面的资讯条目加工成中文资讯卡。
铁律（违反即废）：
1. 只能使用每条「原文」里已有的信息（原文=标题+正文摘要）。原文没有的事实、数字、主体名、因果，一个都不许出现。
2. 不做自由发挥，不加观点，不用夸张词（{banned} 全部禁用）。
3. quote 必须从「正文摘要」里逐字摘录（英文保留英文；禁止摘标题——标题不算正文）。逐字=原样复制粘贴正文里的连续原句，不改词、不改标点、不拼接两处；优先摘有信息量的完整句子，长度 ≤200 字符；正文摘要为空或短到凑不出一句时 quote 给空字符串。
4. 标题 ≤32 个汉字；一句话是什么 ≤60 字且最多 1 句，必须说出正文摘要里的具体事实（做了什么/是多少/影响谁），不得复述标题；为什么重要 ≤60 字：必填——用原文里的事实写明影响面或意义（有正文摘要必须从正文取材），不许留空。
5. nums 填原文出现的关键数字（字符串数组）；orgs 填原文出现的主体名（公司/模型/产品/人名，保留原文拼写）。nums/orgs 里的每一项都必须能在原文里逐字找到。
6. 原文本身就是中文的条目：quote=正文原句（没有正文才允许给标题并置空 quote），标题只做轻度去噪（去「重磅：」之类前缀），不得改写事实。

对每条输出一个对象：{{"i":序号,"title_zh":"…","one_liner_zh":"…","why_zh":"…","nums":["…"],"orgs":["…"],"quote":"…"}}
只输出 JSON 数组，不要任何解释。

条目：
{items}"""

REWRITE_PROMPT = """下面这些中文资讯卡的标题/一句话/为什么重要有禁用词、超长或缺失。逐条重写：保留事实不变，去掉夸张词，标题 ≤32 字，一句话 ≤60 字（说正文摘要里的具体事实，不复述标题），为什么重要 ≤60 字且必填（用原文事实写影响面）。
只输出 JSON 数组 [{{"i":序号,"title_zh":"…","one_liner_zh":"…","why_zh":"…"}}]，不要解释。
原中文（序号|标题|一句话|为什么）：
{items}"""

CHECK_PROMPT = """你是事实核查员。逐条检查：下面每张中文资讯卡里的中文陈述（标题/一句话/为什么重要），有哪些在对应的「原文」里找不到依据（无中生有、数字对不上、主体名不在原文、因果虚构）？
只点名确实无依据的条目和具体哪句话。全部有依据就输出空数组。
只输出 JSON 数组 [{{"i":序号,"bad":["具体哪句无依据"]}}]，不要解释。
（nums/orgs/quote 字段不用检查，那两道由代码比对。）

{cards}"""

TRANSLATE_PROMPT = """把下面这条 AI 资讯的标题直译成简体中文。只翻译标题本身的字面信息，不添加任何原文没有的内容，不用夸张词，≤32 字。
只输出 JSON 对象 {{"title_zh":"…"}}，不要解释。
标题：{title}"""

ONE_LINER_FIX_PROMPT = """下面这些 AI 资讯卡的「一句话」字段错写成了英文原句。逐条改写成不超过 60 字的中文句子（专有名词如 GPT-6/Agents API 可保留英文），只复述资讯本身，不加观点不加新信息。
只输出 JSON 数组 [{{"i":序号,"one_liner_zh":"…"}}]，不要解释。

{items}"""

# D6 §2 标题专项二次重写（Fable 裁决 v2-2：超长标题先重写再截断，目标 ≤28 字留余量）
TITLE_REWRITE_PROMPT = """下面这些 AI 资讯卡的中文标题超长了（>32 字）。逐条重写成一个更短的中文标题：
- 目标不超过 {target} 个字（硬上限 32 字），保留最关键的主体名与事实（模型名/产品名/版本号可保留英文）
- 只压缩表述，不许改变事实、不许加新信息、不许用夸张词
- 是完整通顺的短语，不要以省略号或任何截断符结尾
只输出 JSON 数组 [{{"i":序号,"title_zh":"…"}}]，不要解释。

条目（序号|原文标题|超长中文标题）：
{items}"""


def zh_purity(s):
    """中文占比：CJK 字符数 / 总字符（空白不计）。"""
    t = re.sub(r"\s", "", s or "")
    if not t:
        return 0.0
    cjk = sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
    return cjk / len(t)


def one_liner_is_chinese(card):
    """出口闸 7（中文纯度）：one_liner_zh 必须是中文句。
    判据：CJK 字符 ≥2 个（专有名词可占大头，如「OpenAI 推出 Agents API。」是合格中文句；
    纯英文回显 0 个 CJK 必须拦）。"""
    t = re.sub(r"\s", "", card.get("one_liner_zh", "") or "")
    return sum(1 for c in t if "\u4e00" <= c <= "\u9fff") >= 2


def fix_one_liners(bad_batch, degrade_log):
    """中文纯度不达标的 one_liner 定向重写一次（漏答的条目单独补捞一次）。
    返回 {i: 新句子}。"""
    def _call(batch_items):
        lines = [f'{b["i"]}. 原文：{full_source(b)[:900]}' for b in batch_items]
        raw = call_json(ONE_LINER_FIX_PROMPT.format(items="\n".join(lines)), model=MODEL_FLAGSHIP)
        out = {}
        if isinstance(raw, list):
            for r in raw:
                if isinstance(r, dict) and isinstance(r.get("i"), int) and r.get("one_liner_zh"):
                    out[r["i"]] = flat(r["one_liner_zh"])
        return out
    out = _call(bad_batch)
    missing = [b for b in bad_batch if b["i"] not in out]
    if missing:
        out.update(_call(missing))   # 漏答补捞（单批重试一次）
    return out


def full_source(b):
    """条目 → 闸门用的完整原文（标题 + note + 正文摘要）。
    G2 实体回验 / G4 引句留痕都以它为比对基准——模型从正文摘要里摘的实体和引句必须能在这里逐字找到。"""
    parts = [flat(b["title"])]
    if b.get("note"):
        parts.append(flat(b["note"])[:200])
    if b.get("body"):
        parts.append(flat(b["body"]))
    return " ".join(parts)


def _fmt_items(batch):
    lines = []
    for b in batch:
        src_text = flat(b["title"])
        if b.get("note"):
            src_text += " | " + flat(b["note"])[:200]
        if b.get("body"):
            src_text += "\n正文摘要：" + flat(b["body"])
        lines.append(f'{b["i"]}. 原文：{src_text}')
    return "\n".join(lines)


# D4 修复包：_clamp 词边界截断（Fable D3 审单 ②：13 卡有 5 张被切在词中「toke…/建…」）。
# 切点规则（确定性）：
#   1) 优先切在 [0.6×maxlen, maxlen] 窗口内最后一个分隔符（句读/空白）之前；
#   2) 否则若切点落在 ASCII 字母数字词中间 → 回退到该词词首（「toke…」根治）；
#   3) 其余（CJK 字间）按字边界切（中文无分词词典，字边界即合法边界）。
_CLAMP_SEPS = "。！？；：，、．,.!?:;）)]】》」”’ 　\t"

def _is_wordy(ch):
    return bool(re.match(r"[A-Za-z0-9._\-+]", ch))

def _clamp(text, maxlen, ellipsis=True):
    t = flat(text)
    if len(t) <= maxlen:
        return t
    floor = max(1, int(maxlen * 0.45))
    cut = -1
    for p in range(maxlen, floor - 1, -1):      # 不含尾分隔符：t[p-1] 是分隔符则截到 p-1
        if p <= len(t) and t[p - 1] in _CLAMP_SEPS:
            cut = p - 1
            break
    if cut < 0 and maxlen < len(t):
        if _is_wordy(t[maxlen - 1]) and _is_wordy(t[maxlen]):
            q = maxlen - 1
            while q > floor and _is_wordy(t[q - 1]):
                q -= 1
            cut = q
        else:
            cut = maxlen
    cut = max(cut, floor)
    out = t[:cut].rstrip(" ，,、；;：")
    # ellipsis=False 用于 quote：截断后必须仍是正文逐字子串（任何后缀标记都会破坏逐字性）
    return out + ("…" if ellipsis else "")


def first_sentence(text, max_len=140):
    """quote 出口闸用：取第一句（句读截断），≤max_len 再走词边界钳制。"""
    t = flat(text)
    m = re.search(r"^(.*?[.!?。！？；;])", t)
    s = m.group(1).strip() if m else t[:max_len]
    return _clamp(s, max_len, ellipsis=False) if len(s) > max_len else s


# ---------- D6 §2 标题可读性（Fable 裁决 v2-2：超长→二次重写→句读边界无省略号截断→退 title_src） ----------
# 病根（Fable 六审 ③）：5/8 精选标题带尾省略号（_clamp 出口加「…」）；AlphaGenome 被钳成
# 「AlphaGenome Atlas…」17 字（floor 45% + 冒号切）。新规：精选卡标题/一句话/why 尾省略号=FAIL。
_ELLIPTAIL = re.compile(r"(?:\u2026|\.{3,})[\s.。…]*$")

# 句读边界（截断切点）：完整子句收尾的标点。冒号不算——切在冒号上会留下悬空的前置短语
# （AlphaGenome Atlas：病根）；括号引号类收尾符也不算。
_CLAUSE_SEPS = "。！？；，、!?,;"


def strip_trailing_ellipsis(s):
    """剥掉尾部省略号（…/...，含后随句号空白）。模型偶发自带省略号 / 旧钳制残留统一收口。"""
    return _ELLIPTAIL.sub("", (s or "").rstrip()).rstrip()


def truncate_no_ellipsis(text, maxlen, floor_ratio=0.5):
    """D6 §2：超长标题在句读边界切，无省略号。返回切好的文本；窗口内找不到句读边界 → None
    （调用方退 title_src）。切点窗口 [maxlen*floor_ratio, maxlen]，从右往左找最后一个子句标点。"""
    t = strip_trailing_ellipsis(flat(text))
    if len(t) <= maxlen:
        return t
    floor = max(8, int(maxlen * floor_ratio))
    for p in range(maxlen, floor - 1, -1):
        if p <= len(t) and t[p - 1] in _CLAUSE_SEPS:
            return t[:p - 1].rstrip(" ，,、；;：")
    return None


# ---------- D7 §1 悬空残句闸（Fable 终审：出口从「只查尾省略号」升级为「完整性检查」） ----------
# 终审病样（真跑实录，原始模型输出在 模型缓存.json）：
#   ① CC v2.1.268 一句话原文 63 字，60 字钳制硬切在字边界 → 尾「每轮HTTP 400的」——悬空助词
#      「的」收尾（窗口内唯一句读边界「，」在 21 字处 < floor 24，旧兜底就走了词边界硬切）；
#   ② IBM Granite why 原文含「（Apache 2.0 与 OpenMDW 1.0）」，切点落在未闭合括号内 → 尾「（Apache」。
# 新规（Fable 原话：句读边界截断或整段丢弃——宁可空，不可残）：
#   完整性 = 非空 ∧ 无尾省略号 ∧ 括号/引号配平 ∧ 不以悬空助词/连词收尾；
#   出口 = ≤上限且完整 → 原样；超长或不完整 → 句读边界截断（切点前缀本身必须完整）；
#         切不出完整段 → 整段丢弃（""）。D6 的词边界硬切路径废除——硬切正是两个病样的病根。

DANGLING_TAILS = ("的", "与", "和", "或", "及", "并", "而", "且", "在", "从", "对", "向", "于",
                  "为", "以", "被", "把", "将", "由", "让", "则")
# 注：了/是 不入表——「踩刹车了」类完整谓语句收尾不算残句（终审病样只涉「的」悬空形态）。
# 尾助词闸只作用于一句话/why（Fable 终审原文范围）；标题是名词短语，「近百万开发者参与」
# 「触手可及」这类以 与/及 收尾的完整词形不算残句，标题只查括号配平+尾省略号。

_BRACKET_PAIRS = (("（", "）"), ("(", ")"), ("［", "］"), ("[", "]"),
                  ("「", "」"), ("『", "』"), ("《", "》"), ("〈", "〉"),
                  ("“", "”"), ("‘", "’"))


def brackets_balanced(s):
    """括号/引号配平：各类成对符号计数相等（（Apache 病根）。ASCII 双引号计数须为偶；
    ASCII 单引号不算（英文所有格 Sam Altman's 不是引文）。"""
    if (s or "").count('"') % 2:
        return False
    for o, c in _BRACKET_PAIRS:
        if s.count(o) != s.count(c):
            return False
    return True


def is_dangling_tail(s):
    """尾助词闸：以悬空助词/连词/介词收尾 = 残句（「每轮HTTP 400的」病根形态）。
    只用于一句话/why；标题豁免（词形收尾歧义大，见 DANGLING_TAILS 注）。"""
    return bool(s) and s[-1] in DANGLING_TAILS


def text_complete(s, tail_gate=True):
    """完整性判定：非空 ∧ 无尾省略号 ∧ 括号/引号配平 ∧（tail_gate 时）非悬空助词收尾。
    标题走 tail_gate=False（只查配平+省略号）。"""
    if not s or not s.strip():
        return False
    if strip_trailing_ellipsis(s) != s:
        return False
    if not brackets_balanced(s):
        return False
    return (not is_dangling_tail(s)) if tail_gate else True


def cut_complete(text, maxlen, floor_ratio=0.4, tail_gate=True):
    """完整性截断：窗口 [floor, maxlen] 从右往左找句读边界，切出的前缀必须通过完整性判定
    （切点落在未闭合括号内或悬空助词上的边界继续左移）；找不到完整切点 → None（调用方丢弃/回退）。"""
    t = strip_trailing_ellipsis(flat(text))
    floor = max(8, int(maxlen * floor_ratio))
    for p in range(maxlen, floor - 1, -1):
        if p <= len(t) and t[p - 1] in _CLAUSE_SEPS:
            cand = t[:p - 1].rstrip(" ，,、；;：")
            if text_complete(cand, tail_gate=tail_gate):
                return cand
    return None


def resolve_title(title, maxlen=TITLE_MAX):
    """D7 §1：标题出口完整性收口（D6 §2 + 终审升级；标题豁免尾助词闸——只查配平+省略号）。
    ≤maxlen 且完整 → 原样；超长或不完整 → 句读边界完整性截断；否则 → ""（退 title_src 渲染）。
    返回 (标题, action)，action ∈ ok|cut|fallback。"""
    t = strip_trailing_ellipsis(flat(title))
    if not t:
        return "", "fallback"
    if len(t) <= maxlen and text_complete(t, tail_gate=False):
        return t, "ok"
    cut = cut_complete(t, maxlen, floor_ratio=0.5, tail_gate=False)
    if cut and len(cut) >= max(8, int(maxlen * 0.5)):
        return cut, "cut"
    return "", "fallback"


def clamp_no_ellipsis(text, maxlen):
    """D7 §1 一句话/why 出口完整性钳制（Fable 终审：残句不得外发——宁可空，不可残）：
    ≤maxlen 且完整 → 原样；超长或不完整 → 句读边界完整性截断；切不出完整段 → 整段丢弃（""）。
    整段丢弃的条目由管线拦出精选并 gates 留痕（liner_complete_discard / why_complete_discard）。"""
    t = strip_trailing_ellipsis(flat(text))
    if not t:
        return ""
    if len(t) <= maxlen and text_complete(t):
        return t
    return cut_complete(t, maxlen, floor_ratio=0.4) or ""


def rewrite_titles(overlong, degrade_log=None):
    """D6 §2 标题专项二次重写（目标 ≤TITLE_REWRITE_TARGET）。overlong: [{id, title_src, title_zh}]。
    返回 {id: 新标题}（模型按 1..n 序号作答——实测会把长 hash id 重排成序号，这里做序号往返映射；
    也兼容直接回显原 id 的形态）。重写失败/漏答返回缺项（调用方走截断/回退，不抛异常）。"""
    if not overlong:
        return {}
    id_by_seq = {j: b["id"] for j, b in enumerate(overlong, 1)}
    lines = [f'{j}|{b["title_src"]}|{b["title_zh"]}' for j, b in enumerate(overlong, 1)]
    out = {}

    def _parse(raw):
        got = {}
        if isinstance(raw, list):
            for r in raw:
                if not (isinstance(r, dict) and r.get("title_zh")):
                    continue
                key = r.get("i")
                if isinstance(key, int) and key in id_by_seq:
                    got[id_by_seq[key]] = flat(r["title_zh"])
                elif isinstance(key, str) and key in {b["id"] for b in overlong}:
                    got[key] = flat(r["title_zh"])
        return got

    try:
        out.update(_parse(call_json(
            TITLE_REWRITE_PROMPT.format(target=TITLE_REWRITE_TARGET, items="\n".join(lines)),
            model=MODEL_FLAGSHIP)))
    except Exception as e:
        if degrade_log is not None:
            degrade_log.append({"i": "?", "title_src": f"标题二次重写整批失手: {e}",
                                "mode": "title_rewrite", "reason": "模型未返回"})
        return {}
    missing = [b for b in overlong if b["id"] not in out]
    if missing:   # 漏答补捞一次（与 process_batch 同策略）
        m_id_by_seq = {j: b["id"] for j, b in enumerate(missing, 1)}
        lines2 = [f'{j}|{b["title_src"]}|{b["title_zh"]}' for j, b in enumerate(missing, 1)]
        try:
            raw2 = call_json(TITLE_REWRITE_PROMPT.format(target=TITLE_REWRITE_TARGET, items="\n".join(lines2)),
                             model=MODEL_FLAGSHIP)
            if isinstance(raw2, list):
                for r in raw2:
                    if isinstance(r, dict) and r.get("title_zh") and isinstance(r.get("i"), int) \
                            and r["i"] in m_id_by_seq:
                        out[m_id_by_seq[r["i"]]] = flat(r["title_zh"])
        except Exception:
            pass
    return out


def resolve_titles_pass(entries, rewrites=None, degrade_log=None):
    """D6 §2 管线钩子（D7 §1 完整性收口）：对全部非空 title_zh 条目做标题出口收口。
    超长**或不完整**（悬空助词/括号不配平）条目先吃重写结果（管线层批量调 rewrite_titles 后传入），
    再走句读完整性截断，否则退 title_src。就地写 e["title_zh"] 与 e["gates"]["title2_*"] 留痕；
    返回 (n_rewrite, n_cut, n_fallback)。重写验收：≤TITLE_MAX、含中文、无禁用词、数字不超出
    原文标题（title_src+旧中文标题）并集、完整性通过（D7）。"""
    n = {"rewrite": 0, "cut": 0, "fallback": 0, "strip": 0}
    rewrites = rewrites or {}
    for e in entries:
        raw = flat(e.get("title_zh") or "")
        if not raw:
            continue
        g = e.setdefault("gates", {})
        t = strip_trailing_ellipsis(raw)
        if t != raw:
            n["strip"] += 1
        if len(t) <= TITLE_MAX and text_complete(t, tail_gate=False):
            e["title_zh"] = t
            continue
        new = rewrites.get(e["id"])
        src_pool = f'{e.get("title_src", "")} {raw}'
        nums_ok = all(verbatim_in(x, src_pool) for x in re.findall(r"\d+(?:\.\d+)*", new or ""))
        if (new and len(new) <= TITLE_MAX and zh_purity(new) > 0 and not banned_hits(new) and nums_ok
                and text_complete(new, tail_gate=False)):
            e["title_zh"] = strip_trailing_ellipsis(new)
            g["title2_rewrite"] = f"超长/不完整 {len(t)} 字 → 重写 {len(e['title_zh'])} 字"
            n["rewrite"] += 1
            continue
        resolved, action = resolve_title(t, TITLE_MAX)
        e["title_zh"] = resolved
        if action == "cut":
            g["title2_cut"] = f"超长/不完整 {len(t)} 字 → 句读边界完整性截断 {len(resolved)} 字（无省略号）"
            n["cut"] += 1
        else:
            g["title_src_fallback"] = f"超长/不完整 {len(t)} 字且无完整句读边界 → 退 title_src 渲染"
            n["fallback"] += 1
    return n


def selected_titles_clean(entries):
    """D7 §1 出口闸断言（验收/单测共用，Fable 终审：从「只查尾省略号」升级为完整性检查）：
    selected 条目的标题/一句话/why 必须**完整**——无尾省略号 ∧ 括号/引号配平；一句话/why 另加
    悬空助词闸（「（Apache」「每轮HTTP 400的」类残句不得外发；标题豁免尾助词闸，词形收尾
    歧义大）。返回违例列表 [{id, field, tail, reason}]。"""
    bad = []
    for e in entries:
        if not e.get("selected"):
            continue
        for f in ("title_zh", "one_liner_zh", "why_zh"):
            v = flat(e.get(f) or "")
            if not v:
                continue
            reason = None
            if strip_trailing_ellipsis(v) != v:
                reason = "尾省略号"
            elif not brackets_balanced(v):
                reason = "括号/引号不配平"
            elif f != "title_zh" and is_dangling_tail(v):
                reason = f"悬空助词「{v[-1]}」收尾"
            if reason:
                bad.append({"id": e.get("id"), "field": f, "tail": v[-12:], "reason": reason})
    return bad



# ---------- D5 §4：quote 选取信息量启发 + 引号闭合（Fable D5 计划 ④） ----------
# 病根（D4 五审 ③）：Verge Amodei 卡 quote 截在引号内「practices and」半句悬空；
# HF Gradio 卡 quote 选了「最平一句」（数节点，零数字零实体）。Fable 裁决：
# 悬空半句不外发（截窗回退到完整句）；选取改「最有信息量句」启发（数字/命名实体密度）。

_CAP_WORD_STOP = {
    "The", "This", "That", "These", "Those", "We", "It", "In", "On", "For", "And", "But",
    "Our", "Their", "His", "Her", "When", "While", "What", "How", "Why", "As", "If", "At",
    "By", "From", "With", "They", "There", "Here", "Now", "Then", "These", "Both", "Each",
    "More", "Most", "Other", "New", "Open", "Using", "Use", "Used", "Its",
}

def info_score(s):
    """句子信息量启发分 = 数字组数 + 大写实体词数（句首常见起手词除外；中文按数字组计）。
    「最平一句」（零数字零实体）=0 分——D4 HF Gradio 病样形态。"""
    t = flat(s)
    if not t:
        return 0
    nums = len(re.findall(r"\d+(?:\.\d+)*", t))
    caps = sum(1 for w in re.findall(r"\b[A-Z][A-Za-z0-9.-]*", t) if w not in _CAP_WORD_STOP)
    return nums + caps


def pick_info_sentence(text, max_len=200, min_score=2):
    """从正文选信息量最高的完整句（数字/命名实体密度启发）。
    只取 ≤max_len 的完整句（不加钳制——保逐字与完整句双约束）；无合格句返回 ""。"""
    t = flat(text)
    if not t:
        return ""
    best, best_s = "", min_score - 1
    for s in re.split(r"(?<=[.!?。！？；])\s+", t):
        s = s.strip()
        if not s or len(s) > max_len:
            continue
        sc = info_score(s)
        if sc > best_s:
            best, best_s = s, sc
    return best


def quotes_balanced(q):
    """引号闭合判定：ASCII 双引号计数为偶数，CJK/弯引号成对。
    单引号撇号（Sam Altman's）不算——英文所有格不是引文。"""
    if q.count('"') % 2:
        return False
    for o, c in (("「", "」"), ("『", "』"), ("“", "”")):
        if q.count(o) != q.count(c):
            return False
    return True


def close_quote_window(q, min_len=30):
    """D5：悬空半句不外发——quote 引号不闭合时，回退到最后一个引号闭合的完整句；
    找不到合格完整句（整段都在开引号里）→ 置空弃用。返回值仍是正文逐字子串（前缀截断）。"""
    if not q or quotes_balanced(q):
        return q or ""
    for i in range(len(q) - 1, 0, -1):
        if q[i] in ".!?。！？；" and quotes_balanced(q[:i + 1]) and len(q[:i + 1].strip()) >= min_len:
            return q[:i + 1].strip()
    return ""


def quote_exit_gate(quote, body, title_src):
    """D4 quote 出口闸（Fable D4 审单 ② + D3 审单 ②「整句抄」病根）：
    - quote=标题（规范化后相等或为标题子串）→ 一律置空外发；
    - quote ≈ 正文全文（≥80% 且正文 ≤500 字，即 teaser 整句抄）→ 降级为信息量最高句窗口
      （D5 §4：由首句改「最有信息量句」）；截完仍 ≈ 全文的短正文 → 置空弃用；
    - D5 §4 信息量升级：「最平一句」（零数字零实体）且正文有 ≥3 分信息量句 → 换信息量句；
    - D5 §4 引号闭合：出口一律过 close_quote_window（悬空半句不外发）；
    - 其余原样放行（verbatim 性已由 G4 对 body 验过；前缀截断仍是逐字子串）。"""
    q = flat(quote or "")
    if not q:
        return ""
    if norm_for_match(q) and norm_for_match(q) in norm_for_match(title_src or ""):
        return ""
    b = flat(body or "")
    if b and len(q) >= 0.8 * len(b) and len(b) <= 500:
        win = pick_info_sentence(q, 140)
        if not win:
            win = first_sentence(q, 140)
        return close_quote_window(win if len(win) < 0.8 * len(b) else "")
    # D5 §4：最平一句升级（HF Gradio 病样：数节点的平句，正文里有带数字/实体的句子）
    if b and info_score(q) == 0:
        cand = pick_info_sentence(b, QUOTE_MAX, min_score=3)
        if cand and norm_for_match(cand) not in norm_for_match(title_src or "") \
                and len(cand) >= 40:
            q = cand
    return close_quote_window(q)


def validate_slots(card, src_text):
    """闸1：槽位完整 + 长度 + 句数。返回问题列表（空=过）。
    D4：why_zh 必填（Fable D3 审单 ②「3/13 空」根治）；纯长度超标（标题/一句话/为什么）只在
    超 2×上限时废卡——轻度超长由出口 _clamp 词边界收口（D4 修复包的截断即治理路径），
    引句超 QUOTE_LEN_HARD 才废卡（≤此值同理由钳制保逐字前缀性）。"""
    probs = []
    for f in ("title_zh", "one_liner_zh", "quote"):
        if not str(card.get(f, "")).strip():
            probs.append(f"{f} 缺失")
    if not str(card.get("why_zh", "")).strip():
        probs.append("why_zh 缺失")           # D4 必填：无支撑重写，仍缺则整卡降级
    if len(flat(card.get("title_zh", ""))) > TITLE_MAX * 2:
        probs.append("标题超长")
    if len(flat(card.get("one_liner_zh", ""))) > LINER_MAX * 2:
        probs.append("一句话超长")
    if len(flat(card.get("why_zh", ""))) > WHY_MAX * 2:
        probs.append("为什么超长")
    n_sent = _sent_count(card.get("one_liner_zh", "")) + _sent_count(card.get("why_zh", ""))
    if n_sent > SENT_MAX:
        probs.append(f"摘要句数 {n_sent}>{SENT_MAX}")
    if len(flat(card.get("quote", ""))) > QUOTE_LEN_HARD:
        probs.append("引句超长")
    return probs


def _sent_count(text):
    t = flat(text)
    if not t:
        return 0
    return max(1, len([s for s in re.split(r"[。！？!?；;]", t) if s.strip()]))


def gate2_entities(card, src_text):
    """闸2：实体回验。返回未通过逐项列表（空=过）。"""
    misses = []
    for n in card.get("nums", []) or []:
        if n and not verbatim_in(str(n), src_text):
            misses.append(f"num:{n}")
    for o in card.get("orgs", []) or []:
        if o and not verbatim_in(str(o), src_text):
            misses.append(f"org:{o}")
    return misses


def gate4_quote(card, body_text):
    """闸4：引句逐字留痕。D4（Fable D4 审单 ②）：回验基准改对 body（正文摘要），
    不再对 full_source（含标题）——否则 quote=标题永远绿。"""
    q = flat(card.get("quote", ""))
    return bool(q) and verbatim_in(q, body_text)


def gate5_banned(card):
    """闸5：标题党禁用词（标题+摘要）。"""
    return banned_hits(flat(card.get("title_zh", "")) + " " + flat(card.get("one_liner_zh", "")))


def gate6_brand(card):
    """闸6：品牌红线。"""
    fields = [card.get(f, "") or "" for f in ("title_zh", "one_liner_zh", "why_zh", "quote")]
    return brand_violation(*fields)


def process_batch(batch, degrade_log, _depth=0):
    """batch: [{i, title, note, body}] → {i: card} 走完整闸门链。
    每卡附带 gates 留痕：{g1,g2,g3,g4,g5,g6, degraded}
    D4：G4 定向修复——批处理里模型偶发把引句轻度改写（实测单条重问合规率高），
    对仅 G4 失败且有正文的条目单条重问一次（≤12 条/批，_depth=1 不再嵌套）。"""
    src_by_i = {}
    for b in batch:
        src_by_i[b["i"]] = full_source(b)

    raw = call_json(PROCESS_PROMPT.format(banned="/".join(BANNED_WORDS[:8]), items=_fmt_items(batch)),
                    model=MODEL_FLAGSHIP)
    cards = {}
    if isinstance(raw, list):
        for c in raw:
            if isinstance(c, dict) and isinstance(c.get("i"), int):
                cards[c["i"]] = c
    missing = [b["i"] for b in batch if b["i"] not in cards]
    if missing:  # 一次重试：把漏掉的条目单独再要一次
        sub = [b for b in batch if b["i"] in missing]
        raw2 = call_json(PROCESS_PROMPT.format(banned="/".join(BANNED_WORDS[:8]), items=_fmt_items(sub)),
                         model=MODEL_FLAGSHIP)
        if isinstance(raw2, list):
            for c in raw2:
                if isinstance(c, dict) and isinstance(c.get("i"), int):
                    cards[c["i"]] = c

    # 闸1 + 闸5 检查 → 需重写集合
    to_rewrite = []
    for b in batch:
        c = cards.get(b["i"])
        if c is None:
            continue
        c["_g1"] = validate_slots(c, src_by_i[b["i"]])
        c["_g5"] = gate5_banned(c)
        if c["_g1"] or c["_g5"]:
            to_rewrite.append(b)
    if to_rewrite:
        lines = [f'{b["i"]}|{flat(cards[b["i"]].get("title_zh",""))}|'
                 f'{flat(cards[b["i"]].get("one_liner_zh",""))}|{flat(cards[b["i"]].get("why_zh",""))}'
                 for b in to_rewrite if b["i"] in cards]
        raw3 = call_json(REWRITE_PROMPT.format(items="\n".join(lines)), model=MODEL_FLAGSHIP)
        if isinstance(raw3, list):
            for c in raw3:
                if isinstance(c, dict) and isinstance(c.get("i"), int) and c["i"] in cards:
                    old = cards[c["i"]]
                    if c.get("title_zh"):
                        old["title_zh"] = c["title_zh"]
                    if c.get("one_liner_zh") is not None:
                        old["one_liner_zh"] = c["one_liner_zh"]
                    if c.get("why_zh") is not None:      # D4：why 缺失也走重写补齐
                        old["why_zh"] = c["why_zh"]
                    old["_rewritten"] = True

    # 闸2 + 闸4 + 闸6（重写后终检；G4 基准=body，D4）
    for b in batch:
        c = cards.get(b["i"])
        if c is None:
            continue
        src = src_by_i[b["i"]]
        c["_g1"] = validate_slots(c, src)
        c["_g5"] = gate5_banned(c)
        c["_g2"] = gate2_entities(c, src)
        c["_g4"] = gate4_quote(c, flat(b.get("body", "")))
        c["_g6"] = gate6_brand(c)

    # D4 G4 定向修复：仅 G4 失败（其余闸干净）且有像样正文的，单条重问一次
    if _depth == 0:
        for b in batch:
            c = cards.get(b["i"])
            if (c is None or c.get("_g1") or c.get("_g2") or c.get("_g5") or c.get("_g6")
                    or c.get("_g4") or len(flat(b.get("body", ""))) < 120):
                continue
            try:
                sub_cards, _ = process_batch([b], [], _depth=1)
            except Exception:
                continue
            cc = sub_cards.get(b["i"])
            if cc and not cc.get("_g1") and not cc.get("_g2") and cc.get("_g4") \
                    and not cc.get("_g5") and not cc.get("_g6"):
                cc["_g4_retried"] = True
                cards[b["i"]] = cc

    return cards, src_by_i


def self_check(cards, src_by_i, batch):
    """闸3：二遍自查（同模型二次调用）。返回 {i: [无依据陈述]}。"""
    lines = []
    for b in batch:
        c = cards.get(b["i"])
        if not c:
            continue
        lines.append(f'序号{b["i"]} 原文：{src_by_i[b["i"]]}\n'
                     f'中文卡：标题={flat(c.get("title_zh",""))}；一句话={flat(c.get("one_liner_zh",""))}；'
                     f'为什么={flat(c.get("why_zh",""))}')
    if not lines:
        return {}
    raw = call_json(CHECK_PROMPT.format(cards="\n\n".join(lines)), model=MODEL_FLAGSHIP)
    flags = {}
    if isinstance(raw, list):
        for f in raw:
            if isinstance(f, dict) and isinstance(f.get("i"), int):
                flags[f["i"]] = f.get("bad") or ["未具体说明的无依据陈述"]
    return flags


def degrade_card(b, mode, reason, degrade_log):
    """降级链。mode: 'translate'=直译标题卡；'raw'=无卡兜底。
    Fable 复审修复 #1：降级条目 title_zh 一律置空（不再塞原文截断冒充中文标题），
    建站组按契约 title_src 字段回退显示原文标题。"""
    src_title = flat(b["title"])
    if mode == "translate":
        try:
            raw = call_json(TRANSLATE_PROMPT.format(title=src_title), model=MODEL_FLAGSHIP)
            t = flat(raw.get("title_zh", "")) if isinstance(raw, dict) else ""
        except Exception:
            t = ""
        if t and not banned_hits(t) and len(t) <= TITLE_MAX + 2:
            card = {"i": b["i"], "title_zh": t, "one_liner_zh": "", "why_zh": "",
                    "nums": [], "orgs": [], "quote": src_title[:QUOTE_MAX]}
        else:
            card = {"i": b["i"], "title_zh": "", "one_liner_zh": "", "why_zh": "",
                    "nums": [], "orgs": [], "quote": src_title[:QUOTE_MAX]}
    else:
        card = {"i": b["i"], "title_zh": "", "one_liner_zh": "", "why_zh": "",
                "nums": [], "orgs": [], "quote": src_title[:QUOTE_MAX]}
    card["_degraded"] = mode
    card["_degrade_reason"] = reason
    degrade_log.append({"i": b["i"], "title_src": src_title[:80], "mode": mode, "reason": reason})
    return card


def finalize(c, b, src_by_i):
    """出口统一：长度收口 + 最终留痕字段。
    D6 §2：标题不再就地钳制加省略号——先按 2×上限保底截断（无省略号），真正的重写/句读截断/
    title_src 回退由 管线.resolve_titles_pass 在加工完成后统一做。
    D7 §1：一句话/why 走完整性钳制（clamp_no_ellipsis）——切不出完整段整段丢弃并 gates 留痕
    （liner_complete_discard / why_complete_discard，管线据此拦出精选）。"""
    liner = clamp_no_ellipsis(c.get("one_liner_zh", ""), LINER_MAX)
    why = clamp_no_ellipsis(c.get("why_zh", ""), WHY_MAX)
    out = {
        "i": c.get("i"),
        "title_zh": strip_trailing_ellipsis(_clamp(c.get("title_zh", ""), TITLE_MAX * 2, ellipsis=False)),
        "one_liner_zh": liner,
        "why_zh": why,
        "nums": [str(x) for x in (c.get("nums") or [])][:8],
        "orgs": [str(x) for x in (c.get("orgs") or [])][:8],
        "quote": _clamp(c.get("quote", ""), QUOTE_MAX, ellipsis=False),  # 逐字性：截断不加省略号
    }
    out["gates"] = {
        "g1_slots": not c.get("_g1"),
        "g2_entities": not c.get("_g2"),
        "g3_selfcheck": not c.get("_g3"),
        "g4_quote": c.get("_g4", False),
        "g5_banned": not c.get("_g5"),
        "g6_brand": not c.get("_g6"),
        "degraded": c.get("_degraded"),
    }
    if flat(c.get("one_liner_zh", "")) and not liner:
        out["gates"]["liner_complete_discard"] = "一句话完整性闸整段丢弃（悬空残句不得外发，Fable 终审）"
    if flat(c.get("why_zh", "")) and not why:
        out["gates"]["why_complete_discard"] = "why 完整性闸整段丢弃（悬空残句不得外发，Fable 终审）"
    return out


def needs_degrade(c):
    """任一硬闸失败 → 必须降级。"""
    return bool(c.get("_g1") or c.get("_g2") or not c.get("_g4") or c.get("_g6") or c.get("_g5"))
