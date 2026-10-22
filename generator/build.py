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
    archive/index.html / api/v1/archive.json                     （2026-10-21：往期，只增不减）

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
    "STALE_MINUTES": 1800,  # 「最后更新」超过该分钟数变红（2026-10-21 改为人工每天一轮，放宽到 30 小时）
    "REPO_NAME": "aiimmigrant-news",
}

# ---------------------------------------------------------------------------
# assets/style.css —— 移动端优先，375px 起步，桌面是加宽版
# ---------------------------------------------------------------------------
CSS = r"""/* AI 资讯时间线 · 样式（生成器产出，勿手改：generator/build.py）
   版式 A「报纸版」（2026-10-21 店主选定）：单一品牌色 + 黑白灰，细分隔线，衬线标题。
   颜色全部在 token 里；默认白色，深色只由 [data-theme="dark"] 触发，不跟系统自动切换。 */
@font-face {
  font-family: "SiteSerif";
  src: url("fonts/SourceSerif4.woff2") format("woff2");
  font-weight: 400 700; font-style: normal; font-display: swap;
}

/* ===== 1. token ===== */
:root {
  color-scheme: light;
  --bg: #fff; --fg: #14181d; --muted: #4d5560; --faint: #69727d;
  --line: #e3e6ea; --line-2: #c5cbd2; --hover: #f3f5f7;
  --brand: #0b2a4a; --brand-rgb: 11 42 74;
  --ok: #1b7f4c; --idle: #99a1aa; --focus: #0b2a4a;
  --serif: "SiteSerif", "Iowan Old Style", "Palatino Linotype", Palatino, "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", Georgia, "Times New Roman", serif;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  /* 旧名别名：关于页 / 404 / agents 页沿用 */
  --ink: var(--fg); --sub: var(--muted); --soft: var(--hover);
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0f1318; --fg: #e8ebef; --muted: #b3bbc5; --faint: #8c95a0;
  --line: #262c35; --line-2: #3b434e; --hover: #171c23;
  --brand: #8fb4dc; --brand-rgb: 143 180 220;
  --ok: #4cc38a; --idle: #6c7580; --focus: #8fb4dc;
}

/* ===== 2. 共用：重置与部件 ===== */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; scroll-padding-top: 100px; }
body { margin: 0; background: var(--bg); color: var(--fg); font-family: var(--sans); font-size: 15px; line-height: 1.28; overflow-x: hidden; }
[hidden] { display: none !important; }
html:not(.js) .js-only { display: none !important; }
a { color: inherit; }
button, input { font: inherit; color: inherit; }
button { cursor: pointer; }
ul, ol { margin: 0; padding: 0; list-style: none; }
h1, h2, h3, h4, p { margin: 0; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.sheet { padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-top: max(8px, env(safe-area-inset-top, 0px)); padding-bottom: max(40px, calc(24px + env(safe-area-inset-bottom, 0px))); overflow-x: clip; }
.wrap { max-width: 1180px; margin-inline: auto; min-width: 0; }
.container { max-width: 1180px; margin: 0 auto; padding: 0 16px; }

.seg { display: inline-flex; gap: 2px; min-width: 0; }
.seg button { background: none; border: 0; border-bottom: 2px solid transparent; border-radius: 0; padding: 4px 8px; min-height: 32px; color: var(--muted); font-size: 13px; font-weight: 600; }
.seg button:hover { color: var(--fg); }
.seg button[aria-pressed="true"] { color: var(--fg); border-bottom-color: var(--brand); }

/* ① 顶栏（窄屏：报头 / 日期 / 工具三行；≥640 两行；≥960 一行） */
.topbar { position: sticky; top: 0; z-index: 20; display: grid; align-items: center; column-gap: 12px; row-gap: 2px;
  grid-template-columns: minmax(0, 1fr); grid-template-areas: "mark" "meta" "tools";
  padding-block: 8px; background: var(--bg); border-top: 1px solid var(--fg); border-bottom: 1px solid var(--line); }
.wordmark { grid-area: mark; display: block; min-width: 0; text-decoration: none; color: var(--brand); text-align: center;
  font-family: var(--serif); font-weight: 700; font-size: 26px; line-height: 1.05; letter-spacing: -.01em; }
.wordmark:hover { text-decoration: none; }
.wm-main { display: block; }
.wm-sub { display: none; margin-top: 3px; font: 500 10px/1.3 var(--sans); letter-spacing: .14em; text-transform: uppercase; color: var(--faint); }
.tb-meta { grid-area: meta; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0 10px; min-width: 0; font-size: 12px; color: var(--muted); }
.tb-date { white-space: nowrap; font-variant-numeric: tabular-nums; }
.fresh { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.dot { display: inline-block; flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--idle); }
.fresh[data-state="fresh"] .dot { background: var(--ok); }
.tb-tools { grid-area: tools; display: flex; align-items: center; gap: 8px; min-width: 0; }
.search { flex: 1 1 120px; min-width: 0; margin: 0; }
.search input { display: block; width: 100%; min-width: 0; height: 32px; padding: 0 9px; border: 1px solid var(--line-2); border-radius: 3px; background: var(--bg); color: var(--fg); font-size: 14px; -webkit-appearance: none; appearance: none; }
.search input::placeholder { color: var(--faint); }
.icon-btn { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; background: none; border: 1px solid var(--line-2); border-radius: 3px; color: var(--fg); font-size: 16px; line-height: 1; }
.icon-btn:hover { background: var(--hover); }
.icon-btn[aria-pressed="true"] { border-color: var(--brand); color: var(--brand); }
.q-status { margin-top: 10px; font-size: 13px; color: var(--muted); }
.linklike { padding: 0 0 0 8px; background: none; border: 0; color: var(--brand); font-size: inherit; text-decoration: underline; }

/* ② 卡片（全站唯一一种） */
.card { min-width: 0; padding: 13.5px 0; border-bottom: 1px solid var(--line); }
.eyebrow { margin: 0 0 .3em; color: var(--faint); overflow-wrap: anywhere; font-size: 12px; letter-spacing: .02em; }
.eyebrow .cat { color: var(--brand); font-weight: 700; }
.tag { display: inline-block; margin-left: 6px; padding: 0 4px; border: 1px solid var(--line-2); border-radius: 2px; font-size: .82em; line-height: 1.35; font-weight: 600; color: var(--muted); white-space: nowrap; vertical-align: 1px; }
.title { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow: hidden; overflow-wrap: anywhere; hyphens: auto;
  font: 700 19px/1.14 var(--serif); letter-spacing: -.005em; }
.title a { color: var(--fg); text-decoration: none; }
.title a:hover { text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: .15em; }
.oneliner { margin-top: .4em; color: var(--fg); overflow-wrap: anywhere; font-size: 15px; line-height: 1.3; }
.why { margin-top: .3em; color: var(--muted); overflow-wrap: anywhere; font-size: 13.5px; line-height: 1.3; }
.times { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 14px; margin-top: .5em; color: var(--faint); font-size: 12px; }
.times .tm { white-space: nowrap; }
details.srcs[open] { flex-basis: 100%; }
details.srcs > summary, details.quote > summary { cursor: pointer; color: var(--muted); font-size: 12.5px; }
details.srcs ul { margin-top: .3em; padding-left: 1.1em; list-style: disc; }
details.srcs li { padding: 1px 0; }
details.quote { margin-top: .4em; }
details.quote blockquote { margin: .4em 0 0; padding-left: .8em; border-left: 2px solid var(--line-2); color: var(--muted); font-style: italic; overflow-wrap: anywhere; font-size: 13px; line-height: 1.3; }
.actions { display: flex; flex-wrap: wrap; gap: 0 16px; margin-top: .3em; font-size: 12.5px; }
.act { display: inline-flex; align-items: center; min-height: 30px; padding: 0; background: none; border: 0; color: var(--muted); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: .2em; }
.act:hover { color: var(--fg); }
a.act.go::after { content: "\00a0\2197"; }
/* 已读变灰：点开过的条目，标题和摘要退成浅灰（两套颜色下对比度均 ≥ 4.5:1） */
.card.is-read .title a, .card.is-read .oneliner, .card.is-read .why { color: var(--faint); }
.card.is-read .eyebrow .cat { color: var(--faint); }

/* ③ 区块与头版 */
.sec { margin-top: 44px; scroll-margin-top: 100px; }
.sec-head { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 4px 14px; padding: 6px 0 5px; border-top: 2px solid var(--brand); }
.blk-h { min-width: 0; font: 700 18px/1.2 var(--serif); color: var(--brand); }
.blk-h small { font: inherit; font-size: .72em; font-weight: 500; color: var(--faint); margin-left: 8px; letter-spacing: 0; text-transform: none; }
.empty { padding: 10px 0; color: var(--faint); }
.fine, .tl-note { margin-top: 2px; font-size: 12.5px; color: var(--faint); }
.front { margin-top: 20px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px 0; }
.card-lead { padding-top: 12px; }
.card-lead .title { font-size: 30px; line-height: 1.1; }
.card-lead .oneliner { margin-top: .5em; font-size: 17px; }
.card-lead .why { font-size: 14.5px; }
.card-lead .eyebrow { font-size: 12.5px; }
.top-list { counter-reset: n; }
.top-list > li { counter-increment: n; display: grid; grid-template-columns: 24px minmax(0, 1fr); column-gap: 8px; border-bottom: 1px solid var(--line); }
.top-list > li::before { content: counter(n); padding-top: 13px; font: 700 20px/1.1 var(--serif); color: var(--brand); }
.top-list > li:last-child { border-bottom: 0; }
.top-list .card { border-bottom: 0; }

/* ④ 营销块：默认 24 小时，可展开到 7 天，链接到往期 */
.mk-more { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 18px; padding: 12px 0 0; font-size: 13.5px; }
.mk-more a { color: var(--brand); font-weight: 600; text-decoration: underline; text-underline-offset: .2em; }
.btn-line { background: none; color: var(--brand); border: 1px solid var(--line-2); border-radius: 2px; padding: 7px 14px; font-size: 13.5px; font-weight: 600; }
.btn-line:hover { background: var(--hover); }

/* ⑤ 时间线 */
.day-group { min-width: 0; }
.day { margin-top: 16px; padding-bottom: 5px; border-bottom: 1px solid var(--fg); font: 700 12px/1.3 var(--sans); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); scroll-margin-top: 100px; }
.day .n { margin-left: 6px; font-weight: 500; letter-spacing: 0; text-transform: none; color: var(--faint); }
.tl-note .chip { display: inline-flex; align-items: center; margin-left: 10px; padding: 0 0 0 8px; border: 1px solid var(--line-2); border-radius: 2px; color: var(--fg); }
.tl-note .chip .linklike { padding: 0 8px; min-height: 24px; }
.more { display: block; margin: 20px auto 0; background: none; color: var(--brand); border: 1px solid var(--line-2); border-radius: 2px; padding: 9px 20px; font-size: 14px; font-weight: 600; }
.more:hover { background: var(--hover); }

/* ⑥ 栏目（六个 Rubriken，点一下筛时间线） */
.cat-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 2px; border-bottom: 1px solid var(--line); }
.cat-list > li { border-top: 1px solid var(--line); min-width: 0; }
.cat-list > li:nth-child(even) { border-left: 1px solid var(--line); }
.cat-btn { display: block; width: 100%; padding: 12px 6px; background: none; border: 0; color: inherit; text-align: center; }
.cat-btn:hover { background: var(--hover); }
.cat-btn[aria-pressed="true"] .cat-name { text-decoration: underline; text-decoration-color: var(--brand); text-decoration-thickness: 2px; text-underline-offset: 4px; }
.cat-name { display: block; font: 700 15px/1.2 var(--serif); color: var(--fg); }
.cat-n { display: block; margin-top: 2px; font: 700 30px/1.05 var(--serif); color: var(--brand); }
.cat-sub { display: block; font-size: 11.5px; letter-spacing: .04em; color: var(--faint); }

/* ⑦ 热度地图（服务端渲染，放在 details 里；单色透明度色阶） */
.heatwrap > summary { cursor: pointer; list-style: none; }
.heatwrap > summary::-webkit-details-marker { display: none; }
.heatwrap > summary .blk-h::after { content: " +"; color: var(--faint); font-weight: 500; }
.heatwrap[open] > summary .blk-h::after { content: " \2212"; }
.heatwrap .hotbox { border: 0; padding: 0; margin: 10px 0 0; background: none; }
.heatwrap .hotbox > h2 { display: none; }
.hm-wrap { overflow-x: auto; }
table.hm { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 3px; font-size: 11.5px; }
table.hm th { padding: 0 0 2px; font-weight: 600; color: var(--muted); text-align: center; white-space: nowrap; overflow: hidden; }
table.hm thead td { width: 92px; }
table.hm tbody th { text-align: left; font-family: var(--serif); font-size: 13px; color: var(--fg); }
table.hm td.hm-c { height: 24px; padding: 0; border-radius: 2px; text-align: center; vertical-align: middle; font-size: 11.5px; font-weight: 600; line-height: 1; color: var(--fg); background: rgb(var(--brand-rgb) / var(--a, .05)); }
.hm-0 { --a: .05; } .hm-1 { --a: .14; } .hm-2 { --a: .28; } .hm-3 { --a: .45; } .hm-4 { --a: .65; } .hm-5 { --a: .85; }
table.hm td.hm-4, table.hm td.hm-5 { color: var(--bg); }
.hm-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 8px; font-size: 11.5px; color: var(--faint); }
.hm-legend i { display: inline-block; width: 14px; height: 10px; border-radius: 2px; background: rgb(var(--brand-rgb) / var(--a, .05)); }
.hm-legend .hm-tz { margin-left: 10px; }
.hm-bars { font-size: 13px; padding-left: 20px; margin-top: 10px; list-style: decimal; }
.hm-bars li { padding: 3px 0; }
.hm-bt { display: inline-block; width: 80px; height: 6px; background: var(--hover); margin: 0 8px; vertical-align: middle; }
.hm-bt i { display: block; height: 6px; background: var(--brand); }
.hm-bn, .hm-bd { color: var(--muted); margin-right: 8px; }
html:not([lang^="zh"]) .hm-bars, html:not([lang^="zh"]) .hm-sub { display: none; }

/* ⑧ 页脚 */
.foot { margin-top: 44px; padding-top: 14px; border-top: 2px solid var(--brand); font-size: 13px; line-height: 1.3; }
.foot-links { display: flex; flex-wrap: wrap; gap: 0 16px; }
.foot-links a { display: inline-block; padding: 4px 0; color: var(--fg); text-decoration: none; }
.foot-links a:hover { text-decoration: underline; }
.foot p { margin-top: 6px; color: var(--muted); }
.upd.stale { color: #b00020; }
:root[data-theme="dark"] .upd.stale { color: #ff8a80; }
.wie { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--line); scroll-margin-top: 110px; }
.wie h2 { font: 700 16px/1.2 var(--serif); color: var(--brand); }
.wie ol { margin-top: 6px; padding-left: 1.4em; list-style: decimal; color: var(--muted); }
.wie li { padding: 2px 0; }
.noscript-box { margin-top: 24px; padding: 12px 0; color: var(--muted); border-top: 1px solid var(--line); }
.noscript-box a { color: var(--brand); text-decoration: underline; }

/* ⑨ 往期页（archive/）：按月跳转 + 按日分组，静态渲染 */
.ar-head { margin-top: 20px; }
.ar-head h1 { font: 700 28px/1.1 var(--serif); color: var(--brand); }
.ar-head p { margin-top: 6px; color: var(--muted); font-size: 13.5px; }
.ar-months { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 12px; padding: 8px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); font-size: 13.5px; }
.ar-months a { color: var(--brand); font-weight: 600; text-decoration: none; white-space: nowrap; }
.ar-months a:hover { text-decoration: underline; }
.ar-filter { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 16px; margin-top: 10px; font-size: 13.5px; scroll-margin-top: 100px; }
.ar-filter a { color: var(--muted); text-decoration: underline; text-underline-offset: .2em; }
.ar-filter a[aria-current="true"] { color: var(--fg); font-weight: 700; text-decoration-color: var(--brand); text-decoration-thickness: 2px; }
.ar-month { scroll-margin-top: 100px; }

/* ⑩ 关于页 / 404 / agents 页 */
.prose { max-width: 720px; margin: 0 auto; padding: 10px 16px 30px; line-height: 1.55; }
.prose h2 { font-family: var(--serif); font-size: 22px; margin: 26px 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--line); }
.prose p, .prose ol, .prose ul { margin: 10px 0; }
.prose ol { list-style: decimal; padding-left: 1.4em; }
.prose ul { list-style: disc; padding-left: 1.4em; }
.prose a { color: var(--brand); text-decoration: underline; }
header.site .tagline { color: var(--sub); margin: 2px 0 0; font-size: 13px; }
header.site h1 { font-family: var(--serif); color: var(--brand); margin: 0; font-size: 26px; }
header.site.container { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding-top: 14px; padding-bottom: 14px; border-bottom: 1px solid var(--line); }
header.site nav a { color: var(--brand); }
footer:not(.foot) { border-top: 2px solid var(--brand); margin-top: 30px; padding: 18px 0 30px; font-size: 13px; color: var(--sub); }
footer:not(.foot) .links a { color: var(--ink); margin-right: 14px; display: inline-block; padding: 3px 0; }
.center-404 { text-align: center; padding: 60px 16px; line-height: 1.5; }
.center-404 .code { font: 700 64px var(--serif); color: var(--brand); }
.center-404 a { color: var(--brand); text-decoration: underline; }

/* ⑪ 断点 */
@media (max-width: 639px) {
  .search input { font-size: 16px; }
  .topbar.compact .tb-meta { display: none; }
  .topbar.compact .wordmark { font-size: 19px; }
}
@media (min-width: 640px) {
  .topbar { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-areas: "mark mark" "meta tools"; }
  .wm-sub { display: block; }
  .wordmark { font-size: 30px; }
  .tb-meta { justify-content: flex-start; }
  .tb-tools { justify-content: flex-end; }
  .search { flex: 0 1 170px; }
  .cat-list { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .cat-list > li, .cat-list > li:nth-child(even) { border-left: 1px solid var(--line); border-top: 1px solid var(--fg); }
  .cat-list > li:nth-child(3n+1) { border-left: 0; }
}
@media (min-width: 900px) {
  .front { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 0 30px; }
  .blk-lead { padding-right: 30px; border-right: 1px solid var(--line); }
  .card-lead .title { font-size: 36px; }
  .day-list { columns: 2; column-gap: 30px; column-rule: 1px solid var(--line); }
  .day-list > li { break-inside: avoid; }
  .foot-cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0 30px; }
  .wie { margin-top: 0; padding-top: 0; border-top: 0; }
}
@media (min-width: 960px) {
  .topbar { grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); grid-template-areas: "meta mark tools"; }
}
@media (min-width: 1100px) {
  .cat-list { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .cat-list > li:nth-child(3n+1) { border-left: 1px solid var(--line); }
  .cat-list > li:first-child { border-left: 0; }
}
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
"""

