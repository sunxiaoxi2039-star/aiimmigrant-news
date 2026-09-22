/* AI 资讯时间线 · 前端（原生 JS，无框架；生成器产出，勿手改） */
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
