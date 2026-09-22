#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 发布链 —— D6 §1：引擎→门禁→staging 构建→原子换入→agent-git commit→push→归档
# （Fable D6 计划裁决 v2-1 五门禁全量落地）
#
#   链路（全部过才动线上）：
#     数据门禁（4）：精选库 JSON schema 校验 ∧ 品牌闸 0 命中 ∧ 精选 ≥5 ∧ 引擎心跳 status=ok
#     git 状态闸（Fable ⑤-①）：fetch 后 pull --ff-only（上轮 push 失败的自愈路径）∧ 工作树除 data/ 外
#               干净 ∧ HEAD==origin/main（或本地领先=上轮遗留 commit 待带出）∧ 永禁 --force
#     staging 构建：数据拷进 staging 目录 → build.py 先在 staging 构建（不碰线上）
#     产物闸（Fable ⑤-②）：index.html 存在且体积 ≥上轮 70% ∧ 精选卡数 ≥上轮-2 ∧
#               正文与心跳 JSON 无本机路径/密钥（心跳进仓前脱敏相对化）
#     原子换入：os.replace 逐文件换入 发布/（build 失败/commit 失败 → git checkout 复位 data/ 与产物）
#     提交推送：agent-git.py zcode commit（message 带 job/generated_at/闸结果）→ push origin main
#               （ff-only 语义：绝不 --force；push 失败=告警留本地 commit，下轮 pull --ff-only 自愈）
#     归档：换入前把当前线上产物归档 发布/回滚/<UTC时间戳>/（gitignore 默认挡住，本地保留最近 20 版）
#
#   回滚（Fable ⑤-④）：--revert = git revert HEAD 推送（不用 reset；本地归档不算回滚）
#
# 用法：
#   发布链.py --job manual            # 走完整链（手跑显式触发）
#   发布链.py --job cold|hot          # 无人值守自动调用
#   发布链.py --contract <path>       # 验收注入门禁投毒用（默认 data/精选库.json）
#   发布链.py --revert                # 回滚演练：git revert HEAD + push
#   发布链.py --dry-run               # 只跑门禁与 staging 构建，不换入不提交
import argparse, json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import BASE, PROJ, DATA_DIR, WORK, brand_violation, to_beijing

# Actions 云端化（Fable 审 S4/B1，2026-09-17）：PY/PUB 两路 env 覆盖，缺省=Mac 原值零变化。
# CI 里 AI_NEWS_PUB=仓根（站点文件在仓根）；PY 缺省回落 homebrew，再回落当前解释器。
PY = os.environ.get("AI_NEWS_PYTHON") or (
    "/opt/homebrew/bin/python3" if os.path.exists("/opt/homebrew/bin/python3") else sys.executable)
# 9-21 实测修复：仓内副本布局（引擎/ 直接在发布仓根下）时 PROJ 本身就是仓根，
# 旧缺省会拼出 发布/发布 → scan_state_secrets 全部 path-miss 静默跳过（假 0 命中）。
_PUB_DEFAULT = PROJ if os.path.basename(PROJ) == "发布" else os.path.join(PROJ, "发布")
PUB = os.environ.get("AI_NEWS_PUB", _PUB_DEFAULT)
BUILD = os.path.join(PUB, "generator", "build.py")
AGENT_GIT = "/Volumes/X10 Pro/HQ/scripts/agent-git.py"
SRC_CONTRACT = os.path.join(DATA_DIR, "精选库.json")
SRC_HEARTBEAT = os.path.join(DATA_DIR, "引擎心跳.json")
PUB_DATA = os.path.join(PUB, "data")
ROLLBACK_DIR = os.path.join(PUB, "回滚")
PUB_LEDGER = os.path.join(WORK, "发布-台账.jsonl")
ALERT_LOG = os.path.join(WORK, "告警-日志.jsonl")

# 数据门禁：精选下限。2026-09-19 军令轮 5→4：D4 硬闸要求精选卡必须真正文（page/rss_full），
# arxiv/HF 高密度窗 teaser 占比高时全绿 710 条精选仅 4——属「硬闸严把质量」非数据病。
# 同日军令轮再校准 4→3：换 DeepSeek 打分器后分布重排，精选=「过闸全绿 ∧ ≥62 ∧ why 必填」
# 三约束的真实水位为 3（实测两张 64/66.5 高分卡被加工质量闸拦 why/quote——质量闸宁缺毋滥
# 的正当结果，非数据不健康）；正文供给已修（arxiv 官方 API 全摘要 455→1300+ 字符）。
# 0-2 条仍拦（真数据病/模型掉线形态：降级条目不参选，故障时精选=0）。
MIN_SELECTED = 3
INDEX_SIZE_FLOOR = 0.70     # 产物闸：新 index ≥上轮 70%
SELECTED_DROP_MAX = 2       # 产物闸：精选卡数 ≥上轮-2
KEEP_ROLLBACKS = 20         # 本地归档保留版数
# 2026-09-22 P1：agent 可接入层四件（feed/llms/agents 页/api 三件）随 LIVE 一起换入、归档、
# 进 staged 范围闸——「版本号进路径，接口一旦公布不破坏」，所以路径写死在这里，改要开 v2。
LIVE_FILES = ("index.html", "about.html", "404.html", "assets/style.css", "assets/app.js",
              "agents/index.html", "feed.xml", "llms.txt",
              "api/v1/latest.json", "api/v1/sources.json", "api/v1/heartbeat.json")
