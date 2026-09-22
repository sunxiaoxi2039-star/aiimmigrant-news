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
CSS = r"""/* AI 资讯时间线 · 样式（生成器产出，勿手改：generator/build.py） */
:root {
  --bg: #f6f7f9;
  --card: #ffffff;
  --ink: #171a28;
  --sub: #5b6472;
  --faint: #98a2b3;
  --line: #e5e8ee;
  --accent: #2e5ce6;
  --accent-soft: #e9efff;
  --accent-line: #ccdcff;
  --danger: #d92d20;
  --ok: #067647;
  --ok-bg: #e6f4ea;
  --warn: #b42318;
  --warn-bg: #fee4e2;
  --heat-a: #f79009;
  --heat-b: #f04438;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
a { color: var(--accent); }
.container { max-width: 720px; margin: 0 auto; padding: 0 14px; }

/* 页头 */
header.site { padding: 18px 0 10px; display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.site h1 { font-size: 20px; margin: 0; letter-spacing: .2px; }
.site .tagline { color: var(--sub); font-size: 13px; margin: 3px 0 0; }
.site nav a { font-size: 14px; text-decoration: none; color: var(--sub); white-space: nowrap; }
.site nav a:hover { color: var(--accent); }

/* 顶部摘要条 */
.summary {
  background: var(--accent-soft);
  border: 1px solid var(--accent-line);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 14px;
  margin: 4px 0 10px;
}
.summary b { color: var(--accent); }

/* 工具条（吸顶） */
.toolbar {
  position: sticky; top: 0; z-index: 20;
  background: rgba(246, 247, 249, .96);
  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--line);
  padding: 8px 0;
}
.tb-inner { display: flex; flex-direction: column; gap: 7px; }
.seg-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.why { font-size: 13.5px; color: var(--sub); border-left: 3px solid var(--accent-line); padding: 2px 0 2px 10px; margin: 8px 0; }
.why b { color: var(--accent); font-weight: 600; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 9px; overflow: hidden; background: var(--card); width: max-content; }
.seg-btn {
  appearance: none; border: 0; background: none; cursor: pointer;
  padding: 5px 14px; font-size: 13.5px; color: var(--sub); font-weight: 600;
}
.seg-btn + .seg-btn { border-left: 1px solid var(--line); }
.seg-btn[aria-pressed="true"] { background: var(--accent); color: #fff; }
.seg-btn .n { font-weight: 400; opacity: .75; font-size: 12px; margin-left: 2px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  appearance: none; cursor: pointer;
  border: 1px solid var(--line); background: var(--card); color: var(--sub);
  border-radius: 999px; padding: 3px 11px; font-size: 13px;
}
.chip[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); font-weight: 600; }
.chip.zero { opacity: .45; }
.chip .n { font-size: 11.5px; opacity: .7; margin-left: 2px; }

/* 日期分组 */
.day-h { margin: 18px 0 9px; font-size: 13px; color: var(--sub); font-weight: 600; display: flex; align-items: baseline; gap: 8px; }
.day-h .today { color: var(--accent); }
.cards { list-style: none; margin: 0; padding: 0; }

/* 卡片 */
.card {
  position: relative;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.card.is-selected::before {
  content: ""; position: absolute; left: -1px; top: 12px; bottom: 12px;
  width: 3px; border-radius: 2px; background: var(--accent);
}
.meta-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }
.meta-row .ct { font: 12px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--faint); margin-right: 2px; }
.cat { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 5px; }
.cat-模型 { color: #5b3df5; background: #eeeaff; }
.cat-产品 { color: #07756d; background: #dff5f1; }
.cat-研究 { color: #9a5b0c; background: #fdf0dc; }
.cat-行业 { color: #44546b; background: #eaedf3; }
.star { color: #f79009; font-size: 13px; }
.badge { font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 5px; }
.badge.pending { color: var(--warn); background: var(--warn-bg); }
.badge.beat { color: var(--ok); background: var(--ok-bg); }
.ctitle { margin: 0; font-size: 16.5px; line-height: 1.45; font-weight: 650; }
.ctitle a { color: inherit; text-decoration: none; }
.ctitle a:hover, .ctitle a:focus { color: var(--accent); text-decoration: underline; }
.ctitle-src a { color: var(--ink); font-weight: 500; }
.ctitle-src .badge.srconly { color: var(--sub); background: #eaedf3; margin-right: 2px; font-weight: 600; }
.oneliner { margin: 6px 0 0; color: var(--sub); font-size: 14px; }
.facts { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; margin-top: 9px; font-size: 12px; color: var(--sub); }
.src .tier { font-weight: 700; font-size: 11px; padding: 0 4px; border-radius: 4px; margin-left: 3px; }
.tier.t1 { color: var(--ok); background: var(--ok-bg); }
.tier.t15 { color: #9a5b0c; background: #fdf0dc; }
.tier.t2 { color: #44546b; background: #eaedf3; }
.heat { display: inline-flex; align-items: center; gap: 5px; }
.heatbar { display: inline-block; width: 54px; height: 4px; background: #e7eaf0; border-radius: 2px; overflow: hidden; }
.heatbar i { display: block; height: 100%; background: linear-gradient(90deg, var(--heat-a), var(--heat-b)); }
.toggle {
  appearance: none; background: none; border: 0; padding: 0; margin-top: 9px;
  font-size: 12.5px; color: var(--accent); cursor: pointer; font-weight: 600;
}
.toggle:hover { text-decoration: underline; }
.detail { display: none; margin-top: 9px; border-top: 1px dashed var(--line); padding-top: 9px; }
.card.open .detail { display: block; }
.quote {
  margin: 0 0 8px; padding-left: 10px; border-left: 3px solid var(--line);
  font-size: 13px; color: var(--sub); white-space: pre-wrap; overflow-wrap: anywhere;
}
.cluster h4 { margin: 0 0 4px; font-size: 12px; color: var(--sub); font-weight: 600; }
.cluster ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.cluster a { font-size: 12.5px; overflow-wrap: anywhere; }
.tiny { font-size: 11.5px; color: var(--faint); margin: 8px 0 0; }

/* D7 goal 第四刀：今日热点（多源簇排行，clusters 多源数据；无数据隐藏） */
.hotbox {
  background: #fff8ec;
  border: 1px solid #f6dca0;
  border-radius: 10px;
  padding: 10px 12px 12px;
  margin: 10px 0;
}
.hotbox h2 {
  font-size: 14px; margin: 0 0 6px; letter-spacing: .2px;
  display: flex; align-items: center; gap: 6px;
}
.hotbox h2 .badge { background: var(--heat-a); color: #fff; padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.hotbox ol { margin: 0; padding-left: 22px; }
.hotbox li { font-size: 13.5px; line-height: 1.55; padding: 2px 0; }
.hotbox li .n { display: inline-block; min-width: 26px; color: var(--heat-b); font-weight: 700; }
.hotbox li a { color: var(--ink); text-decoration: none; }
.hotbox li a:hover { color: var(--accent); text-decoration: underline; }
.hotbox li .meta { color: var(--sub); font-size: 11.5px; margin-left: 4px; }

/* 空态与页脚 */
.empty-state {
  border: 1px dashed var(--line); border-radius: 12px; background: var(--card);
  text-align: center; color: var(--sub); padding: 34px 16px; margin: 16px 0; font-size: 14px;
}
.empty-state .big { font-size: 16px; font-weight: 650; color: var(--ink); margin-bottom: 6px; }
footer { padding: 26px 0 44px; text-align: center; font-size: 12.5px; color: var(--sub); }
footer .upd { display: inline-block; }
footer .upd.stale { color: var(--danger); font-weight: 700; }
footer .links { margin-top: 6px; color: var(--faint); }
footer a { color: var(--sub); }
.noscript-box { border: 1px solid var(--warn-bg); background: var(--warn-bg); color: var(--warn); border-radius: 10px; padding: 12px 14px; margin: 12px 0; font-size: 14px; }

/* 文章页（about / 404） */
.prose { max-width: 720px; margin: 0 auto; padding: 6px 14px 30px; }
.prose h2 { font-size: 17px; margin: 26px 0 8px; }
.prose p, .prose li { color: var(--sub); font-size: 14.5px; }
.prose strong { color: var(--ink); }
.prose ul { padding-left: 20px; margin: 8px 0; }
.prose code { background: var(--accent-soft); border-radius: 4px; padding: 0 5px; font-size: 13px; }
.center-404 { text-align: center; padding: 64px 14px; }
.center-404 .code { font-size: 54px; font-weight: 800; color: var(--accent); letter-spacing: 2px; }

/* 桌面 = 加宽版 */
@media (min-width: 640px) {
  .site h1 { font-size: 22px; }
  .ctitle { font-size: 17.5px; }
  .card { padding: 14px 16px; }
  .tb-inner { flex-direction: row; justify-content: space-between; align-items: center; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
"""

