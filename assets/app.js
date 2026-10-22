/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改）
   2026-10-21 版式 A「报纸版」：首页 index.html 与往期页 archive/index.html 共用这一份，按 <body data-page> 分支。
   浏览器本地只存三样：语言 lang、深浅色 kin-theme、已读条目 id 列表 kin-read；读写一律 try/catch，存不了就只在本页内存里记。 */
(function () {
  "use strict";
  var TZ = "Europe/Berlin";
  var RUBS = ["marketing", "unternehmen", "china", "modelle", "robotik", "forschung"];
  var I18N = {
    de: {
      locale: "de-DE", title: "KI-Nachrichten · Was heute in der KI zählt", wordmark: "KI-Nachrichten",
      sub: "Was heute in der KI zählt", city: "Berlin", arTitle: "Archiv · KI-Nachrichten",
      rub: { marketing: "Marketing & Commerce", unternehmen: "KI im Unternehmen", china: "China global",
             modelle: "Modelle & Infrastruktur", robotik: "Robotik", forschung: "Forschung & Tools" },
      cat: { "模型": "Modelle", "产品": "Produkte", "研究": "Forschung", "行业": "Branche" },
      ph: "Titel suchen, Enter zum Filtern", theme: "Dunkler Modus", scopeAl: "Umfang der Chronik",
      hLead: "Schlagzeile", hTop: "Top-Themen", hMulti: "Mehrfach berichtet", empty: "Gerade keine ausgewählten Meldungen.",
      mkH: "Marketing & Commerce", mk24: "letzte 24 Stunden", mkLatest: "die jüngsten",
      mkNone: "In den 24 Stunden vor der letzten Aktualisierung gab es keine Marketing-Meldung. Die drei jüngsten:",
      mkEmpty: "Noch keine Marketing-Meldungen.", mkLess: "Nur 24 Stunden zeigen", mkAll: "Alle früheren (Archiv)",
      mkMore: function (n) { return "Letzte 7 Tage zeigen (+" + n + ")"; },
      timeline: "Chronik", scSel: "Auswahl", scAll: "Alle", tlTz: "Alle Zeiten in Berliner Zeit.",
      catLbl: "Rubrik", clear: "Zurücksetzen", today: "Heute", yesterday: "Gestern", undated: "Ohne Datum",
      none: "In diesem Bereich gibt es keine Einträge.", more: "Ältere Meldungen laden",
      arLink: "Archiv: alle bisher ausgewählten Meldungen und Marketing-Meldungen nach Tag",
      hCats: "Rubriken", todayLbl: "heute",
      heatTitle: "Themen-Hitzekarte", heatSub: "Je dunkler, desto mehr Relevanz an diesem Tag (Hitze × Quellen)",
      cold: "kalt", hot: "heiß", tz: "Tage nach Berliner Zeit",
      off: "Offiziell", orig: "Original", pub: "Veröffentlicht", seen: "Erfasst", quote: "Originalzitat (EN)",
      go: "Quelle", bug: "Fehler melden", stale: "möglicherweise veraltet", tzShort: "(Berliner Zeit)",
      updated: "Zuletzt aktualisiert {t}",
      fresh: function (h) { return "Aktualisiert vor " + h + " Std."; },
      freshMin: function (m) { return "Aktualisiert vor " + m + " Min."; },
      nItems: function (n) { return n === 1 ? "1 Meldung" : n + " Meldungen"; },
      nSrc: function (n) { return n + " Quellen"; },
      found: function (n, q) { return n ? n + " Treffer für „" + q + "“" : "Keine Treffer für „" + q + "“"; },
      arH: "Archiv", arIntro: "Alle bisher ausgewählten Meldungen und alle Marketing-Meldungen, nach Tag geordnet (Berliner Zeit), neueste zuerst.",
      arAll: "Alle", arMk: "Nur Marketing & Commerce", arNone: "Keine passenden Einträge.",
      arN: function (d, n) { return (d === 1 ? "1 Tag" : d + " Tage") + " · " + (n === 1 ? "1 Meldung" : n + " Meldungen"); },
      wieH: "Wie wir sortieren",
      wie1: "Wir sammeln täglich Meldungen aus öffentlichen Quellen wie offiziellen Blogs, Preprint-Servern, Open-Source-Communities und Tech-Medien; wird dasselbe Ereignis mehrfach berichtet, fassen wir es zu einer Meldung zusammen und nennen die Zahl der Quellen.",
      wie2: "Die Auswahl folgt der Beachtung und Aktualität eines Ereignisses; dasselbe Thema belegt nur einen Platz, Studien stellen höchstens ein Top-Thema, und die Schlagzeile ist bevorzugt keine Studie und hat eine Kurzfassung.",
      wie3: "Titel und Kurzfassungen sind nur ein Verzeichnis und ersetzen das Original nicht; stimmt etwas nicht, bitte „Fehler melden“ auf der Karte nutzen.",
      f: { sources: "Quellen", archive: "Archiv", home: "Startseite", impressum: "Impressum", privacy: "Datenschutz", api: "API", rss: "RSS",
           note: "Auswahl, Zusammenfassung und Übersetzung KI-gestützt; Links führen zur Originalquelle." }
    },
    en: {
      locale: "en-GB", title: "AI News · What matters in AI today", wordmark: "AI News",
      sub: "What matters in AI today", city: "Berlin", arTitle: "Archive · AI News",
      rub: { marketing: "Marketing & Commerce", unternehmen: "AI in Business", china: "China global",
             modelle: "Models & Infrastructure", robotik: "Robotics", forschung: "Research & Tools" },
      cat: { "模型": "Models", "产品": "Products", "研究": "Research", "行业": "Industry" },
      ph: "Search titles, press Enter", theme: "Dark mode", scopeAl: "Timeline scope",
      hLead: "Top story", hTop: "Top topics", hMulti: "Reported by several outlets", empty: "No curated stories right now.",
      mkH: "Marketing & Commerce", mk24: "last 24 hours", mkLatest: "most recent",
      mkNone: "No marketing items in the 24 hours before the last update. The three most recent:",
      mkEmpty: "No marketing items yet.", mkLess: "Show 24 hours only", mkAll: "All earlier (archive)",
      mkMore: function (n) { return "Show last 7 days (+" + n + ")"; },
      timeline: "Timeline", scSel: "Curated", scAll: "All", tlTz: "All times are Berlin time.",
      catLbl: "Section", clear: "Clear", today: "Today", yesterday: "Yesterday", undated: "No date",
      none: "No items in this range.", more: "Load older stories",
      arLink: "Archive: every curated story and every marketing item so far, by day",
      hCats: "Sections", todayLbl: "today",
      heatTitle: "Topic heat map", heatSub: "Darker = more relevant that day (heat × sources)",
      cold: "cold", hot: "hot", tz: "Days in Berlin time",
      off: "Official", orig: "Original", pub: "Published", seen: "Added", quote: "Source quote (EN)",
      go: "Source", bug: "Report issue", stale: "may be outdated", tzShort: "(Berlin time)",
      updated: "Last updated {t}",
      fresh: function (h) { return "Updated " + h + " h ago"; },
      freshMin: function (m) { return "Updated " + m + " min ago"; },
      nItems: function (n) { return n === 1 ? "1 item" : n + " items"; },
      nSrc: function (n) { return n + " sources"; },
      found: function (n, q) { return n ? n + " matches for “" + q + "”" : "No matches for “" + q + "”"; },
      arH: "Archive", arIntro: "Every curated story and every marketing item so far, grouped by day (Berlin time), newest first.",
      arAll: "All", arMk: "Marketing & Commerce only", arNone: "No matching items.",
      arN: function (d, n) { return (d === 1 ? "1 day" : d + " days") + " · " + (n === 1 ? "1 item" : n + " items"); },
      wieH: "How we rank",
      wie1: "Every day we collect items from public sources such as official blogs, preprint servers, open-source communities and tech media; when several outlets cover the same event we merge them into one item and show the number of sources.",
      wie2: "The curated list follows how much attention and how recent an event is; the same story never takes two slots, papers take at most one top-topic slot, and the top story prefers a non-paper with a one-liner.",
      wie3: "Titles and summaries are only an index and do not replace the original; if something is ranked or worded wrongly, please use “Report issue” on the card.",
      f: { sources: "Sources", archive: "Archive", home: "Home", impressum: "Imprint", privacy: "Privacy", api: "API", rss: "RSS",
           note: "Selection, summaries and translations are AI-assisted; links go to the original source." }
    },
    zh: {
      locale: "zh-CN", title: "AI 资讯时间线 · 每天扫上百条，只留值得看的", wordmark: "AI 资讯时间线",
      sub: "每天扫上百条，只留值得看的", city: "柏林", arTitle: "往期 · AI 资讯时间线",
      rub: { marketing: "营销与电商", unternehmen: "欧洲企业 AI 应用", china: "中国 AI 出海",
             modelle: "大模型与基建", robotik: "具身智能", forschung: "论文与工具" },
      cat: { "模型": "模型", "产品": "产品", "研究": "研究", "行业": "行业" },
      ph: "搜索标题，回车筛选", theme: "深色模式", scopeAl: "时间线范围",
      hLead: "头条", hTop: "要闻", hMulti: "多家报道", empty: "当前没有精选条目。",
      mkH: "营销与电商", mk24: "近 24 小时", mkLatest: "最近几条",
      mkNone: "最近一次更新前的 24 小时里没有营销条目，下面是最近 3 条：",
      mkEmpty: "暂无营销条目。", mkLess: "只看 24 小时", mkAll: "全部往期",
      mkMore: function (n) { return "展开近 7 天（另 " + n + " 条）"; },
      timeline: "时间线", scSel: "精选", scAll: "全部", tlTz: "时间均为柏林时间。",
      catLbl: "栏目", clear: "清除", today: "今天", yesterday: "昨天", undated: "未标日期",
      none: "这个范围里没有条目。", more: "加载更早的消息",
      arLink: "往期：历次精选和营销条目按日期回看",
      hCats: "栏目", todayLbl: "今日",
      heatTitle: "热度地图", heatSub: "格子越深＝该主题当天越值得关注（热度×多源）",
      cold: "冷", hot: "烫", tz: "日期按柏林时间切",
      off: "官方", orig: "原文", pub: "发布", seen: "收录", quote: "英文原句",
      go: "原文", bug: "报错", stale: "可能过期", tzShort: "（柏林时间）",
      updated: "最后更新 {t}",
      fresh: function (h) { return "更新于 " + h + " 小时前"; },
      freshMin: function (m) { return "更新于 " + m + " 分钟前"; },
      nItems: function (n) { return n + " 条"; },
      nSrc: function (n) { return n + " 个信源"; },
      found: function (n, q) { return n ? "找到 " + n + " 条标题含“" + q + "”" : "没有标题含“" + q + "”的条目"; },
      arH: "往期", arIntro: "历次精选和全部营销条目按日期（柏林时间）分组，新的在前。",
      arAll: "全部", arMk: "只看营销与电商", arNone: "没有符合条件的条目。",
      arN: function (d, n) { return d + " 天 · " + n + " 条"; },
      wieH: "我们怎么排",
      wie1: "我们每天从官方博客、论文库、开源社区和科技媒体等公开信源收集消息，同一件事被多家报道时合并成一条并标出信源数。",
      wie2: "精选按事件的关注程度和新近度排序，同一件事不重复占位，论文最多占一个要闻位，头条优先选非论文且带一句话摘要的消息。",
      wie3: "标题和摘要只是索引，不能替代原文；排得不对或写得不对，请点卡片上的「报错」。",
      f: { sources: "信源", archive: "往期", home: "首页", impressum: "Impressum", privacy: "数据保护", api: "API", rss: "RSS",
           note: "筛选、摘要与翻译由 AI 辅助完成，链接指向原始出处。" }
    }
  };
  var HTML_LANG = { de: "de", en: "en", zh: "zh-CN" };
  var CJK = /[㐀-鿿]/;
  var root = document.documentElement;
  var PAGE = document.body.getAttribute("data-page") || "index";
  var ISSUES = document.body.getAttribute("data-issues") || "";
  var STALE_MIN = parseInt(document.body.getAttribute("data-stale-min"), 10) || 1800;

  // —— 小工具 ——
  function $(id) { return document.getElementById(id); }
  function all(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function setKids(node, kids) { if (!node) return; node.textContent = ""; kids.forEach(function (k) { node.appendChild(k); }); }
  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  function has(v) { return v != null && String(v).trim() !== ""; }
  function uniq(a) { var s = {}, o = []; a.forEach(function (x) { if (x && !s[x]) { s[x] = 1; o.push(x); } }); return o; }
  function readJSON(id) { var n = $(id); if (!n) return null; try { return JSON.parse(n.textContent); } catch (e) { return null; } }

  // —— 本地存储：localStorage 不可用（隐私模式、禁用存储）时退回内存，页面照常工作 ——
  var mem = {};
  function sget(k) {
    try { var v = localStorage.getItem(k); if (v !== null) return v; } catch (e) {}
    return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null;
  }
  function sset(k, v) { mem[k] = v; try { localStorage.setItem(k, v); } catch (e) {} }

  function pickLang() {
    var q = null;
    try { q = new URLSearchParams(location.search).get("lang"); } catch (e) {}
    if (q && I18N[q]) return q;
    var s = sget("lang"); if (s && I18N[s]) return s;
    var nav = ((navigator.languages && navigator.languages[0]) || navigator.language || "").slice(0, 2).toLowerCase();
    if (I18N[nav]) return nav;
    return "de";
  }
  var lang = pickLang();
  var T = I18N[lang];

  // —— 时间：一律按柏林时间切日；「今天」＝契约生成时刻（generated_at_utc）所在的柏林日，不用浏览器当前日期 ——
  var FMT = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
                                               hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  function bparts(iso) {
    if (!iso) return null;
    var d = new Date(iso); if (isNaN(d.getTime())) return null;
    var o = {}; FMT.formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
    var y = +o.year, mo = +o.month, dd = +o.day;
    return { y: y, mo: mo, d: dd, h: (+o.hour) % 24, mi: +o.minute, key: y + "-" + pad(mo) + "-" + pad(dd),
             ord: Math.round(Date.UTC(y, mo - 1, dd) / 864e5), t: d.getTime() };
  }
  var seed = PAGE === "index" ? (readJSON("seed-data") || { items: [] }) : { items: [] };
  var rubMap = readJSON("rubriken-data") || {};
  var kindMap = readJSON("kind-data") || {};
  var GP = bparts(seed.generated_at_utc || document.body.getAttribute("data-gen") || "");
  var GEN_OK = !!(GP && GP.y >= 2000);           // 1970 是 normalize_seed 的缺省占位，不算有效时间
  if (!GEN_OK) GP = bparts(new Date().toISOString());
  var T0 = GP.ord, GEN_MS = GP.t;

  function dateStr(ord) {
    var d = new Date(ord * 864e5 + 432e5), o = { timeZone: "UTC", weekday: "short", day: "numeric", month: "long" };
    if (d.getUTCFullYear() !== GP.y) o.year = "numeric";
    return new Intl.DateTimeFormat(T.locale, o).format(d);
  }
  function monthStr(ym) {
    var p = String(ym).split("-");
    return new Intl.DateTimeFormat(T.locale, { timeZone: "UTC", month: "long", year: "numeric" })
      .format(new Date(Date.UTC(+p[0], (+p[1] || 1) - 1, 15)));
  }
  function fmtTime(p, full) {
    var hm = pad(p.h) + ":" + pad(p.mi), yr = full || p.y !== GP.y;
    if (lang === "zh") return (yr ? p.y + "年" : "") + p.mo + "月" + p.d + "日 " + hm;
    if (lang === "de") return pad(p.d) + "." + pad(p.mo) + "." + (yr ? p.y : "") + " " + hm;
    var M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return M[p.mo - 1] + " " + p.d + (yr ? ", " + p.y : "") + ", " + hm;
  }
  function ordOf(key) { var p = String(key).split("-"); return Math.round(Date.UTC(+p[0], +p[1] - 1, +p[2]) / 864e5); }

  // —— 文案取舍：DE/EN 视图永远不落到中文；中文视图缺译时用原文题并标 Original ——
  function cleanT(s) { s = String(s || "").trim(); var c = s.replace(/^(?:\[[^\]]{1,60}\]\s*)+/, "").trim(); return c || s; }
  function title(it) {
    if (lang === "zh") {
      if (has(it.title_zh)) return { t: cleanT(it.title_zh) };
      return has(it.title_src) ? { t: cleanT(it.title_src), orig: true } : null;
    }
    var order = lang === "de" ? ["title_de", "title_en", "title_src"] : ["title_en", "title_de", "title_src"];
    for (var i = 0; i < order.length; i++) {
      var v = it[order[i]];
      if (has(v) && !CJK.test(v)) return { t: cleanT(v), orig: order[i] === "title_src" };
    }
    return null;
  }
  function liner(it) {
    if (lang === "zh") return it.one_liner_zh || "";
    var v = lang === "de" ? (it.one_liner_de || it.one_liner_en) : (it.one_liner_en || it.one_liner_de);
    return v && !CJK.test(v) ? v : "";
  }
  function why(it) {
    var v = it["why_" + lang] || (lang === "zh" ? "" : (it.why_en || it.why_de));
    return v && (lang === "zh" || !CJK.test(v)) ? v : "";
  }
  function nSrc(it) { return parseInt(it.n_sources, 10) || ((it.clusters || []).length + 1); }

  // —— 信源只按 URL 域名显示（X 显示 @账号），不显示数据里的 source_name ——
  function inDom(h, d) { return h === d || (h.length > d.length && h.slice(-d.length - 1) === "." + d); }
  function srcInfo(u) {
    var h = "", path = "", ok = false;
    try { var x = new URL(u); h = x.hostname.toLowerCase().replace(/^www\./, ""); path = x.pathname; ok = /^https?:$/.test(x.protocol); } catch (e) {}
    var isX = inDom(h, "x.com") || inDom(h, "twitter.com"), name = h;
    if (isX) {
      var m = /^\/([A-Za-z0-9_]{1,30})(?:\/|$)/.exec(path);
      name = m && !/^(i|home|search|intent|share)$/i.test(m[1]) ? "@" + m[1] : "x.com";
    }
    return { name: name, x: isX, ok: ok };
  }
  function safeUrl(u) { return srcInfo(u).ok ? u : "#"; }
  function rubsOf(it) { return rubMap[it.id || it.url] || ["forschung"]; }
  function kindOf(it) { return kindMap[it.id || it.url] || { k: "medien" }; }
  function isPaper(it) { try { return inDom(new URL(it.url).hostname.toLowerCase(), "arxiv.org"); } catch (e) { return false; } }

  // —— 已读变灰：点开过的条目 id 记进 kin-read，最多留 500 个，超出丢最旧；不存别的 ——
  var READ_KEY = "kin-read", READ_MAX = 500;
  var readList = (function () {
    var a = [];
    try { a = JSON.parse(sget(READ_KEY) || "[]"); } catch (e) { a = []; }
    if (!Array.isArray(a)) a = [];
    return a.filter(function (s) { return typeof s === "string" && s; }).slice(-READ_MAX);
  })();
  var readSet = {};
  readList.forEach(function (id) { readSet[id] = 1; });
  function isRead(id) { return !!readSet[id]; }
  function markRead(id) {
    if (!id) return;
    var i = readList.indexOf(id);
    if (i >= 0) readList.splice(i, 1);
    readList.push(id);
    if (readList.length > READ_MAX) readList = readList.slice(-READ_MAX);
    readSet = {}; readList.forEach(function (k) { readSet[k] = 1; });
    sset(READ_KEY, JSON.stringify(readList));
    all(".card[data-id]").forEach(function (c) { if (c.getAttribute("data-id") === id) c.classList.add("is-read"); });
  }

  // —— 深浅色：默认白；只有用户点过开关才变深（head 里的内联脚本在渲染前已按 kin-theme 设好） ——
  function effTheme() { return root.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
  function syncThemeBtn() { var b = $("theme-btn"); if (b) b.setAttribute("aria-pressed", effTheme() === "dark" ? "true" : "false"); }
  function toggleTheme() {
    var n = effTheme() === "dark" ? "light" : "dark";
    if (n === "dark") root.setAttribute("data-theme", "dark"); else root.removeAttribute("data-theme");
    sset("kin-theme", n);
    syncThemeBtn();
  }

  // —— 静态文案：data-i / data-f / data-ph / data-al / data-ti 按当前语言替换 ——
  function applyStatic() {
    root.setAttribute("lang", HTML_LANG[lang]);
    document.title = PAGE === "archive" ? T.arTitle : T.title;
    all("[data-i]").forEach(function (n) { var v = T[n.getAttribute("data-i")]; if (typeof v === "string") n.textContent = v; });
    all("[data-f]").forEach(function (n) { var v = T.f[n.getAttribute("data-f")]; if (typeof v === "string") n.textContent = v; });
    all("[data-ph]").forEach(function (n) { var v = T[n.getAttribute("data-ph")]; if (typeof v === "string") n.setAttribute("placeholder", v); });
    all("[data-al]").forEach(function (n) { var v = T[n.getAttribute("data-al")]; if (typeof v === "string") n.setAttribute("aria-label", v); });
    all("[data-ti]").forEach(function (n) { var v = T[n.getAttribute("data-ti")]; if (typeof v === "string") n.setAttribute("title", v); });
    all("[data-lang]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-lang") === lang ? "true" : "false"); });
    all("[data-scope]").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-scope") === tl.scope ? "true" : "false"); });
    var w = $("wordmark"); if (w) w.textContent = T.wordmark;
    var d = $("today-date"); if (d) d.textContent = T.city + " · " + dateStr(T0);
    syncThemeBtn();
  }
  function updateFresh() {
    var f = $("fresh"), ft = $("fresh-txt"), lu = $("last-updated");
    var ms = GEN_OK ? Math.max(0, Date.now() - GEN_MS) : NaN;
    var stale = isNaN(ms) || ms > STALE_MIN * 6e4, txt;
    if (isNaN(ms)) txt = T.stale;
    else {
      var h = Math.floor(ms / 36e5);
      txt = h < 1 ? T.freshMin(Math.floor(ms / 6e4)) : T.fresh(h);
      if (stale) txt += " · " + T.stale;
    }
    if (f) f.setAttribute("data-state", stale ? "stale" : "fresh");
    if (ft) ft.textContent = txt;
    if (lu) {
      lu.textContent = GEN_OK ? T.updated.replace("{t}", fmtTime(GP, true) + " " + T.tzShort) : T.stale;
      lu.classList.toggle("stale", stale);
    }
  }

  // ======================= 首页 =======================
  // 预处理：只留当前语言能显示的条目；ALLX＝seed 全量，SELX＝其中 selected；都按时间新→旧
  var ALLX = [], SELX = [];
  function prep() {
    ALLX = []; SELX = [];
    (seed.items || []).forEach(function (it) {
      var tt = title(it);
      if (!tt) return;
      var x = { it: it, tt: tt, p: bparts(it.published_utc) || bparts(it.first_seen_utc), id: String(it.id || it.url || ""),
                rubs: rubsOf(it), hay: [it.title_zh, it.title_de, it.title_en, it.title_src].map(cleanT).join(" ").toLowerCase() };
      ALLX.push(x);
      if (it.selected) SELX.push(x);
    });
    var byT = function (a, b) { return (b.p ? b.p.t : 0) - (a.p ? a.p.t : 0); };
    ALLX.sort(byT); SELX.sort(byT);
  }

  function link(text, href, cls) {
    var a = el("a", cls || null, text);
    a.href = safeUrl(href); a.target = "_blank"; a.rel = "noopener";
    return a;
  }
  // 全站唯一一种卡片：栏目 · 信源 → 标题 → 一句话 → 为什么重要 → 时间/多源 → 英文原句 → 原文 / 报错
  function renderCard(x, o) {
    o = o || {};
    var it = x.it, k = kindOf(it), info = srcInfo(it.url);
    var card = el("article", "card" + (o.lead ? " card-lead" : "") + (isRead(x.id) ? " is-read" : ""));
    card.setAttribute("data-id", x.id);
    card.setAttribute("data-hay", x.hay);
    var eb = el("p", "eyebrow");
    eb.appendChild(el("span", "cat", T.rub[x.rubs[0]] || ""));
    var name = k.k === "x" && k.h ? "@" + k.h : info.name;
    if (name) { eb.appendChild(document.createTextNode(" · ")); eb.appendChild(el("span", "src", name)); }
    if (k.k === "x" || info.x) eb.appendChild(el("span", "tag", "X"));
    else if (k.k === "offiziell") eb.appendChild(el("span", "tag", T.off));
    if (x.tt.orig) eb.appendChild(el("span", "tag", T.orig));
    card.appendChild(eb);

    var h = el("h" + (o.level || 3), "title"), a = link(x.tt.t, it.url);
    a.setAttribute("data-open", "1");
    h.appendChild(a);
    card.appendChild(h);
    var l = liner(it), w = why(it);
    if (l) card.appendChild(el("p", "oneliner", l));
    if (w) card.appendChild(el("p", "why", w));

    var tm = el("div", "times"), any = false;
    var pp = bparts(it.published_utc), sp = bparts(it.first_seen_utc);
    if (pp) { tm.appendChild(el("span", "tm", T.pub + " " + fmtTime(pp))); any = true; }
    if (sp) { tm.appendChild(el("span", "tm", T.seen + " " + fmtTime(sp))); any = true; }
    var urls = uniq([it.url].concat((it.clusters || []).map(function (c) { return c && c.url; })));
    if (urls.length > 1) {
      var dt = el("details", "srcs"), ul = el("ul");
      dt.appendChild(el("summary", null, T.nSrc(urls.length)));
      urls.forEach(function (u) { var li = el("li"), s = link(srcInfo(u).name || u, u); s.setAttribute("data-open", "1"); li.appendChild(s); ul.appendChild(li); });
      dt.appendChild(ul); tm.appendChild(dt); any = true;
    }
    if (any) card.appendChild(tm);
    if (has(it.quote_en)) {
      var qd = el("details", "quote");
      qd.appendChild(el("summary", null, T.quote));
      qd.appendChild(el("blockquote", null, it.quote_en));
      card.appendChild(qd);
    }
    var ac = el("div", "actions"), go = link(T.go, it.url, "act go");
    go.setAttribute("data-open", "1");
    ac.appendChild(go);
    if (ISSUES) ac.appendChild(link(T.bug, ISSUES.replace(/\/+$/, "") + "/new?title=" + encodeURIComponent(x.tt.t), "act"));
    card.appendChild(ac);
    return card;
  }
  function cardLi(x, level) { var li = el("li"); li.appendChild(renderCard(x, { level: level })); return li; }

  // —— 头版：只取当前契约 selected；major_event 优先，再按热度；头条优先非论文且有一句话；要闻 5 条、论文至多 1 条、同一件事不重复 ——
  var STOP = { the: 1, and: 1, "for": 1, "with": 1, from: 1, that: 1, "this": 1, "new": 1, its: 1, are: 1, has: 1, how: 1, into: 1, over: 1, about: 1, now: 1 };
  function toks(it) {
    var s = [it.title_en, it.title_zh, it.title_src].map(function (v) { return cleanT(v).toLowerCase(); }).join(" ");
    var m = s.match(/[a-z0-9]+(?:\.[0-9]+)?/g) || [], o = {}, n = 0;
    m.forEach(function (w) { if (w.length >= 3 && !STOP[w] && !o[w]) { o[w] = 1; n++; } });
    return { set: o, n: n };
  }
  function nearDup(a, b) {
    // 同一件事：共享 ≥4 个词、占较短标题的六成以上，且至少共享一个带数字的词（版本号、日期）
    var c = 0, dg = false, k;
    for (k in a.set) { if (b.set[k]) { c++; if (/[0-9]/.test(k)) dg = true; } }
    var mn = Math.min(a.n, b.n);
    return dg && c >= 4 && mn > 0 && c / mn >= 0.6;
  }
  function pickFront() {
    var pool = SELX.slice().sort(function (a, b) {
      return ((b.it.major_event ? 1 : 0) - (a.it.major_event ? 1 : 0)) || ((parseFloat(b.it.heat) || 0) - (parseFloat(a.it.heat) || 0));
    });
    var lead = null, i;
    for (i = 0; i < pool.length; i++) { if (!isPaper(pool[i].it) && liner(pool[i].it)) { lead = pool[i]; break; } }
    if (!lead) lead = pool[0] || null;
    var tops = [], picked = lead ? [toks(lead.it)] : [], papers = lead && isPaper(lead.it) ? 1 : 0;
    for (i = 0; i < pool.length && tops.length < 5; i++) {
      var x = pool[i];
      if (x === lead) continue;
      if (isPaper(x.it) && papers >= 1) continue;
      var tk = toks(x.it);
      if (picked.some(function (p) { return nearDup(p, tk); })) continue;
      if (isPaper(x.it)) papers++;
      picked.push(tk); tops.push(x);
    }
    return { lead: lead, tops: tops };
  }
  function renderFront() {
    var f = pickFront();
    setKids($("lead"), f.lead ? [renderCard(f.lead, { lead: true, level: 3 })] : [el("p", "empty", T.empty)]);
    setKids($("top-list"), f.tops.map(function (x) { return cardLi(x, 3); }));
  }
  var multiShow = false;
  function renderMulti() {
    var items = SELX.filter(function (x) { return nSrc(x.it) > 1; });
    setKids($("multi-list"), items.map(function (x) { return cardLi(x, 3); }));
    multiShow = items.length >= 2;   // 不足 2 条不单列
  }

  // —— 营销块：以契约生成时刻为准取 24 小时；展开看近 7 天；24 小时内没有就给最近 3 条（卡片上带时间） ——
  var mkOpen = false;
  function renderMarketing() {
    if (!$("marketing")) return;
    var pool = ALLX.filter(function (x) { return x.p && x.rubs.indexOf("marketing") >= 0; });
    var c24 = GEN_MS - 24 * 36e5, c7 = GEN_MS - 7 * 864e5;
    var head = pool.filter(function (x) { return x.p.t >= c24; }), fb = !head.length;
    if (fb) head = pool.slice(0, 3);
    var shown = {};
    head.forEach(function (x) { shown[x.id] = 1; });
    var ext = pool.filter(function (x) { return x.p.t >= c7 && !shown[x.id]; });
    $("mk-sub").textContent = fb ? T.mkLatest : T.mk24;
    $("mk-note").textContent = fb ? (pool.length ? T.mkNone : T.mkEmpty) : "";
    $("mk-note").hidden = !fb;
    setKids($("mk-list"), head.map(function (x) { return cardLi(x, 3); }));
    setKids($("mk-ext"), ext.map(function (x) { return cardLi(x, 3); }));
    $("mk-ext").hidden = !mkOpen;
    var b = $("mk-btn");
    b.hidden = !ext.length;
    b.textContent = mkOpen ? T.mkLess : T.mkMore(ext.length);
    b.setAttribute("aria-expanded", mkOpen ? "true" : "false");
  }

  // —— Chronik：按柏林日分组；先放最近两天进 DOM，「Ältere Meldungen laden」每次追加一天；无日期的排最后 ——
  var tl = { scope: "selected", cat: null, q: "", shown: 0, groups: [] };
  function groupDays(list) {
    var map = {}, keys = [], undated = [];
    list.forEach(function (x) {
      if (!x.p) { undated.push(x); return; }
      if (!map[x.p.ord]) { map[x.p.ord] = []; keys.push(x.p.ord); }
      map[x.p.ord].push(x);
    });
    keys.sort(function (a, b) { return b - a; });
    var g = keys.map(function (k) { return { ord: k, items: map[k] }; });
    if (undated.length) g.push({ ord: null, items: undated });
    return g;
  }
  function dayLabel(ord) {
    if (ord == null) return T.undated;
    var ds = dateStr(ord);
    if (ord === T0) return T.today + " · " + ds;
    if (ord === T0 - 1) return T.yesterday + " · " + ds;
    return ds;
  }
  function dayGroup(g) {
    var sec = el("section", "day-group"), h = el("h3", "day", dayLabel(g.ord));
    h.appendChild(el("span", "n", T.nItems(g.items.length)));
    sec.appendChild(h);
    var ul = el("ul", "day-list");
    g.items.forEach(function (x) { ul.appendChild(cardLi(x, 4)); });
    sec.appendChild(ul);
    return sec;
  }
  function renderTimeline() {
    var q = tl.q.trim().toLowerCase(), src = tl.scope === "all" ? ALLX : SELX;
    var items = src.filter(function (x) { return (!tl.cat || x.rubs.indexOf(tl.cat) >= 0) && (!q || x.hay.indexOf(q) >= 0); });
    tl.groups = groupDays(items);
    var box = $("tl-days");
    box.textContent = "";
    tl.shown = 0;
    var first = q ? tl.groups.length : Math.min(2, tl.groups.length);   // 搜索时把命中的各天全放出来
    while (tl.shown < first) box.appendChild(dayGroup(tl.groups[tl.shown++]));
    if (!items.length) box.appendChild(el("p", "empty", T.none));
    var btn = $("more");
    btn.textContent = T.more;
    btn.hidden = tl.shown >= tl.groups.length;
    var note = [document.createTextNode(T.tlTz)];
    if (tl.cat) {
      var chip = el("span", "chip", T.catLbl + ": " + T.rub[tl.cat]), b = el("button", "linklike", T.clear);
      b.type = "button"; b.setAttribute("data-clearcat", "1");
      chip.appendChild(b); note.push(chip);
    }
    setKids($("tl-note"), note);
  }
  function moreDay() {
    if (tl.shown < tl.groups.length) $("tl-days").appendChild(dayGroup(tl.groups[tl.shown++]));
    $("more").hidden = tl.shown >= tl.groups.length;
  }

  // —— 栏目：六个 Rubriken，数字＝「今天」（契约生成日）该栏目的条目数；点一下筛 Chronik，再点取消 ——
  function renderCats() {
    var src = tl.scope === "all" ? ALLX : SELX;
    setKids($("cat-list"), RUBS.map(function (r) {
      var n = 0;
      src.forEach(function (x) { if (x.p && x.p.ord === T0 && x.rubs.indexOf(r) >= 0) n++; });
      var li = el("li"), b = el("button", "cat-btn");
      b.type = "button"; b.setAttribute("data-cat", r); b.setAttribute("aria-pressed", tl.cat === r ? "true" : "false");
      b.appendChild(el("span", "cat-name", T.rub[r]));
      b.appendChild(el("span", "cat-n", String(n)));
      b.appendChild(el("span", "cat-sub", T.todayLbl));
      li.appendChild(b);
      return li;
    }));
  }

  // —— 热度地图：服务端已渲染好格子，这里只换语言；中文原题提示保存在 data-tip，切回中文时还原 ——
  function renderHeat() {
    var w = $("heat");
    if (!w) return;
    var lg = w.querySelector(".hm-legend");
    if (lg) { var sp = lg.querySelectorAll("span"); if (sp[0]) sp[0].textContent = T.cold; if (sp[1]) sp[1].textContent = T.hot; if (sp[2]) sp[2].textContent = T.tz; }
    all("table.hm tbody th", w).forEach(function (th) {
      var k = th.getAttribute("data-cat") || th.textContent; th.setAttribute("data-cat", k); th.textContent = T.cat[k] || k; });
    all("table.hm td.hm-c", w).forEach(function (td) {
      var tip = td.getAttribute("data-tip");
      if (tip == null) { tip = td.getAttribute("title") || ""; td.setAttribute("data-tip", tip); }
      if (lang === "zh" && tip) td.setAttribute("title", tip); else td.removeAttribute("title");
    });
  }

  // —— 搜索：头版/营销块在 DOM 里隐藏不命中的卡片；Chronik 在数据层过滤（见 renderTimeline） ——
  function visibleCards(box) { return all(".card", box).filter(function (c) { return !(c.closest("li") || c).hidden; }); }
  function applyFilter() {
    var q = tl.q.trim().toLowerCase(), n = 0, seen = {};
    all(".card[data-hay]").forEach(function (c) {
      var ok = !q || c.getAttribute("data-hay").indexOf(q) >= 0;
      (c.closest("li") || c).hidden = !ok;
      var id = c.getAttribute("data-id");
      if (ok && !seen[id]) { seen[id] = 1; n++; }
    });
    all(".blk-lead,.blk-top").forEach(function (b) { b.hidden = !!q && !visibleCards(b).length; });
    $("multi").hidden = !(multiShow && (!q || visibleCards($("multi")).length > 0));
    $("mk-ext").hidden = !(mkOpen || (q && visibleCards($("mk-ext")).length > 0));
    $("marketing").hidden = !!q && !visibleCards($("marketing")).length;
    var st = $("q-status");
    if (q) {
      var b = el("button", "linklike", T.clear);
      b.type = "button"; b.setAttribute("data-clearq", "1");
      setKids(st, [document.createTextNode(T.found(n, tl.q.trim())), b]);
      st.hidden = false;
    } else st.hidden = true;
  }

  // ======================= 往期页 =======================
  // 卡片由 build.py 静态渲染（德语为默认，无 JS 也能读、能被抓取）；这里只做换语言、#marketing 筛选与已读变灰
  function arPick(a) {
    var g = function (k) { return a.getAttribute("data-" + k) || ""; };
    var order = lang === "zh" ? ["zh", "src"] : lang === "en" ? ["en", "de", "src", "zh"] : ["de", "en", "src", "zh"];
    for (var i = 0; i < order.length; i++) { var v = g(order[i]); if (v) return { t: v, orig: order[i] === "src" }; }
    return { t: a.textContent, orig: false };
  }
  function renderArchive() {
    all(".card[data-id]").forEach(function (c) {
      var a = c.querySelector(".title a"), tg = c.querySelector(".tag-orig"), ol = c.querySelector(".oneliner");
      if (a) { var r = arPick(a); a.textContent = r.t; if (tg) { tg.textContent = T.orig; tg.hidden = !r.orig; } }
      if (ol) {
        var de = ol.getAttribute("data-de") || "", en = ol.getAttribute("data-en") || "", zh = ol.getAttribute("data-zh") || "";
        var v = lang === "zh" ? zh : lang === "en" ? (en || de) : (de || en);
        ol.textContent = v; ol.hidden = !v;
      }
      all(".cat[data-rub]", c).forEach(function (s) { s.textContent = T.rub[s.getAttribute("data-rub")] || ""; });
      all(".tag-off", c).forEach(function (s) { s.textContent = T.off; });
      all(".tm[data-t]", c).forEach(function (s) {
        var p = bparts(s.getAttribute("data-t"));
        if (p) s.textContent = (s.getAttribute("data-k") === "pub" ? T.pub : T.seen) + " " + fmtTime(p, true);
      });
      c.classList.toggle("is-read", isRead(c.getAttribute("data-id")));
    });
    all("[data-month]").forEach(function (m) { m.textContent = monthStr(m.getAttribute("data-month")); });
    arFilter();
  }
  function arFilter() {
    var mk = location.hash === "#marketing", nd = 0, ni = 0;
    all(".card[data-rub]").forEach(function (c) {
      (c.closest("li") || c).hidden = mk && (" " + c.getAttribute("data-rub") + " ").indexOf(" marketing ") < 0;
    });
    all(".day-group[data-date]").forEach(function (g) {
      var n = all(".day-list > li", g).filter(function (li) { return !li.hidden; }).length;
      g.hidden = !n;
      if (n) { nd++; ni += n; }
      var dl = g.querySelector(".dl"), dn = g.querySelector(".day .n");
      if (dl) dl.textContent = dateStr(ordOf(g.getAttribute("data-date")));
      if (dn) dn.textContent = T.nItems(n);
    });
    all(".ar-month").forEach(function (m) {
      var vis = all(".day-group", m).some(function (g) { return !g.hidden; });
      m.hidden = !vis;
      var a = document.querySelector('.ar-months a[href="#' + m.id + '"]');
      if (a) a.hidden = !vis;
    });
    all("[data-ar]").forEach(function (a) { a.setAttribute("aria-current", (a.getAttribute("data-ar") === "marketing") === mk ? "true" : "false"); });
    var cnt = $("ar-count"); if (cnt) cnt.textContent = T.arN(nd, ni);
    var em = $("ar-empty"); if (em) { em.textContent = T.arNone; em.hidden = ni > 0; }
  }

  // ======================= 开关与事件 =======================
  function render() {
    applyStatic();
    if (PAGE === "archive") { renderArchive(); updateFresh(); return; }
    prep(); renderFront(); renderMulti(); renderMarketing(); renderTimeline(); renderCats(); renderHeat(); updateFresh(); applyFilter();
  }
  function setLang(k) {
    if (!I18N[k] || k === lang) return;
    lang = k; T = I18N[k];
    sset("lang", k);
    try { var u = new URL(location.href); u.searchParams.set("lang", k); history.replaceState(null, "", u); } catch (e) {}
    render();
  }
  function rerenderList() { renderTimeline(); renderCats(); applyFilter(); }

  function onOpen(e) {
    var a = e.target && e.target.closest ? e.target.closest("a[data-open]") : null;
    if (!a) return false;
    var c = a.closest(".card[data-id]");
    if (c) markRead(c.getAttribute("data-id"));
    return true;
  }
  document.addEventListener("click", function (e) {
    var t = e.target, b;
    if (!t || !t.closest) return;
    if (onOpen(e)) return;
    if ((b = t.closest("[data-lang]"))) { setLang(b.getAttribute("data-lang")); return; }
    if (t.closest("#theme-btn")) { toggleTheme(); return; }
    if (PAGE === "archive") {
      if ((b = t.closest('[data-ar="all"]'))) {
        e.preventDefault();
        try { history.replaceState(null, "", location.pathname + location.search); } catch (err) {}
        arFilter();
      }
      return;
    }
    if ((b = t.closest("[data-scope]"))) { tl.scope = b.getAttribute("data-scope") === "all" ? "all" : "selected"; applyStatic(); rerenderList(); return; }
    if ((b = t.closest(".cat-btn"))) {
      var c = b.getAttribute("data-cat");
      tl.cat = tl.cat === c ? null : c;
      rerenderList();
      if (tl.cat) $("timeline").scrollIntoView();
      return;
    }
    if (t.closest("[data-clearcat]")) { tl.cat = null; rerenderList(); return; }
    if (t.closest("[data-clearq]")) { $("q").value = ""; tl.q = ""; rerenderList(); return; }
    if (t.closest("#more")) { moreDay(); applyFilter(); return; }
    if (t.closest("#mk-btn")) { mkOpen = !mkOpen; renderMarketing(); applyFilter(); return; }
  });
  // 中键 / 新标签页打开也算「点开过」
  document.addEventListener("auxclick", function (e) { if (e.button === 1) onOpen(e); });

  if (PAGE === "archive") {
    window.addEventListener("hashchange", arFilter);
  } else {
    var sf = $("search-form"), qi = $("q");
    if (sf) sf.addEventListener("submit", function (e) { e.preventDefault(); tl.q = qi.value; rerenderList(); });
    if (qi) qi.addEventListener("input", function () { if (this.value === "" && tl.q !== "") { tl.q = ""; rerenderList(); } });
    var hw = $("heat");
    if (hw && window.matchMedia && window.matchMedia("(min-width: 700px)").matches) hw.open = true;
    setInterval(updateFresh, 60000);
  }
  // 窄屏往下滚时顶栏收紧（只藏日期行、缩报头）
  var tbar = $("topbar"), ticking = false;
  if (tbar) window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      var y = window.pageYOffset || 0, c = tbar.classList.contains("compact");
      if (!c && y > 200) tbar.classList.add("compact");
      else if (c && y < 80) tbar.classList.remove("compact");
    });
  }, { passive: true });

  render();
})();