SRC_SOURCES = os.path.join(DATA_DIR, "信源登记.json")   # 信源对账.py 产出，build 的旁料（不换入）
SITE_DOMAIN = "news.aiimmigrant.de"   # M3（Fable 9-21 v2 审）：push 前断言 HEAD 树 CNAME 必等于此常量，不读 env

# ---------- Actions 云端化 · CI 模式（Fable 审 §7-1 GO + S4，2026-09-17） ----------
# AI_NEWS_CI_MODE = shadow（推 ci/shadow-<ts> 分支 + 开 PR 不碰 main）/ live（推 origin main）。
# 铁律三护：
#   ① 只在 AI_NEWS_CI=1 ∧ GITHUB_ACTIONS=true 同时成立才激活（Mac 误设 CI_MODE → 拒跑，
#     防绕过 agent-git 署名铁律——S4 保险是 §7-1 GO 的组成部分）；
#   ② CI 提交身份 = github-actions[bot]（Actions 自身主体，非 ZCode 的 git commit）；
#      Mac 路径（不设这组 env）逐字节走 agent-git wrapper + ZCode 双验，原样不动；
#   ③ 发布台账记 author 与 trigger（trigger 由 AI_NEWS_TRIGGER=ci 传入），审计可分账。
CI_MODE = (os.environ.get("AI_NEWS_CI_MODE") or "").strip().lower() or None
CI_ACTIVE = bool(CI_MODE) and os.environ.get("AI_NEWS_CI") == "1" \
    and os.environ.get("GITHUB_ACTIONS") == "true"
CI_BOT_NAME = "github-actions[bot]"
CI_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
# CI 每轮随发布回仓的状态文件（state-in-repo，全在 data/ 子树内——git 状态闸「除 data/ 外净」
# 原样成立，不需要给闸放水）
CI_STATE_PATHS = ("data/雷达/抢跑台账.json", "data/雷达/回填库.json", "data/雷达/短链缓存.json",
                  "data/引擎产物/摘要缓存.json", "data/引擎产物/页面正文缓存.json",
                  "data/引擎产物/发布-台账.jsonl", "data/引擎产物/告警-日志.jsonl")


def ci_guard():
    """S4 保险：CI_MODE 有值但不在 GitHub Actions 里 = 有人在 Mac 上误开 → 拒跑。"""
    if CI_MODE and not CI_ACTIVE:
        raise SystemExit("[发布链] 拒跑：AI_NEWS_CI_MODE 只允许在 GitHub Actions 内激活"
                         "（需同时 AI_NEWS_CI=1 ∧ GITHUB_ACTIONS=true）；Mac 提交必须走 agent-git wrapper")


# ---------- M2/M3/M4 提取（Fable 9-21 v2 审：纯函数化换单测覆盖） ----------
def ci_stage_paths():
    """staged 范围计算：LIVE 五件+两契约恒在；CI 再加实际存在的状态文件。"""
    paths = list(LIVE_FILES) + ["data/精选库.json", "data/引擎心跳.json"]
    if CI_ACTIVE:
        paths += [p for p in CI_STATE_PATHS if os.path.exists(os.path.join(PUB, p))]
    return paths


def ci_staged_scope_ok(staged_names):
    """M2：CI 下 staged 文件集必须落在 白名单 内，越界即 False（GateFail 调用方拦）。"""
    allowed = set(LIVE_FILES) | {"data/精选库.json", "data/引擎心跳.json"} | set(CI_STATE_PATHS)
    return all(name.strip() in allowed for name in staged_names if name.strip())


def cname_gate_ok(cname_text):
    """M3：HEAD 树 CNAME 存在且等于域名常量。None/空/被改 → False。"""
    return bool(cname_text) and cname_text.strip() == SITE_DOMAIN


def sig_ok(sig, ci_active=None):
    """提交署名校验（提取为函数换单测）：CI=github-actions[bot]；Mac=ZCode 双验署名。"""
    ci = CI_ACTIVE if ci_active is None else ci_active
    want = CI_BOT_EMAIL if ci else "ZCode <zcode@pipeline.local>"
    return want in (sig or "")

