#!/usr/bin/env python3
# 【CI 副本】2026-09-21 快照自 ~/ai-radar/抢跑雷达.py（原件零触碰——雷达组地盘纪律）
# 与原件的 delta（仅 3 处，env 门控/纯路径调整，抓取逻辑零改动）：
#   ① DATA 支持 AI_RADAR_DATA 覆盖（CI 指到仓内 data/雷达/）
#   ② OUTDIR 支持 AI_RADAR_OUT 覆盖，缺省挪到 DATA 下（CI 里雷达输出不落仓根碍 git 状态闸）
#   ③ AI_RADAR_CI=1 时跳过末尾两处 Mac 专属子调用（面板生成器 + 德国信源站网站生成器）
# 纪律：改了原件必须重新快照本副本（README 已写明）。
# 抢跑雷达 —— 盯一手信源，早二手博主一步
# 八路免费信源：arXiv / GitHub / HuggingFace(全球+中国实验室) / HN / 官方RSS / 官方博客差分 / aihot中文聚合 / GitHub组织release
# 可选 --x 加扫 X 官方账号（走 OpenCLI 借 Chrome，Chrome 没开就跳过并注明）
# 产出: 雷达输出/YYYY-MM-DD.md（追加） + 大鱼单独进 今日可抢发.md + 台账去重
# 原则: 全免费零Key；只写文件绝不自动发布
import json, os, re, time, hashlib, subprocess, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("AI_RADAR_DATA", os.path.join(BASE, "data"))
OUTDIR = os.environ.get("AI_RADAR_OUT", os.path.join(DATA, "雷达输出"))
LEDGER = os.path.join(DATA, "抢跑台账.json")
TODAY_FISH = os.path.join(OUTDIR, "今日可抢发.md")

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Accept-Language": "en,zh;q=0.8"}

HOT_WORDS = re.compile(
    r"llm|language model|gpt|agent|agentic|multimodal|diffusion|transformer|reasoning|"
    r"text.to.video|video generation|image generation|speech|voice|world model|"
    r"embodied|robot|vision|code generation|coding|foundation model|token|context window|"
    r"open.source|benchmark|fine.?tun|quantiz|moe|mixture of experts|glm|qwen|deepseek|"
    r"kimi|minimax|hunyuan|seedance|seedream|omni|video model|3d|spatial", re.I)

# 大鱼：官方发布级关键词（命中且来自官方通道 → 可抢发）
BIG_RE = re.compile(
    r"gpt.?6|astra|o3|o4|claude|gemini|grok|glm|qwen|deepseek|kimi|minimax|hunyuan|"
    r"launch|release|introduc|announc|发布|上新|重磅|亮相|旗舰|benchmark|state.of.the.art|sota", re.I)
OFFICIAL_SRC = ("官方RSS", "官方博客", "中国实验室", "组织Release")

