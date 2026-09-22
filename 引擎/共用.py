#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 共用工具 —— 模型调用(DeepSeek 官方 API,2026-09-19 起替代 arkcli/GLM)、时区、URL 规范化、文本闸门、缓存
# D1 内部打通日 · 打分宪法 v3 配套
# 铁律：内部一律 UTC，渲染一律 UTC+8；对外产物零「AIHot」字样
import json, os, re, shutil, subprocess, time, hashlib, hashlib as _hl
import urllib.request as _urlreq, urllib.error as _urlerr
import html as _html
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
# Actions 云端化（Fable 审 B1/S1，2026-09-17）：DATA_DIR/WORK/RADAR 三路 env 覆盖，缺省=Mac 原值
# 零行为变化。B1 病根：CI 里 PROJ==仓根==AI_NEWS_PUB，DATA_DIR 若不挪走会与线上 data/ 塌缩成同一
# 目录——管线把新契约直接写进线上文件，发布链 prev_selected_count 读到的「上轮」变成本轮，产物闸
# （精选 ≥上轮-2）恒真失效。CI 把 DATA_DIR 指到仓内被 gitignore 挡住的 data/引擎产物/契约/
# （引擎产出走发布链 staging 拷入线上，恢复「旧站原样」语义）。ENGINE_HEARTBEAT 随 DATA_DIR 走。
DATA_DIR = os.environ.get("AI_NEWS_DATA", os.path.join(PROJ, "data"))   # 契约输出目录（建站组消费）
WORK = os.environ.get("AI_NEWS_WORK", os.path.join(PROJ, "产物"))       # 中间产物与证据
CACHE_FILE = os.path.join(WORK, "模型缓存.json")

# S1：心跳.py 读 RADAR 根的 heartbeat.json——CI 无 ~/ai-radar，雷达副本在仓内 雷达/ 自写心跳
RADAR = os.environ.get("AI_NEWS_RADAR", os.path.expanduser("~/ai-radar"))
# D5 §3/补验收：RADAR_DATA 允许环境变量覆盖——网络/通道故障降级演示走真实代码路径，
# 不 mock 内部函数（Fable D5 裁决 v2-4）。缺省值与 D1-D4 完全一致。
RADAR_DATA = os.environ.get("AI_NEWS_RADAR_DATA", os.path.join(RADAR, "data"))