# 产物闸扫描：本机路径 / 密钥形态（"token" 一词是 AI 正文常用词不算密钥，只抓赋值形态；
# sk- 键须同时含数字与大写——正文里 "task-of-marginalisation" 类连字符短语不误伤）
_SECRET_PATTERNS = [
    # 9-21 实测修复：sk- 后禁连字符——heise URL slug「sk-laesst-Klage-gegen-Apple-fallen-11454459」
    # （大写+数字+20 字符全齐）撞旧形态；真实 sk- 钥匙从不含连字符。
    re.compile(r"sk-(?=[A-Za-z0-9_]{20,})(?=[A-Za-z0-9_]*[0-9])(?=[A-Za-z0-9_]*[A-Z])[A-Za-z0-9_]{20,}"),
    # 9-21 实测修复：占位符负向前瞻——新闻正文常含「TYPESAFE_API_KEY=your_typesafe_api_key」
    # 这类教程示例（真实样例出自页面正文缓存），旧形态会让 CI 的 S2 状态闸假拦每一轮。
    re.compile(r"(?i)(api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"]?"
               r"(?!(?i:your_|xxx|example|dummy|placeholder|test_))[A-Za-z0-9_\-]{12,}"),
    re.compile(r"/Users/[A-Za-z0-9_\-]+"),
    re.compile(r"/Volumes/[^\s\"']+"),
    re.compile(r"/home/[a-z][A-Za-z0-9_\-]*"),
]


class GateFail(Exception):
    """门禁失败：不发布、旧站原样、告警留痕。"""


def now_utc():
    return datetime.now(timezone.utc)


def sh(cmd, cwd=PUB, timeout=120, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"命令失败 {' '.join(cmd[:3])}…: {(r.stderr or r.stdout)[:300]}")
    return r


