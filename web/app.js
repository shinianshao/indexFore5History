/* 古籍檢索 · 前端
   數據由 pipeline/ 生成：
     app-data.js     索引（人物 / 地名 / 篇目 / 命中句）
     corpus-data.js  全篇正文，只在「讀全篇」時按需注入

   兩套實體、一套界面：
     人物  marks   —— 一人多稱（同人異稱）+ 一稱多人（同稱異人，按篇目上下文判定）
     地名  pmarks  —— 一字多名（同名異寫）+ 單字國名與姓氏/常用字撞車（按鄰字守衛排除）
   兩處高亮一律以「索引裏的標記」為準，不按別名直接搜正文：
     正文裏的「梁王」可能指彭越也可能指劉武，直接搜會張冠李戴；
     正文裏的「陳」可能是陳國，也可能是「陳師牧野」（陳列）或陳平（姓氏）。 */
(function () {
  "use strict";

  var DATA = window.BOOK_DATA;
  var out = document.getElementById("out");
  var note = document.getElementById("note");
  var quick = document.getElementById("quick");
  var sub = document.getElementById("sub");

  if (!DATA) {
    out.innerHTML = '<div class="empty">數據文件未加載，請確認 app-data.js 與 index.html 在同一目錄。</div>';
    return;
  }

  var persons = DATA.persons;
  var places = DATA.places || [];
  var chapters = DATA.chapters;
  var sentences = DATA.sentences;
  var meta = DATA.meta;

  var chapterMap = {};
  var personMap = {};
  var placeMap = {};
  chapters.forEach(function (c) { chapterMap[c.id] = c; });
  persons.forEach(function (p) { personMap[p.id] = p; });
  places.forEach(function (p) { placeMap[p.id] = p; });

  /* 稱號類別名（泛稱）：歸屬由篇目上下文逐條判定，不能無條件用於高亮 */
  var genericForms = {};
  (DATA.genericAliases || []).forEach(function (g) {
    (g.forms || []).forEach(function (f) { genericForms[f] = g.alias; });
  });

  var GUESS_TIER = "guess";
  var TIER_LABEL = {
    owner: "本篇主人公",
    related: "篇內相關人物",
    sentence: "同句共現",
    paragraph: "同段共現",
    chapter: "本篇共現",
    era: "本篇時代",
    guess: "未能判定"
  };

  /* 稱謂表的分組。判定規則見 pipeline/annotate.py 的 alias_kind()。 */
  var KIND_ORDER = ["name", "title", "generic", "short", "other"];
  var KIND_LABEL = {
    name: "本名",
    title: "職銜（不參與檢索）",
    generic: "泛稱",
    short: "單字",
    other: "其他"
  };
  var KIND_HINT = {
    name: "姓名本身",
    title: "職銜、封號等（僅展示，不參與檢索；檢索請用本名/字/專屬稱謂）",
    generic: "稱號類別名，同一稱號在不同篇目可能指不同人，按篇目上下文逐條判定",
    short: "單字指代，只在特定篇目內有效，不做全庫匹配",
    other: "字、號、尊稱、別稱等"
  };

  /* 地名按類型分組展示。順序與 pipeline/annotate_places.py 的 KIND_ORDER 一致。 */
  var PLACE_KIND_ORDER = ["国", "郡", "县", "关", "山", "川", "湖", "域", "外"];

  /* ---------------- 索引 ---------------- */

  var mainByPerson = {};
  chapters.forEach(function (c) {
    (c.mainPersons || []).forEach(function (pid) {
      (mainByPerson[pid] = mainByPerson[pid] || []).push(c.id);
    });
  });

  var mentionsByPerson = {};
  var mentionsByPlace = {};
  var sentByChapter = {};
  var exactIndex = {};
  var placeIndex = {};
  /* 一句話多次提到同一實體 → 索引裏是多個標記，但結果列表裏這句話只該出現一次。
     否則「舜耕歷山，歷山之人皆讓畔」會原樣排兩遍，展開時"顯示全部 N 處"也虛增。
     所以此處按「實體 + 篇目」對句子去重；重複的交給 markCountOf 計"處"。
     人物層上游已給 persons 去重，這裏一併加守衛，防後期上游改動悄悄退化。 */
  sentences.forEach(function (s) {
    var seenP = {}, seenL = {};
    s.persons.forEach(function (pid) {
      if (seenP[pid]) return;
      seenP[pid] = 1;
      var bucket = mentionsByPerson[pid] = mentionsByPerson[pid] || {};
      (bucket[s.chapterId] = bucket[s.chapterId] || []).push(s);
    });
    (s.pmarks || []).forEach(function (m) {
      if (seenL[m.pid]) return;
      seenL[m.pid] = 1;
      var bucket = mentionsByPlace[m.pid] = mentionsByPlace[m.pid] || {};
      (bucket[s.chapterId] = bucket[s.chapterId] || []).push(s);
    });
    (sentByChapter[s.chapterId] = sentByChapter[s.chapterId] || []).push(s);
  });
  persons.forEach(function (p) {
    var forms = (p.aliases || []).slice();
    (p.aliasList || []).forEach(function (a) {
      (a.variants || []).forEach(function (v) {
        if (forms.indexOf(v) < 0) forms.push(v);
      });
    });
    p._forms = forms;
    forms.forEach(function (f) {
      (exactIndex[f] = exactIndex[f] || []).push(p.id);
    });
  });
  places.forEach(function (p) {
    var forms = (p.aliases || []).slice();
    (p.aliasList || []).forEach(function (a) {
      (a.variants || []).forEach(function (v) {
        if (forms.indexOf(v) < 0) forms.push(v);
      });
    });
    p._forms = forms;
    forms.forEach(function (f) {
      (placeIndex[f] = placeIndex[f] || []).push(p.id);
    });
  });

  /* ---------------- 書作用域 ----------------
     多書之後每一本書都有自己的條目列表：選一本＝書內檢索，選幾本＝多書合檢。
     計數一律走 byBook（由 pipeline/annotate.py 按書分帳），
     頂層 mentionCount 是兩書合計，只在「全選」時才等於顯示值。 */
  var BOOKS = meta.books || [];
  var BOOK_NAME = {};
  BOOKS.forEach(function (b) { BOOK_NAME[b.code] = b.name; });
  var scope = BOOKS.map(function (b) { return b.code; });   // 默認全選＝多書合檢
  var peiOn = true;     // 默認顯示裴注（三國志裴松之注；開啟後統計＝正文+注文）
  var bookBar = document.getElementById("books");

  function isMulti() { return BOOKS.length > 1; }

  function inScope(cid) {
    var c = chapterMap[cid];
    if (!c) return false;
    return !isMulti() || scope.indexOf(c.bookId) >= 0;
  }

  /* 裴注（三國志裴松之注）+ 晉書舊史注：獨立索引；peiOn 時併入顯示統計 */
  function peiOf(pid) {
    var d = window.PEI_DATA;
    if (!d || !d.persons) return null;
    return d.persons[pid] || null;
  }

  function jsNoteOf(pid) {
    var d = window.JS_NOTE_DATA;
    if (!d || !d.persons) return null;
    return d.persons[pid] || null;
  }

  /* 裴注只在「開關開 + 三國志在作用域」時計入 */
  function peiActive() {
    return peiOn && (!isMulti() || scope.indexOf("sgz") >= 0);
  }

  function jsNoteActive() {
    return peiOn && (!isMulti() || scope.indexOf("js") >= 0);
  }

  function peiStatOf(ent) {
    if (!ent || !ent.id) return { n: 0, c: 0 };
    var n = 0, c = 0;
    if (peiActive()) {
      var pei = peiOf(ent.id);
      if (pei) { n += pei.n || 0; c += pei.chapters || 0; }
    }
    if (jsNoteActive()) {
      var jn = jsNoteOf(ent.id);
      if (jn) { n += jn.n || 0; c += jn.chapters || 0; }
    }
    return { n: n, c: c };
  }

  /* 實體在當前書作用域內的「處 / 篇」。單書時取該書分帳，多書時相加。
     peiOn 時 nAll/cAll = 正文 + 裴注；pn/pc = 注文分量（顯示成【裴N】）。 */
  function scopeStat(ent) {
    var bb = ent.byBook;
    var n = 0, c = 0;
    if (!bb || !isMulti()) {
      n = ent.mentionCount || 0;
      c = ent.mentionChapterCount || 0;
    } else {
      scope.forEach(function (code) {
        var r = bb[code];
        if (r) { n += r.mentionCount; c += r.mentionChapterCount; }
      });
    }
    var ps = peiStatOf(ent);
    /* 篇數仍按正文（注文篇與正文篇常重疊，相加會重複計）；
       處數＝正文+注文，注文分量以【裴N】標出。 */
    return {
      n: n, c: c,
      pn: ps.n, pc: ps.c,
      nAll: n + ps.n,
      cAll: c
    };
  }

  /* 顯示用：總數（含裴注）+【裴N】；無注文分量則不標。
     withUnit=true 時補「處」（候選列表用）；索引格與舊斷言對齊、不帶單位。 */
  function statText(st, withUnit) {
    var t = st.cAll + " 篇 / " + count(st.nAll) + (withUnit ? " 處" : "");
    if (st.pn > 0) t += "【裴" + count(st.pn) + "】";
    return t;
  }

  /* 稱謂/寫法的次數：單書時只算這一本 */
  function scopeAliasN(a) {
    var bb = a.byBook;
    if (!bb || !isMulti()) return a.n || 0;
    var n = 0;
    scope.forEach(function (code) { n += bb[code] || 0; });
    return n;
  }

  /* 懸停提示裏列出各書的分帳，多書合檢時一眼看出命中分佈在哪本 */
  function bookBreakdown(ent) {
    var bb = ent.byBook;
    if (!bb || !isMulti()) return "";
    var parts = [];
    BOOKS.forEach(function (b) {
      var r = bb[b.code];
      if (r && r.mentionCount) {
        parts.push("《" + b.name + "》" + r.mentionChapterCount + " 篇 / " +
                   count(r.mentionCount) + " 處");
      }
    });
    return parts.join("；");
  }

  function renderBookBar() {
    if (!bookBar || !isMulti()) return;
    var html = "";
    BOOKS.forEach(function (b) {
      var on = scope.indexOf(b.code) >= 0;
      html += '<span class="bk' + (on ? " on" : "") + '" data-book="' + b.code +
              '" title="' + esc("《" + b.name + "》" + b.chapterCount + " 篇 · " +
                                count(b.sentenceCount) + " 句 · 人物 " + b.personCount +
                                " 人 · 地名 " + b.placeCount + " 個") + '">' +
              esc("《" + b.name + "》") + "<em>" + b.chapterCount + " 篇</em></span>";
      /* 三国志后紧跟裴注小胶囊（三國志裴松之注） */
      if (b.code === "sgz") {
        html += '<span class="bk pei-chip' + (peiOn ? " on" : "") + '" data-book="pei"' +
                ' title="三國志裴松之注·開啟後統計為原文+注文合計，標【裴N】；關閉則只計正文">' +
                '三國志裴松之注</span>';
      }
    });
    var allOn = scope.length === BOOKS.length;
    html += '<span class="bk all' + (allOn ? " on" : "") + '" data-book="all">' +
            "多書合檢<em>同時選中 " + scope.length + " / " + BOOKS.length + " 本</em></span>";
    bookBar.innerHTML = html;
    bookBar.querySelectorAll(".bk").forEach(function (el) {
      el.addEventListener("click", function () {
        var code = el.getAttribute("data-book");
        if (code === "all") {
          /* 合檢只全選書，與裴注開關無關 */
          scope = BOOKS.map(function (b) { return b.code; });
        } else if (code === "pei") {
          peiOn = !peiOn;
          /* 裴注开启时自动选三国志 */
          if (peiOn && scope.indexOf("sgz") < 0) {
            scope.push("sgz");
            scope.sort(function (a, b) {
              return BOOKS.map(function (x) { return x.code; }).indexOf(a) -
                     BOOKS.map(function (x) { return x.code; }).indexOf(b);
            });
          }
        } else {
          var i = scope.indexOf(code);
          if (i >= 0) {
            if (scope.length === 1) return;
            scope.splice(i, 1);
            /* 关闭三国志时顺带关裴注 */
            if (code === "sgz") peiOn = false;
          } else {
            scope.push(code);
            /* 重新勾选三国志时恢复裴注 */
            if (code === "sgz") peiOn = true;
          }
          scope.sort(function (a, b) {
            return BOOKS.map(function (x) { return x.code; }).indexOf(a) -
                   BOOKS.map(function (x) { return x.code; }).indexOf(b);
          });
        }
        renderBookBar();
        renderSub();
        initQuick();
        switchTab(currentTab);
        if (currentTab === "search") {
          if (currentPlace) renderPlace(currentPlace);
          else if (currentPerson) renderPerson(currentPerson);
        }
      });
    });
  }

  function scopeLabel() {
    if (!isMulti()) return meta.book || "史記";
    if (scope.length === BOOKS.length) {
      return BOOKS.map(function (b) { return "《" + b.name + "》"; }).join(" + ");
    }
    return scope.map(function (c) { return "《" + (BOOK_NAME[c] || c) + "》"; }).join(" + ");
  }

  function renderSub() {
    var n = 0;
    chapters.forEach(function (c) { if (inScope(c.id)) n += 1; });
    sub.textContent = scopeLabel() + " · 全 " + n + " 篇 · 人名索引 + 地名索引";
  }

  var currentPerson = null;
  var currentPlace = null;
  var currentTab = "search";
  /* 讀全篇時要點亮誰：{kind:"person"|"place", id} */
  var readerTarget = { kind: "person", id: null };

  /* ---------------- 工具 ---------------- */

  function esc(text) {
    return String(text).replace(/[&<>"]/g, function (ch) {
      return ch === "&" ? "&amp;" : ch === "<" ? "&lt;" : ch === ">" ? "&gt;" : "&quot;";
    });
  }

  function count(n) { return Number(n).toLocaleString(); }

  /* 取一句話裏屬於「當前實體」的標記。人物用 marks，地名用 pmarks。 */
  function marksOf(sent, kind) {
    return (kind === "place" ? sent.pmarks : sent.marks) || [];
  }

  /* 一句話裏某實體出現了幾次（標記數）。
     一句話可以多次提到同一個人、同一個地（「舜耕歷山，歷山之人皆讓畔」），
     索引裏就是多個標記。列表按「句」去重後這句話只出現一次，但次數不能因此
     丟掉——所以「處」（標記數）與「句」（去重後的句子數）分開算、分開顯示。 */
  function markCountOf(sent, id, kind) {
    var list = marksOf(sent, kind), n = 0;
    for (var i = 0; i < list.length; i++) if (list[i].pid === id) n++;
    return n;
  }

  function markCountAll(list, id, kind) {
    var n = 0;
    for (var i = 0; i < list.length; i++) n += markCountOf(list[i], id, kind);
    return n;
  }

  /* 一句話裏含多處時，標題行只報「處」，兩者不等才補「句」，避免常見的相等情況下囉嗦 */
  function hitMeta(list, id, kind) {
    var marks = markCountAll(list, id, kind);
    var sents = list.length;
    return count(marks) + " 處" + (marks === sents ? "" : " · " + count(sents) + " 句");
  }

  /* 只高亮「歸到目標實體」的標記。
     早期版本把句子裏的所有人物標記都點亮，搜「劉邦」會把同句的「項羽」也標上，
     屬於顯示錯誤：用戶會以為那段講的是劉邦。 */
  function highlightSent(sent, id, kind) {
    var list = marksOf(sent, kind);
    if (!list.length) return esc(sent.text);
    return renderWithSpans(sent.text, list.filter(function (m) {
      return m.pid === id;
    }), kind);
  }

  /* 注文区间：裴注/夹注 〈…〉，以及脚注标记 [一][二]…
     渲染时套 .annot / .fn-mark，字号与颜色与正文区分。 */
  function annotRanges(text) {
    var out = [], re = /〈[^〉]*〉|\[[一二三四五六七八九十百]+\]/g, m;
    while ((m = re.exec(text))) {
      out.push({ s: m.index, e: m.index + m[0].length, t: m[0].charAt(0) });
    }
    return out;
  }

  /* 按區間列表給一段文本打高亮；區間必須來自索引標記。
     弱標記（人物「歸屬存疑」、地名「單字國名」）用不同樣式區分，別讓用戶
     把低置信結果當成確定結論。注文区间与标记叠加时，注文在外、标记在内。 */
  function renderWithSpans(text, spans, kind) {
    var annots = annotRanges(text);
    if (!spans || !spans.length) return renderPlain(text, annots);
    var weak = kind === "place" ? "char" : GUESS_TIER;
    var weakCls = kind === "place" ? "approx" : "guess";
    var weakTip = kind === "place"
      ? "單字國名，與姓氏/常用字同形，靠鄰字排除判定，可能有誤"
      : "是稱號，此處歸屬未能判定";
    var list = spans.slice().sort(function (a, b) { return a.s - b.s; });
    var html = "", last = 0;
    list.forEach(function (h) {
      if (h.s < last) return;                 // 區間重疊時跳過，避免錯位
      html += renderPlain(text.slice(last, h.s), shiftRanges(annots, last, h.s));
      var isWeak = h.tier === weak;
      var cls = isWeak ? ' class="' + weakCls + '"' : "";
      var tip = isWeak
        ? ' title="“' + esc(h.alias || "") + "”" + weakTip + '"'
        : (h.alias
            ? ' title="' + esc(h.alias) + (kind === "person" && TIER_LABEL[h.tier]
                ? " · " + TIER_LABEL[h.tier] : "") + '"'
            : "");
      html += "<mark" + cls + tip + ">" +
              renderPlain(text.slice(h.s, h.e), shiftRanges(annots, h.s, h.e)) +
              "</mark>";
      last = h.e;
    });
    return html + renderPlain(text.slice(last), shiftRanges(annots, last, text.length));
  }

  /* 截取 [from,to) 窗口内的注文区间（已平移到窗口局部坐标）。 */
  function shiftRanges(annots, from, to) {
    var out = [];
    for (var i = 0; i < annots.length; i++) {
      var a = annots[i];
      if (a.e <= from || a.s >= to) continue;
      out.push({
        s: Math.max(a.s, from) - from,
        e: Math.min(a.e, to) - from,
        t: a.t
      });
    }
    return out;
  }

  /* 纯文本段：按注文区间切开并包 span，仍转义 HTML。 */
  function renderPlain(text, annots) {
    if (!text) return "";
    if (!annots || !annots.length) return esc(text);
    var html = "", last = 0;
    annots.forEach(function (a) {
      if (a.s < last) return;
      html += esc(text.slice(last, a.s));
      var cls = a.t === "〈" ? "annot" : "fn-mark";
      html += '<span class="' + cls + '">' + esc(text.slice(a.s, a.e)) + "</span>";
      last = a.e;
    });
    return html + esc(text.slice(last));
  }

  /* 某人在某篇裏的泛稱稱號歸屬依據：稱號 -> 依據 -> 次數 */
  function titlesOf(person) {
    var map = {};
    var bucket = mentionsByPerson[person.id] || {};
    Object.keys(bucket).forEach(function (cid) {
      if (!inScope(cid)) return;            // 只統計當前選中的書
      bucket[cid].forEach(function (s) {
        (s.marks || []).forEach(function (m) {
          if (m.pid !== person.id || !genericForms[m.alias]) return;
          var one = map[m.alias] = map[m.alias] || { total: 0, tiers: {} };
          one.total += 1;
          one.tiers[m.tier] = (one.tiers[m.tier] || 0) + 1;
        });
      });
    });
    return Object.keys(map).map(function (alias) {
      var one = map[alias];
      return { alias: alias, total: one.total, tiers: one.tiers };
    }).sort(function (a, b) { return b.total - a.total; });
  }

  /* 「稱號歸屬存疑」的處數：詞典裏的 guessCount 是全部書合計，
     單書檢索時必須按作用域重算，否則會顯示一本書裏並不存在的存疑數。 */
  function scopeGuess(person) {
    var n = 0;
    var bucket = mentionsByPerson[person.id] || {};
    Object.keys(bucket).forEach(function (cid) {
      if (!inScope(cid)) return;
      bucket[cid].forEach(function (s) {
        (s.marks || []).forEach(function (m) {
          if (m.pid === person.id && m.tier === GUESS_TIER) n += 1;
        });
      });
    });
    return n;
  }

  /* ---------------- 全篇閱讀 ---------------- */

  /* 段落級下標索引。
     索引裏只存「命中句」，正文是整段，所以必須把**句內下標**換算成**段內下標**：
     按 seq 順序在段落文本里 find 每句，遊標只前進不後退（句子本就連續）。
     換算失敗（理論上不會發生）就不標，寧缺勿錯。 */
  var paraIndex = {};

  function buildParaIndex(cid) {
    if (paraIndex[cid]) return paraIndex[cid];
    var res = { marks: {}, pmarks: {}, hitAll: [] };
    var doc = (window.BOOK_CORPUS || {})[cid];
    if (!doc) { paraIndex[cid] = res; return res; }
    res.notes = doc.notes || [];
    // notes 与 paragraphs 平行；句层定位只查正文 paragraphs

    var byPara = {};
    (sentByChapter[cid] || []).forEach(function (s) {
      (byPara[s.paraSeq] = byPara[s.paraSeq] || []).push(s);
    });

    Object.keys(byPara).forEach(function (key) {
      var pno = parseInt(key, 10);
      var text = (doc.paragraphs || [])[pno - 1];
      if (typeof text !== "string") return;
      var recs = byPara[key].slice().sort(function (a, b) { return a.seq - b.seq; });
      var offs = [], cursor = 0, ok = true;
      recs.forEach(function (s) {
        // 段落文本按 \u3000 斷開時 indexOf 仍可定位，因為句子是原文連續子串
        var i = text.indexOf(s.text, cursor);
        if (i < 0) { ok = false; return; }
        offs.push(i);
        cursor = i + s.text.length;
      });
      if (!ok) return;
      var pm = [], om = [];
      recs.forEach(function (s, i) {
        (s.marks || []).forEach(function (m) {
          om.push({ s: offs[i] + m.s, e: offs[i] + m.e,
                    pid: m.pid, tier: m.tier, alias: m.alias });
        });
        (s.pmarks || []).forEach(function (m) {
          pm.push({ s: offs[i] + m.s, e: offs[i] + m.e,
                    pid: m.pid, tier: m.tier, alias: m.alias });
        });
      });
      om.sort(function (a, b) { return a.s - b.s; });
      pm.sort(function (a, b) { return a.s - b.s; });
      res.marks[pno] = om;
      res.pmarks[pno] = pm;
      res.hitAll.push(pno);
    });
    res.hitAll.sort(function (a, b) { return a - b; });
    paraIndex[cid] = res;
    return res;
  }

  var reader = document.getElementById("reader");
  var readerBody = document.getElementById("readerBody");
  var readerHead = document.getElementById("readerHead");
  var readerTitle = document.getElementById("readerTitle");
  var readerTools = document.getElementById("readerTools");

  var corpusLoading = false;
  var corpusQueue = [];
  var RENDER_CHUNK = 200;          // 一次渲染多少段：太大卡，太小點得手痠
  var readerState = null;

  function ensureCorpus(cb) {
    if (window.BOOK_CORPUS) { cb(); return; }
    corpusQueue.push(cb);
    if (corpusLoading) return;
    corpusLoading = true;
    var s = document.createElement("script");
    s.src = "corpus-data.js";
    s.onload = function () {
      corpusLoading = false;
      var q = corpusQueue.slice();
      corpusQueue.length = 0;
      q.forEach(function (fn) { fn(); });
    };
    s.onerror = function () {
      corpusLoading = false;
      corpusQueue.length = 0;
      readerBody.innerHTML = '<div class="empty">全篇正文未加載（缺少 corpus-data.js）。</div>';
    };
    document.body.appendChild(s);
  }

  function paraNums() {
    var st = readerState;
    if (st.hitOnly && st.hitParas.length) return st.hitParas;
    var all = [];
    for (var i = 1; i <= st.paragraphs.length; i++) all.push(i);
    return all;
  }

  /* 渲染下一批段落。渲染完成後 moreNode 可能已被移除（全文已顯示完），
     所以調用方一律不能假設它還在——早期版本正是在這裏空指針，導致讀全篇打不開。 */
  function renderMore() {
    var st = readerState;
    if (!st || !st.moreNode) return;
    var nums = st.nums;
    var end = Math.min(st.next + RENDER_CHUNK, nums.length);
    var src = st.kind === "place" ? st.pmarks : st.marks;
    var html = "";
    for (var i = st.next; i < end; i++) {
      var pno = nums[i];
      var spans = st.pid ? (src[pno] || []).filter(function (m) {
        return m.pid === st.pid;
      }) : [];
      var ptext = st.paragraphs[pno - 1] || "";
      var ntext = (st.notes && st.notes[pno - 1]) || "";
      /* 整段脚注（段首 [一]…）：段落级 .fn，字号颜色与正文区分 */
      var fnPara = /^\[[一二三四五六七八九十百]+\]/.test(ptext) ? ' class="fn"' : "";
      if (ptext) {
        html += '<p data-para="' + pno + '"' + fnPara + ">" +
                renderWithSpans(ptext, spans, st.kind) + "</p>";
      }
      /* 校勘/版本对照/夹注：平行 note，小字蓝色，不进统计 */
      if (ntext) {
        html += '<p class="coll-note" data-para="' + pno + '">' +
                esc(ntext) + "</p>";
      }
    }
    st.moreNode.insertAdjacentHTML("beforebegin", html);
    st.next = end;

    if (end >= nums.length) {
      st.moreNode.remove();
      st.moreNode = null;
    } else {
      st.moreNode.textContent = "繼續顯示餘下 " + count(nums.length - end) +
        " 段（已顯示 " + count(end) + " / " + count(nums.length) + "）▾";
    }
  }

  function renderReaderHead() {
    var st = readerState;
    var metaC = chapterMap[st.chapterId];
    var base = [metaC.category, count(metaC.charCount) + " 字",
                count(metaC.sentenceCount) + " 句", count(st.paragraphs.length) + " 段"];
    var who = st.pid ? (st.kind === "place" ? placeMap[st.pid] : personMap[st.pid]) : null;
    var html = '<div class="title">' + esc(metaC.fullTitle) +
               "<small>" + base.join(" · ") + "</small>";
    if (who) {
      html += '<small class="legend">黃底＝' + esc(who.name) +
              (st.kind === "place" ? "；虛線下劃線＝單字國名（可能有誤）"
                                   : "；虛線下劃線＝稱號歸屬存疑") + "</small>";
    }
    html += "</div>";

    var tools = "";
    if (who && st.hitParas.length) {
      tools += '<button data-act="filter" class="' + (st.hitOnly ? "on" : "") +
        '">' + (st.hitOnly
          ? "只看與" + esc(who.name) + "有關的段落（" + count(st.hitParas.length) + "）"
          : "只看與" + esc(who.name) + "有關的段落") + "</button>";
    }
    if (st.nums.length > RENDER_CHUNK) {
      tools += '<button data-act="all">一次顯示全部</button>';
    }
    tools += '<button data-act="close">關閉</button>';
    readerTools.innerHTML = tools;
    readerTitle.innerHTML = html;
  }

  function renderReader(resetScroll) {
    readerBody.innerHTML = '<div class="more" id="readerMore"></div>';
    readerState.moreNode = document.getElementById("readerMore");
    readerState.next = 0;
    renderReaderHead();
    renderMore();
    if (resetScroll) readerBody.scrollTop = 0;
  }

  /* 定位到某段：先把段落渲染出來（列表被過濾時自動切回全文），再滾動過去 */
  function jumpToParagraph(pno) {
    var st = readerState;
    if (st.nums.indexOf(pno) < 0 && st.hitOnly) {
      st.hitOnly = false;
      st.nums = paraNums();
      renderReader(false);
    }
    var pos = st.nums.indexOf(pno);
    if (pos < 0) return;
    while (st.next <= pos && st.moreNode) renderMore();
    var node = readerBody.querySelector('p[data-para="' + pno + '"]');
    if (!node) return;
    readerBody.scrollTop += node.getBoundingClientRect().top -
                            readerBody.getBoundingClientRect().top -
                            readerBody.clientHeight * 0.3;
    node.classList.add("target");
  }

  function openChapter(chapterId, targetSentenceId) {
    var metaC = chapterMap[chapterId];
    if (!metaC) return;
    ensureCorpus(function () {
      var doc = (window.BOOK_CORPUS || {})[chapterId];
      reader.classList.add("on");           // 先顯示，否則滾動定位算不出位置
      if (!doc) {
        readerTitle.innerHTML = esc(metaC.fullTitle);
        readerTools.innerHTML = '<button data-act="close">關閉</button>';
        readerBody.innerHTML = '<div class="empty">本篇正文缺失。</div>';
        return;
      }
      var paragraphs = doc.paragraphs || [];
      var kind = readerTarget.kind;
      var pid = readerTarget.id;
      var idx = buildParaIndex(chapterId);
      var src = kind === "place" ? idx.pmarks : idx.marks;
      var hitParas = pid ? idx.hitAll.filter(function (p) {
        return (src[p] || []).some(function (m) { return m.pid === pid; });
      }) : [];

      readerState = {
        chapterId: chapterId,
        kind: kind,
        paragraphs: paragraphs,
        notes: doc.notes || [],
        marks: idx.marks,
        pmarks: idx.pmarks,
        pid: pid,
        hitParas: hitParas,
        // 默認給全文——「讀全篇」就該是全文；只看命中段是可選動作
        hitOnly: false,
        nums: [],
        next: 0,
        moreNode: null
      };
      readerState.nums = paraNums();
      renderReader(true);

      if (targetSentenceId) {
        var seg = String(targetSentenceId).split("-");
        var pno = parseInt(seg[2], 10);
        if (pno > 0) jumpToParagraph(pno);
      }
      writeHash();          // readerState 已就绪，此时写 hash 才带得上 ?c=
    });
  }

  /* 閱讀器內的點擊：關閉 / 只看命中段 / 一次顯示全部。用事件委託，
     免得每次重渲染都要重新綁定。 */
  readerBody.addEventListener("click", function (ev) {
    if (ev.target && ev.target.id === "readerMore") renderMore();
  });
  readerHead.addEventListener("click", function (ev) {
    var el = ev.target.closest ? ev.target.closest("[data-act]") : null;
    if (!el) return;
    var act = el.getAttribute("data-act");
    if (act === "close") {
      closeReader();
    } else if (act === "filter") {
      readerState.hitOnly = !readerState.hitOnly;
      readerState.nums = paraNums();
      renderReader(true);
    } else if (act === "all") {
      /* 命中段列表和全文段號不同，混着追加會串行，所以先整篇重排一次，
         再一直渲染到底。注意不能把 moreNode 刪掉——renderMore() 靠它插入，
         刪了它就沒地方插，表現是「點了沒反應、按鈕還消失了」。 */
      if (readerState.hitOnly) {
        readerState.hitOnly = false;
        readerState.nums = paraNums();
        renderReader(false);
      }
      while (readerState.moreNode) renderMore();
    }
  });
  reader.addEventListener("click", function (ev) {
    if (ev.target === reader) closeReader();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeReader();
  });

  /* ---------------- 命中句渲染 ---------------- */

  function renderSentences(list, shown, chapterId, kind, id) {
    return list.slice(0, shown).map(function (s) {
      return '<div class="sentence" data-sid="' + s.id + '" data-chapter="' + chapterId + '">' +
             highlightSent(s, id, kind) + "</div>";
    }).join("");
  }

  /* ---------------- 裴注（三國志裴松之注 · 明細） ---------------- */
  /* peiOf / peiActive / peiStatOf 已在書作用域節定義。 */

  function peiSection(pid) {
    if (!peiActive()) return "";
    var pei = peiOf(pid);
    if (!pei || !pei.n) return "";
    var html = '<div class="group-title">三國志裴松之注明細 <span class="count">' +
               count(pei.n) + " 處 / " + count(pei.chapters) +
               " 篇 · 已計入上方合計【裴N】</span></div>";

    var byCh = pei.byChapter || {};
    var cids = Object.keys(byCh).sort(function (a, b) { return byCh[b] - byCh[a]; });
    if (cids.length) {
      html += '<div class="card">';
      cids.slice(0, 12).forEach(function (id) {
        var c = chapterMap[id];
        if (!c) return;
        html += '<div class="mention-head">' +
                '<span class="name">' + esc(c.fullTitle) + "</span>" +
                '<span class="meta">' + count(byCh[id]) + " 處 · " +
                '<b class="open-full" data-chapter="' + id + '">讀全篇 ›</b></span>' +
                "</div>";
      });
      if (cids.length > 12) {
        html += '<div class="note-more">另有 ' + count(cids.length - 12) + " 篇…</div>";
      }
      html += "</div>";
    }

    var items = pei.items || [];
    if (items.length) {
      html += '<div class="card">';
      items.slice(0, 8).forEach(function (it) {
        html += '<div class="pei-line" data-chapter="' + esc(it.cid) + '"' +
                (it.pseq ? ' data-pseq="' + it.pseq + '"' : "") +
                ' title="' + esc(it.alias || "") + '">' +
                esc(it.text) + "</div>";
      });
      html += '<div class="alias-note">摘自三國志裴松之注（〈…〉），樣例最多顯示 8 條；' +
              "完整計數見上方，全文可在讀全篇中以灰藍小字辨認。</div>";
      html += "</div>";
    }
    return html;
  }

  /* ---------------- 人物頁 ---------------- */

  /* 完整稱謂表：一個人所有稱謂，按類別分組，標註本批出現次數 */
  function aliasTable(person) {
    var groups = {};
    (person.aliasList || []).forEach(function (a) {
      (groups[a.kind] = groups[a.kind] || []).push(a);
    });
    if (!person.aliasList || !person.aliasList.length) {
      return '<div class="alias-line">原文中寫作：' +
             (person.aliases || []).map(function (a) { return esc(a); }).join("、") + "</div>";
    }
    var html = '<div class="alias-groups">';
    KIND_ORDER.forEach(function (kind) {
      var list = groups[kind];
      if (!list || !list.length) return;
      html += '<div class="alias-group"><span class="kind" title="' +
              esc(KIND_HINT[kind]) + '">' + KIND_LABEL[kind] + "</span><span class=\"chips\">";
      list.forEach(function (a) {
        var an = scopeAliasN(a);
        var others = (a.variants || []).filter(function (v) { return v !== a.w; });
        var tip = a.w + (others.length ? "（亦作 " + others.join("、") + "）" : "") +
                  "\n" + KIND_HINT[kind] + "\n在選中的書中出現 " + an + " 次";
        html += '<span class="chip' + (an ? "" : " off") +
                (kind === "generic" ? " gen" : "") + '" title="' + esc(tip) + '">' +
                esc(a.w) + "<em>" + (an ? "×" + count(an) : "未用") + "</em></span>";
      });
      html += "</span></div>";
    });
    html += "</div>";
    if (groups.generic && groups.generic.length) {
      html += '<div class="alias-note">泛稱稱號（' +
              groups.generic.map(function (a) { return esc(a.w); }).join("、") +
              "）不固定屬於誰，每處都按所在篇目的上下文判定歸屬，見下方「泛稱稱號歸屬依據」。</div>";
    }
    return html;
  }

  function renderPerson(person) {
    readerTarget = { kind: "person", id: person.id };
    writeHash();                  // currentPerson 由调用方先设好，此处回写路由
    var pid = person.id;
    var primaryIds = (mainByPerson[pid] || []).filter(inScope);
    var mentionMap = mentionsByPerson[pid] || {};
    var mentionIds = Object.keys(mentionMap).filter(function (id) {
      return primaryIds.indexOf(id) < 0 && inScope(id);
    });
    mentionIds.sort(function (a, b) { return mentionMap[b].length - mentionMap[a].length; });

    /* 「處」＝標記數（一句話提到兩次算兩處），與索引頁的 mentionCount 同口徑；
       「句」＝去重後實際能展開的句子數。兩個數都對，誰也不冒充誰。 */
    var total = 0, totalSents = 0;
    mentionIds.forEach(function (id) {
      total += markCountAll(mentionMap[id], pid, "person");
      totalSents += mentionMap[id].length;
    });

    var aliases = person.aliasList || [];
    var aliasHit = aliases.filter(function (a) { return scopeAliasN(a) > 0; }).length;
    var guess = scopeGuess(person);
    var ps = peiStatOf(person);
    var totalAll = total + ps.n;
    var peiBadge = ps.n > 0 ? "【裴" + count(ps.n) + "】" : "";

    var html = "";
    html += '<div class="group-title">' + esc(person.name) +
            ' <span class="count">' + esc(person.dynasty || "") +
            (person.title ? " · " + esc(person.title) : "") + "</span></div>";
    html += '<div class="card">';
    if (person.summary) {
      html += '<div class="summary">' + esc(person.summary) + "</div>";
    }
    html += '<div class="stats">' +
            "<div>整篇講述 <b>" + primaryIds.length + "</b> 篇</div>" +
            "<div>其他篇目提及 <b>" + mentionIds.length + "</b> 篇 / <b>" +
            count(totalAll) + "</b> 處" + peiBadge +
            "（正文 <b>" + count(total) + "</b> 處" +
            (total === totalSents ? "" : " / <b>" + count(totalSents) + "</b> 句") +
            (ps.n ? " + 裴松之注 <b>" + count(ps.n) + "</b> 處" : "") + "）</div>" +
            "<div>稱謂 <b>" + aliases.length + "</b> 條（本批出現 <b>" +
            aliasHit + "</b> 條）</div>" +
            (guess ? "<div>稱號歸屬存疑 <b>" + count(guess) + "</b> 處</div>" : "") +
            "</div>";

    html += '<div class="alias-title">全部稱謂<span class="hint">' +
            "原文寫法 + 出現次數；「未用」＝詞典已收錄、當前選中的書未用此寫法" +
            "（如《史記》只寫高祖／沛公／漢王，「劉邦」這個現代通行名反而未見）</span></div>";
    html += aliasTable(person);

    /* 泛稱稱號的歸屬依據：說明每個稱號是按什麼算到他頭上的 */
    var titles = titlesOf(person);
    if (titles.length) {
      html += '<div class="titles"><div class="titles-head">泛稱稱號歸屬依據</div>';
      titles.forEach(function (t) {
        var parts = Object.keys(t.tiers)
          .sort(function (a, b) { return t.tiers[b] - t.tiers[a]; })
          .map(function (k) {
            return '<span class="tier' + (k === GUESS_TIER ? " warn" : "") + '">' +
                   TIER_LABEL[k] + " " + count(t.tiers[k]) + "</span>";
          }).join("");
        html += '<div class="title-row"><span class="w">' + esc(t.alias) + "</span>" +
                '<span class="n">共 ' + count(t.total) + " 處</span>" + parts + "</div>";
      });
      html += "</div>";
    }
    html += "</div>";

    html += '<div class="group-title">整篇講述 <span class="count">' +
            primaryIds.length + " 篇 · 點擊讀全篇</span></div>";
    if (!primaryIds.length) {
      html += '<div class="card muted-card">暫無專篇（該人物在本批篇目中未作為主人公）</div>';
    } else {
      html += '<div class="card">';
      primaryIds.forEach(function (id) {
        var c = chapterMap[id];
        html += '<div class="primary-row" data-chapter="' + id + '">' +
                '<span class="name">' + esc(c.fullTitle) +
                '<span class="alias">' + esc(c.category) + "</span></span>" +
                '<span class="meta">' + count(c.charCount) + " 字 · " +
                count(c.sentenceCount) + " 句 · 讀全篇 ›</span>" +
                "</div>";
      });
      html += "</div>";
    }

    html += '<div class="group-title">其他篇目提及 <span class="count">' +
            mentionIds.length + " 篇 / " + count(totalAll) + " 處" + peiBadge + "</span></div>";
    if (!mentionIds.length) {
      html += '<div class="card muted-card">本批篇目中未見提及</div>';
    } else {
      mentionIds.forEach(function (id) {
        var c = chapterMap[id];
        var list = mentionMap[id];
        html += '<div class="card" data-chapter="' + id + '">' +
                '<div class="mention-head">' +
                '<span class="name">' + esc(c.fullTitle) + "</span>" +
                '<span class="meta">' + hitMeta(list, pid, "person") + ' · 點擊展開　' +
                '<b class="open-full" data-chapter="' + id + '">讀全篇 ›</b></span>' +
                "</div>" +
                '<div class="body">' + renderSentences(list, 3, id, "person", pid) + "</div>" +
                (list.length > 3
                  ? '<div class="more" data-total="' + list.length + '">顯示全部 ' +
                    count(list.length) + " 句 ▾</div>"
                  : "") +
                "</div>";
      });
    }

    /* 三國志裴松之注明細（合計已含於上方【裴N】） */
    html += peiSection(pid);

    out.innerHTML = html;
    bindCards("person", pid, mentionMap);
  }

  /* ---------------- 地名頁 ---------------- */

  function placeAliasTable(place) {
    var rows = place.aliasList || [];
    if (!rows.length) {
      return '<div class="alias-line">原文中寫作：' +
             (place.aliases || []).map(esc).join("、") + "</div>";
    }
    var html = '<div class="alias-groups"><div class="alias-group">' +
      '<span class="kind" title="地名的各種寫法；「未用」＝詞典收錄但當前選中的書未用此寫法">寫法</span>' +
      "<span class=\"chips\">";
    rows.forEach(function (a) {
      var an = scopeAliasN(a);
      var others = (a.variants || []).filter(function (v) { return v !== a.w; });
      var tip = a.w + (others.length ? "（亦作 " + others.join("、") + "）" : "") +
                "\n在選中的書中出現 " + an + " 次";
      html += '<span class="chip' + (an ? "" : " off") +
              (a.isName ? " gen" : "") + '" title="' + esc(tip) + '">' +
              esc(a.w) + "<em>" + (an ? "×" + count(an) : "未用") + "</em></span>";
    });
    html += "</span></div></div>";
    if (place.isChar) {
      html += '<div class="alias-note">這是<b>單字地名</b>，與姓氏、動詞同形' +
              "（如「陳」既指陳國，也可能是「陳師牧野」的陳列、「陳平」的姓氏）。" +
              "命中的每一處都經過「人名佔用排除 + 鄰字排除」兩道關卡，" +
              "正文裏以虛線下劃線標出，可能仍有誤收。</div>";
    }
    return html;
  }

  function renderPlace(place) {
    readerTarget = { kind: "place", id: place.id };
    writeHash();                  // 同上
    var pid = place.id;
    var mainList = (place.mainChapters || []).filter(function (r) { return inScope(r.cid); });
    var mainIds = mainList.map(function (r) { return r.cid; });
    var mentionMap = mentionsByPlace[pid] || {};
    var mentionIds = Object.keys(mentionMap).filter(function (id) {
      return mainIds.indexOf(id) < 0 && inScope(id);
    });
    mentionIds.sort(function (a, b) { return mentionMap[b].length - mentionMap[a].length; });
    /* 同人物頁：「處」＝標記數，「句」＝去重後可展開的句子數。
       地名層尤其常見一句話提同一地多次（「殷…殷」），不去重就會重複排。 */
    var total = 0, totalSents = 0;
    mentionIds.forEach(function (id) {
      total += markCountAll(mentionMap[id], pid, "place");
      totalSents += mentionMap[id].length;
    });

    var byTitle = mainList.filter(function (r) { return r.byTitle; }).length;
    var aliases = place.aliasList || [];
    var aliasHit = aliases.filter(function (a) { return scopeAliasN(a) > 0; }).length;

    var html = "";
    html += '<div class="group-title">' + esc(place.name) +
            ' <span class="count">' + esc(place.kindLabel || place.kind) +
            (place.era ? " · " + esc(place.era) : "") + "</span></div>";
    html += '<div class="card">';
    if (place.summary) {
      html += '<div class="summary">' + esc(place.summary) + "</div>";
    }
    html += '<div class="stats">' +
            "<div>整篇講述 <b>" + mainList.length + "</b> 篇（篇名含地名 <b>" +
            byTitle + "</b> 篇）</div>" +
            "<div>其他篇目提及 <b>" + mentionIds.length + "</b> 篇 / <b>" +
            count(total) + "</b> 處" +
            (total === totalSents ? ""
              : "（<b>" + count(totalSents) + "</b> 句）") + "</div>" +
            "<div>寫法 <b>" + aliases.length + "</b> 條（本批出現 <b>" +
            aliasHit + "</b> 條）</div>" +
            "</div>";

    html += '<div class="alias-title">全部寫法<span class="hint">' +
            "原文寫法 + 出現次數；同地的異寫（洛陽／雒陽）已併為一條</span></div>";
    html += placeAliasTable(place);
    html += "</div>";

    html += '<div class="group-title">整篇講述 <span class="count">' +
            mainList.length + " 篇 · 點擊讀全篇</span></div>";
    if (!mainList.length) {
      html += '<div class="card muted-card">沒有以該地為主體的專篇（篇名不含此地名，' +
              "篇內出現也較零散）</div>";
    } else {
      html += '<div class="card">';
      mainList.forEach(function (r) {
        var c = chapterMap[r.cid];
        html += '<div class="primary-row" data-chapter="' + r.cid + '">' +
                '<span class="name">' + esc(c.fullTitle) +
                '<span class="alias">' + esc(c.category) + "</span>" +
                (r.byTitle ? '<span class="alias">篇名含地名</span>' : "") + "</span>" +
                '<span class="meta">本篇 " ' + esc(place.name) + " " +
                count(r.n) + " 處 · " + count(c.sentenceCount) + " 句 · 讀全篇 ›</span>" +
                "</div>";
      });
      html += "</div>";
    }

    html += '<div class="group-title">其他篇目提及 <span class="count">' +
            mentionIds.length + " 篇 / " + count(total) + " 處</span></div>";
    if (!mentionIds.length) {
      html += '<div class="card muted-card">其他篇目中未見提及</div>';
    } else {
      mentionIds.forEach(function (id) {
        var c = chapterMap[id];
        var list = mentionMap[id];
        html += '<div class="card" data-chapter="' + id + '">' +
                '<div class="mention-head">' +
                '<span class="name">' + esc(c.fullTitle) + "</span>" +
                '<span class="meta">' + hitMeta(list, pid, "place") + ' · 點擊展開　' +
                '<b class="open-full" data-chapter="' + id + '">讀全篇 ›</b></span>' +
                "</div>" +
                '<div class="body">' + renderSentences(list, 3, id, "place", pid) + "</div>" +
                (list.length > 3
                  ? '<div class="more" data-total="' + list.length + '">顯示全部 ' +
                    count(list.length) + " 句 ▾</div>"
                  : "") +
                "</div>";
      });
    }

    out.innerHTML = html;
    bindCards("place", pid, mentionMap);
  }

  /* 兩類實體的卡片交互完全一樣，只有取數據的索引不同 */
  function bindCards(kind, id, mentionMap) {
    out.querySelectorAll(".primary-row").forEach(function (row) {
      row.addEventListener("click", function () {
        openChapter(row.getAttribute("data-chapter"));
      });
    });
    out.querySelectorAll(".open-full").forEach(function (el) {
      el.addEventListener("click", function (ev) {
        ev.stopPropagation();
        openChapter(el.getAttribute("data-chapter"));
      });
    });
    var expand = function (card) {
      if (!card) return;
      var cid = card.getAttribute("data-chapter");
      var list = mentionMap[cid];
      var body = card.querySelector(".body");
      /* 裴注卡片 / 无数据的 .more 不走正文展开 */
      if (!list || !body) return;
      body.innerHTML = renderSentences(list, list.length, cid, kind, id);
      var more = card.querySelector(".more");
      if (more) more.remove();
    };
    out.querySelectorAll(".mention-head").forEach(function (head) {
      if (!head.parentElement || !head.parentElement.classList.contains("card")) return;
      if (!head.parentElement.querySelector(".body")) return;  // 裴注分篇行无 .body
      head.addEventListener("click", function () { expand(head.parentElement); });
    });
    out.querySelectorAll(".more").forEach(function (el) {
      var parent = el.parentElement;
      if (!parent || !parent.querySelector(".body") || !parent.getAttribute("data-chapter")) {
        return;  // 裴注「另有 N 篇…」等静态 more
      }
      el.addEventListener("click", function (ev) {
        ev.stopPropagation();
        expand(parent);
      });
    });
    out.querySelectorAll(".sentence").forEach(function (node) {
      node.addEventListener("click", function (ev) {
        ev.stopPropagation();
        openChapter(node.getAttribute("data-chapter"), node.getAttribute("data-sid"));
      });
    });
    /* 裴注样例：整段摘录，点开对应篇（优先定位段） */
    out.querySelectorAll(".pei-line").forEach(function (node) {
      node.addEventListener("click", function (ev) {
        ev.stopPropagation();
        openChapter(node.getAttribute("data-chapter"));
      });
    });
  }

  /* ---------------- 候選選擇 ---------------- */

  /* 一個詞可能既像人名又像地名，也可能對應多個實體：
     「梁王」既是彭越也是劉武，「梁」既是國名也在人名裏。 */
  function renderChooser(query, people, lands, partial) {
    var n = people.length + lands.length;
    var html = '<div class="group-title">「' + esc(query) + '」<span class="count">' +
               (partial ? "包含該詞的名稱對應 " : "該名稱對應 ") + n +
               " 個實體，請選擇</span></div>";
    html += '<div class="card"><div class="candidate-list">';
    people.forEach(function (p) {
      var primary = (mainByPerson[p.id] || []).filter(inScope).length;
      var shared = (p.aliasList || []).filter(function (a) {
        return scopeAliasN(a) > 0 && (a.w === query || (a.variants || []).indexOf(query) >= 0);
      }).map(function (a) { return a.w; }).join("、");
      var st = scopeStat(p);
      html += '<div class="candidate" data-kind="person" data-id="' + p.id + '">' +
              '<span class="name">' + esc(p.name) +
              '<span class="alias">人物 · ' + esc(p.dynasty || "") +
              (shared ? " · 此處寫作「" + esc(shared) + "」" : "") + "</span></span>" +
              '<span class="meta">' + primary + " 篇專述 · 共 " +
              statText(st, true) + " ›</span>" +
              "</div>";
    });
    lands.forEach(function (p) {
      var st = scopeStat(p);
      var pn = (p.mainChapters || []).filter(function (r) { return inScope(r.cid); }).length;
      html += '<div class="candidate" data-kind="place" data-id="' + p.id + '">' +
              '<span class="name">' + esc(p.name) +
              '<span class="alias">地名 · ' + esc(p.kindLabel || p.kind) +
              (p.era ? " · " + esc(p.era) : "") + "</span></span>" +
              '<span class="meta">' + pn + " 篇專述 · 共 " +
              statText(st, true) + " ›</span>" +
              "</div>";
    });
    html += "</div></div>";
    out.innerHTML = html;
    out.querySelectorAll(".candidate").forEach(function (el) {
      el.addEventListener("click", function () {
        var kind = el.getAttribute("data-kind");
        var id = el.getAttribute("data-id");
        if (kind === "place") {
          currentPlace = placeMap[id];
          currentPerson = null;
          renderPlace(currentPlace);
        } else {
          currentPerson = personMap[id];
          currentPlace = null;
          renderPerson(currentPerson);
        }
      });
    });
  }

  /* ---------------- 人物索引 / 地名索引 / 篇目一覽 ---------------- */

  function indexGrid(list, aliasKey) {
    var shown = list.filter(function (p) { return scopeStat(p).nAll > 0; }).sort(byScopeCount);
    var html = '<div class="card"><div class="grid">';
    shown.forEach(function (p) {
      var aliases = (p.aliasList || []).filter(function (a) { return scopeAliasN(a) > 0; })
        .map(function (a) { return a.w; });
      var st = scopeStat(p);
      var tip = aliases.length ? aliasKey + "：" + aliases.join("、")
                               : "原文未見" + aliasKey;
      var bd = bookBreakdown(p);
      if (bd) tip += "\n" + bd;
      html += '<div class="item" data-name="' + esc(p.name) + '" title="' + esc(tip) + '">' +
              '<span class="n">' + esc(p.name) + "</span>" +
              '<span class="c">' + statText(st) +
              "</span></div>";
    });
    html += "</div></div>";
    return html;
  }

  function bindIndexItems() {
    out.querySelectorAll(".item").forEach(function (el) {
      el.addEventListener("click", function () {
        switchTab("search");
        document.getElementById("q").value = el.getAttribute("data-name");
        search(el.getAttribute("data-name"));
      });
    });
  }

  function renderIndex(list, zeroText, groupTitle, aliasKey) {
    var shown = list.filter(function (p) { return scopeStat(p).nAll > 0; }).sort(byScopeCount);
    var sortLabel = sortMode === "c" ? "按提及篇數排序" : "按提及次數排序";
    var html = '<div class="group-title">' + groupTitle + " <span class=\"count\">" +
      count(shown.length) + ' 個 · <span class="sort-toggle" role="button" tabindex="0">' +
      sortLabel + '</span> · 懸停看全部' + aliasKey + "</span></div>";
    html += indexGrid(shown, aliasKey);
    if (zeroText) html += '<div class="note">' + zeroText + "</div>";
    out.innerHTML = html;
    bindIndexItems();
    var tog = out.querySelector(".sort-toggle");
    if (tog) {
      tog.addEventListener("click", function () {
        sortMode = sortMode === "c" ? "n" : "c";
        if (currentTab === "places") renderPlacesIndex();
        else renderPersonsIndex();
      });
    }
  }

  /* 断代史：本书记载时代 vs 相对本书的古人（相邻书有意重叠，见 BOOK_ERA） */
  function bookEraRange() {
    if (isMulti() && scope.length !== 1) return null;
    var code = scope[0];
    for (var i = 0; i < BOOKS.length; i++) {
      if (BOOKS[i].code === code) return BOOKS[i].eraRange || null;
    }
    return null;
  }

  function inBookEra(p) {
    var range = bookEraRange();
    if (!range) return true;
    var code = scope[0];
    // 本书篇主必然属本纪时代（朝代字段偶有偏差时以此为准）
    if ((mainByPerson[p.id] || []).some(function (cid) {
      return cid.indexOf(code + "-") === 0;
    })) return true;
    var r = p.eraRank;
    if (r == null) return false;
    return r >= range[0] && r <= range[1];
  }

  function renderPersonsIndex() {
    /* 每本書有自己的條目列表：不在當前書作用域內的實體不列出 */
    var list = persons.filter(function (p) { return scopeStat(p).nAll > 0; });
    var zero = persons.length - list.length;
    var zeroText = zero > 0
      ? "另有 " + zero + " 個人物在當前選中的書中未出現（詞典已收錄）。"
      : "";
    if (!bookEraRange()) {
      renderIndex(list, zeroText, "人物索引", "稱謂");
      return;
    }
    // 单选断代史：拆两组，各自排序
    var here = list.filter(inBookEra);
    var past = list.filter(function (p) { return !inBookEra(p); });
    var sortLabel = sortMode === "c" ? "按提及篇數排序" : "按提及次數排序";
    var html = "";
    html += '<div class="group-title">本书记载时代 <span class="count">' +
            here.length + ' 人 · <span class="sort-toggle" role="button" tabindex="0">' +
            sortLabel + "</span></span></div>";
    html += indexGrid(here, "稱謂");
    html += '<div class="group-title">相对于本书的古人 <span class="count">' +
            past.length + " 人 · 被引用/追述</span></div>";
    html += indexGrid(past, "稱謂");
    if (zeroText) html += '<div class="note">' + zeroText + "</div>";
    out.innerHTML = html;
    bindIndexItems();
    var tog = out.querySelector(".sort-toggle");
    if (tog) {
      tog.addEventListener("click", function () {
        sortMode = sortMode === "c" ? "n" : "c";
        renderPersonsIndex();
      });
    }
  }

  function renderPlacesIndex() {
    var overall = places.filter(function (p) { return scopeStat(p).n > 0; });
    var groups = {};
    overall.forEach(function (p) { (groups[p.kind] = groups[p.kind] || []).push(p); });
    Object.keys(groups).forEach(function (k) { groups[k].sort(byScopeCount); });
    var html = "";
    PLACE_KIND_ORDER.forEach(function (k) {
      var one = groups[k];
      if (!one || !one.length) return;
      html += '<div class="group-title">' + esc((one[0].kindLabel) || k) +
              ' <span class="count">' + one.length + " 個</span></div>";
      html += '<div class="card"><div class="grid">';
      one.forEach(function (p) {
        var st = scopeStat(p);
        var bd = bookBreakdown(p);
        html += '<div class="item' + (p.isChar ? " char-place" : "") +
                '" data-name="' + esc(p.name) + '" title="' +
                esc(p.summary || "") + (bd ? "\n" + bd : "") + '">' +
                '<span class="n">' + esc(p.name) + "</span>" +
                '<span class="c">' + statText(st) + "</span></div>";
      });
      html += "</div></div>";
    });
    var zero = places.length - overall.length;
    if (zero > 0) {
      html += '<div class="note">另有 ' + zero +
        " 個地名在當前選中的書中未出現（詞典已收錄）。</div>";
    }
    out.innerHTML = html;
    out.querySelectorAll(".item").forEach(function (el) {
      el.addEventListener("click", function () {
        switchTab("search");
        document.getElementById("q").value = el.getAttribute("data-name");
        search(el.getAttribute("data-name"));
      });
    });
  }

  function chapterBlock(list) {
    var groups = {};
    list.forEach(function (c) {
      (groups[c.category] = groups[c.category] || []).push(c);
    });
    var order = ["本紀", "世家", "列傳", "表", "書", "載記", "其他"];
    var html = "";
    order.forEach(function (cat) {
      var one = groups[cat];
      if (!one || !one.length) return;
      html += '<div class="group-title">' + cat + ' <span class="count">' +
              one.length + " 篇</span></div>";
      html += '<div class="card">';
      one.forEach(function (c) {
        var owners = (c.mainPersons || []).map(function (pid) {
          return personMap[pid] ? personMap[pid].name : "";
        }).filter(Boolean).join("、");
        var tops = (c.topPlaces || []).map(function (r) {
          return placeMap[r.pid] ? placeMap[r.pid].name : "";
        }).filter(Boolean).join("、");
        html += '<div class="chap-row" data-chapter="' + c.id + '">' +
                '<span class="t">' + esc(c.fullTitle) +
                '<span class="tag">' + esc(c.category) + "</span>" +
                (owners ? '<span class="tag">' + esc(owners) + "</span>" : "") +
                (tops ? '<span class="tag">地：' + esc(tops) + "</span>" : "") +
                "</span>" +
                '<span class="m">' + count(c.charCount) + " 字 · " +
                count(c.sentenceCount) + " 句 · 讀全篇 ›</span>" +
                "</div>";
      });
      html += "</div>";
    });
    return html;
  }

  function renderChapterIndex() {
    var list = chapters.filter(function (c) { return inScope(c.id); });
    var html = "";
    /* 多書合檢時先分書、再分體例——每本書的篇目列表各自獨立 */
    if (isMulti() && scope.length > 1) {
      BOOKS.forEach(function (b) {
        if (scope.indexOf(b.code) < 0) return;
        var one = list.filter(function (c) { return c.bookId === b.code; });
        if (!one.length) return;
        html += '<div class="book-title">《' + esc(b.name) + '》<span class="count">' +
                one.length + " 篇 · " + count(b.charCount) + " 字</span></div>";
        html += chapterBlock(one);
      });
    } else {
      html += chapterBlock(list);
    }
    out.innerHTML = html;
    out.querySelectorAll(".chap-row").forEach(function (el) {
      el.addEventListener("click", function () {
        readerTarget = { kind: "person", id: null };
        openChapter(el.getAttribute("data-chapter"));
      });
    });
  }

  /* ---------------- 檢索 ---------------- */

  /* 異體字歸一：與語料層 pipeline/common.py 的 VARIANTS 同源（由 meta.variants 帶出）。
     語料是維基文庫《史記》正文，混用了大量異體形——「髙祖」寫作「髙」、
     河「內」寫作「内」、「荊軻」寫作「荆軻」——而詞典只收規範形。
     所以**用戶輸入**也得走同一次歸一，否則照正文寫法反而查不到。
     1:1 映射，只用於查詢，不改展示（正文照原樣顯示，見 pipeline/trad.py）。 */
  var VARIANT_MAP = meta.variants || {};
  /* 简→繁单字映射（由 annotate.py 的 build_simp2trad_map 带出）：输入简体
     「刘邦」→「劉邦」也能命中繁体正文。只作并列候选、不替换原串——一简对多繁
     （后/里/云…）s2t 会猜错，但原串 q 仍保留试，猜错形不会顶掉正确命中。 */
  var SIMP2TRAD_MAP = meta.simp2trad || {};

  function s2tQuery(text) {
    if (!text) return text;
    var out = "";
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      out += (SIMP2TRAD_MAP[ch] || ch);
    }
    return out;
  }

  function normQuery(text) {
    if (!text) return text;
    var out = "";
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      out += (VARIANT_MAP[ch] || ch);
    }
    return out;
  }

  function uniqEntities(list) {
    var seen = {}, out = [];
    list.forEach(function (p) {
      if (!p || seen[p.id]) return;
      seen[p.id] = 1;
      out.push(p);
    });
    return out;
  }

  function exactPersonMatches(query) {
    var q = (query || "").trim();
    if (!q) return [];
    return (exactIndex[q] || []).map(function (pid) { return personMap[pid]; });
  }

  function exactPlaceMatches(query) {
    var q = (query || "").trim();
    if (!q) return [];
    return (placeIndex[q] || []).map(function (pid) { return placeMap[pid]; });
  }

  function partialMatches(list, q) {
    return list.filter(function (p) {
      return p.name.indexOf(q) >= 0 ||
             (p._forms || []).some(function (a) { return a.indexOf(q) >= 0; });
    });
  }

  function search(query) {
    var q = (query || "").trim();
    var qn = normQuery(q);
    /* 候選按書作用域過濾：選《史記》時，只在漢書裏出現的人不進候選 */
    var keep = function (p) { return p && scopeStat(p).nAll > 0; };
    var people = exactPersonMatches(q).filter(keep);
    var lands = exactPlaceMatches(q).filter(keep);
    // 輸入是正文異體寫法（髙祖／内史／荆軻）時，歸一後再試一次；
    // 兩個寫法都命中的併為一組，避免同一實體在候選頁裏出現兩次。
    if (qn !== q) {
      people = uniqEntities(people.concat(exactPersonMatches(qn))).filter(keep);
      lands = uniqEntities(lands.concat(exactPlaceMatches(qn))).filter(keep);
    }
    // 簡體輸入（「刘邦」）→ s2t 成「劉邦」再試；原串與歸一串都已試過，純增量。
    var qs2t = s2tQuery(q);
    if (qs2t !== q && qs2t !== qn) {
      people = uniqEntities(people.concat(exactPersonMatches(qs2t))).filter(keep);
      lands = uniqEntities(lands.concat(exactPlaceMatches(qs2t))).filter(keep);
    }
    if (people.length + lands.length > 1) {
      currentPerson = null; currentPlace = null;
      renderChooser(q, people, lands, false);
      return;
    }
    if (!people.length && !lands.length) {
      people = uniqEntities(partialMatches(persons, q).concat(partialMatches(persons, qn))
        .concat(partialMatches(persons, qs2t))).filter(keep);
      lands = uniqEntities(partialMatches(places, q).concat(partialMatches(places, qn))
        .concat(partialMatches(places, qs2t))).filter(keep);
      if (people.length + lands.length > 1) {
        currentPerson = null; currentPlace = null;
        renderChooser(q, people.slice(0, 20), lands.slice(0, 20), true);
        return;
      }
    }
    if (lands.length) {
      currentPlace = lands[0]; currentPerson = null;
      renderPlace(lands[0]);
      return;
    }
    if (people.length) {
      currentPerson = people[0]; currentPlace = null;
      renderPerson(people[0]);
      return;
    }
    currentPerson = null; currentPlace = null;
    out.innerHTML = '<div class="empty">未收錄「' + esc(q) + "」" +
      (isMulti() && scope.length < BOOKS.length
        ? "（或該條目不在當前選中的書中，可改選其他書）" : "") +
      (!peiOn ? "（裴松之注已關閉，注文中提及不會計入）" : "") +
      "。<br>詞典共 " +
      count(persons.length) + " 個人物、" + count(places.length) + " 個地名，" +
      "可切換「人物索引」「地名索引」瀏覽，或換個稱謂/寫法試試" +
      "（如 項王、留侯、梁王、滎陽、鉅鹿、會稽）。</div>";
  }

  function switchTab(tab) {
    currentTab = tab;
    syncTabUI(tab);
    if (tab !== "search") writeHash();   // 檢索页的 hash 由具体 person/place 决定
    if (tab === "search") {
      if (currentPlace) renderPlace(currentPlace);
      else if (currentPerson) renderPerson(currentPerson);
      else renderPersonsIndex();
    } else if (tab === "persons") {
      renderPersonsIndex();
    } else if (tab === "places") {
      renderPlacesIndex();
    } else {
      renderChapterIndex();
    }
  }

  /* ================= 回退 / hash 路由 =================
     本地页可能以 file:// 打开，此时 history.pushState 抛 SecurityError，
     所以一律走 hash 路由：file:// 与 http 都能用，浏览器「后退」天然可用。

     路由格式：
       #/search              檢索页（人物索引列表）
       #/person/<pid>        人物详情
       #/place/<plid>        地名详情
       #/persons #/places #/chapters
       ?c=<chapterId>        叠加原文层（reader）；后退一步即关闭它

     渲染函数内部会调 writeHash() 回写；由 hash 触发的渲染期间用 suppressHash
     掐断回写，否则会形成「渲染 → 写 hash → hashchange → 渲染」的死循环。 */
  var suppressHash = false;
  var ROUTE_RE = /^#\/(search|persons|places|chapters|person|place)(?:\/([^?]+))?(?:\?(.*))?$/;

  function queryOf(q) {
    var out = {};
    (q || "").split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) out[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
    });
    return out;
  }

  function syncTabUI(tab) {
    document.querySelectorAll(".tabs span").forEach(function (el) {
      el.classList.toggle("on", el.getAttribute("data-tab") === tab);
    });
  }

  function routeHash() {
    var base;
    if (currentPerson) base = "#/person/" + currentPerson.id;
    else if (currentPlace) base = "#/place/" + currentPlace.id;
    else base = "#/" + (currentTab || "search");
    var cid = reader.classList.contains("on") && readerState ? readerState.chapterId : null;
    return base + (cid ? "?c=" + cid : "");
  }

  function syncBackBtn() {
    var btn = document.getElementById("back");
    if (!btn) return;
    var onReader = reader.classList.contains("on");
    // 有历史可退，或正停在详情/原文层，就把返回露出来
    btn.hidden = !(history.length > 1 || currentPerson || currentPlace || onReader);
    btn.textContent = onReader ? "← 關閉原文" : "← 返回";
    btn.title = onReader ? "關閉原文層（Esc）" : "回到上一層";
  }

  /* lastWritten：记住「刚由我们自己写进去」的那个 hash。
     hashchange 是异步派发的，自己写的那一次也会回头触发 applyHash；
     若不去重，界面会被**重渲染一遍**——在测试里表现为刚切到篇目一覽
     又被拉回人物页（实测【7】因此失败）。自己写的不重渲染，
     只有浏览器后退/前进或手改地址栏才真正重新渲染。 */
  var lastWritten = null;

  function writeHash() {
    if (suppressHash) return;
    var h = routeHash();
    if (location.hash === h) { syncBackBtn(); return; }
    lastWritten = h;              // 入历史栈 → 浏览器后退可用
    location.hash = h;
    syncBackBtn();
  }

  /* 统一的「关闭原文层」：三处入口（遮罩 / Esc / 关闭按钮）都走这里，
     否则关了浮层但 hash 里还留着 ?c=，后退会莫名其妙。 */
  function closeReader() {
    if (!reader.classList.contains("on")) return;
    reader.classList.remove("on");
    writeHash();                  // 清掉 ?c=
  }

  function applyHash() {
    var cur = location.hash || "";
    if (lastWritten && cur === lastWritten) {   // 自己刚写的，界面已是这个状态
      lastWritten = null;
      syncBackBtn();
      return;
    }
    lastWritten = null;
    var m = ROUTE_RE.exec(cur);
    var type = m ? m[1] : "search";
    var id = m && m[2] ? decodeURIComponent(m[2]) : null;
    var q = m ? queryOf(m[3]) : {};
    suppressHash = true;
    try {
      var tab = (type === "person" || type === "place") ? "search" : type;
      currentTab = tab;
      syncTabUI(tab);
      if (type === "person" && personMap[id]) {
        currentPerson = personMap[id]; currentPlace = null;
        renderPerson(currentPerson);
      } else if (type === "place" && placeMap[id]) {
        currentPlace = placeMap[id]; currentPerson = null;
        renderPlace(currentPlace);
      } else {
        currentPerson = null; currentPlace = null;
        if (tab === "places") renderPlacesIndex();
        else if (tab === "chapters") renderChapterIndex();
        else renderPersonsIndex();
      }
      if (q.c && chapterMap[q.c]) {
        if (!(reader.classList.contains("on") && readerState &&
              readerState.chapterId === q.c)) {
          openChapter(q.c);
        }
      } else if (reader.classList.contains("on")) {
        reader.classList.remove("on");
      }
    } finally {
      suppressHash = false;
    }
    syncBackBtn();
  }

  window.addEventListener("hashchange", applyHash);
  document.getElementById("back").addEventListener("click", function () {
    // 原文层开着就先关它（更符合「退一步」的直觉），否则退真正的上一步
    if (reader.classList.contains("on")) { closeReader(); return; }
    if (history.length > 1) history.back();
    else { location.hash = "#/search"; }
  });

  /* ---------------- 初始化 ---------------- */

  /* 按「當前書作用域內的提及數」排序：換書後快捷詞跟著換，
     不會出現「選了漢書，頭一排快捷詞全是漢書裏查不到的人」。
     默認按**篇數**（.c）排，可切換按次數（.n）——見 sortMode 與 renderIndex 的開關。 */
  var sortMode = "c";   // "c" = 篇數（默認），"n" = 次數
  function byScopeCount(a, b) {
    var sa = scopeStat(a), sb = scopeStat(b);
    var ka = sortMode === "c" ? sa.cAll : sa.nAll;
    var kb = sortMode === "c" ? sb.cAll : sb.nAll;
    if (kb !== ka) return kb - ka;
    return sb.nAll - sa.nAll;   // 篇數相同時再按次數，保證穩定
  }

  function initQuick() {
    var topP = persons.filter(function (p) { return scopeStat(p).nAll > 0; })
                      .sort(byScopeCount).slice(0, 20);
    var topL = places.filter(function (p) { return scopeStat(p).nAll > 0; })
                     .sort(byScopeCount).slice(0, 10);
    var html = topP.map(function (p) {
      var st = scopeStat(p);
      return '<span data-name="' + esc(p.name) + '">' + esc(p.name) +
             '<b class="qn"> ' + count(st.nAll) +
             (st.pn > 0 ? "裴" + count(st.pn) : "") + "</b></span>";
    }).join("");
    html += '<i class="sep"></i>' + topL.map(function (p) {
      var st = scopeStat(p);
      return '<span class="land" data-name="' + esc(p.name) + '">' + esc(p.name) +
             '<b class="qn"> ' + count(st.nAll) + "</b></span>";
    }).join("");
    quick.innerHTML = html;
    quick.querySelectorAll("span").forEach(function (el) {
      el.addEventListener("click", function () {
        switchTab("search");
        document.getElementById("q").value = el.getAttribute("data-name");
        search(el.getAttribute("data-name"));
      });
    });
  }

  function initDatalist() {
    var html = persons.map(function (p) {
      return '<option value="' + esc(p.name) + '">' +
             esc((p.dynasty || "") + (p.title ? " · " + p.title : "")) + "</option>";
    }).join("");
    html += places.map(function (p) {
      return '<option value="' + esc(p.name) + '">' +
             esc("地名 · " + (p.kindLabel || p.kind)) + "</option>";
    }).join("");
    document.getElementById("names").innerHTML = html;
  }

  document.getElementById("btn").addEventListener("click", function () {
    switchTab("search");
    search(document.getElementById("q").value);
  });
  document.getElementById("q").addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") { switchTab("search"); search(ev.target.value); }
  });
  document.querySelectorAll(".tabs span").forEach(function (el) {
    el.addEventListener("click", function () { switchTab(el.getAttribute("data-tab")); });
  });

  var tiers = meta.tierStat || {};
  var tierText = Object.keys(TIER_LABEL)
    .filter(function (k) { return tiers[k]; })
    .map(function (k) { return TIER_LABEL[k] + " " + count(tiers[k]); })
    .join("、");

  renderBookBar();
  renderSub();
  note.innerHTML =
    "數據說明：語料取自維基文庫（公有領域），本地離線運行，不聯網。當前收錄 " +
    (isMulti()
      ? BOOKS.map(function (b) {
          return "《" + b.name + "》" + b.chapterCount + " 篇";
        }).join("、")
      : "《" + (meta.book || "史記") + "》" + meta.chapterCount + " 篇") +
    "，共 " + meta.chapterCount + " 篇 / " + count(meta.sentenceCount) + " 句 / " +
    count(meta.charCount) + " 字；可按上方書名切換「單書檢索」與「多書合檢」。" +
    "<br><b>人物</b>：收錄 " + meta.personCount + " 人、稱謂 " + count(meta.aliasCount) +
    " 條。人名及其全部稱謂逐句匹配（「劉邦」＝高祖／沛公／漢王／劉季），" +
    "按「是否為本篇主人公」拆成「整篇講述」與「其他篇目提及」兩組；" +
    "人物頁列出全部稱謂並標註出現次數。" +
    "<br><b>地名</b>：收錄 " + count(meta.placeCount || 0) + " 個地名、寫法 " +
    count(meta.placeMarkCount || 0) + " 處標記（具名 " +
    count(meta.placeCoreMarks || 0) + " + 單字國名 " +
    count(meta.placeCharMarks || 0) + "）。「整篇講述」以<b>篇名含該地名</b>為準" +
    "（秦本紀→秦、匈奴列傳→匈奴、河渠書→河），篇名不含但篇內密集出現的另作補充。" +
    "地名頁列出該地的各種寫法（洛陽／雒陽、鉅鹿／鉅鹿）。" +
    "<br><b>同稱異人</b>：稱號（梁王、淮南王、齊王、湯…）在不同篇目常指不同人——" +
    "「梁王」在《魏豹彭越列傳》是彭越，在《梁孝王世家》是劉武。這類稱號共 " +
    count(meta.genericAliasCount) + " 個，按篇目上下文逐條判定（有依據 " +
    count(meta.genericConfident) + " 處 / 共 " + count(meta.genericMarks) +
    " 處）。依據分佈：" + (tierText || "—") + "。" +
    "<br><b>單字地名</b>：齊楚燕趙韓魏秦魯宋衛鄭吳越陳蔡曹等單字國名與姓氏、動詞同形" +
    "（「陳師牧野」是陳列、「紂乃許之」是答應、「摯代立」是替代）。這些字需先扣除" +
    "人名佔用區間、再過鄰字排除表才成立，正文中以虛線下劃線標出；" +
    "「許、代、隨、息、舒、漢、紀、申」等因作地名是少數義，只保留多字寫法。" +
    "<br><b>讀全篇</b>：點擊篇名打開全文；正文中黃底＝當前檢索對象的名稱。" +
    "篇幅大的篇目（如《十二諸侯年表》3267 段）可用「只看與 TA 有關的段落」快速跳讀。" +
    "<br>生成時間 " + meta.generatedAt + "。";

  initQuick();
  initDatalist();
  /* 帶 hash 進來（後退回來、或別人分享的鏈接）就先按路由還原，
     否則走默認的「劉邦」首屏。注意順序：先 applyHash 再 search。 */
  if (location.hash) applyHash();
  else search("劉邦");
})();