# 2026-09-19 军令：火山 arkcli 弃用（STS 9-18 过期失效），全线切 DeepSeek 官方 API。
# 两档型号实测名单（/models 2026-09-19）：deepseek-v4-pro（旗舰）、deepseek-flash（快档）。
# 两档同为思考型：max_tokens 须留足思考+正文额度，过小会 content 空（Hy4 同款坑）。
DEEPSEEK_URL = os.environ.get("AI_NEWS_DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
# 2026-09-22 小茜军令「V4.1 flash 一定只能用这个」：全线只走 deepseek-flash（弹药库 ledger 实锤 wire 名 deepseek-flash＝DeepSeek-V4.1-Flash）。
# v4-pro 不再调用；要回退只改这一行。
MODEL_FLAGSHIP = "deepseek-flash"    # 五维打分 / 中文加工 / 二遍自查（原 deepseek-v4-pro，9-22 起改 flash）
MODEL_FLASH = "deepseek-flash"       # 预筛（是否 AI 相关）/ 三语翻译

def _deepseek_key():
    """env 优先（CI/手跑）；launchd 无人值守从钥匙串 arsenal/deepseek-api 现取，零明文落盘。"""
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", "arsenal/deepseek-api", "-w"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

# 2026-09-22 小茜军令「¥49.91 是全部预算」：每轮跑前查余额，低于地板只发心跳不调模型。
# 钥匙在进程内取（_deepseek_key），余额只记金额不记钥匙——日志/心跳/仓里永不出现 key。
DEEPSEEK_BALANCE_URL = os.environ.get("AI_NEWS_DEEPSEEK_BALANCE_URL", "https://api.deepseek.com/user/balance")
BUDGET_FLOOR_CNY = float(os.environ.get("AI_NEWS_BUDGET_FLOOR_CNY", "10"))


def deepseek_balance(timeout=20):
    """查 DeepSeek 账户余额 → (cny: float|None, why: str)。
    cny=None 表示「查不到」（无钥匙/网络/接口异常）——调用方按未知处理，不当 0 拦停（宁可多跑一轮，
    也不因一次网络抖动把站点冻住；真没钱时 401/402 熔断仍会兜住）。"""
    key = _deepseek_key()
    if not key:
        return None, "无钥匙（env 与钥匙串 arsenal/deepseek-api 皆空）"
    try:
        req = _urlreq.Request(DEEPSEEK_BALANCE_URL, headers={"Authorization": f"Bearer {key}"})
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except _urlerr.HTTPError as e:
        return None, f"http={e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}:{str(e)[:60]}"
    for info in (j.get("balance_infos") or []):
        if (info.get("currency") or "").upper() == "CNY":
            try:
                return float(info.get("total_balance")), ("可用" if j.get("is_available") else "账户不可用")
            except (TypeError, ValueError):
                return None, "余额字段不可解析"
    return None, "返回无 CNY 余额"


CST = timezone(timedelta(hours=8))   # UTC+8 渲染时区（北京时间）

# ---------- 时区：本模块是全项目唯一的时间进出口 ----------
# 病根（D1 确诊）：本机时区 PDT(-0700)，雷达台账/大鱼/heartbeat 用 naive 本地时间写入，
# 回填库 pub 却是 aware UTC。两种时间混存。以下函数统一收口。

def local_tz():
    """运行时探测本机时区（D1 实测为 PDT UTC-0700）。"""
    return datetime.now().astimezone().tzinfo

def to_utc(ts):
    """任意时间戳 → aware UTC datetime。
    - aware：直接转 UTC
    - naive：按本机时区解释（雷达台账的真实语义），再转 UTC
    - None/空：返回 None
    """
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        s = str(ts).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(timezone.utc)

def utc_iso(dt):
    """aware UTC datetime → 'YYYY-MM-DDTHH:MM:SSZ'（台账内部格式）。"""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def to_beijing(dt):
    """aware datetime → 'YYYY-MM-DD HH:MM'（页面渲染用，UTC+8）。"""
    if dt is None:
        return ""
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M")

def to_berlin(dt):
    """aware datetime → 'YYYY-MM-DD HH:MM'（站点口径，Europe/Berlin）。
    德国有夏令时，必须走 IANA 时区而不是固定偏移；zoneinfo 缺席时退回 UTC 并标注，不抛。"""
    if dt is None:
        return ""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") + " UTC"

def beijing_day(dt):
    """aware datetime → 北京日期 'YYYY-MM-DD'（按天分组用）。"""
    if dt is None:
        return ""
    return dt.astimezone(CST).strftime("%Y-%m-%d")

# ---------- URL 规范化（去重第一层） ----------
_TRACK_PARAMS = re.compile(
    r"^(utm_[a-z_]+|ref|referrer|source|spm|from|scid|share_|wt_mc|wt_mc2|mc_cid|mc_eid|"
    r"fbclid|gclid|igshid|campid|trk|trkContact|cli|chksm|cvbt|session_id|nsukey)$", re.I)
_SHORT_HOSTS = {"t.co", "bit.ly", "goo.gl", "ow.ly", "is.gd", "buff.ly", "tinyurl.com"}

def norm_url(url):
    """URL 规范化：小写 host、剥跟踪参数、去尾斜杠、合并默认端口。
    已知短链域直接查雷达短链缓存（不联网）。301 全量解析留给 D2+（报告注明）。"""
    if not url:
        return ""
    u = url.strip()
    cache = _shortlink_cache()
    if u.rstrip("/").lower() in cache:
        u = cache[u.rstrip("/").lower()]
    m = re.match(r"^(https?)://([^/]+)(.*)$", u, re.I)
    if not m:
        return u.lower()
    scheme, host, rest = m.group(1).lower(), m.group(2).lower(), m.group(3)
    host = host.split(":")[0] if host.endswith((":80", ":443")) else host
    if host.startswith("www.") and host.count(".") > 1:
        host = host[4:]
    # 剥跟踪参数
    if "?" in rest:
        path, qs = rest.split("?", 1)
        kept = [kv for kv in qs.split("&") if kv and not _TRACK_PARAMS.match(kv.split("=")[0])]
        rest = path + ("?" + "&".join(kept) if kept else "")
    return f"{scheme}://{host}{rest.rstrip('/') or ''}"

_SC_CACHE = None
def _shortlink_cache():
    global _SC_CACHE
    if _SC_CACHE is None:
        _SC_CACHE = {}
        try:
            with open(os.path.join(RADAR_DATA, "短链缓存.json"), encoding="utf-8") as f:
                _SC_CACHE = {k.lower(): v for k, v in json.load(f).items()}
        except Exception:
            pass
    return _SC_CACHE

def url_id(url):
    """条目稳定 id：规范化 URL 的 md5 前 12 位。"""
    return hashlib.md5(norm_url(url).encode()).hexdigest()[:12]

def host_of(url):
    m = re.match(r"^https?://([^/]+)", url or "", re.I)
    return (m.group(1).lower().replace("www.", "") if m else "")

# ---------- 文本工具 ----------
_WS = re.compile(r"\s+")

def flat(s):
    return _WS.sub(" ", (s or "")).strip()

# ---------- HTML 剥离（D4 修复包：转义循环至稳定 + 行内/块标签区分） ----------
# 病根（Fable 三审 ② / D3 遗留）：
#   1. 双重/多重转义（&amp;lt;）固定两遍解不净；固定顺序还会把「a &lt; b」里解出的裸 < 连同
#      后文到 > 之间整段当标签剥掉。
#   2. 所有标签一律替换为空格，造成「set ( ANTHROPIC_BASE_URL ) to」类空格伪迹——
#      <code> 是行内标签，本该替换为空串。
# D4 方案：循环「解实体→剥标签」直到稳定（≤3 轮），标签分三档：
#   行内标签（code/em/a/span…）→ 空串；块标签（p/div/li/h*…）→ 空格；其余 → 空格。
# 标签识别用 </?[A-Za-z!][^>]*>：'<' 后必须紧跟字母或 '!' 才算标签形态，
# 「a < b」「5 < 10」里的裸 <（后随空格/数字）永不被剥（Fable 反例单测锚点）。
_INLINE_TAG = re.compile(
    r"</?(?:a|abbr|b|bdi|bdo|cite|code|data|dfn|em|font|i|kbd|mark|picture|rb|rp|rt|ruby|"
    r"s|samp|small|source|span|strong|sub|sup|time|u|var|wbr)\b[^>]*/?>", re.I)
_BLOCK_TAG = re.compile(
    r"</?(?:address|article|aside|blockquote|body|br|button|caption|dd|details|div|dl|dt|"
    r"fieldset|figcaption|figure|footer|form|h[1-6]|header|hr|label|legend|li|main|menu|nav|"
    r"ol|optgroup|option|p|pre|section|select|summary|table|td|tfoot|th|thead|tr|ul)\b[^>]*/?>", re.I)
_ANY_TAG = re.compile(r"</?[A-Za-z!][^>]*>")
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)

