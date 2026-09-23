/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改） */
(function () {
  "use strict";
  var TZ = "Europe/Berlin";
  var RUBS = ["marketing", "unternehmen", "china", "modelle", "robotik", "forschung"];
  var I18N = {
    de: {
      locale: "de-DE", title: "KI-Nachrichten · Was heute in der KI zählt", wordmark: "KI-Nachrichten",
      rub: { marketing: "Marketing & Commerce", unternehmen: "KI im Unternehmen", china: "China global",
             modelle: "Modelle & Infrastruktur", robotik: "Robotik", forschung: "Forschung & Tools" },
      cat: { "模型": "Modelle", "产品": "Produkte", "研究": "Forschung", "行业": "Branche" },
      top: "Top-Themen", timeline: "Chronik", empty: "Noch keine Meldungen heute",
      today: "Heute", yesterday: "Gestern", more: "Ältere Meldungen laden", heat: "Hitze",
      expand: "Mehr", why: "Warum es zählt", nsrc: "{n} Quellen berichten", single: "Einzelquelle",
      pub: "Veröffentlicht", origTitle: "Originaltitel", orig: "Original",
      heatTitle: "Themen-Hitzekarte", heatSub: "Je dunkler, desto mehr Relevanz an diesem Tag (Hitze × Quellen)",
      cold: "kalt", hot: "heiß", tz: "Tage nach Berliner Zeit",
      mins: "vor {n} Min.", hours: "vor {n} Std.", updated: "Zuletzt aktualisiert {t}",
      f: { sources: "Quellen", impressum: "Impressum", privacy: "Datenschutz", api: "API", rss: "RSS",
           note: "Auswahl, Zusammenfassung und Übersetzung KI-gestützt; Links führen zur Originalquelle." }
    },
    en: {
      locale: "en-GB", title: "AI News · What matters in AI today", wordmark: "AI News",
      rub: { marketing: "Marketing & Commerce", unternehmen: "AI in Business", china: "China global",
             modelle: "Models & Infrastructure", robotik: "Robotics", forschung: "Research & Tools" },
      cat: { "模型": "Models", "产品": "Products", "研究": "Research", "行业": "Industry" },
      top: "Top stories", timeline: "Timeline", empty: "No stories yet today",
      today: "Today", yesterday: "Yesterday", more: "Load older stories", heat: "Heat",
      expand: "More", why: "Why it matters", nsrc: "{n} sources reporting", single: "Single source",
      pub: "Published", origTitle: "Original title", orig: "Original",
      heatTitle: "Topic heat map", heatSub: "Darker = more relevant that day (heat × sources)",
      cold: "cold", hot: "hot", tz: "Days in Berlin time",
      mins: "{n} min ago", hours: "{n} h ago", updated: "Last updated {t}",
      f: { sources: "Sources", impressum: "Imprint", privacy: "Privacy", api: "API", rss: "RSS",
           note: "Selection, summaries and translations are AI-assisted; links go to the original source." }
    },
    zh: {
      locale: "zh-CN", title: "AI 资讯时间线 · 每天扫上百条，只留值得看的", wordmark: "AI 资讯时间线",
      rub: { marketing: "营销与电商", unternehmen: "欧洲企业 AI 应用", china: "中国 AI 出海",
             modelle: "大模型与基建", robotik: "具身智能", forschung: "论文与工具" },
      cat: { "模型": "模型", "产品": "产品", "研究": "研究", "行业": "行业" },
      top: "要闻", timeline: "时间线", empty: "今天暂无消息",
      today: "今天", yesterday: "昨天", more: "加载更早的消息", heat: "热度",
      expand: "展开", why: "值得细看", nsrc: "共 {n} 家报道", single: "单一信源",
      pub: "发布时间", origTitle: "原文题", orig: "原文",
      heatTitle: "热度地图", heatSub: "格子越深＝该主题当天越值得关注（热度×多源）",
      cold: "冷", hot: "烫", tz: "日期按柏林时间切",
      mins: "{n} 分钟前", hours: "{n} 小时前", updated: "最后更新 {t}",
      f: { sources: "信源", impressum: "Impressum", privacy: "数据保护", api: "API", rss: "RSS",
           note: "筛选、摘要与翻译由 AI 辅助完成，链接指向原始出处。" }
    }
  };
  var CJK = /[㐀-鿿]/;

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fmt(s, n) { return s.replace("{n}", n); }
  function readJSON(id) { try { return JSON.parse($(id).textContent); } catch (e) { return null; } }

  var seed = readJSON("seed-data") || { items: [] };
  var rubMap = readJSON("rubriken-data") || {};
  var lang = pickLang();
  var T = I18N[lang];

  function pickLang() {
    var q = null;
    try { q = new URLSearchParams(location.search).get("lang"); } catch (e) {}
    if (q && I18N[q]) return q;
    try { var s = localStorage.getItem("lang"); if (s && I18N[s]) return s; } catch (e) {}
    var nav = ((navigator.languages && navigator.languages[0]) || navigator.language || "").slice(0, 2).toLowerCase();
    if (I18N[nav]) return nav;
    return "de";
  }

  function when(it) { var s = it.published_utc || it.first_seen_utc; var d = s ? new Date(s) : null; return d && !isNaN(d) ? d : null; }
  var dayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
  function dayKey(d) { return dayFmt.format(d); }
  function nSrc(it) { return parseInt(it.n_sources, 10) || ((it.clusters || []).length + 1); }
  function heat(it) { return parseFloat(it.heat) || 0; }

  function title(it) {
    if (lang === "zh") {
      if (it.title_zh) return { t: it.title_zh };
      return it.title_src ? { t: it.title_src, orig: true } : null;
    }
    var order = lang === "de" ? ["title_de", "title_en", "title_src"] : ["title_en", "title_de", "title_src"];
    for (var i = 0; i < order.length; i++) {
      var v = it[order[i]];
      if (v && !CJK.test(v)) return { t: v, orig: order[i] === "title_src" };
    }
    return null; // DE/EN 视图永远不落到中文
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
  function srcName(it) {
    var s = it.source_name || "";
    if (lang !== "zh" && CJK.test(s)) { try { s = new URL(it.url).hostname.replace(/^www\./, ""); } catch (e) {} }
    return s;
  }
  function rubsOf(it) { return rubMap[it.id || it.url] || ["forschung"]; }

  function timeStr(d) {
    var diff = (Date.now() - d.getTime()) / 60000;
    if (diff >= 0 && diff < 60) return fmt(T.mins, Math.max(1, Math.round(diff)));
    if (diff >= 0 && diff < 24 * 60) return fmt(T.hours, Math.round(diff / 60));
    return new Intl.DateTimeFormat(T.locale, { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(d);
  }
  function clock(d) { return new Intl.DateTimeFormat(T.locale, { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d); }

  // 预处理：只留当前语言能显示的条目
  var all = [];
  (seed.items || []).forEach(function (it) {
    var d = when(it), tt = title(it);
    if (!d || !tt) return;
    all.push({ it: it, d: d, day: dayKey(d), tt: tt });
  });
  all.sort(function (a, b) { return b.d - a.d; });
  var days = [];
  all.forEach(function (x) { if (days.indexOf(x.day) < 0) days.push(x.day); });
  var todayKey = dayKey(new Date());
  var yKey = dayKey(new Date(Date.now() - 864e5));

  function dach(x) { var r = rubsOf(x.it)[0]; return esc(T.rub[r] + " · " + srcName(x.it)); }
  function hlHTML(x, tag) {
    return "<" + tag + ' class="hl"><a href="' + esc(x.it.url) + '" target="_blank" rel="noopener">' + esc(x.tt.t) + "</a>" +
      (x.tt.orig && lang === "zh" ? '<span class="orig">' + esc(T.orig) + "</span>" : "") + "</" + tag + ">";
  }
  function card(x) {
    var l = liner(x.it);
    return '<article class="card"><p class="dach">' + dach(x) + "</p>" + hlHTML(x, "h3") +
      (l ? '<p class="vor">' + esc(l) + "</p>" : "") + '<div class="meta">' + esc(timeStr(x.d)) + "</div></article>";
  }

  function renderStatic() {
    document.documentElement.lang = lang;
    document.title = T.title;
    $("wordmark").textContent = T.wordmark;
    $("today-date").textContent = new Intl.DateTimeFormat(T.locale, { timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
    ["de", "en", "zh"].forEach(function (k) { $("lang-" + k).setAttribute("aria-pressed", String(k === lang)); });
    $("rubnav-in").innerHTML = RUBS.map(function (r) { return '<a href="#rub-' + r + '" data-r="' + r + '">' + esc(T.rub[r]) + "</a>"; }).join("");
    document.querySelectorAll("[data-f]").forEach(function (el) { el.textContent = T.f[el.getAttribute("data-f")]; });
    $("heat-sum").textContent = T.heatTitle;
    $("heat-sub").textContent = T.heatSub;
    var lg = document.querySelector(".hm-legend");
    if (lg) { var sp = lg.querySelectorAll("span"); if (sp[0]) sp[0].textContent = T.cold; if (sp[1]) sp[1].textContent = T.hot; if (sp[2]) sp[2].textContent = T.tz; }
    document.querySelectorAll("table.hm tbody th").forEach(function (th) {
      var k = th.getAttribute("data-cat") || th.textContent; th.setAttribute("data-cat", k); th.textContent = T.cat[k] || k; });
    if (lang !== "zh") document.querySelectorAll("table.hm td[title]").forEach(function (td) { td.removeAttribute("title"); });
    var g = seed.generated_at_utc ? new Date(seed.generated_at_utc) : null;
    if (g && !isNaN(g)) {
      $("last-updated").textContent = T.updated.replace("{t}", timeStr(g));
      if ((Date.now() - g) / 60000 > 180) $("last-updated").classList.add("stale");
    }
  }

  function renderLead() {
    var pool = all.filter(function (x) { return x.day === todayKey; });
    if (!pool.length) pool = all.filter(function (x) { return x.day === (days.indexOf(yKey) >= 0 ? yKey : days[0]); });
    var two = all.filter(function (x) { return x.day === days[0] || x.day === days[1]; });
    var rank = function (a, b) { return (nSrc(b.it) > 1) - (nSrc(a.it) > 1) || (!!liner(b.it)) - (!!liner(a.it)) || heat(b.it) - heat(a.it); };
    pool = pool.slice().sort(rank);
    var lead = pool[0];
    if (!lead) { $("lead").innerHTML = '<p class="empty">' + esc(T.empty) + "</p>"; return null; }
    var l = liner(lead.it);
    var top = two.filter(function (x) { return x !== lead; })
      .sort(function (a, b) { return heat(b.it) * nSrc(b.it) - heat(a.it) * nSrc(a.it); }).slice(0, 5);
    $("lead").innerHTML = '<div class="aufm"><p class="dach">' + dach(lead) + "</p>" + hlHTML(lead, "h1") +
      (l ? '<p class="vor">' + esc(l) + "</p>" : "") +
      '<div class="meta">' + esc(timeStr(lead.d)) + " · " + esc(nSrc(lead.it) > 1 ? fmt(T.nsrc, nSrc(lead.it)) : T.single) + "</div></div>" +
      '<aside class="top5"><h2>' + esc(T.top) + "</h2><ol>" + top.map(function (x) {
        return '<li><div><p class="dach">' + dach(x) + "</p>" + hlHTML(x, "h3") + "</div></li>"; }).join("") + "</ol></aside>";
    return lead;
  }

  function renderBlocks() {
    $("rubrics").innerHTML = RUBS.map(function (r) {
      var list = all.filter(function (x) { return rubsOf(x.it).indexOf(r) >= 0; }).slice(0, 6);
      return '<section class="block" id="rub-' + r + '"><h2>' + esc(T.rub[r]) + "</h2>" +
        (list.length ? '<div class="grid">' + list.map(card).join("") + "</div>" : '<p class="empty">' + esc(T.empty) + "</p>") + "</section>";
    }).join("");
  }

  function dayLabel(k) {
    if (k === todayKey) return T.today;
    if (k === yKey) return T.yesterday;
    var p = k.split("-");
    return new Intl.DateTimeFormat(T.locale, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" })
      .format(new Date(Date.UTC(+p[0], +p[1] - 1, +p[2], 12)));
  }
  function row(x) {
    var it = x.it, l = liner(it), w = why(it), n = nSrc(it);
    var det = "";
    if (w || n > 1 || x.tt.t !== it.title_src) {
      det = "<details><summary>" + esc(T.expand) + "</summary>" +
        (w ? "<p><strong>" + esc(T.why) + ":</strong> " + esc(w) + "</p>" : "") +
        (it.title_src && it.title_src !== x.tt.t && (lang === "zh" || !CJK.test(it.title_src)) ? "<p><strong>" + esc(T.origTitle) + ":</strong> " + esc(it.title_src) + "</p>" : "") +
        "<p><strong>" + esc(T.pub) + ":</strong> " + esc(new Intl.DateTimeFormat(T.locale, { timeZone: TZ, dateStyle: "medium", timeStyle: "short" }).format(x.d)) + "</p>" +
        "</details>";
    }
    return '<article class="row"><div class="t">' + esc(clock(x.d)) + '</div><div><p class="dach">' + dach(x) + "</p>" + hlHTML(x, "h3") +
      (l ? '<p class="vor">' + esc(l) + "</p>" : "") +
      '<div class="meta">' + esc(T.heat) + " " + Math.round(heat(it)) + " · " + esc(n > 1 ? fmt(T.nsrc, n) : T.single) + "</div>" + det + "</div></article>";
  }
  var shown = 0;
  function renderDay(k) {
    var list = all.filter(function (x) { return x.day === k; });
    var el = document.createElement("div");
    el.innerHTML = '<h3 class="day">' + esc(dayLabel(k)) + "</h3>" + list.map(row).join("");
    $("tl-days").appendChild(el);
  }
  function renderTimeline() {
    $("tl-title").textContent = T.timeline;
    $("tl-days").innerHTML = "";
    shown = 0;
    // 只渲染最近两天（今天+昨天）进 DOM，更早的按钮追加
    while (shown < Math.min(2, days.length)) renderDay(days[shown++]);
    var btn = $("more");
    btn.textContent = T.more;
    btn.hidden = shown >= days.length;
  }

  function setLang(k) {
    try { localStorage.setItem("lang", k); } catch (e) {}
    try { var u = new URL(location.href); u.searchParams.set("lang", k); history.replaceState(null, "", u); } catch (e) {}
    location.reload();
  }

  renderStatic();
  renderLead();
  renderBlocks();
  renderTimeline();
  $("more").addEventListener("click", function () {
    if (shown < days.length) renderDay(days[shown++]);
    this.hidden = shown >= days.length;
  });
  ["de", "en", "zh"].forEach(function (k) { $("lang-" + k).addEventListener("click", function () { if (k !== lang) setLang(k); }); });
  $("rubnav-in").addEventListener("click", function (e) {
    var a = e.target.closest("a"); if (!a) return;
    this.querySelectorAll("a").forEach(function (x) { x.classList.toggle("on", x === a); });
  });
  var hw = $("heat");
  if (hw && window.matchMedia && window.matchMedia("(min-width: 700px)").matches) hw.open = true;
})();
