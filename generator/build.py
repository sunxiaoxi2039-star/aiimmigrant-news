#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 资讯时间线 · 静态站生成器

用法（纯标准库，零依赖）：
    /opt/homebrew/bin/python3 generator/build.py [数据JSON路径] [输出目录]

默认：
    数据 = <发布仓>/data/精选库.json （即本脚本所在目录的 ../data/精选库.json）
    输出 = <发布仓> 根目录

产物（全部在 .gitignore 白名单内）：
    index.html / about.html / 404.html / assets/style.css / assets/app.js
    feed.xml / llms.txt / agents/index.html                      （2026-09-22 P1：agent 可接入）
    api/v1/latest.json / api/v1/sources.json / api/v1/heartbeat.json

数据契约见项目根《建站规格书》。时间在数据里一律 UTC，页面渲染统一 Europe/Berlin（由 app.js 用 Intl 完成，自动跟随夏令时）。
"""

import json
import pathlib
import sys
from html import escape as hesc

# ---------------------------------------------------------------------------
# 品牌与站点常量：改名只动这一个字典（D4 换名时一处替换）
# ---------------------------------------------------------------------------
CONFIG = {
    "SITE_NAME": "AI 资讯时间线",
    "SITE_TAGLINE": "每天扫上百条，只留值得看的",
    "SITE_DESCRIPTION": (
        "给中文读者的 AI 时间线：模型 / 产品 / 研究 / 行业，按柏林时间排列，"
        "标注抢跑时长与多源报道，每条卡片可展开核对英文原文引句。"
    ),
    "DOMAIN": "news.aiimmigrant.de",
    "ISSUES_URL": "https://github.com/sunxiaoxi2039-star/aiimmigrant-news/issues",
    "CATEGORIES": ["模型", "产品", "研究", "行业"],
    "STALE_MINUTES": 180,   # 页脚最后更新超过该分钟数变红
    "REPO_NAME": "aiimmigrant-news",
}

# ---------------------------------------------------------------------------
# assets/style.css —— 移动端优先，375px 起步，桌面是加宽版
# ---------------------------------------------------------------------------
CSS = r"""/* AI 资讯时间线 · 样式（生成器产出，勿手改：generator/build.py）
   版式语法：单一品牌色 + 黑白灰，细分隔线，衬线标题，无彩色盒子/阴影/徽章 */
@font-face {
  font-family: "SiteSerif";
  src: url("fonts/SourceSerif4.woff2") format("woff2");
  font-weight: 400 700; font-style: normal; font-display: swap;
}
:root {
  --brand: #0b2a4a;
  --ink: #111;
  --sub: #5c5c5c;
  --line: #d9d9d9;
  --bg: #fff;
  --soft: #f4f4f4;
  --serif: "SiteSerif", Georgia, "Times New Roman", "Songti SC", serif;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Noto Sans CJK SC", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root { --brand: #8fb4dc; --ink: #ececec; --sub: #a3a3a3; --line: #333; --bg: #121212; --soft: #1c1c1c; }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 16px; line-height: 1.5; }
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap, .container { max-width: 1180px; margin: 0 auto; padding: 0 16px; }

/* ① 顶栏 */
header.site { border-bottom: 1px solid var(--line); padding: 0; }
.top { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px; padding-top: 12px; padding-bottom: 12px; }
.top .date { font-size: 13px; color: var(--sub); }
.wordmark { font-family: var(--serif); font-weight: 700; font-size: 30px; letter-spacing: -.01em; color: var(--brand); text-align: center; white-space: nowrap; }
.wordmark:hover { text-decoration: none; }
.langs { justify-self: end; display: flex; gap: 2px; }
.langs button { font: 600 13px var(--sans); background: none; border: 0; border-bottom: 2px solid transparent; color: var(--sub); padding: 4px 6px; cursor: pointer; }
.langs button[aria-pressed="true"] { color: var(--ink); border-bottom-color: var(--brand); }

/* ② Rubriken 导航 */
.rubnav { border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--bg); z-index: 5; }
.rubnav .wrap { display: flex; gap: 22px; overflow-x: auto; scrollbar-width: none; }
.rubnav .wrap::-webkit-scrollbar { display: none; }
.rubnav a { font-size: 14px; font-weight: 600; padding: 11px 0 9px; border-bottom: 3px solid transparent; white-space: nowrap; }
.rubnav a:hover { text-decoration: none; color: var(--brand); }
.rubnav a.on { border-bottom-color: var(--brand); color: var(--brand); }
.rubnav a.xtog { margin-left: auto; font-weight: 500; }
.chip { display: inline-block; font: 600 10px/1.4 system-ui, sans-serif; letter-spacing: .04em; text-transform: uppercase; border: 1px solid currentColor; padding: 0 5px; margin-right: 7px; vertical-align: middle; color: var(--brand); }

/* 通用条目 */
.dach { font-size: 11.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--brand); margin: 0 0 4px; }
.hl { font-family: var(--serif); font-weight: 700; line-height: 1.2; margin: 0; }
.vor { color: var(--ink); margin: 6px 0 0; }
.meta { font-size: 12.5px; color: var(--sub); margin-top: 6px; }
.orig { font: 600 10.5px var(--sans); color: var(--sub); border: 1px solid var(--line); padding: 0 4px; margin-left: 6px; vertical-align: middle; }

/* ③ Aufmacher + Top-Themen */
.lead { display: grid; grid-template-columns: 1fr; gap: 20px; padding: 18px 0 20px; border-bottom: 1px solid var(--line); }
.lead .aufm .hl { font-size: 28px; }
.lead .vor { font-size: 17px; }
.top5 h2, .block h2, .tl h2, .heatwrap summary { font-family: var(--serif); font-size: 21px; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 2px solid var(--brand); }
.top5 ol { list-style: none; margin: 0; padding: 0; counter-reset: t; }
.top5 li { counter-increment: t; display: grid; grid-template-columns: 28px 1fr; padding: 9px 0; border-bottom: 1px solid var(--line); }
.top5 li::before { content: counter(t); font: 700 20px var(--serif); color: var(--brand); }
.lead .top5 .hl { font-size: 17px; }
.lead > *, .grid > *, .row > *, .top > * { min-width: 0; }
.hl { overflow-wrap: break-word; hyphens: auto; }
body { overflow-x: hidden; }
@media (min-width: 900px) {
  .lead { grid-template-columns: 2fr 1fr; gap: 36px; padding-top: 26px; }
  .lead .aufm .hl { font-size: 36px; }
  .lead > .aufm { padding-right: 36px; border-right: 1px solid var(--line); }
}