def _strip_tags_once(t):
    t = _INLINE_TAG.sub("", t)
    t = _BLOCK_TAG.sub(" ", t)
    t = _ANY_TAG.sub(" ", t)
    return t

def strip_html_stable(s, max_rounds=3):
    """CDATA/HTML/多重转义 → 纯文本。循环「解实体→剥标签」至稳定（≤max_rounds 轮）。
    反例保护：正文合法的「a < b」类裸小于号（含 &lt; 解出者）不被当标签剥掉。"""
    t = _CDATA.sub(r"\1", s or "")
    for _ in range(max_rounds):
        new = _strip_tags_once(_html.unescape(t))
        if new == t:
            break
        t = new
    return flat(t)

_DASHES = {chr(c): "-" for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212, 0xFF0D)}  # ‐‑‒–—−－ → -
_QUOTES = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
           "\u2033": '"', "\u2032": "'", "\u00ab": '"', "\u00bb": '"', "`": "'"}  # 弯引号 → ASCII

def norm_for_match(s):
    """实体回验用的宽松规范化：压空白、统一大小写、全角数字→半角、
    各类横线（U+2010/2011/2012/2013/2014/2212/FF0D）→ASCII、弯引号→ASCII。
    （Fable 复审修复 #3：原文排版字符不得造成实体回验误杀——GPT‑Live‑1 的 U+2011 实证案例）"""
    s = flat(s).lower()
    trans = str.maketrans("０１２３４５６７８９％．：，", "0123456789%.:,")
    s = s.translate(trans)
    for k, v in {**_DASHES, **_QUOTES}.items():
        s = s.replace(k, v)
    return s

def verbatim_in(needle, haystack):
    """G2/G4 共用：规范化后逐字子串比对。"""
    return norm_for_match(needle) in norm_for_match(haystack)

def tokens_en(title):
    """英文/德文标题 token 集。连字符/点连接的字母数字串视为一个 token
    （保住 GPT-6 / gpt-6.1 / v2.1.272 这类版本号，防版本号被切碎后误合并）。"""
    return set(w for w in re.findall(r"[a-z0-9][a-z0-9._-]*[a-z0-9]|[a-z0-9]+", (title or "").lower())
               if len(w) >= 2)