# ---------------------------------------------------------------------------
# assets/app.js —— 数据渲染 + 交互（含可被 Node 单测的纯函数层 TL）
# ---------------------------------------------------------------------------
JS = r"""/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改）
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
"""

# ---------------------------------------------------------------------------
# 页面模板（{{KEY}} 占位，避免 f-string 与 CSS/JS 花括号冲突）
# ---------------------------------------------------------------------------
# head 里的极短内联脚本：渲染前按 kin-theme 设好 data-theme（默认白，不跟系统），并给 <html> 加 js 类
THEME_BOOT = ('<script>(function(){var r=document.documentElement;r.className+=" js";'
              'try{if(localStorage.getItem("kin-theme")==="dark")r.setAttribute("data-theme","dark")}catch(e){}})();</script>')

HEAD_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
""" + THEME_BOOT + """
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

# 顶栏首页与往期页共用：报头 / 柏林日期 + 新鲜度 / 语言、搜索、深浅色
_TOPBAR = """<header class="topbar" id="topbar">
  <a class="wordmark" href="{{HOME}}" aria-label="KI-Nachrichten"><span class="wm-main" id="wordmark">KI-Nachrichten</span><span class="wm-sub" data-i="sub">Was heute in der KI zählt</span></a>
  <div class="tb-meta">
    <span class="tb-date" id="today-date"></span>
    <span class="fresh js-only" id="fresh" data-state="stale"><i class="dot" aria-hidden="true"></i><span id="fresh-txt"></span></span>
  </div>
  <div class="tb-tools">
    <div class="seg js-only" role="group" aria-label="Sprache / Language / 语言">
      <button type="button" id="lang-de" data-lang="de" aria-pressed="true">DE</button>
      <button type="button" id="lang-en" data-lang="en" aria-pressed="false">EN</button>
      <button type="button" id="lang-zh" data-lang="zh" aria-pressed="false">ZH</button>
    </div>
    {{SEARCH}}<button type="button" class="icon-btn js-only" id="theme-btn" aria-pressed="false" aria-label="Dunkler Modus" title="Dunkler Modus" data-al="theme" data-ti="theme">&#9680;</button>
  </div>
</header>
"""
_SEARCH = """<form class="search js-only" id="search-form" role="search"><input type="search" id="q" enterkeyhint="search" autocomplete="off" placeholder="Titel suchen, Enter zum Filtern" aria-label="Titel suchen, Enter zum Filtern" data-ph="ph" data-al="ph"></form>
    """