/* ④ Rubrik 分块 */
.block { padding: 26px 0 10px; scroll-margin-top: 50px; }
.grid { display: grid; grid-template-columns: 1fr; }
.card { padding: 12px 0; border-bottom: 1px solid var(--line); }
.card .hl { font-size: 20px; }
.card .vor { font-size: 14.5px; color: var(--sub); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.empty { color: var(--sub); font-style: italic; padding: 10px 0; }
@media (min-width: 760px) {
  .grid { grid-template-columns: repeat(3, 1fr); column-gap: 28px; }
}

/* ⑤ 时间线 */
.tl { padding: 26px 0 10px; }
.day { font: 700 13px var(--sans); text-transform: uppercase; letter-spacing: .06em; color: var(--sub); margin: 18px 0 0; padding-bottom: 6px; border-bottom: 1px solid var(--ink); }
.row { display: grid; grid-template-columns: 58px 1fr; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.row .t { font-size: 13px; color: var(--sub); padding-top: 2px; }
.row .hl { font-size: 18px; }
.row .vor { font-size: 14.5px; }
.row details { margin-top: 6px; font-size: 13.5px; }
.row summary { cursor: pointer; color: var(--brand); font-weight: 600; font-size: 12.5px; }
.row details p { margin: 6px 0; }
.more { display: block; margin: 20px auto; font: 600 14px var(--sans); background: none; color: var(--brand); border: 1px solid var(--brand); padding: 9px 20px; cursor: pointer; }

/* ⑥ 热度地图（单色） */
.heatwrap { margin: 26px 0 10px; }
.heatwrap summary { cursor: pointer; list-style: none; }
.heatwrap .hotbox { border: 0; padding: 0; margin: 10px 0 0; background: none; }
.heatwrap .hotbox > h2 { display: none; }
.hm-wrap { overflow-x: auto; }
table.hm { border-collapse: collapse; font-size: 12px; }
table.hm th { font-weight: 600; color: var(--sub); padding: 3px 8px; text-align: left; white-space: nowrap; }
table.hm td.hm-c { width: 44px; height: 30px; text-align: center; border: 2px solid var(--bg); font-size: 11px; }
.hm-0 { background: var(--soft); }
.hm-1 { background: rgba(11,42,74,.15); } .hm-2 { background: rgba(11,42,74,.32); }
.hm-3 { background: rgba(11,42,74,.52); color: #fff; } .hm-4 { background: rgba(11,42,74,.74); color: #fff; }
.hm-5 { background: rgba(11,42,74,.95); color: #fff; }
.hm-legend { display: flex; align-items: center; gap: 3px; font-size: 11.5px; color: var(--sub); margin-top: 8px; }
.hm-legend i { display: inline-block; width: 14px; height: 10px; }
.hm-legend .hm-tz { margin-left: 10px; }
.hm-bars { font-size: 13px; padding-left: 20px; }
.hm-bars li { padding: 3px 0; }
.hm-bt { display: inline-block; width: 80px; height: 6px; background: var(--soft); margin: 0 8px; vertical-align: middle; }
.hm-bt i { display: block; height: 6px; background: var(--brand); }
.hm-bn, .hm-bd { color: var(--sub); margin-right: 8px; }
html:not([lang^="zh"]) .hm-bars, html:not([lang^="zh"]) .hm-sub { display: none; }

/* ⑦ 页脚 */
footer { border-top: 2px solid var(--brand); margin-top: 30px; padding: 18px 0 30px; font-size: 13px; color: var(--sub); }
footer .links a { color: var(--ink); margin-right: 14px; display: inline-block; padding: 3px 0; }
footer p { margin: 8px 0 0; }
.upd.stale { color: #b00020; }
.noscript-box { padding: 16px 0; }

/* 关于页 / 404 */
.prose { max-width: 720px; margin: 0 auto; padding: 10px 16px 30px; }
.prose h2 { font-family: var(--serif); font-size: 22px; margin: 26px 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--line); }
.prose a { color: var(--brand); text-decoration: underline; }
header.site .tagline { color: var(--sub); margin: 2px 0 0; font-size: 13px; }
header.site h1 { font-family: var(--serif); color: var(--brand); margin: 0; font-size: 26px; }
header.site.container { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding-top: 14px; padding-bottom: 14px; }
header.site nav a { color: var(--brand); }
.center-404 { text-align: center; padding: 60px 16px; }
.center-404 .code { font: 700 64px var(--serif); color: var(--brand); }

/* 手机 */
@media (max-width: 600px) {
  .top { grid-template-columns: 1fr auto; padding-top: 8px; padding-bottom: 8px; }
  .top .date { grid-column: 1 / -1; order: 3; font-size: 12px; display: none; }
  .wordmark { font-size: 22px; text-align: left; }
  .lead { padding-top: 12px; }
  .lead .aufm .hl { font-size: 25px; }
  .lead .vor { font-size: 16px; }
}
"""

# ---------------------------------------------------------------------------
# assets/app.js —— 数据渲染 + 交互（含可被 Node 单测的纯函数层 TL）
# ---------------------------------------------------------------------------
JS = r"""/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改） */
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
      xnav: "Stimmen von X", xchip: "Stimme von X", off: "Offiziell", xempty: "Noch keine Stimmen heute",
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
      xnav: "Voices from X", xchip: "Voice from X", off: "Official", xempty: "No voices yet today",
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
      xnav: "X 风向", xchip: "X 观点", off: "官方", xempty: "今天暂无 X 声音",
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
  var kindMap = readJSON("kind-data") || {};
  var xOnly = false;
  try { xOnly = new URL(location.href).searchParams.get("kind") === "x"; } catch (e) {}
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
  function kindOf(it) { return kindMap[it.id || it.url] || { k: "medien" }; }
  function isX(x) { return kindOf(x.it).k === "x"; }
  // arXiv/GitHub 单源：簇里只有 HF Papers 等论文镜像也算单源
  function paper(x) {
    if (kindOf(x.it).k !== "forschung") return false;
    return (x.it.clusters || []).every(function (c) { return /arxiv\.org|github\.com|huggingface\.co/.test(c.url || ""); });
  }

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

  function dach(x) {
    var r = rubsOf(x.it)[0], k = kindOf(x.it);
    if (k.k === "x") return esc(T.rub[r] + " · X" + (k.h ? " · @" + k.h : ""));
    return esc(T.rub[r] + " · " + srcName(x.it));
  }
  function chip(x) {
    var k = kindOf(x.it).k;
    if (k === "x") return '<span class="chip">' + esc(T.xchip) + "</span>";
    if (k === "offiziell") return '<span class="chip">' + esc(T.off) + "</span>";
    return "";
  }
  function hlHTML(x, tag) {
    return "<" + tag + ' class="hl">' + chip(x) + '<a href="' + esc(x.it.url) + '" target="_blank" rel="noopener">' + esc(x.tt.t) + "</a>" +
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
    var rank = function (a, b) { return paper(a) - paper(b) || (nSrc(b.it) > 1) - (nSrc(a.it) > 1) || (!!liner(b.it)) - (!!liner(a.it)) || heat(b.it) - heat(a.it); };
    pool = pool.slice().sort(rank);
    var lead = pool[0];
    if (!lead) { $("lead").innerHTML = '<p class="empty">' + esc(T.empty) + "</p>"; return null; }
    var l = liner(lead.it);
    var nPaper = 0;
    var top = two.filter(function (x) { return x !== lead; })
      .sort(function (a, b) { return paper(a) - paper(b) || heat(b.it) * nSrc(b.it) - heat(a.it) * nSrc(a.it); })
      .filter(function (x) { if (!paper(x)) return true; return nPaper++ < 1; }).slice(0, 5);
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

  function renderX() {
    var list = all.filter(isX);
    $("lead").innerHTML = "";
    $("rubrics").innerHTML = '<section class="block" id="rub-x"><h2>' + esc(T.xnav) + "</h2>" +
      (list.length ? list.map(row).join("") : '<p class="empty">' + esc(T.xempty) + "</p>") + "</section>";
    $("tl-title").parentNode.hidden = true;
  }
  function xToggle() {
    var a = document.createElement("a");
    a.href = xOnly ? "?" : "?kind=x"; a.className = "xtog" + (xOnly ? " on" : ""); a.textContent = T.xnav;
    a.setAttribute("aria-pressed", String(xOnly));
    a.addEventListener("click", function (e) {
      e.preventDefault();
      try { var u = new URL(location.href); if (xOnly) u.searchParams.delete("kind"); else u.searchParams.set("kind", "x"); location.href = u.toString(); } catch (err) {}
    });
    $("rubnav-in").appendChild(a);
  }

  renderStatic();
  xToggle();
  if (xOnly) renderX(); else {
  renderLead();
  renderBlocks();
  renderTimeline();
  }
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
"""

# ---------------------------------------------------------------------------
# 页面模板（{{KEY}} 占位，避免 f-string 与 CSS/JS 花括号冲突）
# ---------------------------------------------------------------------------
HEAD_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{TITLE}}</title>
<meta name="description" content="{{SITE_DESCRIPTION}}">
<link rel="canonical" href="https://{{DOMAIN}}/">
<meta property="og:site_name" content="{{SITE_NAME}}">
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="{{SITE_DESCRIPTION}}">
<link rel="stylesheet" href="assets/style.css">
<link rel="alternate" type="application/rss+xml" title="{{SITE_NAME}}" href="/feed.xml">
<link rel="alternate" type="application/json" title="{{SITE_NAME}} · API v1" href="/api/v1/latest.json">
</head>
<body>
"""

INDEX_TMPL = HEAD_TMPL.replace('<html lang="zh-CN">', '<html lang="de">') + """
<header class="site">
  <div class="wrap top">
    <span class="date" id="today-date"></span>
    <a class="wordmark" id="wordmark" href="./">KI-Nachrichten</a>
    <div class="langs" role="group" aria-label="Sprache / Language / 语言">
      <button type="button" id="lang-de" aria-pressed="true">DE</button>
      <button type="button" id="lang-en" aria-pressed="false">EN</button>
      <button type="button" id="lang-zh" aria-pressed="false">ZH</button>
    </div>
  </div>
</header>
<nav class="rubnav" aria-label="Rubriken"><div class="wrap" id="rubnav-in"></div></nav>

<main class="wrap" id="main">
  <section class="lead" id="lead" aria-live="polite"></section>
  <div id="rubrics"></div>
  <section class="tl"><h2 id="tl-title">Chronik</h2><div id="tl-days"></div>
    <button type="button" class="more" id="more" hidden>Ältere Meldungen laden</button></section>
  <details class="heatwrap" id="heat"><summary id="heat-sum">Themen-Hitzekarte</summary>
    <p class="meta" id="heat-sub"></p>
    {{HEATMAP_HTML}}
  </details>
</main>

<footer>
  <div class="wrap">
    <div class="links"><a href="agents/" data-f="sources">Quellen</a><a href="about.html#impressum" data-f="impressum">Impressum</a><a href="about.html#datenschutz" data-f="privacy">Datenschutz</a><a href="api/v1/latest.json" data-f="api">API</a><a href="feed.xml" data-f="rss">RSS</a></div>
    <p><span data-f="note">Auswahl, Zusammenfassung und Übersetzung KI-gestützt; Links führen zur Originalquelle.</span> · <span id="last-updated" class="upd"></span></p>
  </div>
</footer>

<noscript><div class="wrap"><div class="noscript-box">JavaScript erforderlich. Rohdaten: <a href="data/%E7%B2%BE%E9%80%89%E5%BA%93.json">data/精选库.json</a></div></div></noscript>

<script type="application/json" id="seed-data">{{SEED_JSON}}</script>
<script type="application/json" id="rubriken-data">{{RUBRIKEN_JSON}}</script>
<script type="application/json" id="kind-data">{{KIND_JSON}}</script>
<script src="assets/app.js" defer></script>
</body>
</html>
"""

ABOUT_TMPL = HEAD_TMPL + """
<header class="site container">
  <div>
    <h1>{{SITE_NAME}}</h1>
    <p class="tagline">{{SITE_TAGLINE}}</p>
  </div>
  <nav><a href="index.html">回到时间线</a></nav>
</header>

<main class="prose">
  <section id="fuer-wen">
  <h2 lang="de">Für wen</h2>
  <ol lang="de">
    <li>Für Content-Schaffende in Europa, die hier jeden Tag ihre Themen finden und keinen Trend verpassen wollen – inklusive der Stimmung bei großen Accounts und offiziellen Kanälen auf X.</li>
    <li>Für Kundinnen und Kunden der Brücke nach China: europäische Investoren mit Interesse an chinesischer KI sowie chinesische Investoren und Praktiker, die sich für KI-Rechenleistung und Content-Export nach Europa interessieren.</li>
    <li>Für KI-Praktiker, die es genauer wissen wollen: Erstquellen, Originaltexte und eine eigene Datenpipeline über <a href="agents/">/agents/</a>.</li>
  </ol>
  <p lang="de">Wie ein gutes chinesisches KI-Briefing, nur europäischer: dreisprachig, europäische Zeitzone, europäische Erstquellen, ruhige Typografie.</p>

  <h2>给谁看</h2>
  <ol>
    <li>欧洲内容工作者：每天靠这站选题、不漏趋势，包括 X 上大 V 和官方号的风向。</li>
    <li>商桥的潜在客户：对中国 AI 感兴趣的欧洲投资者；对 AI 算力服务和内容出海感兴趣的中国投资者与从业者。</li>
    <li>稍硬核的 AI 从业者：要一手源、要原文、要能自己接管道（见 <a href="agents/">/agents/</a>）。</li>
  </ol>
  <p>像一份好的中文 AI 简报，只是更欧洲：三语、欧洲时区、欧洲一手源、安静的排版。</p>

  <h2 lang="en">Who this is for</h2>
  <ol lang="en">
    <li>Content creators in Europe who pick their daily topics here and don't want to miss a trend — including the mood among big accounts and official channels on X.</li>
    <li>Prospective clients of our China bridge: European investors interested in Chinese AI, and Chinese investors and practitioners interested in AI compute services and taking content abroad.</li>
    <li>Hands-on AI practitioners who want primary sources, original texts and their own pipeline via <a href="agents/">/agents/</a>.</li>
  </ol>
  <p lang="en">Like a good Chinese AI briefing, only more European: trilingual, European time zone, European primary sources, calm typography.</p>
  </section>

  <h2>这是什么</h2>
  <p>这是一张三语 AI 时间线。每天从上百条原始信号里，按一套固定的打分规则做筛选，只留下真正值得看的几条，按<strong>柏林时间</strong>（Europe/Berlin，含夏令时）排列成按天分组的时间线。覆盖四个分类：<strong>模型、产品、研究、行业</strong>。</p>
  <ul>
    <li><strong>三语界面</strong>：德语 / 英语 / 中文，标题与摘要按所选语言显示，缺译时回退到原文标题。</li>
    <li><strong>六个栏目</strong>：营销与电商、欧洲企业 AI 应用、中国 AI 出海、大模型与基建、具身智能、论文与工具。</li>
    <li><strong>多源核对</strong>：同一条新闻被多家媒体报道时合并为一条卡片，展开可见全部信源。</li>
    <li><strong>原文留痕</strong>：每张卡片可展开查看英文原文引句，方便你直接核对。</li>
  </ul>

  <h2>版权与免责声明</h2>
  <p>本站<strong>只收录「中文标题 + 一句话摘要 + 原文直链」</strong>，不翻译全文、不托管任何原文正文。所有内容的版权归原作者及原发布机构所有，请以原文链接所指页面为准。</p>
  <p>摘要由机器辅助生成，可能存在偏差；点击标题即可跳回原始出处。若您是权利人并认为某条收录不妥，请通过下方纠错通道提出，确认后我们会立即移除。</p>

  <h2>纠错与反馈</h2>
  <p>发现事实错误、失效链接或分类不当，请到 GitHub 仓库的 issue 区留言：</p>
  <p><a href="{{ISSUES_URL}}" target="_blank" rel="noopener noreferrer">{{ISSUES_URL}}</a></p>

  <h2>AI 辅助标注</h2>
  <p>本站的<strong>筛选、摘要与翻译由 AI 辅助完成</strong>，人工复核正在进行中。每条卡片附带的英文原文引句用于降低机器转述失真，也欢迎你监督。</p>

  <h2 id="impressum">Impressum</h2>
  <p lang="de">Impressum folgt.</p>
  <p lang="en">Imprint to follow.</p>
  <p>Impressum 即将补充。</p>

  <h2 id="datenschutz">Datenschutz</h2>
  <p lang="de">Datenschutzerklärung folgt.</p>
  <p lang="en">Privacy notice to follow.</p>
  <p>数据保护声明即将补充。</p>

  <p style="margin-top:30px"><a href="index.html">← 回到时间线</a></p>
</main>

<footer>
  <div class="container">
    <div class="links">{{SITE_NAME}} · <a href="index.html">时间线</a> · AI 辅助筛选，人工复核中</div>
  </div>
</footer>
</body>
</html>
"""

NOT_FOUND_TMPL = HEAD_TMPL + """
<main class="center-404">
  <div class="code">404</div>
  <p>这个页面不存在，可能已随时间线翻篇。</p>
  <p><a href="index.html">← 回到{{SITE_NAME}}首页</a></p>
</main>
<footer>
  <div class="container">
    <div class="links">{{SITE_NAME}} · <a href="about.html">关于 · 免责 · 纠错</a></div>
  </div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 构建逻辑
# ---------------------------------------------------------------------------
def tmpl(text, mapping):
    out = text
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def json_island(seed):
    """把 seed 序列化为可安全内嵌 <script type=application/json> 的字符串。"""
    s = json.dumps(seed, ensure_ascii=False, separators=(",", ":"))
    # JSON 里 < > & 只可能出现在字符串内，转成 \uXXXX 防止提前闭合 script 标签
    return s.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")


def load_seed(path):
    if not path.is_file():
        sys.stderr.write(
            "[build] 数据文件不存在: %s\n"
            "[build] 空态发布可先写入: "
            '{"generated_at_utc":"<当前UTC>","items":[]}\n' % path
        )
        raise SystemExit(2)
    try:
        seed = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        sys.stderr.write("[build] 数据文件不可解析: %s（%s）\n" % (path, e))
        raise SystemExit(2)
    if not isinstance(seed, dict):
        sys.stderr.write("[build] 数据顶层必须是对象 {generated_at_utc, items}\n")
        raise SystemExit(2)
    return seed


def normalize_seed(seed):
    items = seed.get("items")
    if not isinstance(items, list):
        items = []
    clean, dropped = [], 0
    for it in items:
        if (
            isinstance(it, dict)
            and (it.get("title_zh") or it.get("title_src"))
            and it.get("url")
        ):
            clean.append(it)
        else:
            dropped += 1
    seed["items"] = clean
    if not seed.get("generated_at_utc"):
        seed["generated_at_utc"] = "1970-01-01T00:00:00Z"
    return clean, dropped


def compute_hotbox(items, max_n=5):
    """D7 goal 第四刀：「今日热点 N 家源在报」服务端渲染。
    规则：
    - 多源簇条目（clusters 长度 > 0，n_sources ≥ 2）
    - published 在 24h 内（按当前时刻算）
    - 按簇源数降序 + published 越新越前
    - 取 top max_n
    返回 (html, n_hot) — n_hot=0 时 html=""（build 时该 div 自动隐藏）。
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    hot = []
    for it in items:
        clusters = it.get("clusters") or []
        n_src = int(it.get("n_sources") or len(clusters) + 1)
        if n_src < 2 or not clusters:
            continue
        pub = it.get("published_utc") or ""
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            continue
        age_h = (now - pub_dt).total_seconds() / 3600
        if age_h < 0 or age_h > 24:
            continue
        title = (it.get("title_zh") or it.get("title_src") or "").strip()
        url = it.get("url", "").strip()
        if not (title and url):
            continue
        # 收集所有报道源（自身 + clusters）；source_name 重复或太笼统时退回 host 二级域
        def _display_source(rec, fallback_url):
            sn = (rec.get("source_name") or "").strip()
            if sn and sn not in ("", "官方RSS", "官方博客"):  # 太笼统的退回 host
                return sn
            # 从 URL 抽 host 二级域（如 ithome.com / qbitai.com）
            import re as _re
            m = _re.search(r"https?://(?:www\.)?([^/]+)", fallback_url or "")
            if not m:
                return sn or "源"
            host = m.group(1).lower().split(":")[0]
            # 短化常见源名
            short_map = {
                "ithome.com": "IT之家", "qbitai.com": "量子位", "leiphone.com": "雷峰网",
                "infoq.cn": "InfoQ中国", "ifanr.com": "爱范儿", "tmtpost.com": "钛媒体",
                "theverge.com": "TheVerge", "theregister.com": "TheRegister",
                "golem.de": "Golem", "t3n.de": "t3n", "heise.de": "heise",
                "tech.eu": "Tech.eu", "faz.net": "FAZ", "github.blog": "GitHub官方博客",
                "blog.google": "Google博客", "openai.com": "OpenAI官网",
                "anthropic.com": "Anthropic官网", "deepmind.google": "DeepMind",
                "huggingface.co": "HuggingFace", "news.ycombinator.com": "HN",
            }
            return short_map.get(host, host)
        src_names = [_display_source(it, it.get("url", ""))]
        for c in clusters:
            sn = _display_source(c, c.get("url", ""))
            if sn and sn not in src_names:
                src_names.append(sn)
        hot.append({"title": title, "url": url, "n_sources": n_src,
                    "age_h": age_h, "src_names": src_names,
                    "selected": bool(it.get("selected"))})
    hot.sort(key=lambda x: (-x["n_sources"], x["age_h"]))
    hot = hot[:max_n]
    if not hot:
        return "", 0
    rows = []
    for i, h in enumerate(hot, 1):
        src_summary = "、".join(h["src_names"][:4])
        if len(h["src_names"]) > 4:
            src_summary += f" 等 {len(h['src_names'])} 家"
        meta = f" · {h['n_sources']} 家源在报（{src_summary}）"
        rows.append(
            f'<li><span class="n">#{i}</span> '
            f'<a href="{hesc(h["url"])}" target="_blank" rel="noopener">{hesc(h["title"])}</a>'
            f'<span class="meta">{hesc(meta)}</span></li>'
        )
    html = (
        '<section class="hotbox" aria-label="今日热点">'
        '<h2>今日热点 <span class="badge">' + str(len(hot)) + ' 事件</span></h2>'
        '<ol>' + "".join(rows) + '</ol></section>'
    )
    return html, len(hot)


# ---------------------------------------------------------------------------
# 2026-09-22 P3：热度地图 v0（AIradar-heatmap 式选题入口）
# 只吃现成数据——精选库里已有的 category / heat / clusters / 时间戳，
# 不新造任何模型调用。日期按 Europe/Berlin 切，跟前端同一套时区口径。
# ---------------------------------------------------------------------------
HEAT_DAYS = 7          # 格子图横轴天数
HEAT_LEVELS = 5        # 色阶档数（0 档=空格）


def _berlin_day(dt):
    """UTC aware datetime → 柏林当地 date。时区库缺席时退回 UTC，不抛。"""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Europe/Berlin")).date()
    except Exception:
        return dt.date()


def _item_time(it):
    """发布时间优先，缺了退回首见时间——787/1278 条没有 published_utc，
    只认 published 会让地图丢掉六成数据。两个都没有就放弃这条。"""
    for k in ("published_utc", "first_seen_utc"):
        dt = parse_iso(it.get(k) or "")
        if dt:
            return dt
    return None


def compute_heatmap(items, days=HEAT_DAYS):
    """主题 × 日期 热度格子图 + 近 24h 主题条。

    格子强度取该格 heat 之和（不是条数）：20 条边角料不该盖过 3 条多源大新闻。
    多源簇按源数加权，簇越多越烫——这正是「值得写」的信号。
    返回 (html, n_cells) ；无可用数据时 ("", 0)，模板里该块自动消失。
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    today = _berlin_day(now)
    day_keys = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    day_pos = {d: i for i, d in enumerate(day_keys)}
    cats = list(CONFIG["CATEGORIES"])

    # cell[(cat, day)] = {"score": float, "n": int, "titles": [..], "clusters": int}
    cell = {}
    last24 = {c: {"score": 0.0, "n": 0, "titles": []} for c in cats}
    for it in items:
        cat = (it.get("category") or "").strip()
        if cat not in cats:
            continue
        dt = _item_time(it)
        if not dt:
            continue
        d = _berlin_day(dt)
        if d not in day_pos:
            continue
        try:
            heat = float(it.get("heat") or 0.0)
        except (TypeError, ValueError):
            heat = 0.0
        n_src = len(it.get("clusters") or [])
        # 多源加权：每多一家源在报，权重 +35%
        w = heat * (1.0 + 0.35 * n_src)
        title = (it.get("title_zh") or it.get("title_src") or "").strip()
        rec = cell.setdefault((cat, d), {"score": 0.0, "n": 0, "titles": [], "clusters": 0})
        rec["score"] += w
        rec["n"] += 1
        rec["clusters"] += 1 if n_src else 0
        if title:
            rec["titles"].append((w, title))
        if (now - dt).total_seconds() <= 24 * 3600:
            last24[cat]["score"] += w
            last24[cat]["n"] += 1
            if title:
                last24[cat]["titles"].append((w, title))

    if not cell:
        return "", 0

    top = max(r["score"] for r in cell.values()) or 1.0

    def level(score):
        if score <= 0:
            return 0
        # 开方压一下长尾：否则一条爆款把整张图压成全灰
        import math
        frac = math.sqrt(score / top)
        return max(1, min(HEAT_LEVELS, int(math.ceil(frac * HEAT_LEVELS))))

    # ---- 格子图 ----
    head = "".join(
        '<th scope="col"><span>%s</span></th>' % hesc("%d/%d" % (d.month, d.day))
        for d in day_keys
    )
    rows = []
    for cat in cats:
        tds = []
        for d in day_keys:
            r = cell.get((cat, d))
            if not r:
                tds.append('<td class="hm-c hm-0" title="%s"></td>'
                           % hesc("%s · %d/%d · 无条目" % (cat, d.month, d.day)))
                continue
            lv = level(r["score"])
            tips = [t for _, t in sorted(r["titles"], reverse=True)[:3]]
            tip = "%s · %d/%d · %d 条 · 热度 %d" % (cat, d.month, d.day, r["n"], round(r["score"]))
            if r["clusters"]:
                tip += " · %d 条多源在报" % r["clusters"]
            for t in tips:
                tip += "\n— " + (t[:42] + "…" if len(t) > 42 else t)
            tds.append('<td class="hm-c hm-%d" title="%s"><span>%d</span></td>'
                       % (lv, hesc(tip), r["n"]))
        rows.append('<tr><th scope="row">%s</th>%s</tr>' % (hesc(cat), "".join(tds)))

    # ---- 近 24h 主题条 ----
    mx = max((v["score"] for v in last24.values()), default=0.0) or 1.0
    bars = []
    for cat, v in sorted(last24.items(), key=lambda kv: -kv[1]["score"]):
        if v["n"] == 0:
            continue
        pct = max(3, round(v["score"] / mx * 100))
        lead = ""
        if v["titles"]:
            t = sorted(v["titles"], reverse=True)[0][1]
            lead = t[:34] + "…" if len(t) > 34 else t
        bars.append(
            '<li><span class="hm-bl">%s</span>'
            '<span class="hm-bt"><i style="width:%d%%"></i></span>'
            '<span class="hm-bn">%d 条</span>'
            '<span class="hm-bd">%s</span></li>'
            % (hesc(cat), pct, v["n"], hesc(lead))
        )
    bar_html = ('<ol class="hm-bars">%s</ol>' % "".join(bars)) if bars else ''

    legend = "".join('<i class="hm-%d"></i>' % i for i in range(HEAT_LEVELS + 1))
    html = (
        '<section class="hotbox heatmap" aria-label="热度地图">'
        '<h2>热度地图 <span class="badge">近 %d 天</span>'
        '<span class="hm-sub">格子越烫＝该主题当天越值得写（热度分×多源加权，鼠标悬停看标题）</span></h2>'
        '<div class="hm-wrap"><table class="hm"><thead><tr><td></td>%s</tr></thead>'
        '<tbody>%s</tbody></table></div>'
        '<div class="hm-legend"><span>冷</span>%s<span>烫</span>'
        '<span class="hm-tz">日期按柏林时间切</span></div>'
        '%s</section>'
    ) % (days, head, "".join(rows), legend, bar_html)
    return html, len(cell)


# ---------------------------------------------------------------------------
# 2026-09-22 P1：agent 可接入层（RSS / JSON API / llms.txt / agents 页）
# 章程「重点保证」：网站首先要机器能直接吃。**版本号进路径，接口一旦公布不破坏**：
# 只增字段不删字段、不改字段含义；要改就开 /api/v2/。
# ---------------------------------------------------------------------------
API_VERSION = "v1"
FEED_MAX = 60          # RSS 条数上限（精选恒在，余额按 24h 新鲜度补）
FRESH_HOURS = 24       # 「24h 全量」档口径
LICENSE_NOTE = ("摘要、标题翻译与点评由本站 AI 生成，可自由取用（署名 news.aiimmigrant.de 即可）；"
                "原文版权归各信源所有，请始终带上 url 回链原文。")
UPDATE_NOTE = ("精选库随引擎轮次更新（常态每小时一轮，launchd :07）；"
               "2026-09-22 起为控预算暂停定时器，当前人工触发，恢复定时后本说明同步。"
               "接口无鉴权、无频控，请自觉别超过 1 次/分钟。")

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def parse_iso(v):
    """宽松解析 ISO8601 → aware datetime；不可解析返回 None（不抛，build 绝不因脏数据崩）。"""
    from datetime import datetime, timezone
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def rfc822(dt):
    """RFC 822 GMT（RSS pubDate 要求）；locale 无关，手写月份/星期名。"""
    from datetime import timezone
    d = dt.astimezone(timezone.utc)
    return "%s, %02d %s %04d %02d:%02d:%02d GMT" % (
        _DAYS[d.weekday()], d.day, _MONTHS[d.month - 1], d.year, d.hour, d.minute, d.second)


def public_item(it):
    """契约条目 → 对外稳定子集。字段名即公开契约，只增不改。"""
    return {
        "id": it.get("id"),
        "url": it.get("url"),
        "title": {"zh": it.get("title_zh"), "en": it.get("title_en"),
                  "de": it.get("title_de"), "src": it.get("title_src")},
        "one_liner": {"zh": it.get("one_liner_zh"), "en": it.get("one_liner_en"),
                      "de": it.get("one_liner_de")},
        "why_it_matters": {"zh": it.get("why_zh"), "en": it.get("why_en"), "de": it.get("why_de")},
        "category": it.get("category"),
        "source": {"name": it.get("source_name"), "tier": it.get("source_tier")},
        "published_utc": it.get("published_utc"),
        "first_seen_utc": it.get("first_seen_utc"),
        "scoop_hours": it.get("scoop_hours"),
        "selected": bool(it.get("selected")),
        "score": it.get("score"),
        "heat": it.get("heat"),
        "n_sources": int(it.get("n_sources") or len(it.get("clusters") or []) + 1),
        "also_reported_by": [{"name": c.get("source_name"), "url": c.get("url")}
                             for c in (it.get("clusters") or []) if isinstance(c, dict)],
        "quote_en": it.get("quote_en"),
    }


def split_items(items, now=None):
    """→ (精选, 24h 内全量)。两档口径固定，供 API 与 RSS 共用。"""
    from datetime import datetime, timezone, timedelta
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=FRESH_HOURS)
    selected, fresh = [], []
    for it in items:
        if it.get("selected"):
            selected.append(it)
        pub = parse_iso(it.get("published_utc")) or parse_iso(it.get("first_seen_utc"))
        if pub and pub >= cutoff:
            fresh.append(it)
    key = lambda x: parse_iso(x.get("published_utc")) or parse_iso(x.get("first_seen_utc")) \
        or datetime(1970, 1, 1, tzinfo=timezone.utc)
    selected.sort(key=key, reverse=True)
    fresh.sort(key=key, reverse=True)
    return selected, fresh


def build_latest_json(seed, items):
    selected, fresh = split_items(items)
    return {
        "api_version": API_VERSION,
        "generated_at_utc": seed.get("generated_at_utc"),
        "site": {"name": CONFIG["SITE_NAME"], "url": "https://" + CONFIG["DOMAIN"],
                 "tagline": CONFIG["SITE_TAGLINE"]},
        "license": LICENSE_NOTE,
        "update": UPDATE_NOTE,
        "counts": {"selected": len(selected), "fresh_24h": len(fresh), "total_pool": len(items)},
        "categories": CONFIG["CATEGORIES"],
        "selected": [public_item(i) for i in selected],
        "fresh_24h": [public_item(i) for i in fresh[:200]],
    }


def build_sources_json(registry):
    """信源登记表 → /api/v1/sources.json。registry 缺失时给出诚实的占位，不编数。"""
    if not isinstance(registry, dict) or not registry.get("sources"):
        return {"api_version": API_VERSION, "status": "pending",
                "note": "信源登记表尚未生成（引擎侧 引擎/信源对账.py 每日产出）",
                "counts": {}, "sources": []}
    out = dict(registry)
    out["api_version"] = API_VERSION
    out["license"] = LICENSE_NOTE
    out["note"] = ("我们与对标公开清单的逐项对账：status=connected 已接 / pending 待接 / "
                   "blocked 不可接。diff_vs_benchmark 是当日条目级差别。")
    return out


def build_feed_xml(seed, items):
    """RSS 2.0：精选恒在（category=精选），其余按 24h 新鲜度补足到 FEED_MAX（category=24h）。
    三语摘要走 content:encoded；中文标题 + 原文链接。"""
    from datetime import datetime, timezone
    selected, fresh = split_items(items)
    picked, seen = [], set()
    for it in selected:
        picked.append((it, "精选"))
        seen.add(it.get("url"))
    for it in fresh:
        if len(picked) >= FEED_MAX:
            break
        if it.get("url") in seen:
            continue
        picked.append((it, "24h"))
        seen.add(it.get("url"))
    gen = parse_iso(seed.get("generated_at_utc")) or datetime.now(timezone.utc)
    site = "https://" + CONFIG["DOMAIN"]
    rows = []
    for it, lane in picked:
        title = (it.get("title_zh") or it.get("title_src") or "").strip()
        url = (it.get("url") or "").strip()
        if not (title and url):
            continue
        pub = parse_iso(it.get("published_utc")) or parse_iso(it.get("first_seen_utc")) or gen
        parts = []
        for lang, label in (("zh", "中文"), ("en", "English"), ("de", "Deutsch")):
            one = (it.get("one_liner_" + lang) or "").strip()
            why = (it.get("why_" + lang) or "").strip()
            if one or why:
                parts.append("<p><strong>%s</strong>：%s%s</p>" % (
                    hesc(label), hesc(one), ("<br>" + hesc(why)) if why else ""))
        src = it.get("source_name") or ""
        parts.append('<p>来源：%s　等级 %s　<a href="%s">原文</a></p>' % (
            hesc(src), hesc(it.get("source_tier") or "-"), hesc(url)))
        body = "".join(parts).replace("]]>", "]]&gt;")
        cats = "".join("<category>%s</category>" % hesc(c)
                       for c in (lane, it.get("category") or "") if c)
        rows.append(
            "<item>"
            "<title>%s</title><link>%s</link>"
            '<guid isPermaLink="false">%s</guid>'
            "<pubDate>%s</pubDate>%s"
            "<description>%s</description>"
            "<content:encoded><![CDATA[%s]]></content:encoded>"
            "<source url=\"%s/feed.xml\">%s</source>"
            "</item>" % (
                hesc(title), hesc(url), hesc(it.get("id") or url), rfc822(pub), cats,
                hesc((it.get("one_liner_zh") or title).strip()), body,
                hesc(site), hesc(CONFIG["SITE_NAME"])))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n<channel>\n'
        "<title>%s</title>\n<link>%s/</link>\n<description>%s</description>\n"
        '<language>zh-CN</language>\n<lastBuildDate>%s</lastBuildDate>\n'
        '<atom:link href="%s/feed.xml" rel="self" type="application/rss+xml"/>\n'
        "<docs>https://www.rssboard.org/rss-specification</docs>\n"
        "<generator>%s build.py</generator>\n"
        "<copyright>%s</copyright>\n%s\n</channel>\n</rss>\n" % (
            hesc(CONFIG["SITE_NAME"]), hesc(site), hesc(CONFIG["SITE_DESCRIPTION"]),
            rfc822(gen), hesc(site), hesc(CONFIG["SITE_NAME"]), hesc(LICENSE_NOTE),
            "\n".join(rows)))


def build_llms_txt(seed, items, sources):
    selected, fresh = split_items(items)
    site = "https://" + CONFIG["DOMAIN"]
    sc = (sources or {}).get("counts") or {}
    src_line = ("已接 %s / 待接 %s / 不可接 %s（共 %s 项对标信源）" % (
        sc.get("connected", "?"), sc.get("pending", "?"), sc.get("blocked", "?"),
        sc.get("total", "?"))) if sc else "登记表生成中"
    return """# %(name)s

> %(desc)s

本站为机器读者（LLM / agent / 爬虫）提供稳定接口，**无需鉴权**。%(update)s

## 接口（版本号进路径，公布即不破坏）

- [%(site)s/api/%(v)s/latest.json](%(site)s/api/%(v)s/latest.json)：精选 %(nsel)d 条 + 24h 全量 %(nfresh)d 条。
  每条含 id、url、三语标题 title.{zh,en,de}、三语一句话 one_liner.{zh,en,de}、
  三语「为什么重要」why_it_matters.{zh,en,de}、category、source.{name,tier}、
  published_utc、first_seen_utc、scoop_hours（抢跑时长）、score/heat、
  n_sources 与 also_reported_by（多源报道簇）、quote_en（英文原文引句）。
- [%(site)s/api/%(v)s/sources.json](%(site)s/api/%(v)s/sources.json)：信源登记表 —— %(src)s。
- [%(site)s/api/%(v)s/heartbeat.json](%(site)s/api/%(v)s/heartbeat.json)：引擎心跳（when/status/selected/total），
  判断数据是否新鲜先看这个。
- [%(site)s/feed.xml](%(site)s/feed.xml)：RSS 2.0，中文标题 + 原文链接，三语摘要在 content:encoded；
  `<category>` 分「精选」与「24h」两档。
- [%(site)s/data/%%E7%%B2%%BE%%E9%%80%%89%%E5%%BA%%93.json](%(site)s/data/%%E7%%B2%%BE%%E9%%80%%89%%E5%%BA%%93.json)：
  完整精选库原始契约（字段最全，含评分闸门细节）。

## 怎么读

- 时间一律 UTC（字段后缀 `_utc`），页面展示按柏林时间（Europe/Berlin，Intl 自动跟夏令时）。
- `selected=true` 是当轮人工口径的精选；`fresh_24h` 是 24 小时内所有捕获。
- `scoop_hours` 是我们比同题报道早多少小时发现，负数表示落后。
- 摘要为 AI 生成，可能有误；`quote_en` 给的是英文原文引句，供你核对。

## 许可

%(lic)s

## 人读版

[%(site)s/agents/](%(site)s/agents/)　|　站点首页 [%(site)s/](%(site)s/)
""" % {"name": CONFIG["SITE_NAME"], "desc": CONFIG["SITE_DESCRIPTION"], "site": site,
       "v": API_VERSION, "nsel": len(selected), "nfresh": len(fresh),
       "lic": LICENSE_NOTE, "update": UPDATE_NOTE, "src": src_line}


AGENTS_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Agents / API · {{SITE_NAME}}</title>
<meta name="description" content="{{SITE_NAME}} 给 LLM 与 agent 的接口：RSS、JSON API、llms.txt，无需鉴权。">
<link rel="canonical" href="https://{{DOMAIN}}/agents/">
<link rel="stylesheet" href="/assets/style.css">
<link rel="alternate" type="application/rss+xml" title="{{SITE_NAME}}" href="/feed.xml">
<style>
.api table { width:100%; border-collapse:collapse; font-size:14px; margin:10px 0 22px; }
.api th,.api td { text-align:left; padding:8px 10px; border-bottom:1px solid rgba(128,128,128,.25); vertical-align:top; }
.api code, .api pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:13px; }
.api pre { padding:12px 14px; border-radius:8px; overflow-x:auto; background:rgba(128,128,128,.12); }
.api h2 { margin-top:30px; }
</style>
</head>
<body>
<header class="site container">
  <div>
    <h1>Agents / API</h1>
    <p class="tagline">给机器读者的入口 · 无鉴权 · 版本号进路径</p>
  </div>
  <nav><a href="/">时间线</a> · <a href="/about.html">关于</a></nav>
</header>

<main class="container api" id="main">
  <p>{{SITE_NAME}} 首先是给机器读的。下面五个地址随引擎每轮更新，直接 <code>curl</code> 即可，
  不需要 key、不需要 UA 伪装。<strong>接口一旦公布就不破坏</strong>：只增字段，要改就开 <code>/api/v2/</code>。</p>

  <h2>五个地址</h2>
  <table>
    <tr><th>地址</th><th>是什么</th><th>格式</th></tr>
    <tr><td><a href="/api/v1/latest.json"><code>/api/v1/latest.json</code></a></td>
        <td>精选 + 24h 全量，三语标题 / 一句话 / 为什么重要，含抢跑时长与多源簇</td><td>JSON</td></tr>
    <tr><td><a href="/api/v1/sources.json"><code>/api/v1/sources.json</code></a></td>
        <td>信源登记表：我们接了哪些源、哪些待接，以及与对标清单的当日差别</td><td>JSON</td></tr>
    <tr><td><a href="/api/v1/heartbeat.json"><code>/api/v1/heartbeat.json</code></a></td>
        <td>引擎心跳：上轮何时跑、成功与否、出了几条精选（判新鲜度看它）</td><td>JSON</td></tr>
    <tr><td><a href="/feed.xml"><code>/feed.xml</code></a></td>
        <td>RSS 2.0，中文标题 + 原文链接，三语摘要在 <code>content:encoded</code></td><td>XML</td></tr>
    <tr><td><a href="/llms.txt"><code>/llms.txt</code></a></td>
        <td>本页的机器版：字段说明与取数口径</td><td>Markdown</td></tr>
  </table>

  <h2>一行接入</h2>
  <p>Claude Code / Codex / Cursor 里直接让它去读：</p>
  <pre>把 https://{{DOMAIN}}/api/v1/latest.json 拉下来，按 selected 挑今天值得看的 AI 新闻，
每条给我中文一句话 + 原文链接，再说说为什么重要（字段 why_it_matters.zh）。</pre>
  <p>命令行：</p>
  <pre>curl -s https://{{DOMAIN}}/api/v1/latest.json | jq '.selected[] | {title: .title.zh, url, why: .why_it_matters.zh}'
curl -s https://{{DOMAIN}}/api/v1/heartbeat.json | jq '{when, status, selected}'
curl -s https://{{DOMAIN}}/feed.xml | head -40</pre>
  <p>MCP / RSS 阅读器：把 <code>https://{{DOMAIN}}/feed.xml</code> 加进订阅即可，
  <code>&lt;category&gt;精选&lt;/category&gt;</code> 是我们当轮挑出来的那几条。</p>

  <h2>字段口径</h2>
  <table>
    <tr><th>字段</th><th>含义</th></tr>
    <tr><td><code>title.{zh,en,de}</code> / <code>one_liner.*</code> / <code>why_it_matters.*</code></td>
        <td>三语标题、一句话摘要、为什么重要。AI 生成，可能有误。</td></tr>
    <tr><td><code>quote_en</code></td><td>英文原文引句，用来核对我们有没有写歪。</td></tr>
    <tr><td><code>scoop_hours</code></td><td>我们比同题报道早多少小时发现；负数表示落后。</td></tr>
    <tr><td><code>n_sources</code> / <code>also_reported_by</code></td><td>同一事件有几家在报、分别是谁。</td></tr>
    <tr><td><code>published_utc</code> / <code>first_seen_utc</code></td><td>原文发布时间 / 我们首次捕获时间，均为 UTC。</td></tr>
    <tr><td><code>source.tier</code></td><td>信源等级：T1 一手官方 / T2 专业媒体 / T3 聚合。</td></tr>
  </table>

  <h2>更新频率与许可</h2>
  <p>{{UPDATE_NOTE}}</p>
  <p>{{LICENSE_NOTE}}</p>
  <p style="margin-top:30px"><a href="/">← 回到时间线</a></p>
</main>

<footer>
  <div class="container">
    <div class="links">{{SITE_NAME}} · <a href="/">时间线</a> · <a href="/about.html">关于</a> · <a href="/llms.txt">llms.txt</a></div>
  </div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 2026-09-22 演示换皮：六个 Rubriken，规则打标，零模型；一条可多标
# ---------------------------------------------------------------------------
RUBRIKEN = [
    ("marketing", ["marketing", "seo", "sea", "geo", "aeo", "google ads", "display advertising", "ads", "adtech",
                   "programmatic", "shopify", "stripe", "checkout", "agentic commerce", "e-commerce", "ecommerce",
                   "retail", "amazon ads", "meta ads", "tiktok shop", "电商", "跨境", "直播带货", "营销", "广告", "投放"]),
    ("unternehmen", ["mittelstand", "sap", "siemens", "bosch", "telekom", "allianz", "volkswagen", "bmw", "mercedes",
                     "eu ai act", "ki-verordnung", "dsgvo", "gdpr", "enterprise", "企业落地", "欧洲", "europe", "europa",
                     "germany", "deutschland", "france", "brussels"]),
    ("china", ["出海", "算力", "短剧", "reelshort", "可灵", "kling", "海螺", "hailuo", "minimax", "deepseek", "qwen",
               "通义", "字节", "bytedance", "豆包", "智谱", "moonshot", "kimi", "腾讯", "阿里", "百度", "huawei", "华为"]),
    ("modelle", ["gpt", "claude", "gemini", "llama", "mistral", "grok", "opus", "sonnet", "gpu", "nvidia", "tpu",
                 "数据中心", "data center", "datacenter", "api 定价", "pricing", "inference", "推理", "训练", "training run"]),
    ("robotik", ["robot", "robotic", "humanoid", "figure ai", "unitree", "具身", "机器人", "boston dynamics",
                 "tesla optimus", "1x technologies", " 1x "]),
    ("forschung", ["arxiv", "paper", "论文", "benchmark", "github", "open source", "开源", "skill", "mcp",
                   "hugging face", "dataset", "实验室", "lab", "发布", "release notes"]),
]


def _kw_regex(words):
    import re
    parts = []
    for w in words:
        if re.search(r"[㐀-鿿]", w):
            parts.append(re.escape(w))
        else:
            parts.append(r"(?<![a-z0-9])" + re.escape(w) + r"(?:s)?(?![a-z0-9])")
    return re.compile("|".join(parts))


_RUB_RX = [(key, _kw_regex(words)) for key, words in RUBRIKEN]


def rubriken_of(item):
    """按标题/摘要/信源/域名做关键词匹配，返回 Rubrik key 列表（至少一个）。"""
    import re
    from urllib.parse import urlparse
    host = ""
    try:
        host = urlparse(item.get("url") or "").hostname or ""
    except ValueError:
        pass
    text = " ".join(str(item.get(f) or "") for f in
                    ("title_src", "title_en", "title_zh", "one_liner_en", "source_name")) + " " + host
    text = text.lower()
    keys = [key for key, rx in _RUB_RX if rx.search(text)]
    if keys:
        return keys
    cat = item.get("category")
    if cat == "模型":
        return ["modelle"]
    if cat == "研究":
        return ["forschung"]
    return ["modelle"] if re.search(r"model|llm|模型|(?<![a-z])ai(?![a-z])", text) else ["unternehmen"]


def kind_of(item):
    """X 双标签：x / offiziell / medien / forschung，并带 X handle。"""
    import re
    from urllib.parse import urlparse
    url = item.get("url") or ""
    name = item.get("source_name") or ""
    host = ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        pass
    if host.endswith("x.com") or host.endswith("twitter.com") or name.startswith("X"):
        m = re.match(r"\s*@([A-Za-z0-9_]{1,30})\s*:", item.get("title_src") or "") or \
            re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,30})", url)
        return {"k": "x", "h": m.group(1) if m else ""}
    if host.endswith("arxiv.org") or host.endswith("github.com"):
        return {"k": "forschung"}
    return {"k": "offiziell" if item.get("source_tier") == "T1" else "medien"}


def main(argv):
    here = pathlib.Path(__file__).resolve().parent        # .../发布/generator
    repo = here.parent                                     # .../发布
    data_path = pathlib.Path(argv[1]) if len(argv) > 1 else (repo / "data" / "精选库.json")
    out_dir = pathlib.Path(argv[2]) if len(argv) > 2 else repo

    seed = load_seed(data_path)
    items, dropped = normalize_seed(seed)
    if dropped:
        sys.stderr.write("[build] 警告：丢弃 %d 条缺 title_zh/url 的条目\n" % dropped)

    # D7 goal 第四刀：「今日热点 N 家源在报」服务端计算（无数据时 HOTBOX_HTML 为空串）
    hotbox_html, n_hot = compute_hotbox(items)
    # 2026-09-22 P3：热度地图（同一份数据，零额外调用）
    heatmap_html, n_cells = compute_heatmap(items)
    if n_hot:
        sys.stderr.write("[build] 今日热点 %d 事件已渲染\n" % n_hot)

    m = {
        "SITE_NAME": hesc(CONFIG["SITE_NAME"]),
        "SITE_TAGLINE": hesc(CONFIG["SITE_TAGLINE"]),
        "SITE_DESCRIPTION": hesc(CONFIG["SITE_DESCRIPTION"]),
        "DOMAIN": hesc(CONFIG["DOMAIN"]),
        "ISSUES_URL": hesc(CONFIG["ISSUES_URL"]),
        "TITLE": hesc(CONFIG["SITE_NAME"] + " · " + CONFIG["SITE_TAGLINE"]),
        "SEED_JSON": json_island(seed),
        "HOTBOX_HTML": hotbox_html or "",
        "HEATMAP_HTML": heatmap_html or "",
        "RUBRIKEN_JSON": json_island({(it.get("id") or it.get("url")): rubriken_of(it) for it in items}),
        "KIND_JSON": json_island({(it.get("id") or it.get("url")): kind_of(it) for it in items}),
        "UPDATE_NOTE": hesc(UPDATE_NOTE),
        "LICENSE_NOTE": hesc(LICENSE_NOTE),
    }

    pages = {
        "index.html": tmpl(INDEX_TMPL, m),
        "about.html": tmpl(ABOUT_TMPL, m),
        "404.html": tmpl(NOT_FOUND_TMPL, m),
        "agents/index.html": tmpl(AGENTS_TMPL, m),
    }
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "agents").mkdir(parents=True, exist_ok=True)
    (out_dir / "api" / API_VERSION).mkdir(parents=True, exist_ok=True)

    written = []
    for name, body in pages.items():
        p = out_dir / name
        p.write_text(body, encoding="utf-8")
        written.append((p, len(body)))
    for name, body in (("assets/style.css", CSS), ("assets/app.js", JS)):
        p = out_dir / name
        p.write_text(body, encoding="utf-8")
        written.append((p, len(body)))

    # 2026-09-22 P1：agent 可接入层。数据同源（同一份精选库 + 同目录的心跳/信源登记），
    # 三个旁料读不到就如实降级（status=pending），绝不为了「好看」编数。
    def _side(name):
        f = data_path.parent / name
        if not f.is_file():
            sys.stderr.write("[build] 提示：%s 不存在，相关接口降级\n" % f)
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            sys.stderr.write("[build] 警告：%s 不可解析（%s），相关接口降级\n" % (f, e))
            return None

    heartbeat = _side("引擎心跳.json")
    registry = _side("信源登记.json")
    api_dir = "api/%s/" % API_VERSION
    machine = {
        api_dir + "latest.json": json.dumps(build_latest_json(seed, items),
                                            ensure_ascii=False, indent=1),
        api_dir + "sources.json": json.dumps(build_sources_json(registry),
                                             ensure_ascii=False, indent=1),
        api_dir + "heartbeat.json": json.dumps(
            heartbeat if isinstance(heartbeat, dict) else
            {"status": "pending", "note": "引擎心跳暂不可读"},
            ensure_ascii=False, indent=1),
        "feed.xml": build_feed_xml(seed, items),
        "llms.txt": build_llms_txt(seed, items, build_sources_json(registry)),
    }
    for name, body in machine.items():
        p = out_dir / name
        p.write_text(body, encoding="utf-8")
        written.append((p, len(body)))

    print("[build] 数据源: %s（%d 条，弃 %d）" % (data_path, len(items), dropped))
    for p, size in written:
        print("[build] 写出 %s（%d B）" % (p, size))
    print("[build] 完成：%s" % CONFIG["SITE_NAME"])


if __name__ == "__main__":
    main(sys.argv)