def append_pub_ledger(rec):
    os.makedirs(WORK, exist_ok=True)
    # D7 §2：触发方式随记录落台账（无人值守经 AI_NEWS_TRIGGER 传入 calendar/kickstart；
    # 手跑/验收注入无该环境变量=manual——验收判据「calendar ∧ published」可直接过滤）
    rec.setdefault("trigger", os.environ.get("AI_NEWS_TRIGGER") or "manual")
    with open(PUB_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_alert(kind, detail):
    os.makedirs(WORK, exist_ok=True)
    rec = {"when_utc": now_utc().isoformat(timespec="seconds"), "kind": kind, "detail": detail[:400]}
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ---------- 心跳脱敏（Fable ⑤-②：心跳 JSON 进仓前脱敏相对化） ----------
_ABS_PATH_RE = re.compile(r"(?:/Users/[A-Za-z0-9_\-]+|/Volumes/[^\s\"'/]+(?:/[^\s\"']*)?|/home/[a-z][A-Za-z0-9_\-]*)(/[^\s\"',\]]*)?")


def sanitize_value(s):
    """字符串值里的本机绝对路径 → 相对路径（含项目根前缀剥除）。"""
    s = s.replace(PROJ + "/", "").replace(BASE + "/", "")
    s = s.replace(os.path.expanduser("~") + "/", "~/")
    s = _ABS_PATH_RE.sub(lambda m: (m.group(1) or "").lstrip("/"), s)
    return s


def sanitize_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    if isinstance(obj, str):
        return sanitize_value(obj)
    return obj


# ---------- 数据门禁 ----------
def validate_contract_schema(seed):
    """精选库 JSON schema 校验：顶层结构与 items 必填字段（缺/型错 = 门禁失败）。"""
    errs = []
    if not isinstance(seed, dict):
        return ["顶层必须是对象"]
    if not isinstance(seed.get("generated_at_utc"), str) or not seed.get("generated_at_utc"):
        errs.append("generated_at_utc 缺失")
    items = seed.get("items")
    if not isinstance(items, list):
        return errs + ["items 必须是数组"]
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errs.append(f"items[{i}] 非对象")
            continue
        if not (it.get("title_zh") or it.get("title_src")):
            errs.append(f"items[{i}] title_zh/title_src 双缺")
        if not isinstance(it.get("url"), str) or not it.get("url", "").startswith("http"):
            errs.append(f"items[{i}] url 非法")
        if not isinstance(it.get("selected"), bool):
            errs.append(f"items[{i}] selected 非布尔")
    if not isinstance(seed.get("counts", {}).get("selected"), int):
        errs.append("counts.selected 缺失")
    return errs


def gate_data(contract, heartbeat):
    """数据门禁（4）：schema ∧ 品牌 ∧ 精选 ≥5 ∧ 心跳 ok。返回 (结果行列表, 选中数)。"""
    rows = []
    errs = validate_contract_schema(contract)
    if errs:
        raise GateFail(f"schema 校验失败 {len(errs)} 处：{errs[:4]}")
    rows.append(f"schema=过（{len(contract['items'])} 条，字段齐）")
    dump = json.dumps({"t": [it.get("title_zh", "") + (it.get("one_liner_zh") or "")
                             + (it.get("why_zh") or "") + (it.get("quote_en") or "")
                             for it in contract["items"]],
                       "note": contract.get("note", "")}, ensure_ascii=False)
    if brand_violation(dump):
        raise GateFail("品牌闸命中（aihot 字样）——投毒拦截")
    rows.append("品牌=0 命中")
    n_sel = contract.get("counts", {}).get("selected", 0)
    n_sel = sum(1 for it in contract["items"] if it.get("selected")) if n_sel <= 0 else n_sel
    if n_sel < MIN_SELECTED:
        raise GateFail(f"精选 {n_sel} < {MIN_SELECTED}（数据不健康不发布）")
    rows.append(f"精选={n_sel}（≥{MIN_SELECTED}）")
    if not isinstance(heartbeat, dict) or heartbeat.get("status") != "ok":
        raise GateFail(f"引擎心跳非 ok：status={getattr(heartbeat, 'get', lambda *_: None)('status')}")
    rows.append(f"心跳=ok（{heartbeat.get('when', '?')}）")
    return rows, n_sel


# ---------- git 状态闸（Fable ⑤-①） ----------
def gate_git():
    """fetch → pull --ff-only → 工作树除 data/ 外干净 → HEAD 与 origin 对齐（或本地领先待带出）。
    永禁 force：本模块任何 git 命令都不含 --force。"""
    rows = []
    try:
        sh(["git", "fetch", "origin", "main"], timeout=90)
        rows.append("fetch=过")
    except Exception as e:
        raise GateFail(f"git fetch 失败（网络/凭据）：{str(e)[:160]}")
    if CI_ACTIVE:
        # CI：checkout 出来的 ref 无 upstream 保障，显式对齐 origin/main（不依赖 pull 默认行为）
        r = sh(["git", "merge", "--ff-only", "origin/main"], check=False, timeout=90)
    else:
        r = sh(["git", "pull", "--ff-only"], check=False, timeout=90)
    if r.returncode != 0:
        raise GateFail(f"pull --ff-only 失败（本地与远端分叉，需人工裁决）：{(r.stderr or '')[:200]}")
    if "Already up to date" not in (r.stdout or "") and "已经是最新的" not in (r.stdout or ""):
        rows.append("pull=带回远端新提交（ff-only）")
    status = sh(["git", "status", "--porcelain"]).stdout.strip()
    dirty = [l for l in status.splitlines() if l.strip() and "data/" not in l]
    if dirty:
        raise GateFail(f"发布仓工作树脏（除 data/ 外须干净）：{dirty[:4]}")
    if status.strip():
        rows.append(f"工作树=data/ 内 {len(status.splitlines())} 处可变（将随本轮构建归位）")
    else:
        rows.append("工作树=净")
    head = sh(["git", "rev-parse", "HEAD"]).stdout.strip()
    origin = sh(["git", "rev-parse", "origin/main"]).stdout.strip()
    if head == origin:
        rows.append("HEAD==origin/main")
    else:
        # 本地领先（上轮 push 失败遗留的 commit）：允许继续，本轮 push 一并带出（仍是 ff）
        ahead = sh(["git", "rev-list", "--count", f"{origin}..{head}"], check=False).stdout.strip()
        behind = sh(["git", "rev-list", "--count", f"{head}..{origin}"], check=False).stdout.strip()
        # 计数是字符串，"0" 为真值——必须转成数再判，否则纯领先永远落进 GateFail（上轮 push
        # 失败后自愈路径被这一处堵死，2026-09-22 实测）。转不出数视为未知，按不对齐拦下。
        try:
            ahead_n, behind_n = int(ahead), int(behind)
        except ValueError:
            ahead_n, behind_n = -1, -1
        if ahead_n > 0 and behind_n == 0:
            rows.append(f"本地领先 origin {ahead} 个提交（上轮 push 遗留，本轮一并 ff 推出）")
        else:
            raise GateFail(f"HEAD 与 origin/main 未对齐且非纯领先（ahead={ahead} behind={behind}）")
    return rows


# ---------- 产物闸（Fable ⑤-②） ----------
def scan_secrets(paths):
    """扫描文件文本：本机路径/密钥形态。返回命中列表 [(path, 模式, 摘要)]。"""
    hits = []
    for p in paths:
        if not os.path.exists(p):
            hits.append((p, "missing", "文件不存在"))
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception as e:
            hits.append((p, "unreadable", str(e)[:80]))
            continue
        for pat in _SECRET_PATTERNS:
            m = pat.search(txt)
            if m:
                hits.append((os.path.basename(p), pat.pattern[:24], m.group(0)[:60]))
    return hits


def scan_state_secrets():
    """S2（Fable 指名）：CI 状态文件只扫密钥两条模式，不扫路径三条——摘要缓存里的普通 URL
    路径会命中 /home/、/Users/ 造成假 GateFail；runner 自身 /home/runner 已被 sanitize
    相对化。返回命中列表。"""
    hits = []
    for rel in CI_STATE_PATHS:
        p = os.path.join(PUB, rel)
        if not os.path.exists(p):
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        for pat in _SECRET_PATTERNS[:2]:
            m = pat.search(txt)
            if m:
                hits.append((rel, pat.pattern[:24], m.group(0)[:60]))
    return hits


def prev_index_size():
    r = sh(["git", "show", "HEAD:index.html"], check=False, timeout=60)
    if r.returncode == 0:
        return len(r.stdout.encode("utf-8", "surrogateescape"))
    p = os.path.join(PUB, "index.html")
    return os.path.getsize(p) if os.path.exists(p) else 0


def prev_selected_count():
    try:
        with open(os.path.join(PUB_DATA, "精选库.json"), encoding="utf-8") as f:
            return sum(1 for it in json.load(f).get("items", []) if it.get("selected"))
    except Exception:
        return 0


# ---------- 归档（规格书 §6：最近 20 版本地留底） ----------
def archive_current(ts):
    dst = os.path.join(ROLLBACK_DIR, ts)
    os.makedirs(dst, exist_ok=True)
    copied = []
    for rel in LIVE_FILES + ("data/精选库.json", "data/引擎心跳.json"):
        src = os.path.join(PUB, rel)
        if os.path.exists(src):
            os.makedirs(os.path.join(dst, os.path.dirname(rel)), exist_ok=True)
            shutil.copy2(src, os.path.join(dst, rel))
            copied.append(rel)
    versions = sorted(d for d in os.listdir(ROLLBACK_DIR)
                      if os.path.isdir(os.path.join(ROLLBACK_DIR, d)))
    pruned = 0
    for old in versions[:-KEEP_ROLLBACKS]:
        shutil.rmtree(os.path.join(ROLLBACK_DIR, old), ignore_errors=True)
        pruned += 1
    return copied, pruned


def git_restore_live():
    """build/commit 失败复位（Fable ⑤-③：否则下轮带脏）：checkout 恢复已换入的线上文件。"""
    sh(["git", "checkout", "--"] + list(LIVE_FILES)
       + ["data/精选库.json", "data/引擎心跳.json"], check=False)


# ---------- 主链 ----------
def prune_stale_staging():
    """清掉历史崩溃残留的 .staging-* 目录（gitignore 默认挡住不进仓，但占盘且碍眼）。"""
    if not os.path.isdir(PUB):
        return
    for d in os.listdir(PUB):
        if d.startswith(".staging-"):
            shutil.rmtree(os.path.join(PUB, d), ignore_errors=True)


def run(job, contract_path=None, dry_run=False):
    t0 = now_utc()
    ts = t0.strftime("%Y%m%d-%H%M%S")
    contract_path = contract_path or SRC_CONTRACT
    gate_rows = []
    staging = None
    try:
        # 1. 读源数据
        try:
            contract = json.load(open(contract_path, encoding="utf-8"))
        except Exception as e:
            raise GateFail(f"精选库不可读：{e}")
        try:
            heartbeat_raw = json.load(open(SRC_HEARTBEAT, encoding="utf-8"))
        except Exception as e:
            raise GateFail(f"引擎心跳不可读：{e}")
        heartbeat = sanitize_json(heartbeat_raw)      # 进仓前脱敏相对化
        # 2. 数据门禁
        rows, n_sel = gate_data(contract, heartbeat)
        gate_rows += rows
        # 3. git 状态闸
        gate_rows += gate_git()
        # 3.5 CI shadow：从已对齐 origin/main 的干净点开影子分支（本链只推进分支，不碰 main）
        ci_branch = None
        if CI_ACTIVE and CI_MODE == "shadow":
            ci_branch = f"ci/shadow-{ts}"
            sh(["git", "checkout", "-b", ci_branch])
            gate_rows.append(f"影子分支={ci_branch}（自 origin/main 干净点开出）")
        # 4. 基线（上轮产物）
        prev_sz, prev_sel = prev_index_size(), prev_selected_count()
        # 5. staging 构建（不碰线上）
        prune_stale_staging()
        staging = os.path.join(PUB, f".staging-{ts}-{os.getpid()}")
        os.makedirs(os.path.join(staging, "data"), exist_ok=True)
        shutil.copyfile(contract_path, os.path.join(staging, "data", "精选库.json"))
        with open(os.path.join(staging, "data", "引擎心跳.json"), "w", encoding="utf-8") as f:
            json.dump(heartbeat, f, ensure_ascii=False, indent=1)
        if os.path.exists(SRC_SOURCES):
            shutil.copyfile(SRC_SOURCES, os.path.join(staging, "data", "信源登记.json"))
        else:
            gate_rows.append("信源登记=缺（/api/v1/sources.json 降级为 pending）")
        r = sh([PY, BUILD, os.path.join(staging, "data", "精选库.json"), staging],
               cwd=PUB, timeout=300, check=False)
        if r.returncode != 0:
            raise GateFail(f"staging 构建失败（exit {r.returncode}，线上未动）：{(r.stderr or r.stdout)[:240]}")
        gate_rows.append("staging构建=过")
        # 6. 产物闸
        st_index = os.path.join(staging, "index.html")
        if not os.path.exists(st_index):
            raise GateFail("staging index.html 不存在")
        sz = os.path.getsize(st_index)
        if prev_sz and sz < int(prev_sz * INDEX_SIZE_FLOOR):
            raise GateFail(f"产物闸：index {sz}B < 上轮 {prev_sz}B 的 {int(INDEX_SIZE_FLOOR*100)}%")
        if n_sel < prev_sel - SELECTED_DROP_MAX:
            raise GateFail(f"产物闸：精选 {n_sel} < 上轮 {prev_sel}-{SELECTED_DROP_MAX}")
        scan_targets = [st_index,
                        os.path.join(staging, "data", "精选库.json"),
                        os.path.join(staging, "data", "引擎心跳.json")] + [
            os.path.join(staging, rel) for rel in LIVE_FILES
            if rel not in ("index.html",) and os.path.exists(os.path.join(staging, rel))]
        leaks = scan_secrets(scan_targets)
        if leaks:
            raise GateFail(f"产物闸：本机路径/密钥泄漏 {leaks[:3]}")
        # 品牌闸②（2026-09-22）：agent 层产物也对外，逐件查一遍对标站字样
        for rel in ("api/v1/sources.json", "llms.txt", "agents/index.html", "feed.xml"):
            f = os.path.join(staging, rel)
            if os.path.exists(f) and brand_violation(open(f, encoding="utf-8").read()):
                raise GateFail(f"品牌闸命中（{rel} 含对标站字样）")
        gate_rows.append("品牌闸②=过（agent 层 4 件）")
        gate_rows += [f"index={sz}B（≥上轮{int(INDEX_SIZE_FLOOR*100)}%={int(prev_sz*INDEX_SIZE_FLOOR)}B）",
                      f"精选={n_sel}（≥上轮-{SELECTED_DROP_MAX}={prev_sel-SELECTED_DROP_MAX}）",
                      "无本机路径/密钥=过（心跳已脱敏相对化）"]
        if dry_run:
            print(f"[发布链] dry-run：门禁与 staging 构建全过（不换入不提交）\n  " + "\n  ".join(gate_rows))
            shutil.rmtree(staging, ignore_errors=True)
            return 0
        # 7. 归档当前线上
        copied, pruned = archive_current(ts)
        gate_rows.append(f"归档={len(copied)} 文件 → 回滚/{ts}（清最旧 {pruned} 版）")
        # 8. 原子换入
        for rel in LIVE_FILES:
            src = os.path.join(staging, rel)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(os.path.join(PUB, rel)), exist_ok=True)
                os.replace(src, os.path.join(PUB, rel))
        os.replace(os.path.join(staging, "data", "精选库.json"), os.path.join(PUB_DATA, "精选库.json"))
        os.replace(os.path.join(staging, "data", "引擎心跳.json"), os.path.join(PUB_DATA, "引擎心跳.json"))
        shutil.rmtree(staging, ignore_errors=True)
        # 9. 提交（署名纪律分流：Mac=agent-git wrapper ZCode 双验；CI=github-actions[bot]
        #    Actions 自身主体——Fable §7-1 GO；两者互斥，由 CI_ACTIVE 环境事实决定，不靠自觉）
        stage_paths = ci_stage_paths()
        if CI_ACTIVE:
            stage_paths += [p for p in CI_STATE_PATHS if os.path.exists(os.path.join(PUB, p))]
            add = sh(["git", "add", "--"] + stage_paths, check=False)
        else:
            add = sh(["python3", AGENT_GIT, "zcode", "add", "--"] + stage_paths, check=False)
        if add.returncode != 0:
            git_restore_live()
            raise GateFail(f"git add 失败（已复位线上文件）：{(add.stderr or '')[:200]}")
        # 9.5 S2：CI 状态文件密钥扫描（staged 前置检查——只查密钥形态，URL 路径不误伤）
        if CI_ACTIVE:
            state_leaks = scan_state_secrets()
            if state_leaks:
                git_restore_live()
                raise GateFail(f"状态文件密钥泄漏 {state_leaks[:3]}")
        staged = sh(["git", "diff", "--cached", "--name-only"]).stdout.strip()
        # M2（Fable 9-21 v2 审）：CI 下 staged 范围硬闸——只许 LIVE 五件+两契约+CI 状态件，
        # 越界（拉错 ref/起点异常/误删文件被顺推）即拦，不兑现任何「零变化」承诺
        if CI_ACTIVE and not ci_staged_scope_ok(staged.splitlines()):
            stray = [l.strip() for l in staged.splitlines()
                     if l.strip() and l.strip() not in (
                         set(LIVE_FILES) | {"data/精选库.json", "data/引擎心跳.json"} | set(CI_STATE_PATHS))]
            git_restore_live()
            raise GateFail(f"CI staged 越界：{stray[:4]}（只许站点五件+两契约+CI 状态件）")
        if not staged:
            print("[发布链] 数据与上轮完全一致，无可提交内容（不产生空提交）")
            append_pub_ledger({"when_utc": t0.isoformat(timespec="seconds"), "job": job,
                               "result": "noop", "gates": gate_rows})
            return 0
        msg = (f"D6 发布链自动上线：job={job} generated_at={contract.get('generated_at_utc')} "
               f"精选={n_sel}；门禁全过（{'；'.join(gate_rows[:3])}…；"
               f"index={sz}B≥{int(INDEX_SIZE_FLOOR*100)}%；无本机路径/密钥）；"
               f"署名={'github-actions[bot]（CI ' + CI_MODE + '）' if CI_ACTIVE else 'agent-git wrapper'}")
        if CI_ACTIVE:
            cm = sh(["git", "-c", f"user.name={CI_BOT_NAME}", "-c", f"user.email={CI_BOT_EMAIL}",
                     "commit", "-m", msg], check=False)
        else:
            cm = sh(["python3", AGENT_GIT, "zcode", "commit", "-m", msg], check=False)
        if cm.returncode != 0:
            git_restore_live()
            raise GateFail(f"commit 失败（已复位线上文件）：{(cm.stderr or '')[:240]}")
        sig = sh(["git", "show", "-s", "--format=%an <%ae> | %cn <%ce>", "HEAD"]).stdout.strip()
        if not sig_ok(sig):
            git_restore_live()
            sh(["git", "reset", "--soft", "HEAD~1"], check=False)
            raise GateFail(f"署名校验失败：{sig}")
        # 9.6 M3（Fable 9-21 v2 审）：CNAME 硬闸——push 前断言 HEAD 树 CNAME 在且等于域名常量。
        #     防 9-18 事故的反向形态（checkout 拉错 ref / 影子分支起点异常 / 人手误删后 CI 顺推）。
        #     shadow 与 live、Mac 与 CI 同开；读的是已提交的 HEAD 树，零副作用只读断言。
        r_cname = sh(["git", "show", "HEAD:CNAME"], check=False, timeout=30)
        if not cname_gate_ok(r_cname.stdout if r_cname.returncode == 0 else None):
            git_restore_live()
            sh(["git", "reset", "--soft", "HEAD~1"], check=False)
            raise GateFail(f"CNAME 闸：HEAD 树缺失或值异常（期望 {SITE_DOMAIN}），拦下不推")
        # 10. 推送（ff-only 语义，永禁 --force）。CI shadow=推影子分支+开 PR；CI live/Mac=推 main
        push_ref = ci_branch if ci_branch else "main"
        push = sh(["git", "push", "origin", push_ref], check=False, timeout=180)
        head = sh(["git", "rev-parse", "HEAD"]).stdout.strip()[:7]
        if push.returncode != 0:
            rec = append_alert("publish_push_fail",
                               f"[{job}] push 失败（commit {head} 留本地，下轮 pull --ff-only 自愈重推）："
                               f"{(push.stderr or '')[:200]}")
            append_pub_ledger({"when_utc": t0.isoformat(timespec="seconds"), "job": job,
                               "result": "push_fail", "commit": head, "gates": gate_rows,
                               "alert": rec["when_utc"]})
            print(f"[发布链] ⚠️ push 失败：commit {head} 留本地（站点本地新、线上旧），已告警")
            return 2
        if ci_branch:
            pr_note = ci_shadow_pr(ci_branch, job, n_sel, gate_rows, t0)
            gate_rows.append(pr_note.splitlines()[0])
        dur = round((now_utc() - t0).total_seconds())
        append_pub_ledger({"when_utc": t0.isoformat(timespec="seconds"), "job": job,
                           "result": "shadow_pushed" if ci_branch else "published",
                           "commit": head, "branch": ci_branch,
                           "author": CI_BOT_NAME if CI_ACTIVE else "ZCode",
                           "generated_at": contract.get("generated_at_utc"),
                           "selected": n_sel, "index_bytes": sz, "duration_s": dur,
                           "gates": gate_rows})
        target = f"影子分支 {ci_branch} + PR" if ci_branch else "origin/main"
        print(f"[发布链] ✅ 发布完成：commit {head} 已推送 → {target}（{dur}s，job={job}）\n  " + "\n  ".join(gate_rows))
        return 0
    except GateFail as e:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
        rec = append_alert("publish_gate_fail", f"[{job}] 门禁拦下不发布（旧站原样）：{e}")
        append_pub_ledger({"when_utc": t0.isoformat(timespec="seconds"), "job": job,
                           "result": "gate_fail", "detail": str(e)[:300], "alert": rec["when_utc"]})
        print(f"[发布链] 🚫 门禁失败不发布（旧站原样）：{e}\n  已过闸：{gate_rows}")
        return 1
    finally:
        if staging and os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)