def versions_of(title):
    """标题里的版本号集合（数字串，含 x.y / x 形态）——版本号不同=不同事件。"""
    return set(re.findall(r"\d+(?:\.\d+)*", title or ""))

def tokens_zh(title):
    """中文标题字符 bigram 集（含穿插的英文 token）。"""
    s = re.sub(r"\s+", "", title or "")
    grams = set()
    for i in range(len(s) - 1):
        if re.match(r"[\u4e00-\u9fff]", s[i]):
            grams.add(s[i:i+2])
    return grams | tokens_en(title)

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

# ---------- 闸门：禁用词 + 品牌红线（代码强制，不靠提示词自觉） ----------
BANNED_WORDS = [
    "炸裂", "震惊", "颠覆", "秒杀", "王炸", "一夜之间", "彻底改变", "最强",
    "重磅", "逆天", "屠榜", "碾压", "史诗级", "疯狂", "暴击", "吊打", "血洗", "变天",
]
BANNED_RE = re.compile("|".join(BANNED_WORDS))

BRAND_BAN_RE = re.compile(r"aihot", re.I)   # 品牌红线：对外零 AIHot 字样（含域名）

# D7 第二刀：客户案例特征清洗（学对方 aihot 的 OpenAI 源清洗——客户案例属「行业」类，
# 对方不在精选层重，本线对账同款处理：命中 → 降级 + gates.case_story 留痕，不外发精选）
# 适用域：OpenAI/Anthropic 厂商官方源；其他源按相同规则（如适用）
CASE_STORY_RE = re.compile(
    r"customer\s*stor(y|ies)|case\s*stud(y|ies)|客户案例|"
    r"如何.{0,8}(公司|企业|团队|团队|机构).{0,4}(用|使用|选用|部署|搭建)|"
    r"how\s+\w+\s+(built|saved|uses?|accelerated|transformed)",
    re.I)

CASE_STORY_DOMAINS = ("openai.com", "anthropic.com")  # 这两家是案例重灾区


def case_story_hit(title, url=""):
    """D7 第二刀：客户案例特征命中？返回 (是否命中, 触发域)。"""
    text = (title or "") + " " + (url or "")
    if not CASE_STORY_RE.search(text):
        return False, None
    host = host_of(url or "")
    for d in CASE_STORY_DOMAINS:
        if host.endswith(d):
            return True, d
    return False, None

def banned_hits(text):
    return sorted({w for w in BANNED_WORDS if w in (text or "")})

def brand_violation(*texts):
    """任一对外文本含 aihot 字样 → True（整条丢弃或拦截）。"""
    return any(BRAND_BAN_RE.search(t or "") for t in texts)

# ---------- 模型调用（DeepSeek 官方 API · 2026-09-19 起） ----------
# 思考型型号：max_tokens 须含思考额度，过小会正文为空（实测 flash 思考 ~190 tokens/条）。
# json_schema 服务端不强制，沿用宽松解析（extract_json）+ 形状校验 + 重试轨道。

class ModelUnavailable(Exception):
    pass

def _cache_load():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _cache_save(c):
    os.makedirs(WORK, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)