# ---------- 官方博客清单（2026-09-04 扩容：并入 Horizon/LearnPrompt/aihot 三开源项目的信源） ----------
RSS_FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml", "AI"),
    ("HuggingFace博客", "https://huggingface.co/blog/feed.xml", "AI"),
    ("通义Qwen博客", "https://qwenlm.github.io/blog/index.xml", "AI"),
    ("DeepMind", "https://deepmind.google/blog/rss.xml", "AI"),
    ("Google AI", "https://blog.google/technology/ai/rss/", "AI"),
    ("微软AI", "https://news.microsoft.com/source/topics/ai/feed/", "AI"),
    ("GitHub官方博客", "https://github.blog/ai-and-ml/feed/", "AI"),
    ("NVIDIA生成式AI", "https://developer.nvidia.com/blog/category/generative-ai/feed/", "AI"),
    ("宝玉博客", "https://baoyu.io/feed.xml", "AI"),
    ("Claude Code Release", "https://github.com/anthropics/claude-code/releases.atom", "AI"),
    ("OpenAI Skills动态", "https://github.com/openai/skills/commits/main.atom", "AI"),
    ("IT之家", "https://www.ithome.com/rss/", "AI"),  # 9-3 养分吸收并入
    ("TheVerge-AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "AI"),  # 9-4 并入
    # —— 9-4 德国信源站 M2：欧洲+金融+德企板块（小茜终极目标：德国第一信源站）——
    ("heise", "https://www.heise.de/rss/heise-atom.xml", "欧洲"),
    ("t3n", "https://t3n.de/rss.xml", "欧洲"),
    ("Golem", "https://www.golem.de/rss.php", "欧洲"),
    ("Tech.eu", "https://tech.eu/feed/", "欧洲"),
    ("TheRegister", "https://www.theregister.com/headlines.atom", "欧洲"),
    ("Sifted", "https://sifted.eu/feed/", "欧洲·创投"),
    ("欧洲央行ECB", "https://www.ecb.europa.eu/rss/press.html", "金融"),
    ("SAP新闻室", "https://news.sap.com/feed/", "德企"),
    ("Bosch新闻室", "https://www.bosch-presse.de/pressblog/de/rss.xml", "德企"),  # 9-5 德国源扩展
    ("Bitkom协会", "https://www.bitkom.org/rss.xml", "Europa"),
    ("FAZ财经", "https://www.faz.net/rss/aktuell/", "金融"),
    # —— 9-16 信源追赶日：中文线扩容（官方直连 + gnews 桥，全部实测过出条目）——
    ("量子位", "https://www.qbitai.com/feed", "AI中文"),
    ("机器之心(gnews桥)", "https://news.google.com/rss/search?q=%E6%9C%BA%E5%99%A8%E4%B9%8B%E5%BF%83+when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "AI中文"),  # 官方 /rss 已死(跳数据服务页)，桥收近2天
    ("新智元(gnews桥)", "https://news.google.com/rss/search?q=%E6%96%B0%E6%99%BA%E5%85%83+when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "AI中文"),  # 公众号无官方RSS，桥代收
    ("雷峰网", "https://www.leiphone.com/feed", "AI中文"),
    ("InfoQ中国", "https://www.infoq.cn/feed.xml", "AI中文"),
    ("爱范儿", "https://www.ifanr.com/feed", "AI中文"),
    ("钛媒体", "https://www.tmtpost.com/feed", "AI中文"),
    # —— 9-16 信源追赶日：英文专业媒体 + 一手博客（对账首轮缺口修复）——
    ("The Decoder", "https://the-decoder.com/feed/", "AI"),  # 对账点名：Anthropic IPO 漏抓之源，SSL抖动重试可救
    ("MarkTechPost", "https://www.marktechpost.com/feed/", "AI"),
    ("TechCrunch-AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "AI"),  # 观察名单摘帽：连续两轮实测通过
    ("ArsTechnica-AI", "https://arstechnica.com/ai/feed/", "AI"),
    ("MIT科技评论AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "AI"),
    ("SimonWillison", "https://simonwillison.net/atom/everything/", "AI"),  # 信源地图十博主主粮之一的一手博客
    ("LatentSpace", "https://www.latent.space/feed", "AI"),  # 含 AINews 日报流
    ("GoogleResearch", "https://research.google/blog/rss/", "AI"),
    ("AWS-ML博客", "https://aws.amazon.com/blogs/machine-learning/feed/", "AI"),
    ("AppleNewsroom", "https://www.apple.com/newsroom/rss-feed.rss", "AI"),  # 对账点名：Apple 事件此前只有德媒二手
]
HTML_CHANNELS = [  # (名字, URL, 卡片链接正则)
    ("Anthropic", "https://www.anthropic.com/news", r'href="(/news/[a-z0-9-]+)"'),
    ("DeepMind", "https://deepmind.google/blog/", r'href="(https://blog\.google/(?:[a-z0-9-]+/){2,6})"'),  # 9-16 修：博客迁 blog.google 后旧正则失配归零
    ("Meta AI", "https://ai.meta.com/blog/", r'href="((?:https://ai\.meta\.com)?/blog/[^"?]+)"'),  # 9-16 修：链接改绝对URL后旧正则失配归零
    ("Mistral", "https://mistral.ai/news", r'href="(/news/[a-z0-9-]+)"'),
    ("Cohere", "https://cohere.com/blog", r'href="(/blog/[a-z0-9-]+)"'),
    ("WorldLabs", "https://www.worldlabs.ai/blog", r'href="(/blog/[a-z0-9-]+)"'),
    ("DeepSeek", "https://api-docs.deepseek.com/news/", r'href="(/news/[a-z0-9_-]+)"'),
    # —— 9-16 信源追赶日：对账点名官方博客（无 RSS，走 HTML 差分）——
    ("Fireworks", "https://fireworks.ai/blog", r'href="(/blog/[a-z0-9-]+)"'),
    ("Suno", "https://suno.com/blog", r'href="(/blog/[a-z0-9-]+)"'),
    # —— goal 第二刀：Claude Blog（goal 第二刀已点名，9-16 加过 Anthropic）、xAI News ——
    # xAI News: Cloudflare 403 常见，加 User-Agent fallback；抓不到静默跳过
    ("xAI News", "https://x.ai/news", r'href="(/news/[a-z0-9-]+)"'),
]
CN_HF_AUTHORS = ["deepseek-ai", "Qwen", "zai-org", "moonshotai", "MiniMaxAI",
                 "Tencent-Hunyuan", "ByteDance-Seed"]
GH_ORGS = ["zai-org", "Tencent-Hunyuan", "deepseek-ai", "moonshotai", "MiniMaxAI"]

X_OFFICIAL_QUERY = ("from%3AOpenAI%20OR%20from%3AAnthropicAI%20OR%20from%3AGoogleDeepMind%20OR%20"
                    "from%3Axai%20OR%20from%3AMistralAI%20OR%20from%3Adeepseek_ai%20OR%20"
                    "from%3AAlibabaQwen%20OR%20from%3AMiniMaxAI%20OR%20"
                    "from%3Arohanpaul_ai%20OR%20from%3Atestingcatalog%20OR%20"
                    "from%3AArtificialAnlys%20OR%20from%3AClementDelangue%20OR%20"
                    "from%3Aemollick%20OR%20from%3ASemiAnalysis_%20OR%20"
                    "from%3AOpenBMB%20OR%20from%3Aalibaba_cloud")  # 9-3 养分吸收：+emollick/SemiAnalysis/OpenBMB/阿里云


def http(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    last = None
    for attempt in range(2):  # 透明代理常抖 SSL，重试一次救回大半
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def load_ledger():
    if os.path.exists(LEDGER):
        d = json.load(open(LEDGER, encoding="utf-8"))
    else:
        d = {}
    d.setdefault("seen", {})
    # goal 第一刀：抢跑台账升级——同时存 items（活水全字段），引擎接管子从此读取
    d.setdefault("items", {})
    return d


def mark(ledger, url_or_sig, meta="", src=""):
    """记录新信号到台账：seen 记 URL→when stamp；items 存全字段（活水数据）。
    兼容两种调用：(url, meta, src) 与 (sig_dict)。"""
    if isinstance(url_or_sig, dict):
        sig = url_or_sig
        url = (sig.get("url") or "").strip()
        meta = sig.get("title", "") or meta
        src = sig.get("src", "") or src
        pub = sig.get("pub")
        note = (sig.get("note") or "")[:200]
        sector = sig.get("sector", "")
        fresh = bool(sig.get("fresh", False))
    else:
        url = url_or_sig
        pub = None
        note = ""
        sector = ""
        fresh = False
    if not url:
        return False
    h = hashlib.md5(url.encode()).hexdigest()
    if h in ledger.get("seen", {}):
        return False
    ledger.setdefault("seen", {})[h] = {
        "url": url, "when": datetime.now().isoformat(timespec="seconds"),
        "meta": meta, "src": src}
    # items：活水全字段——引擎第一刀接管子的入口（pub/note/sector/fresh 都在）
    ledger.setdefault("items", {})[h] = {
        "url": url, "title": meta, "src": src, "sector": sector,
        "pub": pub, "note": note, "fresh": fresh,
        "when": datetime.now().isoformat(timespec="seconds")}
    return True


def since(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def since_compact(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")


# ---------- 八路信源 ----------
def from_arxiv():
    url = ("http://export.arxiv.org/api/query?search_query="
           + urllib.parse.quote(
               "(cat:cs.AI OR cat:cs.CL OR cat:cs.CV OR cat:cs.LG OR cat:cs.RO)"
               f" AND submittedDate:[{since_compact(3)}0000 TO {since_compact(0)}2359]")
           + "&sortBy=submittedDate&sortOrder=descending&max_results=60")
    try:
        xml = http(url, 30)
    except Exception as e:
        print("  arXiv 失手:", e); return []
    out = []
    for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.S):
        e = m.group(1)
        t = re.search(r"<title>(.*?)</title>", e, re.S)
        link = re.search(r"<id>(.*?)</id>", e)
        summ = re.search(r"<summary>(.*?)</summary>", e, re.S)
        if not (t and link): continue
        title = re.sub(r"\s+", " ", t.group(1)).strip()
        s = re.sub(r"\s+", " ", summ.group(1)).strip() if summ else ""
        if HOT_WORDS.search(title + " " + s[:400]):
            out.append({"src": "arXiv论文", "title": title, "url": link.group(1).strip(),
                        "score": 3, "note": s[:160]})
    return out


def from_github():
    url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(
        f"created:>{since(3)} " + "(llm OR agent OR diffusion OR multimodal OR rag OR vision)")
        + "&sort=stars&order=desc&per_page=25")
    try:
        j = json.loads(http(url))
    except Exception as e:
        print("  GitHub 失手:", e); return []
    out = []
    for it in j.get("items", []):
        if HOT_WORDS.search((it.get("description") or "") + " " + it.get("name", "")):
            out.append({"src": "GitHub代码", "title": it["full_name"], "url": it["html_url"],
                        "score": 3 + min(2, it.get("stargazers_count", 0) // 100),
                        "note": f"★{it.get('stargazers_count',0)} {(it.get('description') or '')[:120]}"})
    return out


def _hf_models(q):
    return json.loads(http("https://huggingface.co/api/models?" + q, 30))


def from_hf_papers():
    """HuggingFace 每日精选论文（goal 第二刀新源）。
    走 HF 官方 daily_papers API：每天 30+ 篇社区点赞高的 arXiv 论文。
    不走 RSS（huggingface.co/papers 无 RSS 端点）。"""
    try:
        # 拉过去 2 天的 daily papers（防单日漏抓）
        all_papers = []
        for d in range(2):
            day = (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d")
            url = f"https://huggingface.co/api/daily_papers?date={day}"
            try:
                j = json.loads(http(url, 30))
            except Exception:
                continue
            if not isinstance(j, list):
                continue
            all_papers.extend(j)
    except Exception as e:
        print("  HF Papers 失手:", e); return []
    out = []
    seen_ids = set()
    for wrap in all_papers:
        # HF API 返回 [{paper: {id, title, upvotes, ...}, ...}]，每条包在 paper 键里
        it = wrap.get("paper") if isinstance(wrap, dict) else None
        if not isinstance(it, dict):
            continue
        pid = it.get("id", "").strip() if isinstance(it.get("id"), str) else str(it.get("id", ""))
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)
        title = (it.get("title") or "").strip()
        if not title:
            continue
        upvotes = it.get("upvotes") or 0
        # 阈值：5 赞以上（HF 论文社区门槛低，热度按赞数排）
        if upvotes < 5:
            continue
        # arXiv 论文页（huggingface.co/papers/{id} 也行）
        url = f"https://huggingface.co/papers/{pid}"
        pub = it.get("publishedAt")  # aware ISO
        # 作者
        authors = [a.get("name", "?") for a in (it.get("authors") or [])[:3]]
        auth_str = " · ".join(authors)
        note_parts = [f"赞{upvotes}"]
        if auth_str:
            note_parts.append(auth_str)
        note = " | ".join(note_parts)
        # 摘要做 note 备份（≤200）
        summary = (it.get("summary") or "").strip()
        if summary:
            note = f"{note} | {summary[:160]}"
        out.append({"src": "HFPapers", "title": title, "url": url,
                    "score": 3 + min(3, upvotes // 10), "note": note[:200],
                    "pub": pub, "sector": "研究"})
    print(f"  HF Papers: {len(out)} 条（API daily_papers，过去 2 天）")
    return out


def from_hf_global():
    try:
        j = _hf_models("sort=createdAt&direction=-1&limit=40")
    except Exception as e:
        print("  HF全球 失手:", e); return []
    out = []
    for it in j:
        name = it.get("modelId") or it.get("id") or ""
        dl = it.get("downloads", 0) or 0
        likes = it.get("likes", 0) or 0
        if dl < 200 and likes < 5:
            continue
        if HOT_WORDS.search(name + " " + " ".join(it.get("tags", [])[:8])):
            out.append({"src": "HuggingFace模型", "title": name,
                        "url": f"https://huggingface.co/{name}",
                        "score": 2, "note": f"下载{dl} 赞{likes}"})
    return out


def from_cn_labs():
    """中国实验室 HF 专项：每家最新模型，全收（他们发什么都算信号）"""
    out = []
    for author in CN_HF_AUTHORS:
        try:
            j = _hf_models(f"author={author}&sort=createdAt&direction=-1&limit=3")
        except Exception as e:
            print(f"  {author} 失手:", e); continue
        for it in j:
            name = it.get("modelId") or it.get("id") or ""
            if not name: continue
            out.append({"src": "中国实验室", "title": name,
                        "url": f"https://huggingface.co/{name}",
                        "score": 4, "note": f"{author} 新模型 下载{it.get('downloads',0)}"})
        time.sleep(0.5)
    return out


def from_hn():
    try:
        j = json.loads(http("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"))
    except Exception as e:
        print("  HN 失手:", e); return []
    out = []
    for h in j.get("hits", []):
        title = h.get("title") or ""
        u = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        if HOT_WORDS.search(title):
            out.append({"src": "HN热议", "title": title, "url": u,
                        "score": 1 + min(3, (h.get("points") or 0) // 100),
                        "note": f"{h.get('points',0)}分/{h.get('num_comments',0)}评"})
    return out


def from_rss():
    out = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    for name, url, sector in RSS_FEEDS:
        try:
            xml = http(url, 25)
        except Exception as e:
            print(f"  {name}RSS 失手:", e); continue
        entries = []  # (title, url, pubdt)
        for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
            e = m.group(1)
            t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", e, re.S)
            link = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", e, re.S)
            pub = re.search(r"<pubDate>(.*?)</pubDate>", e)
            entries.append((t.group(1) if t else "", link.group(1).strip() if link else "",
                            _parse_date(pub.group(1) if pub else "")))
        if not entries:  # Atom
            for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.S):
                e = m.group(1)
                t = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", e, re.S)
                link = re.search(r'<link[^>]*href="([^"]+)"', e)
                pub = re.search(r"<(?:updated|published)>(.*?)</(?:updated|published)>", e)
                entries.append((t.group(1) if t else "", link.group(1).strip() if link else "",
                                _parse_date(pub.group(1) if pub else "")))
        for title, u, dt in entries[:15]:
            if not (title and u):
                continue
            fresh = (dt is None) or (dt >= cutoff)  # 没给时间的保守放行，超过48h的历史条目不当大鱼
            score = 5 if fresh else 2
            # 宽域聚合源（IT之家等）必须撞强 AI 词且在标题前 40 字（主题位）才算（打分宪法v2·9-4 夜班降噪升级）
            # 9-16 信源追赶日：名单扩容——新中文宽域源+gnews桥+AppleNewsroom 全走同一闸
            WIDE_SOURCES = ("IT之家", "量子位", "雷峰网", "InfoQ中国", "爱范儿", "钛媒体",
                            "机器之心(gnews桥)", "新智元(gnews桥)", "AppleNewsroom")
            if name in WIDE_SOURCES:
                head = title[:40]
                strong = re.search(r"AI|人工智能|大模型|GPT|Claude|Gemini|Grok|DeepSeek|Qwen|Kimi|LLM|智能体|OpenAI|Anthropic|英伟达|NVIDIA|算力|Apple Intelligence|Siri", head, re.I)
                if not strong:
                    continue  # 主题不是 AI 的整条丢弃，不灌台账
                if not HOT_WORDS.search(title):
                    score = 2
            out.append({"src": "官方RSS", "sector": sector, "title": f"[{name}] " + re.sub(r"\s+", " ", title).strip(),
                        "url": u, "score": score,
                        "note": f"{name}官方" + ("" if fresh else "（历史条目）")})
        time.sleep(0.4)
    return out


def _parse_date(s):
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def from_official_html():
    out = []
    for name, url, pat in HTML_CHANNELS:
        try:
            html = http(url, 25)
        except Exception as e:
            print(f"  {name}博客 失手:", e); continue
        links = []
        for m in re.finditer(pat, html):
            href = m.group(1)
            full = href if href.startswith("http") else urllib.parse.urljoin(url, href)
            links.append(full)
        for u in list(dict.fromkeys(links))[:8]:
            slug = u.rstrip("/").split("/")[-1][:60]
            out.append({"src": "官方博客", "title": f"[{name}] {slug}", "url": u,
                        "score": 5, "note": f"{name}博客更新"})
        time.sleep(0.4)
    return out


def from_aihot():
    out = []
    for label, url in [("aihot热榜", "https://aihot.virxact.com/api/v1/hot-topics"),
                       ("aihot精选", "https://aihot.virxact.com/api/v1/items?mode=selected&window=24h&limit=15")]:
        try:
            j = json.loads(http(url, 25))
        except Exception as e:
            print(f"  {label} 失手:", e); continue
        items = j if isinstance(j, list) else (j.get("items") or j.get("topics") or [])
        for it in items:
            if not isinstance(it, dict): continue
            title = (it.get("title") or it.get("name") or "").strip()
            if not title: continue
            links = it.get("links") or {}
            u = (links.get("original") or links.get("aihot") or
                 (it.get("url") or "") or "https://aihot.virxact.com")
            out.append({"src": "aihot中文", "title": title, "url": u,
                        "score": 3, "note": (it.get("summary") or "")[:120]})
        time.sleep(1)  # 不同端点，礼貌间隔即可；同一端点跨轮≥60s由小时级闹钟天然保证
    return out


def from_org_releases():
    out = []
    for org in GH_ORGS:
        try:
            j = json.loads(http(f"https://api.github.com/orgs/{org}/releases?per_page=3", 20))
        except Exception as e:
            continue  # 没有release的org静默跳过
        if not isinstance(j, list): continue
        for it in j:
            out.append({"src": "组织Release", "title": f"[{org}] {it.get('name') or it.get('tag_name','')}",
                        "url": it.get("html_url", ""), "score": 4,
                        "note": (it.get("body") or "")[:120]})
        time.sleep(0.4)
    return out


def from_x_official():
    """X 官方账号哨（可选）：借 Chrome 登录态扫 x.com 搜索，Chrome 没开就跳过（CI 不加 --x，天然关）"""
    out = []
    try:
        r = subprocess.run(["opencli", "browser", "x", "open",
                            f"https://x.com/search?q={X_OFFICIAL_QUERY}&f=live"],
                           capture_output=True, text=True, timeout=40)
        m = re.search(r'"page"\s*:\s*"([0-9A-F]+)"', r.stdout or "")
        if not m:
            print("  X官方哨: Chrome/会话不可用，跳过")
            return out
        time.sleep(7)
        js = ('(()=>{const arts=[...document.querySelectorAll("article")].slice(0,12);'
              'const rows=[];for(const a of arts){const t=a.innerText||"";if(t.length<15)continue;'
              'const tm=a.querySelector("time");rows.push({txt:t.slice(0,400),'
              'at:tm?tm.getAttribute("datetime"):"",u:tm&&tm.closest("a")?tm.closest("a").href:""})}'
              'return JSON.stringify(rows)})()')
        r2 = subprocess.run(["opencli", "browser", "x", "eval", "--tab", m.group(1), js],
                            capture_output=True, text=True, timeout=40)
        for line in (r2.stdout or "").splitlines():
            line = line.strip()
            if line.startswith('['):
                try:
                    rows = json.loads(line)
                except Exception:
                    continue
                for row in rows:
                    who = row["txt"].split("\n")[0].strip()[:24]
                    out.append({"src": "X官方哨", "title": f"@{who}: {row['txt'][:100]}",
                                "url": row.get("u") or "https://x.com", "score": 4,
                                "note": row.get("at", "")})
                break
    except Exception as e:
        print("  X官方哨 失手:", e)
    return out


def from_x_sample_file():
    """X 哨兵采样器输出读取（goal 第二刀新源）——CI 里样本文件不存在=返回空（天然关）"""
    out = []
    path = os.path.join(DATA, "X样本.jsonl")
    if not os.path.exists(path):
        print("  X样本.jsonl 不存在（先跑 X采样器.py）")
        return out
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                # row: {txt, links, at (ISO), url, handle}
                at = row.get("at", "")
                if not at:
                    continue
                try:
                    pub_dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
                except Exception:
                    continue
                # 只取 24h 内（与 from_rss 一致宽域）
                if (datetime.now(timezone.utc) - pub_dt).total_seconds() > 48 * 3600:
                    continue
                # 标题：handle + txt 首行（≤120 字符）
                handle = row.get("handle", "x")
                first_line = (row.get("txt", "") or "").split("\n")[0].strip()[:120]
                if not first_line:
                    continue
                title = f"@{handle}: {first_line}"
                # URL：优先 row.url，再 row.links[0]
                url = row.get("url") or (row.get("links") or ["https://x.com"])[0]
                out.append({"src": "X官方哨", "sector": "AI",
                            "title": title, "url": url, "score": 4,
                            "note": first_line[:200],
                            "pub": pub_dt.isoformat()})
    except Exception as e:
        print("  X样本读取失手:", e)
    print(f"  X样本：{len(out)} 条（来自 data/X样本.jsonl）")
    return out


def from_wechat_mp():
    """公众号桥输出读取（goal 第二刀新源）——CI 里样本文件不存在=返回空（天然关）"""
    out = []
    path = os.path.join(DATA, "公众号样本.jsonl")
    if not os.path.exists(path):
        print("  公众号样本.jsonl 不存在（先跑 公众号桥.py）")
        return out
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                account = row.get("_account", "公众号")
                title = row.get("title", "").strip()
                url = row.get("url", "").strip()
                pub = row.get("pub")  # aware ISO or None
                if not (title and url):
                    continue
                # 24h 内优先
                if pub:
                    try:
                        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                        if (datetime.now(timezone.utc) - pub_dt).total_seconds() > 48 * 3600:
                            continue
                    except Exception:
                        pass
                note = (row.get("summary") or row.get("digest") or "")[:200]
                out.append({"src": "公众号", "sector": "AI中文",
                            "title": f"[{account}] {title}"[:200], "url": url, "score": 4,
                            "note": note, "pub": pub})
    except Exception as e:
        print("  公众号样本读取失手:", e)
    print(f"  公众号：{len(out)} 条（来自 data/公众号样本.jsonl）")
    return out


# ---------- 主流程 ----------
def main():
    use_x = "--x" in sys.argv
    stamp = datetime.now()
    print(f"抢跑雷达开机 {stamp.strftime('%Y-%m-%d %H:%M')} use_x={use_x}")
    routes = [
        ("官方RSS", from_rss), ("官方博客", from_official_html),
        ("中国实验室", from_cn_labs), ("组织Release", from_org_releases),
        ("arXiv", from_arxiv), ("GitHub", from_github),
        ("HF全球", from_hf_global), ("HF Papers", from_hf_papers),
        ("HN", from_hn), ("X样本", from_x_sample_file),
        ("公众号", from_wechat_mp), ("aihot", from_aihot),
    ]
    if use_x:
        routes.append(("X官方哨", from_x_official))

    all_sigs = []
    for name, fn in routes:
        got = fn()
        print(f"  {name}: {len(got)} 条")
        all_sigs += got

    # 社区源质量门槛（学 Horizon 的 min_score：低热度社区帖降权，防一股脑全筛）
    for s in all_sigs:
        if s["src"] == "GitHub代码":
            m = re.search(r"★(\d+)", s.get("note", ""))
            if m and int(m.group(1)) < 50:
                s["score"] -= 1
        elif s["src"] == "HN热议":
            m = re.search(r"(\d+)分", s.get("note", ""))
            if m and int(m.group(1)) < 30:
                s["score"] -= 1

    ledger = load_ledger()
    fresh = []
    for s in all_sigs:
        # goal 第二刀：传全 sig dict 让 mark() 拿到 pub/note/sector/fresh（不是只 url/title/src）
        if s.get("url") and mark(ledger, s):
            # 大鱼加分：官方通道 + 发布级关键词
            if s["src"] in OFFICIAL_SRC and BIG_RE.search(s["title"] + " " + s.get("note", "")):
                s["score"] += 4
                s["big"] = True
            fresh.append(s)
    print(f"去重后新信号 {len(fresh)} 条")
    fresh.sort(key=lambda x: -x["score"])

    os.makedirs(OUTDIR, exist_ok=True)
    day_path = os.path.join(OUTDIR, stamp.strftime("%Y-%m-%d.md"))
    with open(day_path, "a", encoding="utf-8") as f:
        f.write(f"\n## 🕐 {stamp.strftime('%H:%M')} 这一轮（新信号 {len(fresh)} 条）\n\n")
        for s in fresh[:30]:
            tag = " 🐟大鱼" if (s.get("big") and s["score"] >= 9) else (" ·候选" if s.get("big") else "")
            f.write(f"- 【{s['src']}】{s['title'][:100]}{tag}\n  {s['url']}\n")
    ledger["seen"] = dict(list(ledger["seen"].items())[-8000:])
    ledger["items"] = dict(list(ledger.get("items", {}).items())[-8000:])
    json.dump(ledger, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    bigs_now = [s for s in fresh if s.get("big") and s["score"] >= 9]
    # 大鱼台账：逮到就记，快照取近 24h（防"早先逮到本轮丢"）
    biglog_path = os.path.join(DATA, "大鱼.json")
    biglog = []
    if os.path.exists(biglog_path):
        try:
            biglog = json.load(open(biglog_path, encoding="utf-8"))
        except Exception:
            biglog = []
    day_ago = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    for s in bigs_now:
        biglog.append({"title": s["title"], "src": s["src"], "url": s["url"],
                       "note": s.get("note", "")[:150], "score": s["score"],
                       "when": datetime.now().isoformat(timespec="seconds")})
    seen_urls = set()
    biglog = [b for b in biglog if b["when"] >= day_ago and not (b["url"] in seen_urls or seen_urls.add(b["url"]))]
    biglog.sort(key=lambda b: (-b.get("score", 0), b["when"]))
    os.makedirs(DATA, exist_ok=True)
    json.dump(biglog, open(biglog_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bigs = biglog[:12]
    if bigs:
        # 快照模式：每次重写，只留当前最值得抢的 ≤12 条，避免洪水
        with open(TODAY_FISH, "w", encoding="utf-8") as f:
            f.write(f"# 🐟 今日可抢发（{stamp.strftime('%Y-%m-%d %H:%M')} 快照，近24h共 {len(bigs)} 条）\n")
            f.write("> 只列官方通道的发布级信号。抢发口诀：官方原文→一句人话→为什么值得看→链接。\n\n")
            for s in bigs:
                f.write(f"### {s['title'][:120]}\n- 信源: {s['src']} | 分数 {s.get('score',0)} | {str(s.get('when',''))[11:16]}\n- 链接: {s['url']}\n- 备注: {s.get('note','')[:150]}\n\n")
        print(f"🐟 大鱼快照 {len(bigs)} 条（本轮新增{len(bigs_now)}）→ {TODAY_FISH}")
    print(f"草稿已追加: {day_path}")
    # 【CI 副本 delta ③】AI_RADAR_CI=1 时跳过两处 Mac 专属子调用（面板生成器同目录、德国信源站绝对路径）
    if os.environ.get("AI_RADAR_CI") != "1":
        try:  # 顺手刷新可视化面板（失败不影响雷达）
            subprocess.run([sys.executable, os.path.join(BASE, "面板生成器.py")], timeout=30)
        except Exception as e:
            print("  面板刷新失手:", e)
        try:  # 重建德国信源站网站（index/api/feed）
            subprocess.run([sys.executable, "/Users/xiaoxisun/ZCodeProject/德国信源站/网站生成器.py"], timeout=30)
        except Exception as e:
            print("  网站重建失手:", e)
    else:
        print("CI 模式：跳过面板刷新与德国信源站重建（Mac 专属）")


if __name__ == "__main__":
    main()