# 「我们怎么排」：静态德语默认，app.js 换语言
_WIE = """<section class="wie" id="wie">
      <h2 data-i="wieH">Wie wir sortieren</h2>
      <ol>
        <li data-i="wie1">Wir sammeln täglich Meldungen aus öffentlichen Quellen wie offiziellen Blogs, Preprint-Servern, Open-Source-Communities und Tech-Medien; wird dasselbe Ereignis mehrfach berichtet, fassen wir es zu einer Meldung zusammen und nennen die Zahl der Quellen.</li>
        <li data-i="wie2">Die Auswahl folgt der Beachtung und Aktualität eines Ereignisses; dasselbe Thema belegt nur einen Platz, Studien stellen höchstens ein Top-Thema, und die Schlagzeile ist bevorzugt keine Studie und hat eine Kurzfassung.</li>
        <li data-i="wie3">Titel und Kurzfassungen sind nur ein Verzeichnis und ersetzen das Original nicht; stimmt etwas nicht, bitte „Fehler melden“ auf der Karte nutzen.</li>
      </ol>
    </section>"""

# 2026-10-21 版式 A「报纸版」：头版（只放当前契约 selected）→ 多家报道 → 营销块 → Chronik → 栏目 → 热度 → 页脚
INDEX_TMPL = (HEAD_TMPL.replace('<html lang="zh-CN">', '<html lang="de">')
              .replace("<body>\n", '<body data-page="index" data-issues="{{ISSUES_URL}}" data-stale-min="{{STALE_MIN}}">\n')
              ) + """<div class="sheet"><div class="wrap">
""" + _TOPBAR.replace("{{HOME}}", "./").replace("{{SEARCH}}", _SEARCH) + """
<p class="q-status" id="q-status" role="status" hidden></p>

<main id="main">
<section class="front sec" id="front" aria-live="polite">
  <div class="blk-lead">
    <div class="sec-head"><h2 class="blk-h" data-i="hLead">Schlagzeile</h2></div>
    <div id="lead"></div>
  </div>
  <div class="blk-top">
    <div class="sec-head"><h2 class="blk-h" data-i="hTop">Top-Themen</h2></div>
    <ol class="top-list" id="top-list"></ol>
  </div>
</section>

<section class="sec" id="multi" hidden>
  <div class="sec-head"><h2 class="blk-h" data-i="hMulti">Mehrfach berichtet</h2></div>
  <ul class="day-list" id="multi-list"></ul>
</section>

<section class="sec" id="marketing">
  <div class="sec-head"><h2 class="blk-h"><span data-i="mkH">Marketing &amp; Commerce</span><small id="mk-sub">letzte 24 Stunden</small></h2></div>
  <p class="fine" id="mk-note" hidden></p>
  <ul class="day-list" id="mk-list"></ul>
  <ul class="day-list" id="mk-ext" hidden></ul>
  <div class="mk-more">
    <button type="button" class="btn-line js-only" id="mk-btn" aria-expanded="false" aria-controls="mk-ext" hidden></button>
    <a href="archive/#marketing" data-i="mkAll">Alle früheren (Archiv)</a>
  </div>
</section>

<section class="sec" id="timeline">
  <div class="sec-head">
    <h2 class="blk-h" id="tl-title" data-i="timeline">Chronik</h2>
    <div class="seg js-only" role="group" aria-label="Umfang der Chronik" data-al="scopeAl">
      <button type="button" data-scope="selected" aria-pressed="true" data-i="scSel">Auswahl</button>
      <button type="button" data-scope="all" aria-pressed="false" data-i="scAll">Alle</button>
    </div>
  </div>
  <p class="tl-note" id="tl-note"></p>
  <div id="tl-days"></div>
  <button type="button" class="more" id="more" hidden>Ältere Meldungen laden</button>
  <p class="fine"><a href="archive/" data-i="arLink">Archiv: alle bisher ausgewählten Meldungen und Marketing-Meldungen nach Tag</a></p>
</section>

<section class="sec" id="cats">
  <div class="sec-head"><h2 class="blk-h" data-i="hCats">Rubriken</h2></div>
  <ul class="cat-list" id="cat-list"></ul>
</section>

<details class="heatwrap sec" id="heat">
  <summary class="sec-head" id="heat-sum"><h2 class="blk-h" data-i="heatTitle">Themen-Hitzekarte</h2></summary>
  <p class="fine" id="heat-sub" data-i="heatSub">Je dunkler, desto mehr Relevanz an diesem Tag (Hitze × Quellen)</p>
  {{HEATMAP_HTML}}
</details>
</main>

<footer class="foot" id="foot">
  <nav class="foot-links" aria-label="Footer"><a href="agents/" data-f="sources">Quellen</a><a href="archive/" data-f="archive">Archiv</a><a href="about.html#impressum" data-f="impressum">Impressum</a><a href="about.html#datenschutz" data-f="privacy">Datenschutz</a><a href="api/v1/latest.json" data-f="api">API</a><a href="feed.xml" data-f="rss">RSS</a></nav>
  <div class="foot-cols">
    <div>
      <p><span data-f="note">Auswahl, Zusammenfassung und Übersetzung KI-gestützt; Links führen zur Originalquelle.</span></p>
      <p><span id="last-updated" class="upd">{{LAST_UPDATED}}</span></p>
    </div>
    """ + _WIE + """
  </div>
</footer>

<noscript><div class="noscript-box">JavaScript erforderlich. Rohdaten: <a href="data/%E7%B2%BE%E9%80%89%E5%BA%93.json">data/精选库.json</a> · Archiv ohne JavaScript / Archive / 往期：<a href="archive/">archive/</a></div></noscript>
</div></div>

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
  <p lang="de">Angaben gemäß § 5 DDG<br>Xiaoxi Sun<br>Beilstein, Deutschland<br>E-Mail: <a href="mailto:sun.xiaoxi2039@gmail.com">sun.xiaoxi2039@gmail.com</a><br>Verantwortlich für den Inhalt: Xiaoxi Sun</p>
  <p lang="en">Operator: Xiaoxi Sun, Beilstein, Germany<br>E-mail: <a href="mailto:sun.xiaoxi2039@gmail.com">sun.xiaoxi2039@gmail.com</a></p>
  <p>运营者：Xiaoxi Sun，Beilstein（德国）<br>邮箱：<a href="mailto:sun.xiaoxi2039@gmail.com">sun.xiaoxi2039@gmail.com</a></p>

  <h2 id="datenschutz">Datenschutz</h2>
  <p lang="de"><strong>Verantwortlicher:</strong> Xiaoxi Sun, Beilstein, Deutschland · E-Mail: <a href="mailto:sun.xiaoxi2039@gmail.com">sun.xiaoxi2039@gmail.com</a></p>
  <p lang="de"><strong>Hosting:</strong> Diese Seite wird als statische Website über GitHub Pages (GitHub, Inc., USA) ausgeliefert. Beim Aufruf verarbeitet GitHub technisch notwendige Server-Logdaten (IP-Adresse, Zeitpunkt, aufgerufene URL, User-Agent) auf Grundlage von Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse am sicheren Betrieb). Details: <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener">GitHub General Privacy Statement</a>. Wir selbst erhalten und speichern keine dieser Daten.</p>
  <p lang="de"><strong>Keine Cookies, kein Tracking:</strong> Diese Seite setzt keine Cookies, nutzt keine Analyse- oder Werbedienste und bindet keine Inhalte Dritter ein. Schriften werden lokal ausgeliefert. Sprachwahl (DE/EN/ZH), die Einstellung „Dunkler Modus“ und die IDs bereits geöffneter Meldungen (höchstens etwa 500, nur um sie als gelesen grau zu markieren) werden ausschließlich im lokalen Speicher Ihres Browsers (localStorage) abgelegt und nicht übertragen; Sie können sie jederzeit in den Browser-Einstellungen löschen.</p>
  <p lang="de"><strong>Externe Links:</strong> Verlinkte Quellen unterliegen den Datenschutzbestimmungen der jeweiligen Anbieter.</p>
  <p lang="de"><strong>Ihre Rechte:</strong> Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung, Widerspruch und Datenübertragbarkeit (Art. 15–21 DSGVO) sowie Beschwerde bei einer Aufsichtsbehörde, z. B. dem Landesbeauftragten für den Datenschutz und die Informationsfreiheit Baden-Württemberg. Stand: 21. Oktober 2026.</p>
  <p lang="en">Controller: Xiaoxi Sun, Beilstein, Germany, <a href="mailto:sun.xiaoxi2039@gmail.com">sun.xiaoxi2039@gmail.com</a>. This static site is served via GitHub Pages; GitHub processes technically necessary server logs (IP address, time, URL, user agent) under Art. 6(1)(f) GDPR. No cookies, no analytics, no third-party embeds, fonts served locally; the language choice, the dark-mode setting and the IDs of items you opened (at most about 500, only to grey them out as read) stay in your browser's local storage and are never transmitted. You have the rights under Art. 15–21 GDPR and may complain to a supervisory authority. Last updated 21 October 2026.</p>
  <p>责任人：Xiaoxi Sun，Beilstein（德国），<a href="mailto:sun.xiaoxi2039@gmail.com">sun.xiaoxi2039@gmail.com</a>。本站为静态站点，经 GitHub Pages 分发；GitHub 会处理技术上必需的服务器日志（IP、时间、URL、浏览器标识），法律依据为 GDPR 第 6 条第 1 款 f 项。本站无 cookie、无统计、无第三方嵌入，字体本地分发；语言选择、深色模式开关和你点开过的条目 id（最多约 500 条，只用来把已读标灰）只保存在你浏览器的本地存储里，不会上传。你享有 GDPR 第 15–21 条的各项权利，并可向监管机构投诉。更新日期：2026 年 10 月 21 日。</p>

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
  <h1 lang="de" style="font-family:var(--serif);color:var(--brand)">Seite nicht gefunden</h1>
  <p lang="de">Diese Meldung gibt es nicht oder sie wurde entfernt. <a href="index.html">Zur Startseite</a></p>
  <p lang="en">Page not found · <a href="index.html">Back to start</a></p>
  <p>页面不存在 · <a href="index.html">回首页</a></p>
</main>
<footer>
  <div class="container">
    <div class="links">{{SITE_NAME}} · <a href="about.html">关于 · 免责 · 纠错</a></div>
  </div>
</footer>
</body>
</html>
"""