# ---------------------------------------------------------------------------
# assets/app.js —— 数据渲染 + 交互（含可被 Node 单测的纯函数层 TL）
# ---------------------------------------------------------------------------
JS = r"""/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改） */
(function (root) {
  'use strict';

  var CATEGORIES = ['模型', '产品', '研究', '行业'];
  var WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  var STALE_MINUTES = 180;
  var SITE_TZ = 'Europe/Berlin';   // 2026-09-22 章程「风格：再欧洲一点」——站点时间口径改欧洲
  var SITE_TZ_LABEL = '柏林时间';

  /* ---------- 纯函数层（Node 可测） ---------- */

  function parseUTC(iso) {
    if (!iso) return null;
    var s = String(iso).trim();
    var hasZone = /[Zz]$/.test(s) || /[+-]\d{2}:?\d{2}$/.test(s);
    if (!hasZone && /\d{2}:\d{2}/.test(s)) s += 'Z';
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  function pad2(n) { return n < 10 ? '0' + n : '' + n; }

  /* 站点时区拆分。德国有夏令时（CET/CEST 来回切），绝不能像上一版那样写死固定偏移——
     用 Intl 按 IANA 时区取真值，换季自动跟上。Intl 缺席（老浏览器）时退回 UTC 而不是猜偏移：
     宁可显示 UTC，也不显示错一小时的「柏林时间」。 */
  var _tzFmt = null;
  try {
    _tzFmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: SITE_TZ, hour12: false,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', weekday: 'short'
    });
  } catch (e) { _tzFmt = null; }
  var _WD_SHORT = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

  function zoneParts(d) {
    if (!_tzFmt) {
      return {
        y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(),
        hh: d.getUTCHours(), mm: d.getUTCMinutes(), wd: d.getUTCDay()
      };
    }
    var got = {};
    _tzFmt.formatToParts(d).forEach(function (part) { got[part.type] = part.value; });
    // 24 小时制下午夜可能给出 "24"，归一到 0（Intl 实现差异，别让它跳到下一天）
    var hh = +got.hour % 24;
    return {
      y: +got.year, m: +got.month, d: +got.day,
      hh: hh, mm: +got.minute,
      wd: _WD_SHORT[got.weekday] != null ? _WD_SHORT[got.weekday] : d.getUTCDay()
    };
  }

  function zoneDayKey(d) { var p = zoneParts(d); return p.y + '-' + pad2(p.m) + '-' + pad2(p.d); }

  function fmtHM(d) { var p = zoneParts(d); return pad2(p.hh) + ':' + pad2(p.mm); }

  function fmtFullLocal(d) {
    var p = zoneParts(d);
    return p.y + '-' + pad2(p.m) + '-' + pad2(p.d) + ' ' + pad2(p.hh) + ':' + pad2(p.mm);
  }

  function dayLabel(key, todayKey, yesterdayKey) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key);
    if (!m) return '日期未详';
    var prefix = '';
    if (key === todayKey) prefix = '今天 · ';
    else if (key === yesterdayKey) prefix = '昨天 · ';
    var wd = WEEKDAYS[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()];
    return prefix + (+m[1]) + ' 年 ' + (+m[2]) + ' 月 ' + (+m[3]) + ' 日 · ' + wd;
  }

  function itemTime(it) { return parseUTC(it.published_utc || it.first_seen_utc); }

  /* 标题回退链：title_zh → title_src → 跳过不渲染 */
  function hasTitle(it) { return !!(it.title_zh || it.title_src); }

  /* 三语回退链（2026-09-19 军令：中/德/英 三版+原文）：
     所选语言缺 → 中文 → 另一语 → 原文（title_src）；任何条目永不空卡 */
  var LANG_FIELDS = {
    title: { zh: 'title_zh', de: 'title_de', en: 'title_en' },
    liner: { zh: 'one_liner_zh', de: 'one_liner_de', en: 'one_liner_en' },
    why: { zh: 'why_zh', de: 'why_de', en: 'why_en' }
  };
  function pickLang(it, kind, lang) {
    var f = LANG_FIELDS[kind];
    var order = [f[lang], f.zh, (lang === 'de' ? f.en : f.de)];
    if (kind === 'title') order.push('title_src');
    for (var i = 0; i < order.length; i++) {
      var k = order[i];
      if (k && it[k]) return { text: it[k], isSrc: (k === 'title_src') };
    }
    return { text: '', isSrc: false };
  }

  function sortItems(items) {
    return items.slice().sort(function (a, b) {
      var ta = itemTime(a), tb = itemTime(b);
      if (!ta && !tb) return 0;
      if (!ta) return 1;
      if (!tb) return -1;
      return tb - ta;
    });
  }

  /* 精选视图：selected 且非待复核（大鱼待复核的不进精选首屏） */
  function applyView(items, view) {
    if (view === 'selected') {
      return items.filter(function (it) { return it.selected && !it.big_fish_pending; });
    }
    return items.slice();
  }

  function applyCategory(items, cat) {
    if (!cat || cat === '全部') return items.slice();
    return items.filter(function (it) { return it.category === cat; });
  }

  function countsByCategory(items) {
    var c = { '全部': items.length };
    CATEGORIES.forEach(function (k) { c[k] = 0; });
    items.forEach(function (it) {
      var k = it.category;
      if (Object.prototype.hasOwnProperty.call(c, k) && k !== '全部') c[k]++;
    });
    return c;
  }

  function groupByDay(items, todayKey, yesterdayKey) {
    var buckets = {}, unknown = [], order = [];
    sortItems(items).forEach(function (it) {
      var d = itemTime(it);
      if (!d) { unknown.push(it); return; }
      var k = zoneDayKey(d);
      if (!Object.prototype.hasOwnProperty.call(buckets, k)) { buckets[k] = []; order.push(k); }
      buckets[k].push(it);
    });
    order.sort().reverse();
    var days = order.map(function (k) {
      return { key: k, label: dayLabel(k, todayKey, yesterdayKey), items: buckets[k] };
    });
    if (unknown.length) days.push({ key: '未知', label: '日期未详', items: unknown });
    return days;
  }

  function fmtAgo(ms) {
    var min = Math.max(0, Math.round(ms / 60000));
    if (min < 1) return { text: '刚刚', stale: false };
    var text;
    if (min < 60) text = min + ' 分钟前';
    else if (min < 1440) {
      var h = Math.floor(min / 60), r = min % 60;
      text = h + ' 小时' + (r ? ' ' + r + ' 分钟' : '') + '前';
    } else text = Math.floor(min / 1440) + ' 天前';
    return { text: text, stale: min > STALE_MINUTES };
  }

  function fmtBeat(h) {
    var v = (h >= 10) ? Math.round(h) : Math.round(h * 10) / 10;
    return String(v);
  }

  function clampHeat(h) {
    var n = Number(h);
    if (isNaN(n)) return 0;
    return Math.max(0, Math.min(100, Math.round(n)));
  }

  function buildViewModel(seed, view, category) {
    var all = sortItems(((seed && seed.items) || []).filter(hasTitle));
    var now = new Date();
    var todayKey = zoneDayKey(now);
    var yesterdayKey = zoneDayKey(new Date(now.getTime() - 24 * 3600 * 1000));
    var viewed = applyView(all, view);
    var filtered = applyCategory(viewed, category);
    var todays = all.filter(function (it) {
      var d = itemTime(it);
      return d && zoneDayKey(d) === todayKey;
    });
    var worthy = todays.filter(function (it) { return it.selected && !it.big_fish_pending; });
    return {
      total: all.length,
      viewTotal: viewed.length,
      days: groupByDay(filtered, todayKey, yesterdayKey),
      counts: countsByCategory(viewed),
      todayCount: todays.length,
      todayWorthy: worthy.length,
      empty: filtered.length === 0
    };
  }

  /* ---------- DOM 渲染层 ---------- */

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function tierClass(t) {
    if (t === 'T1') return 't1';
    if (t === 'T1.5') return 't15';
    if (t === 'T2') return 't2';
    return 't2';
  }

  function cardHTML(it, showStar) {
    var d = itemTime(it);
    var cats = ['cat', 'cat-' + (CATEGORIES.indexOf(it.category) >= 0 ? it.category : '行业')];
    var h = '';
    h += '<article class="card' + (it.selected ? ' is-selected' : '') + '">';
    h += '<div class="meta-row">';
    if (d) h += '<time class="ct">' + esc(fmtHM(d)) + '</time>';
    h += '<span class="' + cats.join(' ') + '">' + esc(it.category || '行业') + '</span>';
    if (showStar && it.selected && !it.big_fish_pending) h += '<span class="star" title="值得细看">★</span>';
    if (it.big_fish_pending) h += '<span class="badge pending">待复核</span>';
    /* 抢跑徽标暂停显示：beat_hours=检测延迟（first_seen−published），语义与「早于二手扩散」不符，
       对账首轮（评审/2026-09-16-抢跑对账-首轮.md）判为虚假宣传；待 D2 重设计指标后再恢复 */
    h += '</div>';
    /* 三语标题回退链：所选语言 → 中文 → 另一语 → 原文标题（降级样式+「原文题」小标）→ 无题不渲染 */
    var tp = pickLang(it, 'title', state.lang);
    if (!tp.text) return '';
    var useSrcTitle = tp.isSrc;
    h += '<h3 class="ctitle' + (useSrcTitle ? ' ctitle-src' : '') + '">';
    if (useSrcTitle) h += '<span class="badge srconly" title="加工未完成的降级条目，显示原文标题">原文题</span> ';
    h += '<a href="' + esc(it.url) + '" target="_blank" rel="noopener noreferrer">' + esc(tp.text) + '</a></h3>';
    var lp = pickLang(it, 'liner', state.lang);
    if (lp.text) h += '<p class="oneliner">' + esc(lp.text) + '</p>';
    h += '<div class="facts">';
    h += '<span class="src">' + esc(it.source_name || '未知来源') + '<b class="tier ' + tierClass(it.source_tier) + '">' + esc(it.source_tier || 'T2') + '</b></span>';
    var heat = clampHeat(it.heat);
    h += '<span class="heat" title="热度 0-100">热度 <span class="heatbar"><i style="width:' + heat + '%"></i></span> ' + heat + '</span>';
    h += '</div>';
    h += '<button type="button" class="toggle" aria-expanded="false">展开原文引句与多源</button>';
    h += '<div class="detail">';
    var wp = pickLang(it, 'why', state.lang);
    if (wp.text && it.selected) h += '<p class="why"><b>值得细看</b> · ' + esc(wp.text) + '</p>';
    if (it.quote_en) h += '<blockquote class="quote">' + esc(it.quote_en) + '</blockquote>';
    var clusters = Array.isArray(it.clusters) ? it.clusters.filter(function (c) { return c && c.url; }) : [];
    if (clusters.length) {
      h += '<div class="cluster"><h4>共 ' + (clusters.length + 1) + ' 家报道</h4><ul>';
      h += '<li><a href="' + esc(it.url) + '" target="_blank" rel="noopener noreferrer">' + esc(it.source_name || '主源') + '</a></li>';
      clusters.forEach(function (c) {
        h += '<li><a href="' + esc(c.url) + '" target="_blank" rel="noopener noreferrer">' + esc(c.source_name || '同事件报道') + '</a></li>';
      });
      h += '</ul></div>';
    } else {
      h += '<div class="cluster"><h4>单一信源</h4></div>';
    }
    var tiny = [];
    if (d) tiny.push('发布 ' + fmtFullLocal(d) + '（' + SITE_TZ_LABEL + '）');
    var fs = parseUTC(it.first_seen_utc);
    if (fs) tiny.push('雷达捕捉 ' + fmtFullLocal(fs));
    if (it.score != null && it.score !== '') tiny.push('综合评分 ' + esc(it.score));
    if (tiny.length) h += '<p class="tiny">' + tiny.join(' · ') + '</p>';
    h += '</div></article>';
    return h;
  }

  function readSeed() {
    var node = document.getElementById('seed-data');
    if (!node) return { items: [] };
    try { return JSON.parse(node.textContent); }
    catch (e) { return { items: [] }; }
  }

  /* 2026-09-22 章程「风格：再欧洲一点」：初始语言按浏览器语言挑，不再一律中文。
     读者自己点过语言段控就以他的选择为准（存 localStorage），下次进来不被浏览器覆盖。
     三语之外的浏览器语言（法语、荷兰语…）落到 en——英文比中文更可能读得懂。 */
  var LANGS = { zh: 1, de: 1, en: 1 };

  function initialLang() {
    try {
      var saved = window.localStorage.getItem('lang');
      if (saved && LANGS[saved]) return saved;
    } catch (e) { /* 隐私模式禁 localStorage：忽略，退回浏览器语言 */ }
    var cands = [];
    /* navigator 整个取不到时（极老浏览器 / 非浏览器宿主）这里会抛，必须连 .language 一起兜住：
       state 在模块加载期就调本函数，漏一个 ReferenceError 整站白屏。 */
    try {
      if (navigator.languages && navigator.languages.length) {
        cands = Array.prototype.slice.call(navigator.languages);
      }
      if (navigator.language) cands.push(navigator.language);
    } catch (e) { /* 忽略：cands 为空 → 落回 zh */ }
    for (var i = 0; i < cands.length; i++) {
      var tag = String(cands[i] || '').toLowerCase();
      if (tag.indexOf('zh') === 0) return 'zh';
      if (tag.indexOf('de') === 0) return 'de';
      if (tag.indexOf('en') === 0) return 'en';
    }
    return cands.length ? 'en' : 'zh';
  }

  function rememberLang(lang) {
    try { window.localStorage.setItem('lang', lang); } catch (e) { /* 存不下不影响本次浏览 */ }
  }

  /* 2026-09-19 军令：默认「全部」视图——当日时间线 ≥100 条滚动是主角，精选仍可一键切 */
  var state = { view: 'all', category: '全部', lang: initialLang() };
  var seed = null;
  var els = {};

  function paint() {
    var vm = buildViewModel(seed, state.view, state.category);

    // 5) 顶部摘要条
    if (vm.total === 0) {
      els.summary.innerHTML = '今日数据加工中，稍后回来再看。';
    } else {
      els.summary.innerHTML = '今天 <b>' + vm.todayCount + '</b> 条，其中 <b>' + vm.todayWorthy + '</b> 条值得细看';
    }

    // 2) 双视图
    [['selected', els.viewSelected], ['all', els.viewAll]].forEach(function (p) {
      var active = state.view === p[0];
      p[1].setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    // 2b) 三语切换（中/德/英；缺译条目走回退链不空卡）
    [['zh', els.langZh], ['de', els.langDe], ['en', els.langEn]].forEach(function (p) {
      if (p[1]) p[1].setAttribute('aria-pressed', state.lang === p[0] ? 'true' : 'false');
    });
    var selCount = applyView(sortItems((seed.items || []).filter(hasTitle)), 'selected').length;
    els.viewSelected.innerHTML = '精选<span class="n">' + selCount + '</span>';
    els.viewAll.innerHTML = '全部<span class="n">' + vm.total + '</span>';

    // 4) 分类筛选：0 计数也保留入口
    var chips = ['全部'].concat(CATEGORIES);
    els.chips.innerHTML = '';
    chips.forEach(function (k) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip' + (vm.counts[k] === 0 ? ' zero' : '');
      b.setAttribute('aria-pressed', state.category === k ? 'true' : 'false');
      b.innerHTML = esc(k) + '<span class="n">' + (vm.counts[k] || 0) + '</span>';
      b.addEventListener('click', function () { state.category = k; paint(); });
      els.chips.appendChild(b);
    });

    // 1) 按天分组时间线
    els.timeline.innerHTML = '';
    if (vm.empty) {
      var box = document.createElement('div');
      box.className = 'empty-state';
      if (vm.total === 0) {
        box.innerHTML = '<div class="big">今日数据加工中</div>时间线暂时为空，引擎正在抓取与精选，稍后自动更新。';
      } else {
        box.innerHTML = '<div class="big">该筛选下暂无条目</div>换个分类或切到「全部」视图看看。';
      }
      els.timeline.appendChild(box);
      return;
    }
    vm.days.forEach(function (day) {
      var h = document.createElement('div');
      h.className = 'day-h';
      var isToday = day.key !== '未知' && day.key === vm.daysTodayKey;
      h.innerHTML = '<span class="' + (day.label.indexOf('今天') === 0 ? 'today' : '') + '">' + esc(day.label) + '</span><span style="font-weight:400">' + day.items.length + ' 条</span>';
      var ol = document.createElement('ol');
      ol.className = 'cards';
      var showStar = state.view !== 'selected';
      ol.innerHTML = day.items.filter(hasTitle).map(function (it) { return '<li>' + cardHTML(it, showStar) + '</li>'; }).join('');
      h.container = null;
      var wrap = document.createElement('section');
      wrap.appendChild(h);
      wrap.appendChild(ol);
      els.timeline.appendChild(wrap);
    });
  }

  function updateFooter() {
    var hasData = seed && Array.isArray(seed.items) && seed.items.length > 0;
    if (!hasData) {
      /* 空态心跳：中性提示，不启用「超 3 小时变红」 */
      els.upd.textContent = '初始化中 · 数据流水线正在首次抓取';
      els.upd.className = 'upd';
      return;
    }
    var g = parseUTC(seed.generated_at_utc);
    if (!g) { els.upd.textContent = '最后更新时间未知'; els.upd.className = 'upd'; return; }
    var a = fmtAgo(Date.now() - g.getTime());
    els.upd.textContent = '最后更新：' + a.text + '（' + fmtFullLocal(g) + ' ' + SITE_TZ_LABEL + '）' + (a.stale ? ' · 数据可能已停滞' : '');
    els.upd.className = 'upd' + (a.stale ? ' stale' : '');
    /* 双心跳之一：引擎心跳（雷达心跳=数据新鲜度已在上方；引擎状态附加显示，取不到静默跳过） */
    try {
      fetch('data/%E5%BC%95%E6%93%8E%E5%BF%83%E8%B7%B3.json', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (hb) {
          if (!hb || !els.upd || els.upd.textContent.indexOf('引擎') >= 0) return;
          var t = parseUTC(hb.generated_at_utc || hb.when || hb.ts);
          var s = hb.status || 'ok';
          var extra = s !== 'ok'
            ? ' · 引擎告警(' + s + ')'
            : ' · 引擎' + (t ? '心跳' + fmtAgo(Date.now() - t.getTime()).text : '心跳在位');
          els.upd.textContent += extra;
        })
        .catch(function () {});
    } catch (e) {}
  }

  function bind() {
    els.viewSelected.addEventListener('click', function () { state.view = 'selected'; paint(); });
    els.viewAll.addEventListener('click', function () { state.view = 'all'; paint(); });
    [['zh', els.langZh], ['de', els.langDe], ['en', els.langEn]].forEach(function (p) {
      if (p[1]) p[1].addEventListener('click', function () {
        state.lang = p[0]; rememberLang(p[0]); paint();
      });
    });
    els.timeline.addEventListener('click', function (ev) {
      var t = ev.target;
      if (t && t.classList && t.classList.contains('toggle')) {
        var card = t.closest ? t.closest('.card') : null;
        if (card) {
          var open = card.classList.toggle('open');
          t.setAttribute('aria-expanded', open ? 'true' : 'false');
          t.textContent = open ? '收起' : '展开原文引句与多源';
        }
      }
    });
  }

  function renderAll() {
    seed = readSeed();
    els.summary = document.getElementById('summary');
    els.toolbar = document.getElementById('toolbar');
    els.viewSelected = document.getElementById('view-selected');
    els.viewAll = document.getElementById('view-all');
    els.langZh = document.getElementById('lang-zh');
    els.langDe = document.getElementById('lang-de');
    els.langEn = document.getElementById('lang-en');
    els.chips = document.getElementById('chips');
    els.timeline = document.getElementById('timeline');
    els.upd = document.getElementById('last-updated');
    if (!els.timeline || !els.summary) return;
    if (els.toolbar) els.toolbar.removeAttribute('hidden');
    paint();
    bind();
    updateFooter();
    setInterval(updateFooter, 30000);
    /* 每小时滚动（2026-09-19 军令）：每 20 分钟查一次契约版本，变了自动刷新拿新数据 */
    setInterval(function () {
      fetch('data/%E7%B2%BE%E9%80%89%E5%BA%93.json', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (d && d.generated_at_utc && seed && seed.generated_at_utc
              && d.generated_at_utc !== seed.generated_at_utc) location.reload();
        }).catch(function () {});
    }, 1200000);
  }

  /* 导出纯函数层供 Node 单测 */
  root.TL = {
    parseUTC: parseUTC, zoneDayKey: zoneDayKey, zoneParts: zoneParts, fmtHM: fmtHM,
    fmtFullLocal: fmtFullLocal, dayLabel: dayLabel, sortItems: sortItems,
    applyView: applyView, applyCategory: applyCategory,
    countsByCategory: countsByCategory, groupByDay: groupByDay,
    fmtAgo: fmtAgo, fmtBeat: fmtBeat, clampHeat: clampHeat,
    buildViewModel: buildViewModel, cardHTML: cardHTML, hasTitle: hasTitle,
    pickLang: pickLang, initialLang: initialLang
  };

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', renderAll);
    } else {
      renderAll();
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
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

INDEX_TMPL = HEAD_TMPL + """
<header class="site container">
  <div>
    <h1>{{SITE_NAME}}</h1>
    <p class="tagline">{{SITE_TAGLINE}}</p>
  </div>
  <nav><a href="agents/">Agents / API</a> · <a href="about.html">关于</a></nav>