def ci_shadow_pr(branch, job, n_sel, gate_rows, t0):
    """S3（Fable 指名）：影子分支 PR——先关掉所有开着的 ci/shadow-* PR（防一天三窗堆积），
    再开新 PR。gh 失败不判 GateFail（commit 已推上分支，PR 可手动补开），返回备注行。"""
    def gh(*args):
        return subprocess.run(["gh", *args], cwd=PUB, capture_output=True, text=True, timeout=90)
    engine_ran = os.environ.get("AI_NEWS_ENGINE_RAN") == "1"
    try:
        lst = gh("pr", "list", "--state", "open", "--json", "number,headRefName")
        for pr in (json.loads(lst.stdout or "[]")):
            if str(pr.get("headRefName", "")).startswith("ci/shadow-"):
                gh("pr", "close", str(pr["number"]), "--delete-branch")
        title = f"shadow: {job} 状态回写 {t0.strftime('%Y-%m-%d %H:%M')} UTC"
        body = ("Actions 影子轮（Phase 1，不自动合并）\n\n"
                f"- 引擎层：{'已跑（模型加工）' if engine_ran else 'SKIP——DEEPSEEK_API_KEY 未配，三步配法见 README'}\n"
                f"- 精选={n_sel}；门禁：{'；'.join(gate_rows[:6])}\n"
                "- 影子纪律：staged 范围硬闸已过（只许站点五件+两契约+CI 状态件，越界即拦）；"
                "首页热区按当前时刻重算 24h 窗，同契约不同时刻 index 也会变——正常现象非污染\n")
        r = gh("pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", body)
        if r.returncode == 0:
            url = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
            return f"影子 PR 已开：{url}"
        return f"影子 PR 开失败（分支已推，可手动开）：{(r.stderr or '')[:160]}"
    except Exception as e:
        return f"影子 PR 异常（分支已推）：{str(e)[:120]}"