# 2026-10-21 往期页 archive/index.html：静态渲染（无 JS 可读、可抓取），按月跳转、按日分组；
# 与首页同一套样式与 app.js（相对路径 ../assets/），#marketing 有 JS 时只看营销，无 JS 时全显示
ARCHIVE_TMPL = (HEAD_TMPL.replace('<html lang="zh-CN">', '<html lang="de">')
                .replace("<title>{{TITLE}}</title>", "<title>{{AR_TITLE}}</title>")
                .replace('content="{{TITLE}}"', 'content="{{AR_TITLE}}"')
                .replace('href="https://{{DOMAIN}}/"', 'href="https://{{DOMAIN}}/archive/"')
                .replace('href="assets/style.css"', 'href="../assets/style.css"')
                .replace("<body>\n", '<body data-page="archive" data-issues="{{ISSUES_URL}}" data-gen="{{AR_GEN}}">\n')
                ) + """<div class="sheet"><div class="wrap">
""" + _TOPBAR.replace("{{HOME}}", "../").replace("{{SEARCH}}", "") + """
<main id="main">
<section class="ar-head">
  <h1 data-i="arH">Archiv</h1>
  <p data-i="arIntro">Alle bisher ausgewählten Meldungen, nach Tag geordnet (Berliner Zeit), neueste zuerst.</p>
  <p class="fine" id="ar-count">{{AR_COUNT}}</p>
  <nav class="ar-months" aria-label="Monate / Months / 月份">{{AR_MONTHS}}</nav>
  <nav class="ar-filter" id="marketing" aria-label="Filter"><a href="./" data-ar="all" aria-current="true" data-i="arAll">Alle</a><a href="#marketing" data-ar="marketing" aria-current="false" data-i="arMk">Nur Marketing &amp; Commerce</a></nav>
</section>
<p class="empty" id="ar-empty" hidden></p>
{{AR_BODY}}
</main>

<footer class="foot" id="foot">
  <nav class="foot-links" aria-label="Footer"><a href="../" data-f="home">Startseite</a><a href="../agents/" data-f="sources">Quellen</a><a href="../about.html#impressum" data-f="impressum">Impressum</a><a href="../about.html#datenschutz" data-f="privacy">Datenschutz</a><a href="../api/v1/archive.json" data-f="api">API</a><a href="../feed.xml" data-f="rss">RSS</a></nav>
  <div class="foot-cols">
    <div>
      <p><span data-f="note">Auswahl, Zusammenfassung und Übersetzung KI-gestützt; Links führen zur Originalquelle.</span></p>
    </div>
    """ + _WIE + """
  </div>
</footer>
</div></div>
<script src="../assets/app.js" defer></script>
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


# 生成的所有文件都不出现一个指定的比较词（站务口径）。引擎写的条目正文偶尔会用到它，
# 读入时统一换成「比肩」，页面、接口、RSS、往期因此同口径。码位写法，源码里也不出现字面。
_AVOID_WORD = "\u5bf9\u6807"
_AVOID_REPL = "比肩"


def neutral_text(o):
    """递归替换读入数据里所有字符串值中的这个词（键名不动，其它类型原样返回）。"""
    if isinstance(o, str):
        return o.replace(_AVOID_WORD, _AVOID_REPL) if _AVOID_WORD in o else o
    if isinstance(o, dict):
        return {k: neutral_text(v) for k, v in o.items()}
    if isinstance(o, list):
        return [neutral_text(v) for v in o]
    return o


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
UPDATE_NOTE = ("精选库现为人工每天跑一轮、跑完再发布，没有固定时刻；数据新旧以 generated_at_utc 为准。"
               "接口无鉴权、无频控，请自觉别超过 1 次/分钟。"
               " / DE: Die Auswahl wird derzeit einmal täglich manuell erstellt und danach veröffentlicht, "
               "ohne festen Zeitpunkt; maßgeblich ist generated_at_utc. Bitte höchstens 1 Abruf pro Minute."
               " / EN: The selection is currently built manually once a day and then published, "
               "with no fixed time; generated_at_utc tells you how fresh it is. Please keep to at most 1 request per minute.")

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
    out["note"] = ("与公开信源清单的逐项对账：status=connected 已接 / pending 待接 / "
                   "blocked 不可接。若含 diff_vs_benchmark 字段，是当日条目级差别（字段名沿用，不改）。")
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
    src_line = ("已接 %s / 待接 %s / 不可接 %s（信源清单共 %s 项）" % (
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
- [%(site)s/api/%(v)s/archive.json](%(site)s/api/%(v)s/archive.json)：往期（历次精选 + 营销栏目全部条目），按柏林日分组，只增不减。
  结构 `{api_version, generated_at_utc, tz, counts.{days,items}, days[].{date, items[]}}`；
  日期新→旧、同日内新→旧；条目字段同 latest.json，另含 `rubriken`（栏目键列表）；`selected=true` 表示曾进过精选，营销栏目里没进精选的条目为 false。
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

[%(site)s/agents/](%(site)s/agents/)　|　往期 [%(site)s/archive/](%(site)s/archive/)　|　站点首页 [%(site)s/](%(site)s/)
""" % {"name": CONFIG["SITE_NAME"], "desc": CONFIG["SITE_DESCRIPTION"], "site": site,
       "v": API_VERSION, "nsel": len(selected), "nfresh": len(fresh),
       "lic": LICENSE_NOTE, "update": UPDATE_NOTE, "src": src_line}


