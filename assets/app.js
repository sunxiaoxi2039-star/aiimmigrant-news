/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改） */
(function (root) {
  'use strict';

  var CATEGORIES = ['模型', '产品', '研究', '行业'];
  var WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  var STALE_MINUTES = 180;
  var BJ_OFFSET_MS = 8 * 3600 * 1000;

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

  function bjParts(d) {
    var t = new Date(d.getTime() + BJ_OFFSET_MS); // 中国无夏令时，固定 +8
    return {
      y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate(),
      hh: t.getUTCHours(), mm: t.getUTCMinutes(), wd: t.getUTCDay()
    };
  }

  function bjDayKey(d) { var p = bjParts(d); return p.y + '-' + pad2(p.m) + '-' + pad2(p.d); }

  function fmtHM(d) { var p = bjParts(d); return pad2(p.hh) + ':' + pad2(p.mm); }

  function fmtFullBJ(d) {
    var p = bjParts(d);
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
      var k = bjDayKey(d);
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
    var all = sortItems((seed && seed.items) || []);
    var now = new Date();
    var todayKey = bjDayKey(now);
    var yesterdayKey = bjDayKey(new Date(now.getTime() - 24 * 3600 * 1000));
    var viewed = applyView(all, view);
    var filtered = applyCategory(viewed, category);
    var todays = all.filter(function (it) {
      var d = itemTime(it);
      return d && bjDayKey(d) === todayKey;
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
    if (it.beat_hours != null && it.beat_hours !== '' && !isNaN(Number(it.beat_hours))) {
      h += '<span class="badge beat" title="雷达捕捉到一手源的时间，早于中文二手扩散">比二手扩散早 ' + esc(fmtBeat(Number(it.beat_hours))) + ' 小时</span>';
    }
    h += '</div>';
    h += '<h3 class="ctitle"><a href="' + esc(it.url) + '" target="_blank" rel="noopener noreferrer">' + esc(it.title_zh) + '</a></h3>';
    if (it.one_liner_zh) h += '<p class="oneliner">' + esc(it.one_liner_zh) + '</p>';
    h += '<div class="facts">';
    h += '<span class="src">' + esc(it.source_name || '未知来源') + '<b class="tier ' + tierClass(it.source_tier) + '">' + esc(it.source_tier || 'T2') + '</b></span>';
    var heat = clampHeat(it.heat);
    h += '<span class="heat" title="热度 0-100">热度 <span class="heatbar"><i style="width:' + heat + '%"></i></span> ' + heat + '</span>';
    h += '</div>';
    h += '<button type="button" class="toggle" aria-expanded="false">展开原文引句与多源</button>';
    h += '<div class="detail">';
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
    if (d) tiny.push('发布 ' + fmtFullBJ(d) + '（北京时间）');
    var fs = parseUTC(it.first_seen_utc);
    if (fs) tiny.push('雷达捕捉 ' + fmtFullBJ(fs));
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

  var state = { view: 'selected', category: '全部' };
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
    var selCount = applyView(sortItems(seed.items || []), 'selected').length;
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
      ol.innerHTML = day.items.map(function (it) { return '<li>' + cardHTML(it, showStar) + '</li>'; }).join('');
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
    els.upd.textContent = '最后更新：' + a.text + '（' + fmtFullBJ(g) + ' 北京时间）' + (a.stale ? ' · 数据可能已停滞' : '');
    els.upd.className = 'upd' + (a.stale ? ' stale' : '');
  }

  function bind() {
    els.viewSelected.addEventListener('click', function () { state.view = 'selected'; paint(); });
    els.viewAll.addEventListener('click', function () { state.view = 'all'; paint(); });
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
    els.chips = document.getElementById('chips');
    els.timeline = document.getElementById('timeline');
    els.upd = document.getElementById('last-updated');
    if (!els.timeline || !els.summary) return;
    if (els.toolbar) els.toolbar.removeAttribute('hidden');
    paint();
    bind();
    updateFooter();
    setInterval(updateFooter, 30000);
  }

  /* 导出纯函数层供 Node 单测 */
  root.TL = {
    parseUTC: parseUTC, bjDayKey: bjDayKey, bjParts: bjParts, fmtHM: fmtHM,
    fmtFullBJ: fmtFullBJ, dayLabel: dayLabel, sortItems: sortItems,
    applyView: applyView, applyCategory: applyCategory,
    countsByCategory: countsByCategory, groupByDay: groupByDay,
    fmtAgo: fmtAgo, fmtBeat: fmtBeat, clampHeat: clampHeat,
    buildViewModel: buildViewModel, cardHTML: cardHTML
  };

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', renderAll);
    } else {
      renderAll();
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