def extract_json(text):
    """从模型输出里剥出第一个完整 JSON 对象/数组（容忍 markdown 围栏与前后闲话）。
    从全文最早出现的 { 或 [ 起算（防内层对象抢先命中）。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    pairs = {"{": "}", "[": "]"}
    pos = {o: t.find(o) for o in pairs}
    starts = [(p, o) for o, p in pos.items() if p != -1]
    if not starts:
        return None
    start, opener = min(starts)
    closer = pairs[opener]
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i+1])
                except Exception:
                    break
    return None

# 2026-09-22 Fable 止血：401/402（鉴权/余额）是账户级致命错误，重试和退避只会把整轮拖过 3600s 超时
# （9-21～22 停摆真根因：DeepSeek 余额 0 → 每批 3 连败×退避 250s → 整轮超时 → 契约不写 → 站点冻结）。
# 首次命中即熔断：本进程内后续调用不再发网络请求，直接抛 ModelUnavailable 让管线走既有降级路径，一轮 40 分钟内跑完。
_FUSE = {"why": None}

def call_model(prompt, model=MODEL_FLAGSHIP, effort="low", timeout=300,
               retries=3, use_cache=True, validator=None, max_tokens=None, think=None):
    """调用 DeepSeek。返回纯文本 content。
    - 缓存：同 (model,prompt,think) 直接复用（中断重跑不重复吃额度）
    - 重试：指数退避 10s/60s/180s；3 连败抛 ModelUnavailable（管线降级模式兜底）
    - max_tokens 缺省按档：flash 9000 / 旗舰 12000（思考型，额度=思考+正文共享）
    - think=False → thinking disabled（二元判断/短翻译提速 10 倍，9-19 实测 completion 1 token）
    - think=None → 读 env AI_NEWS_THINK（缺省"1"=开思考；首轮全量快跑用 =0——9-19 军令赶早，
      思考开关质量差实测：打分 ±1-2 分、分类边界少量波动，质量闸 g1-g7 不受影响）
    - effort 仅为缓存 key 兼容保留，不发给 API"""
    key = _hl.md5((model + "||" + effort + "||" + str(think) + "||" + prompt).encode()).hexdigest()
    cache = _cache_load()
    if use_cache and key in cache:
        return cache[key]
    api_key = _deepseek_key()
    if not api_key:
        raise ModelUnavailable("DEEPSEEK_API_KEY 不在 env 也不在钥匙串 arsenal/deepseek-api")
    if _FUSE["why"]:
        raise ModelUnavailable(f"模型熔断中（本进程不再调用）：{_FUSE['why']}")
    if think is None:
        think = os.environ.get("AI_NEWS_THINK", "1") != "0"
    if max_tokens is None:
        # 思考型实测：20 条批量预筛的思考链可达 3000+ tokens——额度宁宽勿紧（只按实际用量计费）
        max_tokens = 9000 if "flash" in model else 12000
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    if think is False:
        payload["thinking"] = {"type": "disabled"}
    body = json.dumps(payload).encode()
    last_err = None
    for attempt in range(retries):
        try:
            req = _urlreq.Request(DEEPSEEK_URL, data=body, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"})
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                j = json.loads(resp.read().decode("utf-8"))
            content = (((j.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            content = content.strip()
            if content:
                if use_cache:
                    cache[key] = content
                    _cache_save(cache)
                return content
            last_err = f"empty-content(max_tokens={max_tokens} 被思考吃满)"
        except _urlerr.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")[:200]
            except Exception:
                detail = ""
            last_err = f"http={e.code} {detail}"
            if e.code in (401, 402):
                _FUSE["why"] = f"http={e.code} {detail[:90]}"
                raise ModelUnavailable(f"模型调用致命 [{model}] last={last_err}（鉴权/余额类错误：本进程熔断，不再重试）")
        except Exception as e:
            last_err = f"{type(e).__name__}:{str(e)[:120]}"
        time.sleep([10, 60, 180][min(attempt, 2)])
    raise ModelUnavailable(f"模型调用 {retries} 连败 [{model}] last={last_err}")

def call_json(prompt, model=MODEL_FLAGSHIP, **kw):
    """call_model + 宽松 JSON 提取。失败返回 None（调用方走降级）。"""
    txt = call_model(prompt, model=model, **kw)
    return extract_json(txt)

# ---------- 总分公式（纯代码，宪法 v3 §公式） ----------
def total_score(dims, weights, tier_coef):
    """五维加权(各 1-10) × 信源等级系数 → 0-100。dims 缺维按 5 中性处理。"""
    s = 0.0
    for k, w in weights.items():
        s += (dims.get(k) or 5) * w
    return round(min(100.0, s * 10 * tier_coef), 1)

def rush_score(beat_hours, is_primary, fresh_placeholder):
    """窗口分档映射（纯函数，抢跑维条欂数值）：
    一手源：≤2h=10(突发) ≤4h=9(官方) ≤5h=8(研究) ≤24h=6 >24h=4
    二手源：基准 4（不抢跑，靠覆盖）
    fresh 占位条目（真实 pub 未知）：6 中性，beat_hours=null
    D3 #3 注意：抢跑维入口是 item_rush（吃 scoop_hours）；
    本函数的 beat 形参不再由 detection_delay_hours 喂入。"""
    if fresh_placeholder or beat_hours is None:
        return 6
    if not is_primary:
        return 4
    if beat_hours <= 2:
        return 10
    if beat_hours <= 4:
        return 9
    if beat_hours <= 5:
        return 8
    if beat_hours <= 24:
        return 6
    return 4


def item_rush(scoop_hours, tier, fresh_placeholder):
    """D3 #3：抢跑维与 detection_delay_hours 脱钩（Fable 审单 ②-1）。
    检测延迟（我们多晚逮到）不是抢跑证据，不得当抢跑加分喂进打分——改名未改用法的病根。
    真正的抢先证据只有多源簇的 scoop_hours（官方 T1 早于二手媒体被逮到的领先小时数）：
    - 单源簇 / 缺数据 → 中性 6（无证据不主张）
    - 负 scoop（媒体先于官方逮到）→ 官方无抢先，同样中性 6
    - 二手源（非 T1）→ 基准 4
    - 一手源 → 按 scoop 窗口分档（复用 rush_score 条款）"""
    if fresh_placeholder or scoop_hours is None or scoop_hours < 0:
        return 6
    if tier != "T1":
        return 4
    return rush_score(scoop_hours, True, False)

def heat_score(score, age_hours, n_sources):
    """热度代理值 0-100 = 宪法分 × 时间衰减 × 多源命中。
    衰减：24h 内 1.0 → 7 天 0.3 线性；多源：1 + 0.1×(n-1)。"""
    if age_hours is None:
        age_hours = 48.0
    decay = max(0.3, 1.0 - (age_hours / 168.0) * 0.7)
    return round(min(100.0, score * decay * (1 + 0.1 * max(0, n_sources - 1))), 1)

def load_profile(name):
    with open(os.path.join(BASE, f"scoring.{name}.json"), encoding="utf-8") as f:
        return json.load(f)

# ---------- 精选判定（Fable 审单修复 #1/#4：精选必须接闸门出口，降级/quick/未加工一律不精选） ----------
_GATE_KEYS = ("g1_slots", "g2_entities", "g3_selfcheck", "g4_quote", "g5_banned", "g6_brand")

def gates_all_green(gates):
    """六道闸全绿才过。quick 冒烟 / 未加工 / 降级 / 任一闸 False → 不绿。"""
    g = gates or {}
    if g.get("quick") or g.get("unprocessed") or g.get("degraded"):
        return False
    return all(g.get(k) is True for k in _GATE_KEYS)

# D3 #1 精选硬闸（Fable 审单 ④「唯一要务」）：代码判，不靠 prompt 自觉。
# 判据实测校准（data/精选库.json 2026-09-16 D2 版全量回放）：
#   健康精选卡 one_liner↔标题 Jaccard 上限 0.476；标题复读带 ≥0.62（APXInf 病样=1.0）。
#   0.6 取健康带与复读带之间的空隙。
REPEAT_JACCARD_MAX = 0.6

# D4 正文分级（Fable D4 审单 ①：硬闸一刀切「只认 page」会在 openai.com 403 下清空首屏）：
#   page     = 页面抽取成功且 ≥PAGE_MIN 字（正文抽取器）
#   rss_full = RSS 自带摘要 ≥RSS_FULL_MIN 字（content:encoded 全文流，如 GitHub Atom/
#              MarkTechPost；不必抓页）
#   rss_teaser = 有摘要但不够长（openai.com 一句 teaser 即此类）
#   none     = 无任何正文
# 精选硬闸只认前两级——teaser/none 不得进精选（回应「OpenAI 一句 teaser 就过」）。
# D5 §1 擦线治理（Fable D5 裁决 v2-1，规则制无白名单）：
#   - 尾「…」永不算 rss_full：RSS 摘要尾部窗口内出现省略号（含「… Source」类尾巴）= 截断
#     teaser（D4 病样：NVIDIA 三张 405/406/403 字、尾「…Source」擦线过闸）。
#   - 非熔断域一律先抓页（正文抽取器.enrich 规则制）；页失败才允许 rss_full 兜底。
RSS_FULL_MIN = 400
PAGE_MIN = 400
BODY_SOURCE_PASS = ("page", "rss_full")

_ELLIPSIS = re.compile(r"\u2026|\.\.\.")          # … / ...
_ELLIPSIS_WINDOW = 64                             # 长度窗：只查尾部窗口（Fable：尾部「…」检测+长度窗校验）

def rss_is_truncated(text, window=_ELLIPSIS_WINDOW):
    """D5：RSS 摘要尾部窗口内出现省略号 → 截断 teaser，永不算 rss_full。
    窗口只看尾部（最后 window 字符），中部合法省略号不误伤。"""
    t = (text or "").rstrip()
    if not t:
        return False
    return bool(_ELLIPSIS.search(t[-window:]))

def classify_body_source(rss_len, page_len=0, rss_truncated=False):
    """四级正文分级（D4 审单 ① + D5 擦线）。rss_len/page_len 为各自文本长度；
    rss_truncated=尾部省略号截断（D5：截断 teaser 永不算 rss_full）。"""
    if page_len >= PAGE_MIN:
        return "page"
    if rss_len >= RSS_FULL_MIN and not rss_truncated:
        return "rss_full"
    if rss_len > 0 or page_len > 0:
        return "rss_teaser"
    return "none"

def one_liner_repeat(one_liner, title_src, title_zh=""):
    """one_liner 与标题的相似度（0-1）：tokens_zh（中文 bigram+英文 token）Jaccard，
    对原文标题与中文标题取最大。≥ REPEAT_JACCARD_MAX 判标题复读。
    空 one_liner 视为完全复读（交由上层非空检查拦截）。"""
    if not one_liner:
        return 1.0
    a = tokens_zh(one_liner)
    j = 0.0
    for t in (title_src or "", title_zh or ""):
        if t:
            j = max(j, jaccard(a, tokens_zh(t)))
    return j

def hard_gate_reasons(body_source, one_liner_zh, title_src, title_zh=""):
    """D4（Fable D4 审单 ②）：硬闸失败原因——记全部，不再只记第一个。
    返回原因列表（空=过硬闸）：no_body:<level> / title_repeat。"""
    reasons = []
    if body_source not in BODY_SOURCE_PASS:
        reasons.append(f"no_body:{body_source or 'none'}")
    if one_liner_repeat(one_liner_zh, title_src, title_zh) >= REPEAT_JACCARD_MAX:
        reasons.append("title_repeat")
    return reasons

def decide_selected(score, category, gates, title_zh, thresholds, one_liner_zh="",
                    body="", title_src="", body_source=None):
    """selected = 过闸全绿 AND 中文标题在 AND 一句话是中文 AND 总分 ≥ 分类目阈值
    AND D3/D4 精选硬闸：正文分级达 page/rss_full AND one_liner 不是标题复读。
    body_source 未显式给出时按 body 长度推断（rss_full ≥400 / teaser / none；
    单测与回放的简化入口，真跑由管线传实测分级）。"""
    if body_source is None:
        body_source = classify_body_source(len((body or "").strip()))
    g = gates or {}
    # D7 第二刀：客户案例特征命中 → 不参选（学对方 aihot 对 OpenAI 源剔除客户案例的做法）
    if g.get("case_story"):
        return False
    return (bool(title_zh) and bool(one_liner_zh) and gates_all_green(g)
            and score >= thresholds.get(category, 55)
            and not hard_gate_reasons(body_source, one_liner_zh, title_src, title_zh))

def decide_big_fish(selected, score, tier, big_fish_cfg):
    """T1 大鱼待确认：已精选 + 指定等级 + 分数过线 → 进待确认队列（不进首屏）。"""
    return bool(selected) and tier in big_fish_cfg["tiers"] and score >= big_fish_cfg["min_score"]

# ---------- D5 §1 补丁卡判定（Fable D5 裁决：regex 必须排除模型名） ----------
# 病样：Claude Code v2.1.272 / v2.1.269——版本流水卡占精选首屏（D4 审：3/17 是 CC 补丁卡）。
# 反例保护：「GPT-6」「Claude 5.1」「Gemini 3.8」「Qwen3.8」都含版本号，但是主角模型名，不降权。
# 判据：三段及以上版本号（x.y.z，模型名从不带三段）或补丁关键词；
#       且版本号不紧跟模型家族名（belt and braces——即使未来出现三段模型名也不误杀）。
_PATCH_VERSION = re.compile(r"\bv?\d+\.\d+\.\d+(?:\.\d+)*\b")
_MODEL_BEFORE_VER = re.compile(
    r"(gpt|claude|gemini|llama|qwen|glm|deepseek|kimi|grok|mistral|mixtral|doubao|ernie|"
    r"hunyuan|seed|nova|o\d|sonnet|opus|haiku|flash|pro|ultra|mini|nano)\s*[-.]?\s*$", re.I)
_PATCH_WORDS = re.compile(r"\b(patch|hotfix|bugfix|changelog|maintenance release)\b|补丁|热修复", re.I)

def is_patch_card(title):
    """D5：补丁/版本流水卡判定（含模型名排除）。True=不计多样性+排序降权。"""
    t = flat(title)
    if not t:
        return False
    if _PATCH_WORDS.search(t):
        return True
    for m in _PATCH_VERSION.finditer(t):
        start = m.start()
        # 版本号若紧跟模型家族名（GPT-2.1.3 这类未来形态）→ 不算补丁卡
        if not _MODEL_BEFORE_VER.search(t[:start]):
            return True
    return False

# ---------- D5 §1 单域上限（代码级，Fable D5 裁决：域集中用上限治，不降阈值线） ----------
DOMAIN_CAP = 3

def apply_domain_cap(entries, cap=DOMAIN_CAP, sort_key=None):
    """单域上限：按（分数降序）逐条放行，每域最多 cap 张精选；超限 selected=False
    留全流（gates.domain_cap 留痕）。entries 为契约条目（就地修改），返回被降为全流的条目数。
    大鱼待确认应在调用本函数之后再判（被 cap 的条目不再是大鱼）。"""
    order = sorted(entries, key=sort_key or (lambda e: -e.get("score", 0)))
    per_host, demoted = {}, 0
    for e in order:
        if not e.get("selected"):
            continue
        h = host_of(e.get("url", ""))
        if not h:
            continue
        per_host[h] = per_host.get(h, 0) + 1
        if per_host[h] > cap:
            e["selected"] = False
            e.setdefault("gates", {})["domain_cap"] = f"{h} 第 {per_host[h]} 张（单域上限 {cap}）"
            demoted += 1
    return demoted

# ---------- D5 §3 原子写 / 输入快照 / 自加锁（无人值守三件套） ----------
def write_json_atomic(path, obj):
    """tmp + os.replace 原子写（Fable D5 裁决 v2-3：精选库/心跳绝不半写——
    读者要么看到旧版要么看到新版，永远不会看到撕裂的半个 JSON）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def snapshot_json(src, max_retry=3, wait=1.5):
    """D5 §3：台账/回填库先快照再读。原件在雷达地盘、雷达随时可能重写——
    直接读会撞上撕裂写（读到半个文件）。快照失败重试，全部失败兜底直读原件。"""
    snap_dir = os.path.join(WORK, "输入快照")
    os.makedirs(snap_dir, exist_ok=True)
    dst = os.path.join(snap_dir, os.path.basename(src))
    last = None
    for _ in range(max_retry):
        try:
            shutil.copy2(src, dst)
            with open(dst, encoding="utf-8") as f:
                return json.load(f)          # 拷到了但解析失败=源正在被写 → 重试
        except Exception as e:
            last = e
            time.sleep(wait)
    with open(src, encoding="utf-8") as f:   # 兜底：最后一次直读
        return json.load(f)