AGENTS_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
""" + THEME_BOOT + """
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
  <nav><a href="/">时间线</a> · <a href="/archive/">往期</a> · <a href="/about.html">关于</a></nav>
</header>

<main class="container api" id="main">
  <p>{{SITE_NAME}} 首先是给机器读的。下面六个地址随每次发布更新，直接 <code>curl</code> 即可，
  不需要 key、不需要 UA 伪装。<strong>接口一旦公布就不破坏</strong>：只增字段，要改就开 <code>/api/v2/</code>。</p>

  <h2>六个地址</h2>
  <table>
    <tr><th>地址</th><th>是什么</th><th>格式</th></tr>
    <tr><td><a href="/api/v1/latest.json"><code>/api/v1/latest.json</code></a></td>
        <td>精选 + 24h 全量，三语标题 / 一句话 / 为什么重要，含抢跑时长与多源簇</td><td>JSON</td></tr>
    <tr><td><a href="/api/v1/sources.json"><code>/api/v1/sources.json</code></a></td>
        <td>信源登记表：我们接了哪些源、哪些待接，以及与公开信源清单的当日差别</td><td>JSON</td></tr>
    <tr><td><a href="/api/v1/heartbeat.json"><code>/api/v1/heartbeat.json</code></a></td>
        <td>引擎心跳：上轮何时跑、成功与否、出了几条精选（判新鲜度看它）</td><td>JSON</td></tr>
    <tr><td><a href="/api/v1/archive.json"><code>/api/v1/archive.json</code></a></td>
        <td>往期：历次精选和营销栏目全部条目，按柏林日分组、只增不减，条目字段同 latest.json 并带 <code>rubriken</code>（<code>selected</code> 表示是否进过精选）；人读版见 <a href="/archive/">/archive/</a></td><td>JSON</td></tr>
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
    <tr><td><code>rubriken</code>（archive.json）</td><td>栏目键：marketing / unternehmen / china / modelle / robotik / forschung，一条可属多个。</td></tr>
  </table>

  <h2>更新频率与许可</h2>
  <p>{{UPDATE_NOTE}}</p>
  <p>{{LICENSE_NOTE}}</p>
  <p style="margin-top:30px"><a href="/">← 回到时间线</a></p>