</header>

<div class="container">
  <p id="summary" class="summary" aria-live="polite">正在载入时间线…</p>
</div>

<div class="container">
  {{HOTBOX_HTML}}
</div>

<div class="toolbar" id="toolbar" hidden>
  <div class="container tb-inner">
    <div class="seg-row">
      <div class="seg" role="group" aria-label="视图切换">
        <button type="button" id="view-selected" class="seg-btn" aria-pressed="false">精选</button>
        <button type="button" id="view-all" class="seg-btn" aria-pressed="true">全部</button>
      </div>
      <div class="seg" role="group" aria-label="语言 Sprache Language">
        <button type="button" id="lang-zh" class="seg-btn" aria-pressed="true">中文</button>
        <button type="button" id="lang-de" class="seg-btn" aria-pressed="false">DE</button>
        <button type="button" id="lang-en" class="seg-btn" aria-pressed="false">EN</button>
      </div>
    </div>
    <div class="chips" id="chips" role="group" aria-label="分类筛选"></div>
  </div>
</div>

<main class="container" id="main">
  <div id="timeline"></div>
</main>

<footer>
  <div class="container">
    <span id="last-updated" class="upd">…</span>
    <div class="links">{{SITE_NAME}} · <a href="about.html">关于 · 免责 · 纠错</a> · <a href="agents/">Agents / API</a> · <a href="feed.xml">RSS</a> · 筛选与翻译由 AI 辅助完成，人工复核中</div>
  </div>