LOCK_FILE = os.path.join(WORK, "管线.lock")

# D5 §3 引擎心跳（独立落 data/，页脚读雷达+引擎两份——发布侧改动留主线程）
ENGINE_HEARTBEAT = os.path.join(DATA_DIR, "引擎心跳.json")

def write_engine_heartbeat(job="manual", status="ok", exit_code=0, duration_s=None,
                           pipeline_generated_at=None, selected=None, total=None,
                           alert=None, balance_cny=None):
    """引擎心跳写入（原子写）。status: ok | fail；fail 必带 alert。
    balance_cny（2026-09-22）：本轮 DeepSeek 余额快照（人民币元，None=本轮没查到）。"""
    now = datetime.now(timezone.utc)
    hb = {
        "when": now.isoformat(timespec="seconds"),
        "when_beijing": to_beijing(now),
        # 2026-09-22 P3：站点时间口径改柏林。when_beijing 是已公布字段，按 /api/v1
        # 「只增不删、不改含义」的承诺原样留着，柏林时间另起新字段。
        "when_berlin": to_berlin(now),
        "job": job,
        "status": status,
        "exit_code": exit_code,
        "duration_s": duration_s,
        "pipeline_generated_at_utc": pipeline_generated_at,
        "selected": selected,
        "total": total,
        "contract": "data/精选库.json",
        "balance_cny": balance_cny,
        "alert": alert,
        "note": "引擎心跳（D5 独立于雷达 heartbeat.json）；页脚陈旧判定读 when/status",
    }
    write_json_atomic(ENGINE_HEARTBEAT, hb)
    return hb

def update_engine_heartbeat(**fields):
    """把附加字段并进现有引擎心跳（原子写）。心跳不存在/不可读时不新建，返回 None。
    用途：管线自己写完心跳后，无人值守层补记轮后余额等运行期事实。"""
    try:
        with open(ENGINE_HEARTBEAT, encoding="utf-8") as f:
            hb = json.load(f)
    except Exception:
        return None
    hb.update(fields)
    write_json_atomic(ENGINE_HEARTBEAT, hb)
    return hb


@contextmanager
def engine_lock(path=LOCK_FILE, blocking=False):
    """D5 §3 自加锁：防手跑撞定时（两趟管线绝不并发写契约/缓存）。
    非阻塞拿锁失败 → EngineBusy（调用方跳过本轮，绝不排队等待造成叠加写）。"""
    import fcntl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(fd, flags)
    except (BlockingIOError, OSError):
        os.close(fd)
        raise BusyError(f"引擎已在运行（锁 {path}）")
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}".encode())
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

class BusyError(Exception):
    pass

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