</main>

<footer>
  <div class="container">
    <div class="links">{{SITE_NAME}} · <a href="/">时间线</a> · <a href="/archive/">往期</a> · <a href="/about.html">关于</a> · <a href="/llms.txt">llms.txt</a></div>
  </div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 2026-09-22 演示换皮：六个 Rubriken，规则打标，零模型；一条可多标
# ---------------------------------------------------------------------------
RUBRIKEN = [
    ("marketing", ["marketing", "seo", " sea ", " geo ", " aeo ", "google ads", "display advertising", " ads ", "adtech",
                   "generative engine optimization", "answer engine optimization", "suchmaschinenwerbung",
                   "onlinemarketing", "performance marketing",
                   "programmatic advertising", "programmatic ad", "programmatische werbung", "shopify", "stripe", "checkout", "agentic commerce", "e-commerce", "ecommerce",
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
    if "robotik" in keys and re.search(r"social.?bot|社交机器人|chatbot|聊天机器人|bot-erkennung|bot detection", text):
        keys.remove("robotik")
    # 执行单 E（2026-09-23）：marketing 反例收紧——硬件新闻、客户案例不进 marketing
    if "marketing" in keys:
        mk_hits = {m.group(0).strip() for m in _RUB_RX[0][1].finditer(text)}
        if len(mk_hits) < 2 and re.search(
                r"notebook|tablet|chromebook|googlebook|laptop|smartphone|pixel \d|hardware", text):
            keys.remove("marketing")
        elif re.search(r"customer story|case study|kundenbeispiel|客户案例|success story"
                       r"|turned \d+ \w+ of work into", text):
            # 例外只看原文标题（译文摘要里的泛化「营销」不算）
            head = " ".join(str(item.get(f) or "") for f in ("title_src", "title_en")).lower()
            if not re.search(r"(?<![a-z])ads?(?![a-z])|adtech|e-commerce|checkout|shopify|营销|广告|投放", head):
                keys.remove("marketing")
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


# ---------------------------------------------------------------------------
# 2026-10-21 往期（archive）：api/v1/archive.json + archive/index.html
# 旁车与精选库同目录，都可选，缺了就跳过：
#   往期精选.json —— 上一次发布出去的 api/v1/archive.json 原样（发布链构建前复制进来，往期因此越攒越多）
#   往期回填.json —— 一次性回填：{"version":1,"generated_at_utc":…,"items":[契约格式条目 + "archive_day"]}
# 合并规则（按 id，缺 id 用 url）：
#   · 收精选和营销栏目（rubriken 含 marketing）的全部条目；一旦进了往期就永远留着，条目数只增不减
#   · selected 有粘性：进过精选的恒为 true；营销栏目里没进精选的为 false（回填只补精选）
#   · 日期「最早已知、之后不变」：往期精选里已有的沿用；回填用 archive_day；契约新进的精选按
#     published_utc → first_seen_utc → 契约 generated_at_utc 换算成柏林日
#   · 内容 契约 > 往期精选 > 回填；契约与回填条目过 public_item() 并附 rubriken，往期精选条目原样沿用
#   · 只收 http:// 或 https:// 开头的 url
# ---------------------------------------------------------------------------
ARCHIVE_PREV = "往期精选.json"
ARCHIVE_BACKFILL = "往期回填.json"
ARCHIVE_TZ = "Europe/Berlin"


def _http_url(u):
    return isinstance(u, str) and (u.startswith("http://") or u.startswith("https://"))


def _valid_day(v):
    """'YYYY-MM-DD' → 规范化后返回；其它一律 None。"""
    from datetime import date
    if not isinstance(v, str) or len(v.strip()) != 10:
        return None
    try:
        return date.fromisoformat(v.strip()).isoformat()
    except ValueError:
        return None


def _day_of(it, fallback):
    """published_utc → first_seen_utc → fallback（aware datetime），换算成柏林日 'YYYY-MM-DD'。"""
    return _berlin_day(_item_time(it) or fallback).isoformat()


def _archive_entry(it):
    """契约格式条目 → 往期条目：public_item 原字段 + rubriken；selected 照条目本身（营销栏目里没进精选的为 false）。"""
    e = public_item(it)
    e["selected"] = bool(it.get("selected"))
    e["rubriken"] = rubriken_of(it)
    return e


def load_archive_sidecars(base):
    """读两个可选旁车 → (prev, backfill)。

    缺文件＝跳过；回填坏了只警告、本轮不用；往期精选存在却坏了 → 中止构建（exit 2）：
    否则这一轮会发布一份缩水的往期，下一轮又以它为底，旧条目就永久丢了。
    """
    def read(name):
        f = base / name
        if not f.is_file():
            return None, None
        try:
            return neutral_text(json.loads(f.read_text(encoding="utf-8"))), None
        except (ValueError, OSError) as e:
            return None, "%s 不可解析（%s）" % (name, e)

    prev, err = read(ARCHIVE_PREV)
    if not err and prev is not None and not (isinstance(prev, dict) and isinstance(prev.get("days"), list)):
        err = "%s 结构不对（缺 days 列表）" % ARCHIVE_PREV
    if err:
        sys.stderr.write("[build] 错误：%s。往期只增不减，不在缺底的情况下发布；修好或移走该文件再跑\n" % err)
        raise SystemExit(2)
    backfill, err = read(ARCHIVE_BACKFILL)
    if not err and backfill is not None and not (isinstance(backfill, dict) and isinstance(backfill.get("items"), list)):
        err = "%s 结构不对（缺 items 列表）" % ARCHIVE_BACKFILL
    if err:
        sys.stderr.write("[build] 警告：%s，本轮跳过回填\n" % err)
        backfill = None
    return prev, backfill


def merge_archive(seed, items, prev=None, backfill=None):
    """→ [(date, [条目…]), …]：日期新→旧；同日内按 published → first_seen 新→旧，没有时间的垫底。"""
    from datetime import datetime, timezone
    gen = parse_iso(seed.get("generated_at_utc") or "")
    if not gen or gen.year < 2000:            # normalize_seed 的 1970 占位不算数
        gen = datetime.now(timezone.utc)
    book = {}                                  # key → [date, 条目]

    def key_of(x):
        return x.get("id") or x.get("url")

    # ① 往期精选：日期与内容原样沿用（它本身就是上次发布的结果）
    for d in (prev or {}).get("days") or []:
        if not isinstance(d, dict):
            continue
        day = _valid_day(d.get("date"))
        for e in d.get("items") or []:
            if not (isinstance(e, dict) and _http_url(e.get("url"))):
                continue
            k = key_of(e)
            if k and k not in book:
                book[k] = [day or _day_of(e, gen), e]
    # ② 回填：只补往期里还没有的；日期用 archive_day，缺了或坏了再按条目时间推
    bf_gen = parse_iso((backfill or {}).get("generated_at_utc") or "") or gen
    for it in (backfill or {}).get("items") or []:
        if not isinstance(it, dict) or it.get("selected") is False or not _http_url(it.get("url")):
            continue
        k = key_of(it)
        if k and k not in book:
            book[k] = [_valid_day(it.get("archive_day")) or _day_of(it, bf_gen), _archive_entry(it)]
    # ③ 当前契约：新进的精选和营销栏目条目定下日期；已在往期里的只换成契约的最新内容，日期不动，
    #    进过精选的 selected 保持 true（此刻是否仍是精选都一样）
    for it in items:
        k = key_of(it)
        if not k or not _http_url(it.get("url")):
            continue
        if k in book:
            was_sel = book[k][1].get("selected") is True
            book[k][1] = _archive_entry(it)
            if was_sel:
                book[k][1]["selected"] = True
        elif it.get("selected") or "marketing" in rubriken_of(it):
            book[k] = [_day_of(it, gen), _archive_entry(it)]

    def order(e):
        dt = parse_iso(e.get("published_utc") or "") or parse_iso(e.get("first_seen_utc") or "")
        return (1 if dt else 0, dt.timestamp() if dt else 0.0, str(key_of(e)))

    by_day = {}
    for day, e in book.values():
        by_day.setdefault(day, []).append(e)
    return [(day, sorted(by_day[day], key=order, reverse=True)) for day in sorted(by_day, reverse=True)]


def build_archive_json(seed, items, prev=None, backfill=None):
    days = merge_archive(seed, items, prev, backfill)
    return {
        "api_version": API_VERSION,
        "generated_at_utc": seed.get("generated_at_utc"),
        "tz": ARCHIVE_TZ,
        "counts": {"days": len(days), "items": sum(len(v) for _, v in days)},
        "days": [{"date": d, "items": v} for d, v in days],
    }


# 往期页静态文案（德语默认；app.js 按所选语言替换）
_RUB_DE = {"marketing": "Marketing & Commerce", "unternehmen": "KI im Unternehmen", "china": "China global",
           "modelle": "Modelle & Infrastruktur", "robotik": "Robotik", "forschung": "Forschung & Tools"}
_DE_MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
              "Oktober", "November", "Dezember")
_DE_WDAYS = ("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So.")


def _clean_title(s):
    """去掉标题前缀的「[信源名] 」标签（与 app.js cleanT 同口径）。"""
    import re
    s = str(s or "").strip()
    c = re.sub(r"^(?:\[[^\]]{1,60}\]\s*)+", "", s).strip()
    return c or s


def _de_when(v):
    """ISO → 'TT.MM.JJJJ HH:MM'（柏林时间，与 app.js 德语格式一致）；不可解析返回 ''。"""
    dt = parse_iso(v or "")
    if not dt:
        return ""
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo(ARCHIVE_TZ))
    except Exception:
        pass
    return "%02d.%02d.%04d %02d:%02d" % (dt.day, dt.month, dt.year, dt.hour, dt.minute)


def _host_label(url):
    """信源只按域名显示（去 www.）；X 链接显示 @账号。"""
    import re
    from urllib.parse import urlparse
    try:
        u = urlparse(url or "")
        host = (u.hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if host in ("x.com", "twitter.com") or host.endswith(".x.com") or host.endswith(".twitter.com"):
        m = re.match(r"/([A-Za-z0-9_]{1,30})(?:/|$)", u.path or "")
        ok = m and not re.match(r"(i|home|search|intent|share)$", m.group(1), re.I)
        return "@" + m.group(1) if ok else "x.com"
    return host


def _archive_card(e):
    """往期条目 → 一张卡片（与首页同一套 .card 结构，精简为 栏目·信源 / 标题 / 一句话 / 时间 / 原文）。"""
    url = e.get("url") or ""
    t = e.get("title") if isinstance(e.get("title"), dict) else {}
    ol = e.get("one_liner") if isinstance(e.get("one_liner"), dict) else {}
    src = e.get("source") if isinstance(e.get("source"), dict) else {}
    tt = {k: _clean_title(t.get(k)) for k in ("de", "en", "zh", "src") if t.get(k)}
    shown, orig = url, False
    for k in ("de", "en", "src", "zh"):        # 德语优先，回退 en → 原文
        if tt.get(k):
            shown, orig = tt[k], k == "src"
            break
    rubs = [r for r in (e.get("rubriken") or []) if r in _RUB_DE] or ["forschung"]
    kind = kind_of({"url": url, "source_name": src.get("name") or "", "title_src": t.get("src") or "",
                    "source_tier": src.get("tier")})
    host = "@" + kind["h"] if kind.get("k") == "x" and kind.get("h") else _host_label(url)
    tags = ""
    if kind.get("k") == "x" or host.startswith("@") or host == "x.com":
        tags += '<span class="tag">X</span>'
    elif kind.get("k") == "offiziell":
        tags += '<span class="tag tag-off">Offiziell</span>'
    tags += '<span class="tag tag-orig"%s>Original</span>' % ("" if orig else " hidden")
    t_attrs = "".join(' data-%s="%s"' % (k, hesc(v)) for k, v in tt.items())
    lo = {k: str(ol.get(k) or "").strip() for k in ("de", "en", "zh")}
    liner = ""
    if any(lo.values()):
        vis = lo["de"] or lo["en"]
        liner = '<p class="oneliner"%s%s>%s</p>' % (
            "".join(' data-%s="%s"' % (k, hesc(v)) for k, v in lo.items() if v),
            "" if vis else " hidden", hesc(vis))
    times = []
    for k, f, lab in (("pub", "published_utc", "Veröffentlicht"), ("seen", "first_seen_utc", "Erfasst")):
        txt = _de_when(e.get(f))
        if txt:
            times.append('<span class="tm" data-k="%s" data-t="%s">%s %s</span>' % (k, hesc(str(e.get(f))), lab, txt))
    return ('<li><article class="card" data-id="%s" data-rub="%s">'
            '<p class="eyebrow"><span class="cat" data-rub="%s">%s</span>%s%s</p>'
            '<h4 class="title"><a href="%s" target="_blank" rel="noopener" data-open="1"%s>%s</a></h4>'
            '%s%s<div class="actions"><a class="act go" href="%s" target="_blank" rel="noopener" data-open="1" '
            'data-i="go">Quelle</a></div></article></li>') % (
        hesc(str(e.get("id") or url)), hesc(" ".join(rubs)), rubs[0], hesc(_RUB_DE[rubs[0]]),
        (" · " + '<span class="src">%s</span>' % hesc(host)) if host else "", tags,
        hesc(url), t_attrs, hesc(shown), liner,
        ('<div class="times">%s</div>' % "".join(times)) if times else "", hesc(url))


def build_archive_html(archive, m):
    """往期 dict → archive/index.html：顶部按月跳转，按日分组，日内新→旧。"""
    from datetime import date
    days = archive.get("days") or []
    months, blocks, cur = [], [], None
    for d in days:
        ds = d.get("date") or ""
        try:
            dd = date.fromisoformat(ds)
        except ValueError:
            continue
        ym = ds[:7]
        if ym != cur:
            if cur is not None:
                blocks.append("</section>")
            cur = ym
            label = "%s %d" % (_DE_MONTHS[dd.month - 1], dd.year)
            months.append('<a href="#m-%s" data-month="%s">%s</a>' % (ym, ym, label))
            blocks.append('<section class="ar-month sec" id="m-%s"><div class="sec-head">'
                          '<h2 class="blk-h" data-month="%s">%s</h2></div>' % (ym, ym, label))
        its = d.get("items") or []
        blocks.append('<section class="day-group" id="d-%s" data-date="%s"><h3 class="day">'
                      '<span class="dl">%s, %d. %s %d</span><span class="n">%s</span></h3>'
                      '<ul class="day-list">%s</ul></section>' % (
                          ds, ds, _DE_WDAYS[dd.weekday()], dd.day, _DE_MONTHS[dd.month - 1], dd.year,
                          "1 Meldung" if len(its) == 1 else "%d Meldungen" % len(its),
                          "".join(_archive_card(e) for e in its if isinstance(e, dict))))
    if cur is not None:
        blocks.append("</section>")
    c = archive.get("counts") or {}
    nd, ni = c.get("days", 0), c.get("items", 0)
    mm = dict(m)
    mm.update({
        "AR_TITLE": hesc("Archiv · KI-Nachrichten"),
        "AR_GEN": hesc(str(archive.get("generated_at_utc") or "")),
        "AR_COUNT": "%s · %s" % ("1 Tag" if nd == 1 else "%d Tage" % nd,
                                 "1 Meldung" if ni == 1 else "%d Meldungen" % ni),
        "AR_MONTHS": "".join(months),
        "AR_BODY": "\n".join(blocks) or '<p class="empty">Noch keine Einträge im Archiv.</p>',   # 放最后替换
    })
    for k in ("SEED_JSON", "RUBRIKEN_JSON", "KIND_JSON"):   # 往期页不内嵌 seed
        mm.pop(k, None)
    return tmpl(ARCHIVE_TMPL, mm)


def main(argv):
    here = pathlib.Path(__file__).resolve().parent        # .../发布/generator
    repo = here.parent                                     # .../发布
    data_path = pathlib.Path(argv[1]) if len(argv) > 1 else (repo / "data" / "精选库.json")
    out_dir = pathlib.Path(argv[2]) if len(argv) > 2 else repo

    seed = neutral_text(load_seed(data_path))   # 见 neutral_text
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
        "TITLE": hesc("KI-Nachrichten · Was heute in der KI zählt"),  # 静态默认德语，与 app.js DE document.title 一致
        "SEED_JSON": json_island(seed),
        "HOTBOX_HTML": hotbox_html or "",
        "HEATMAP_HTML": heatmap_html or "",
        "RUBRIKEN_JSON": json_island({(it.get("id") or it.get("url")): rubriken_of(it) for it in items}),
        "KIND_JSON": json_island({(it.get("id") or it.get("url")): kind_of(it) for it in items}),
        "UPDATE_NOTE": hesc(UPDATE_NOTE),
        "LICENSE_NOTE": hesc(LICENSE_NOTE),
        "STALE_MIN": str(int(CONFIG["STALE_MINUTES"])),
        # 无 JS 时页脚也有「最后更新」（柏林时间）；有 JS 时 app.js 按所选语言重写
        "LAST_UPDATED": hesc("Zuletzt aktualisiert %s (Berliner Zeit)" % _de_when(seed.get("generated_at_utc"))
                             if _de_when(seed.get("generated_at_utc")) and not str(seed.get("generated_at_utc")).startswith("1970") else ""),
    }

    # 2026-10-21 往期：两个旁车与精选库同目录、都可选；往期精选在却坏了会在这里中止
    ar_prev, ar_backfill = load_archive_sidecars(data_path.parent)
    archive = build_archive_json(seed, items, ar_prev, ar_backfill)

    pages = {
        "index.html": tmpl(INDEX_TMPL, m),
        "about.html": tmpl(ABOUT_TMPL, m),
        "404.html": tmpl(NOT_FOUND_TMPL, m),
        "agents/index.html": tmpl(AGENTS_TMPL, m),
        "archive/index.html": build_archive_html(archive, m),
    }
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "agents").mkdir(parents=True, exist_ok=True)
    (out_dir / "archive").mkdir(parents=True, exist_ok=True)
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
            return neutral_text(json.loads(f.read_text(encoding="utf-8")))
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
        api_dir + "archive.json": json.dumps(archive, ensure_ascii=False, indent=1),
        "feed.xml": build_feed_xml(seed, items),
        "llms.txt": build_llms_txt(seed, items, build_sources_json(registry)),
    }
    for name, body in machine.items():
        p = out_dir / name
        p.write_text(body, encoding="utf-8")
        written.append((p, len(body)))

    print("[build] 数据源: %s（%d 条，弃 %d）" % (data_path, len(items), dropped))
    print("[build] 往期：%d 天 / %d 条（往期精选%s，回填%s）" % (
        archive["counts"]["days"], archive["counts"]["items"],
        "已读" if ar_prev is not None else "缺", "已读" if ar_backfill is not None else "缺"))
    for p, size in written:
        print("[build] 写出 %s（%d B）" % (p, size))
    print("[build] 完成：%s" % CONFIG["SITE_NAME"])


if __name__ == "__main__":
    main(sys.argv)