</footer>

<noscript><div class="container"><div class="noscript-box">浏览时间线需要启用 JavaScript。原始数据可查看 <a href="data/%E7%B2%BE%E9%80%89%E5%BA%93.json">data/精选库.json</a>。</div></div></noscript>

<script type="application/json" id="seed-data">{{SEED_JSON}}</script>
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
  <h2>这是什么</h2>
  <p>这是一张给中文读者的 AI 时间线。每天从上百条原始信号里，按一套固定的打分规则做筛选，只留下真正值得看的几条，按<strong>柏林时间</strong>（Europe/Berlin，含夏令时）排列成按天分组的时间线。覆盖四个分类：<strong>模型、产品、研究、行业</strong>。</p>
  <ul>
    <li><strong>精选 / 全部双视图</strong>：默认只看精选（宁缺毋滥），可一键切到全部。</li>
    <li><strong>抢跑标注</strong>：带「比二手扩散早 X 小时」徽标的条目，是我们的雷达在一手信源上捕捉到、领先于中文二手转载的时间差。</li>
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
  <p>本站的<strong>筛选、摘要与翻译由 AI 辅助完成</strong>，人工复核正在进行中。标有「<strong>待复核</strong>」的条目表示尚未完成人工确认，仅在「全部」视图中展示。每条卡片附带的英文原文引句用于降低机器转述失真，也欢迎你监督。</p>

  <h2>Impressum（版本说明 · 占位）</h2>
  <p>本站为自动化运行的 AI 资讯聚合项目，运营者信息以代码托管仓库公示为准，联系通道为 GitHub Issues：<a href="{{ISSUES_URL}}" target="_blank" rel="noopener noreferrer">{{ISSUES_URL}}</a>。完整的 Impressum（依德国 DDG §5）将在正式上线前补齐。</p>
  <p lang="de">Hinweis: Ein vollständiges Impressum gemäß § 5 DDG folgt vor dem offiziellen Start.</p>
  <p lang="en">Note: A full imprint will be published before the official launch.</p>

  <h2>Datenschutz（数据保护声明 · 占位）</h2>
  <p>本站是<strong>纯静态站点</strong>：不设置 Cookie、不运行统计或追踪脚本、不主动收集任何个人数据。页面由第三方托管平台分发，托管方（如 GitHub Pages 等）的服务器日志可能按其运营惯例记录访问 IP 等技术数据，详情以托管方隐私政策为准。完整的数据保护声明将在正式上线前发布。</p>
  <p lang="de">Hinweis: Diese Seite ist statisch, setzt keine Cookies und bindet keine Tracker ein. Serverprotokolle des Hosters können technische Zugriffsdaten enthalten. Eine vollständige Datenschutzerklärung folgt vor dem Start.</p>
  <p lang="en">Note: This site is static, sets no cookies and embeds no trackers. The hosting provider's server logs may record technical access data. A full privacy notice will follow before launch.</p>

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
# 2026-09-22 P1：agent 可接入层（RSS / JSON API / llms.txt / agents 页）
# 章程「重点保证」：网站首先要机器能直接吃。**版本号进路径，接口一旦公布不破坏**：
# 只增字段不删字段、不改字段含义；要改就开 /api/v2/。
# ---------------------------------------------------------------------------
API_VERSION = "v1"
FEED_MAX = 60          # RSS 条数上限（精选恒在，余额按 24h 新鲜度补）
FRESH_HOURS = 24       # 「24h 全量」档口径
LICENSE_NOTE = ("摘要、标题翻译与点评由本站 AI 生成，可自由取用（署名 news.aiimmigrant.de 即可）；"
                "原文版权归各信源所有，请始终带上 url 回链原文。")
UPDATE_NOTE = "引擎每小时一轮（launchd :07），精选库随轮更新；接口无鉴权、无频控，请自觉别超过 1 次/分钟。"

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