def do_revert(job="revert-drill"):
    """Fable ⑤-④：回滚=git revert HEAD 推送（不用 reset；本地归档不算回滚）。"""
    t0 = now_utc()
    sh(["git", "fetch", "origin", "main"], timeout=90)
    r = sh(["git", "pull", "--ff-only"], check=False, timeout=90)
    if r.returncode != 0:
        append_alert("publish_revert_fail", f"[{job}] revert 前 pull --ff-only 失败：{(r.stderr or '')[:200]}")
        return 1
    rv = sh(["python3", AGENT_GIT, "zcode", "revert", "HEAD", "--no-edit"], check=False)
    if rv.returncode != 0:
        append_alert("publish_revert_fail", f"[{job}] git revert 失败：{(rv.stderr or '')[:240]}")
        return 1
    sig = sh(["git", "show", "-s", "--format=%an <%ae> | %cn <%ce>", "HEAD"]).stdout.strip()
    if "ZCode <zcode@pipeline.local>" not in sig:
        append_alert("publish_revert_fail", f"[{job}] revert 提交署名异常：{sig}")
        return 1
    push = sh(["git", "push", "origin", "main"], check=False, timeout=180)
    head = sh(["git", "rev-parse", "HEAD"]).stdout.strip()[:7]
    if push.returncode != 0:
        append_alert("publish_push_fail", f"[{job}] revert push 失败（commit {head} 留本地）："
                                        f"{(push.stderr or '')[:200]}")
        return 2
    append_pub_ledger({"when_utc": t0.isoformat(timespec="seconds"), "job": job,
                       "result": "reverted", "commit": head})
    print(f"[发布链] ↩️ 回滚完成：revert 提交 {head} 已推送（线上回到上一版）")
    return 0


def main():
    ci_guard()      # S4：CI_MODE 误在 Mac 上激活 → 立即拒跑（防绕过署名铁律）
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="manual")
    ap.add_argument("--contract", default=None, help="验收注入门禁投毒用")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true", help="回滚演练：git revert HEAD + push")
    args = ap.parse_args()
    if args.revert:
        return do_revert()
    return run(args.job, contract_path=args.contract, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
