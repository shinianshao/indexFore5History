/* 古籍檢索 · 本地索引前端（docs/21 P2）
 * 數據全部來自 /api/*，不再整包注入——所以 32MB 的 app-data.js 從此與本頁無關。
 *
 * 界面文案**一律繁體**：check_trad.py 會掃描本目錄，簡體會讓 F 界面閘失敗。
 */
(function () {
  "use strict";

  var out = document.getElementById("out");
  var hint = document.getElementById("hint");
  var qEl = document.getElementById("q");
  var reader = document.getElementById("reader");
  var readerTitle = document.getElementById("readerTitle");
  var readerBody = document.getElementById("readerBody");
  var backBtn = document.getElementById("back");

  var mode = "person";                    // person | fts
  var currentPid = null;
  var lastQuery = "";
  // 原文層狀態。聲明放在這裡（而不是用它的函數附近），
  // 因為 renderPerson 在上面就會寫 hitUids —— 分散聲明只靠 var 提升才不出錯，
  // 順序一變就變成 undefined。
  var readerState = { sents: [], pid: null, hitsOnly: false, hitUids: null,
                      targetUid: null };

  /* ---------- 離線快照（dist/）----------
     同一份 app.js 同時服務「聯機 FastAPI 版」與「離線靜態版 dist/」：
     dist/data.js 會定義 window.BOOKINDEX_DATA，有它＝離線。
     刻意**不複製一套前端**——兩套前端的維護稅已經交過一次（web/ 靜態版凍結後，
     每次改動都要糾結要不要同步），這裡只換數據來源。
     業務規則仍然只有服務端一份：離線層做的是「緊湊數組 → 前端要的物件形狀」的
     **機械還原**，不含計數／排序／關係推導（docs/29 §六-6）。 */
  var OFF = !!window.BOOKINDEX_DATA;
  var D = OFF ? window.BOOKINDEX_DATA : null;
  var CHAPT = {};                 // 篇號 → 全名（還原命中時要用，避免每次查表）
  if (OFF) {
    Object.keys(D.chaps).forEach(function (cid) { CHAPT[cid] = D.chaps[cid][0]; });
  }

  /* 還原：全部是下標查找 + 物件組裝，沒有任何規則。
     與聯機版唯一的刻意差異——mentions / 句子**不截斷**（聯機上限 200 / 500），
     快照一次給全；只多不少，不影響顯示。 */
  function offChapter(cid) {
    var c = D.chaps[cid];
    if (!c) return null;
    var rows = [];
    for (var i = c[2]; i < c[3]; i++) {
      var s = D.sents[i];
      // s[3] 是段號（para_seq）——原文層的「跳段」靠它。
      // ⚠️ 與聯機版 /api/chapter 保持**同一個字段名**（para_seq）：
      // 離線與聯機的響應體必須同構，否則同一段渲染代碼要寫兩套。
      rows.push({ uid: s[0], chapter_id: cid, text: s[2], para_seq: s[3] });
    }
    return { chapter: { id: cid, full_title: c[0], book_id: c[1] }, sentences: rows };
  }

  function offRel(pid, key) {
    var m = D.rel[pid];
    // 沒邊的人聯機返回的就是這個形狀，離線自己造一個同形的
    return (m && m[key]) || { nodes: [{ id: pid, degree: 0 }], edges: [] };
  }

  function offPerson(pid) {
    var p = D.pers[pid];
    if (!p) return null;
    return {
      profile: { id: pid, trad_name: p[0], name: p[1], dynasty: p[2],
                 title: p[3], summary: p[4], aliases: p[5],
                 // 稱謂表：只是「緊湊數組 → 物件」的機械還原，
                 // 與聯機 person_payload 的 aliasList **同形**，共用 aliasTable 渲染。
                 aliasList: (p[6] || []).map(function (a) {
                   return { w: a[0], simp: a[1], n: a[2],
                            kind: ALIAS_KINDS[a[3]] || "other",
                            variants: a[4] || [], byBook: a[5] || {} };
                 }) },
      mentions: (D.pm[pid] || []).map(function (m) {
        var s = D.sents[m[0]];
        return { chapter: CHAPT[s[1]] || "", chapter_id: s[1], uid: s[0],
                 text: s[2], surface: m[1], s: m[2], e: m[3], tier: m[4] };
      }),
      // 注文：離線版與聯機版**同源**（同一份 pei-data.json / js-note-data.json），
      // 形狀也一樣，所以 notesSection 一段代碼兩邊都能用。
      notes: offNotes(pid),
      relations: offRel(pid, "1:0")
    };
  }

  function offNotes(pid) {
    var N = D.notes || {};
    return {
      pei: (N.pei || {})[pid] || null,
      peiMeta: N.peiMeta || {},
      jsNote: (N.jsNote || {})[pid] || null,
      jsNoteMeta: N.jsNoteMeta || {},
      chapterTitles: N.chapterTitles || {}
    };
  }

  /* 檢索與全文：離線沒有 SQLite 也沒有 FTS——直接掃。
     9.6 萬句在內存裡做 indexOf 是毫秒級，比分詞建索引划算得多，
     而且跟線上 FTS 的「按字切分 + 短語」在效果上等價（都是連續子串）。 */
  function offFts(q, limit) {
    var got = [];
    for (var i = 0; i < D.sents.length && got.length < limit; i++) {
      var s = D.sents[i];
      if (s[2].indexOf(q) >= 0) {
        got.push({ uid: s[0], text: s[2], chapter_id: s[1],
                   chapter: CHAPT[s[1]] || "" });
      }
    }
    return { query: q, items: got };
  }

  function offSearch(q, limit) {
    var got = [];
    Object.keys(D.pers).forEach(function (pid) {
      var p = D.pers[pid], pb = D.pbook[pid] || [0, []];
      if (p[0].indexOf(q) >= 0 || p[1].indexOf(q) >= 0 ||
          p[5].some(function (a) { return a.indexOf(q) >= 0; })) {
        got.push({ id: pid, trad_name: p[0], name: p[1], dynasty: p[2],
                   title: p[3], summary: p[4], n: pb[0],
                   books: pb[1].map(function (b) {
                     return { id: b[0], name: b[1], n: b[2] }; }) });
      }
    });
    got.sort(function (a, b) { return b.n - a.n; });
    return { query: q, items: got.slice(0, limit) };
  }

  function offlineGet(path) {
    var u = path.replace(/^\/?api\//, ""), m;
    if (u === "stats") return Promise.resolve(D.stats);
    if (u.indexOf("index") === 0) {
      var bk = (u.match(/book=([^&]*)/) || [0, ""])[1];
      return Promise.resolve(D.idx[decodeURIComponent(bk)] || D.idx[""]);
    }
    if ((m = u.match(/^person\/([^/?]+)\/relations/))) {
      var rp = decodeURIComponent(m[1]);
      var dg = (u.match(/degree=(\d)/) || [0, 1])[1];
      var cf = parseFloat((u.match(/min_conf=([\d.]+)/) || [0, 0])[1]) || 0;
      return Promise.resolve(offRel(rp, dg + ":" + cf));
    }
    if ((m = u.match(/^person\/([^/?]+)/))) {
      var pid = decodeURIComponent(m[1]);
      var d = offPerson(pid);
      return d ? Promise.resolve(d)
               : Promise.reject(new Error("查無此人：" + pid));
    }
    if ((m = u.match(/^chapter\/([^/?]+)/))) {
      var cid = decodeURIComponent(m[1]);
      var c = offChapter(cid);
      return c ? Promise.resolve(c)
               : Promise.reject(new Error("查無此篇：" + cid));
    }
    if ((m = u.match(/^search\?q=(.*)$/))) {
      return Promise.resolve(offSearch(decodeURIComponent(m[1]), 30));
    }
    if ((m = u.match(/^fts\?q=(.*)$/))) {
      return Promise.resolve(offFts(decodeURIComponent(m[1]), 50));
    }
    return Promise.reject(new Error("離線版沒有這個接口：" + path));
  }

  /* ---------- 請求層：錯誤要映射成人話，4xx 不重試、5xx 最多重試 3 次 ---------- */
  function request(path, retry) {
    if (OFF) return offlineGet(path);
    retry = retry || 0;
    return fetch(path, { headers: { Accept: "application/json" } }).then(function (r) {
      if (r.ok) return r.json();
      if (r.status >= 500 && retry < 3) {
        return new Promise(function (res) { setTimeout(res, 300); })
          .then(function () { return request(path, retry + 1); });
      }
      return r.json().catch(function () { return {}; }).then(function (b) {
        throw new Error(b.message || ("請求失敗（" + r.status + "）"));
      });
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* 命中高亮：core 實線，其餘（推斷）虛線 + 依據標註。
     這是「方便查找確認」的核心——一眼看出哪些是硬命中、哪些是猜的。 */
  var TIER_NOTE = {
    owner: "篇主", chapter: "篇目", era: "時代", sentence: "句內",
    paragraph: "段內", related: "關聯", scoped: "限定", guess: "推斷"
  };
  function markSentence(text, surface, tier) {
    var i = String(text || "").indexOf(surface || "");
    if (i < 0 || !surface) return esc(text);
    var cls = (tier && tier !== "core") ? "guess" : "";
    var html = esc(text.slice(0, i)) +
      "<mark class=\"" + cls + "\">" + esc(surface) + "</mark>" +
      esc(text.slice(i + surface.length));
    var note = TIER_NOTE[tier];
    return html + (note ? "<span class=\"tier-note\">？" + note + "</span>" : "");
  }

  /* ---------- 渲染：結果列表 ---------- */
  function renderResults(items, query) {
    if (!items.length) {
      out.innerHTML = "<div class=\"empty\">查不到「" + esc(query) + "」</div>";
      return;
    }
    var many = items.length > 1;
    var html = "<div class=\"card\"><div class=\"person-head\">" +
      "<span class=\"name\">「" + esc(query) + "」</span>" +
      "<span class=\"dyn\">共 " + items.length + " 人</span></div>";
    /* 同名異人消歧：給序號徽章，並標出各自**主要見於哪幾本書**——
       同名往往各屬一書（張溫：後漢書一人、三國志一人），
       光看朝代與頭銜分不出來，分書是最好用的判據。 */
    items.forEach(function (p, i) {
      var idx = many ? "<span class=\"dup-idx\">" + (i + 1) + "</span>" : "";
      var bk = (p.books && p.books.length)
        ? "見於 " + p.books.map(function (b) { return esc(b.name); }).join(" · ")
        : "";
      html += "<div class=\"row\" data-pid=\"" + esc(p.id) + "\">" +
        "<span class=\"name\">" + idx + esc(p.trad_name) +
        (p.name && p.name !== p.trad_name ? "（" + esc(p.name) + "）" : "") + "</span>" +
        "<span class=\"meta\">" + esc(p.dynasty || "") +
        (p.title ? " · " + esc(p.title) : "") + " · " + p.n + " 處" +
        (bk ? "　<span class=\"books\">" + bk + "</span>" : "") + "</span></div>";
    });
    out.innerHTML = html + "</div>";
    hint.textContent = many
      ? "同名異人 " + items.length + " 位：先看「見於」哪本書，再點進去分開看命中。"
      : "";
  }

  /* ---------- 渲染：人物詳情 ---------- */
  /* ---------- 注文區塊（裴注 / 晉書舊史注）----------
     兩本獨立賬本，**不合進正文命中**（紅線）。顯示策略照 static 版：
     按篇 Top 12 + 明細抽 8 條。差異只有兩處，都是刻意的：
       1. 合計處標【裴N】/【舊注N】——讓用戶知道這是另一層文本的數字；
       2. 晉書舊史注只留一行（docs/29 §六-3：全庫僅 4 篇 / 69 處，
          為它做完整區塊是浪費），但**不是不顯示**——完全藏起來
          等於讓人以為「這個人沒有舊史注材料」。 */
  /* 千分位：注文的處數可以到四位数（曹操 726），不隔位的話讀不過來。
     ⚠️ UI 測試斷過千分位（×1,026），別改成裸數字。 */
  function count(n) { return (n || 0).toLocaleString("en-US"); }

  function noteBlock(note, label, noteBook, showItems, titles) {
    if (!note || !note.n) return "";
    var h = "<div class=\"group-title\">" + label + "　<span class=\"count\">" +
      count(note.n) + " 處 / " + count(note.chapters) + " 篇" +
      "　<span class=\"note-warn\">獨立賬本，不計入正文命中</span></span></div>";

    var byCh = note.byChapter || {};
    var cids = Object.keys(byCh).sort(function (a, b) { return byCh[b] - byCh[a]; });
    if (cids.length) {
      h += "<div class=\"card\">";
      cids.slice(0, showItems ? 12 : 6).forEach(function (id) {
        var c = (titles && titles[id]) || CHAPT[id] || id;
        h += "<div class=\"mention-head\"><span class=\"name\">" + esc(c) +
          "</span><span class=\"meta\">" + count(byCh[id]) + " 處 · " +
          "<b class=\"open-full\" data-chapter=\"" + esc(id) + "\">讀全篇 ›</b>" +
          "</span></div>";
      });
      if (cids.length > (showItems ? 12 : 6)) {
        h += "<div class=\"alias-note\">另有 " +
          count(cids.length - (showItems ? 12 : 6)) + " 篇…</div>";
      }
      h += "</div>";
    }

    var items = note.items || [];
    if (items.length && showItems) {
      h += "<div class=\"card\">";
      items.slice(0, 8).forEach(function (it) {
        h += "<div class=\"pei-line\" data-chapter=\"" + esc(it.cid) + "\"" +
          (it.pseq ? " data-pseq=\"" + esc(String(it.pseq)) + "\"" : "") +
          " title=\"" + esc(it.alias || "") + "\">" + esc(it.text) + "</div>";
      });
      h += "<div class=\"alias-note\">摘自" + esc(noteBook || "") +
        "注文（〈…〉），樣本最多顯示 8 條；完整計數見上方，" +
        "全文可在讀全篇中以灰藍小字辨認。</div></div>";
    }
    return h;
  }

  function notesSection(pid, notes, mainN) {
    var h = "";
    var pei = notes.pei;
    if (pei && pei.n) {
      // 【裴N】標記擺在正文命中旁邊：讓用戶一眼看到這是另一層文本的數字。
      // ⚠️ 這裡**不做 n + pei.n 的相加**（紅線：注文不進 mentionCount）。
      h += "<div class=\"note-sum\">正文命中 <b>" + count(mainN) +
        "</b> 處　＋　注文另計 <b class=\"note-chip\">【裴" +
        count(pei.n) + "】</b></div>";
    }
    var titles = notes.chapterTitles || {};
    h += noteBlock(pei, "三國志裴松之注明細", "三國志", true, titles);
    var js = notes.jsNote;
    if (js && js.n) {
      // 晉書舊史注：docs/29 §六-3 判定只留一行（全庫僅少數篇），
      // 但**不是不顯示**——完全藏起來會讓人以為這人沒這份材料。
      h += "<div class=\"group-title\">晉書舊史注　<span class=\"count\">" +
        count(js.n) + " 處（另有 " + count(js.chapters) +
        " 篇）　<span class=\"note-warn\">獨立賬本</span></span></div>";
    }
    return h;
  }

  /* ---------------- 完整稱謂表 ----------------
     「這個別名靠不靠譜」的唯一依據：「漢王 ×739」是硬命中，「未用」是詞典收了
     但這批書裡沒出現過——兩者差一個數量級的可信度，混在一起顯示就等於沒告訴用戶。
     數據由後端 db.person_alias_list 出（離線快照複用同一份），前端只做展示選擇。 */
  var ALIAS_KINDS = ["name", "title", "generic", "short", "other"];
  var ALIAS_KIND_LABEL = {
    name: "本名",
    title: "職銜（不參與檢索）",
    generic: "泛稱",
    short: "單字",
    other: "其他"
  };
  var ALIAS_KIND_HINT = {
    name: "姓名本身",
    title: "職銜、封號等（僅展示，不參與檢索；檢索請用本名／字／專屬稱謂）",
    generic: "稱號類別名，同一稱號在不同篇目可能指不同人，按篇目上下文逐條判定",
    short: "單字指代，只在特定篇目內有效，不做全庫匹配",
    other: "字、號、尊稱、別稱等"
  };

  /* 當前書作用域內的出現次數。
     ⚠️ **刻意在前端算**：離線版沒有服務端，請求裡帶 book 也只會被離線路由當成
     查詢串忽略，理应收窄時就收不到等值結果。讓聯機與離線跑**同一段代碼**，
     是唯一不會悄悄分叉的辦法。前提是 n == ΣbyBook（後端 verify_p3 [14] 守著）。 */
  function aliasScopeN(a) {
    var bb = a.byBook;
    if (!scopeBook || !bb) return a.n || 0;
    return bb[scopeBook] || 0;
  }

  /* 懸停提示裡列出各書分帳——不被當前書作用域影響，否則「收窄」就看不到全貌了 */
  function aliasBookTip(a) {
    var bb = a.byBook, parts = [];
    if (!bb) return "";
    BOOKS.forEach(function (b) {
      if (bb[b.code]) parts.push(b.name + " " + count(bb[b.code]));
    });
    return parts.length ? "\n分書：" + parts.join("　") : "";
  }

  function aliasTable(list) {
    var groups = {};
    list.forEach(function (a) {
      var k = ALIAS_KINDS.indexOf(a.kind) >= 0 ? a.kind : "other";
      (groups[k] = groups[k] || []).push(a);
    });
    var html = '<div class="alias-groups">';
    ALIAS_KINDS.forEach(function (kind) {
      var rows = groups[kind];
      if (!rows || !rows.length) return;
      html += '<div class="alias-group"><span class="kind" title="' +
        esc(ALIAS_KIND_HINT[kind]) + '">' + esc(ALIAS_KIND_LABEL[kind]) +
        '</span><span class="chips">';
      rows.forEach(function (a) {
        var n = aliasScopeN(a);
        var others = (a.variants || []).filter(function (v) { return v !== a.w; });
        var tip = a.w + (others.length ? "（亦作 " + others.join("、") + "）" : "") +
          "\n" + ALIAS_KIND_HINT[kind] + aliasBookTip(a) +
          "\n" + (scopeBook ? "在本書出現 " : "五書合計出現 ") + count(n) +
          // 文案要跟着作用域走：全五书下叫「一律未用」才准确，不能说「本书」
          " 次" + (n ? "" : (scopeBook ? "（本書未用）" : "（五書均未出現）"));
        html += '<span class="chip' + (n ? "" : " off") +
          (kind === "generic" ? " gen" : "") + '" title="' + esc(tip) + '">' +
          esc(a.w) + "<em>" + (n ? "×" + count(n) : "未用") + "</em></span>";
      });
      html += "</span></div>";
    });
    html += "</div>";
    if (groups.generic && groups.generic.length) {
      html += '<div class="alias-note">泛稱稱號（' +
        groups.generic.map(function (a) { return esc(a.w); }).join("、") +
        "）不固定屬於誰，每處都按所在篇目的上下文判定歸屬。</div>";
    }
    return html;
  }

  /* ---------- 網頁「標錯」入口（P3-4）----------
     人物頁每條命中都能標錯：改歸給別人，或「這處不算他」。
     與句級編輯同一套：**寫進 workbook/overrides.xlsx**（那張表歸人寫，這裡是 UI 代筆），
     重建後才生效——所以每記一條都要把「待重建」說清楚。
     ⚠️ nth 不自己算：`/api/override` 只收 (uid, s, e, surface)，由後端換成
     「本句第幾條命中」。前端看到的是**這個人在本句裡的第幾條**，兩個序號不是一回事，
     自己算必然改到別人頭上，而且不報錯。
     離線快照沒有服務端可寫，一律不給這顆按鈕。 */
  var ovMap = {};          // "uid|s|e|surface" → 糾錯行
  var ovPending = 0;       // 還沒重建生效的糾錯條數
  var ovMsg = "";          // 重建狀態文字（要跨重渲染存活，見 ovStatus）
  var ovMsgFor = "";       // 這條狀態屬於哪個 pid
  var fixTimer = null;

  function ovKeyOf(uid, s, e, surface) {
    return [uid, s, e, surface].join("|");
  }
  function loadOverrides() {
    if (OFF) return Promise.resolve({ items: [] });
    // 拿不到就算了：糾錯是附加資訊，不能因為它失敗就整個人打不開
    return request("/api/overrides").catch(function () { return { items: [] }; });
  }
  /* 徽章要分「待重建 / 已生效」兩種樣子。
     ⚠️ 表裡的行永遠 active（revoke 只改狀態），所以「已生效」是**算出來的**
     （`db.override_states` 拿行去問庫）。不算的話：重建完頂欄還是那句
     「重建後生效」，而且改歸生效後那處命中已經屬於別人，別人的頁面上也會
     掛出這句——看著像還沒做。 */
  function flagBadge(ov) {
    var txt = (ov.action === "drop")
      ? "已標錯：這處不作數"
      : ("已標錯 → " + (ov.toName || ov.to || "？"));
    if (ov.applied) txt += " ✓";
    return "<span class=\"flag-badge\"" +
      (ov.applied ? " title=\"重建已生效\"" : " title=\"待重建生效\"") + ">" +
      esc(txt) + "<button data-act=\"unflag\">撤銷</button></span>";
  }
  /* 重建狀態也得在**人物頁**看得見——原文層的 `#edstat` 在原文層頭上，
     沒開原文層時按了重建就是 30 秒靜默等待。
     ⚠️ 狀態文字要**記在變數裡**，不能只寫進 DOM：重建完成後人物頁會重渲染，
     只寫 DOM 的話這句「重建完成」跟著舊節點一起沒了（此時 pending 歸零，
     條子本身也會被收走）。ovMsgFor 記這條消息屬於哪個 pid，免得竄到別人的頁面上。 */
  function ovStatus(msg, pid) {
    ovMsg = msg || "";
    ovMsgFor = pid || "";
    var el = out.querySelector(".ovbar .ovtxt");
    if (el) el.textContent = ovMsg;
  }

  function renderPerson(pid) {
    return Promise.all([
      request("/api/person/" + encodeURIComponent(pid)),
      loadOverrides()
    ]).then(function (rs) {
      var d = rs[0];
      var p = d.profile;
      // 換人就把上一個人的重建狀態丟掉，免得回來時看到一句過期的「重建完成」
      if (ovMsgFor && ovMsgFor !== pid) { ovMsg = ""; ovMsgFor = ""; }
      ovMap = {};
      (rs[1].items || []).forEach(function (r) {
        ovMap[ovKeyOf(r.uid, r.s, r.e, r.surface)] = r;
      });
      ovPending = rs[1].pending || 0;
      // 記住這個人的命中 uid —— 原文層的「只看相關段落」靠它。
      // ⚠️ mentions 有 limit（默認 200），**只覆蓋前 N 條**。所以篩選是
      // 「本頁已加載的命中」，不是全集；命中太多時人物頁本身也只顯示前 N，
      // 兩者口徑一致，不會出現「原文層說沒有、人物頁說有」的自相矛盾。
      var uids = {};
      (d.mentions || []).forEach(function (m) { if (m.uid) uids[m.uid] = 1; });
      readerState.hitUids = uids;
      var html = "<div class=\"card\">" +
        "<div class=\"person-head\"><span class=\"name\">" + esc(p.trad_name) + "</span>" +
        "<span class=\"dyn\">" + esc(p.dynasty || "") +
        (p.title ? " · " + esc(p.title) : "") + "</span></div>";
      if (p.summary) html += "<p class=\"summary\">" + esc(p.summary) + "</p>";
      // 完整稱謂表（含次數 / 類別 / 分書），沒有它就退回扁平寫法——
      // 稱謂表是 aliasList 的超集（別名都併進各條的 variants），所以不必兩個都顯示。
      if (p.aliasList && p.aliasList.length) {
        html += aliasTable(p.aliasList);
      } else if (p.aliases && p.aliases.length) {
        html += "<div class=\"alias-note\">" + p.aliases.map(function (a) {
          return "<span class=\"alias-tag\">" + esc(a) + "</span>";
        }).join("") + "</div>";
      }
      html += "</div>";
      // 頂欄：只在**還沒生效**的糾錯存在時掛（生效了就不該再催你重建）。
      // 掛了就帶一塊 .ovtxt 給重建狀態用——否則人物頁點了重建，
      // 狀態只發給原文層的 #edstat，那層沒開就是 30 秒靜默。
      // ovMsg 非空時也保留這條：重建完成 pending 歸零、條子被收走，
      // 那一瞬間的「重建完成」得留得住。
      if (ovPending || (ovMsg && ovMsgFor === pid)) {
        html += "<div class=\"ovbar\">" +
          (ovPending ? "有 " + ovPending + " 條糾錯待重建" : "") +
          "<span class=\"ovtxt\">" + esc(ovMsg) + "</span>" +
          (OFF || !ovPending ? "" : "<button data-act=\"ovrebuild\">重建</button>") +
          "</div>";
      }

      // 命中按篇分組
      var groups = [], byId = {};
      (d.mentions || []).forEach(function (m) {
        var key = m.chapter_id;        if (!byId[key]) { byId[key] = { title: m.chapter, rows: [] }; groups.push(byId[key]); }
        byId[key].rows.push(m);
      });
      if (!groups.length) {
        html += "<div class=\"empty\">此人在目前語料裡沒有命中。</div>";
      }
      groups.forEach(function (g) {
        html += "<div class=\"chapter-title\">" + esc(g.title || "") +
          " · " + g.rows.length + " 處</div>";
        g.rows.forEach(function (m) {
          var ov = ovMap[ovKeyOf(m.uid, m.s, m.e, m.surface)];
          html += "<div class=\"sent\" data-chapter=\"" + esc(m.chapter_id) +
            "\" data-uid=\"" + esc(m.uid) +
            "\" data-s=\"" + esc(m.s) + "\" data-e=\"" + esc(m.e) +
            "\" data-surface=\"" + esc(m.surface) + "\" data-pid=\"" + esc(pid) + "\">" +
            markSentence(m.text, m.surface, m.tier) +
            (ov ? flagBadge(ov) : "") +
            // 沒有偏移（s/e 缺失）就別給按鈕：後端靠 (s, e, surface) 定位，
            // 給了也只能報 400，不如一開始就不出現
            ((!OFF && m.s != null && m.e != null)
              ? "<span class=\"acts\"><button data-act=\"flag\">標錯</button></span>"
              : "") +
            "</div>";
        });
      });

      /* 注文區塊（裴注 / 晉書舊史注）——**獨立賬本**。
         ⚠️ 紅線：注文命中**不進正文 mentionCount**。這裡只把它的分量
         寫成【裴N】/【舊注N】並列，絕不與正文的「N 處」相加。
         數據源是 pipeline 產的 pei-data.json / js-note-data.json（不入庫），
         經 db.person_notes_payload 傳過來，與聯機端點/離線導出共用一份。 */
      html += notesSection(pid, d.notes || {}, (d.mentions || []).length);

      /* 關係：資料來自 workbook/relations.xlsx，後端已轉成 {nodes, edges}。
         圖 + 列表並存：**虛線＝無證據的推斷**，實線＝語料裡有原句可跳，
         別讓推斷看起來像事實（docs/25 §四）。 */
      relState = { degree: 1, minConf: 0 };
      html += "<div class=\"card\" id=\"relcard\" style=\"margin-top:14px\">" +
        relCardInner(pid, d.relations || { nodes: [], edges: [] }, relState) + "</div>";

      out.innerHTML = html;
      hint.textContent = "實線＝正名或別名直接命中；虛線＋？＝泛稱推斷，待確認。";
      currentPid = pid;
    });
  }

  /* 標錯面板：不彈窗，就地展開一行——彈窗要管焦點與層級，
     而這裡只需要「輸入人名 → 點候選」兩下。 */
  function openFixBox(row) {
    var old = row.parentNode ? row.parentNode.querySelector(".fixbox") : null;
    if (old) { old.parentNode.removeChild(old); }
    var surface = row.getAttribute("data-surface") || "";
    var box = document.createElement("div");
    box.className = "fixbox";
    ["uid", "s", "e", "surface", "pid"].forEach(function (k) {
      box.setAttribute("data-" + k, row.getAttribute("data-" + k) || "");
    });
    box.innerHTML =
      "<div class=\"fix-head\">這處判為「" + esc(surface) + "」</div>" +
      "<div class=\"fix-line\"><input class=\"fix-input\" " +
      "placeholder=\"改歸給誰？輸入人名，如 項羽\" autocomplete=\"off\">" +
      "<button data-act=\"cancel\">取消</button></div>" +
      "<div class=\"fix-cand\"></div>" +
      "<div class=\"fix-alt\">或者 <button data-act=\"drop\">不是他（這處不算）</button>" +
      "<span class=\"fix-hint\">　改動記進 overrides.xlsx，重建後生效</span></div>";
    if (row.nextSibling) { row.parentNode.insertBefore(box, row.nextSibling); }
    else { row.parentNode.appendChild(box); }
    var inp = box.querySelector(".fix-input");
    inp.addEventListener("input", function () { fixSearch(box, inp.value); });
    inp.focus();
  }

  function fixSearch(box, q) {
    var cand = box.querySelector(".fix-cand");
    q = String(q || "").trim();
    if (!q) { cand.innerHTML = ""; return; }
    clearTimeout(fixTimer);
    // 防抖：每敲一個字就查一次，古籍人名兩三個字，會連著查三次
    fixTimer = setTimeout(function () {
      request("/api/search?q=" + encodeURIComponent(q)).then(function (r) {
        var items = (r.items || []).slice(0, 6);
        cand.innerHTML = items.length
          ? items.map(function (x) {
              return "<div class=\"fix-cand-row\" data-pid=\"" + esc(x.id) + "\">" +
                "<span class=\"nm\">" + esc(x.trad_name) + "</span>" +
                "<span class=\"mt\">" + esc(x.dynasty || "") +
                (x.title ? " · " + esc(x.title) : "") + " · " + x.n + " 處</span></div>";
            }).join("")
          : "<div class=\"fix-empty\">查不到這個人</div>";
      }).catch(function () { cand.innerHTML = ""; });
    }, 220);
  }

  function submitFlag(box, action, newPid) {
    var body = {
      uid: box.getAttribute("data-uid"),
      s: parseInt(box.getAttribute("data-s"), 10),
      e: parseInt(box.getAttribute("data-e"), 10),
      surface: box.getAttribute("data-surface"),
      pid: box.getAttribute("data-pid"),
      action: action
    };
    if (newPid) { body.new = newPid; }
    requestPost("/api/override", body).then(function (r) {
      // 重渲染：徽章與計數都由服務端那份決定
      return renderPerson(currentPid).then(function () {
        // ⚠️ overrides.py 在 Excel 被別人占著（.new.xlsx 已寫、退出碼還是 0）時
        // 會回 warning。不顯示的話介面說「已記錄」而權威源裡根本沒有。
        ovStatus(r.warning ? "⚠️ " + r.warning : "已記錄，重建後生效", currentPid);
      });
    }).catch(function (e) {
      var alt = box.querySelector(".fix-hint");
      if (alt) { alt.textContent = "　失敗：" + ((e && e.message) || e); }
    });
  }

  function submitUnflag(row) {
    requestPost("/api/override/revoke", { uid: row.getAttribute("data-uid") })
      .then(function () { renderPerson(currentPid); })
      .catch(showErr);
  }

  /* ---------- 渲染：全文檢索 ---------- */
  function renderFts(items, query) {
    if (!items.length) {
      out.innerHTML = "<div class=\"empty\">全文查不到「" + esc(query) + "」</div>";
      return;
    }
    var html = "<div class=\"card\"><div class=\"person-head\">" +
      "<span class=\"name\">全文「" + esc(query) + "」</span>" +
      "<span class=\"dyn\">" + items.length + " 句</span></div></div>";
    var byId = {}, order = [];
    items.forEach(function (r) {
      var k = r.chapter_id;
      if (!byId[k]) { byId[k] = { t: r.chapter, rows: [] }; order.push(k); }
      byId[k].rows.push(r);
    });
    order.forEach(function (k) {
      html += "<div class=\"chapter-title\">" + esc(byId[k].t || "") + "</div>";
      byId[k].rows.forEach(function (r) {
        html += "<div class=\"sent\" data-chapter=\"" + esc(r.chapter_id) +
          "\" data-uid=\"" + esc(r.uid) + "\">" + esc(r.text) + "</div>";
      });
    });
    out.innerHTML = html;
    hint.textContent = "";
  }

  /* ---------- 句級編輯（P4-2）----------
     寫進 workbook/sentence-edits.xlsx（那張表歸人寫，這裡是 UI 代筆），
     重建後才生效——所以每記一條都要說清楚「待重建」。 */
  var edstat = document.getElementById("edstat");
  var btnRebuild = document.getElementById("btnRebuild");
  var pending = {};        // uid → action
  var readerCid = null;
  var onRebuilt = null;    // 重建完成後要重取的那一屏（由發起處設）

  /* ---------- 原文層的跳段與段落篩選（對齊靜態版）----------
     兩件事，都是純前端：
       跳段        —— 長篇（如《十二諸侯年表》幾千段）能直接定位到第 N 段
       只看相關段落 —— 只留下與當前這個人有關的段落，讀長篇時的救命功能
     數據都已經在 /api/chapter 回來裡（sentences 帶 para_seq），不需要後端改。 */
  var jumpBox = document.getElementById("jumpBox");
  var jumpInput = document.getElementById("jumpInput");
  var jumpTotal = document.getElementById("jumpTotal");
  var btnHits = document.getElementById("btnHits");
  var JUMP_MIN = 40;        // 少於這麼段就不顯示跳段控件（加了是噪聲）

  function paraCount() {
    var seen = {}, n = 0;
    (readerState.sents || []).forEach(function (s) {
      if (s.para_seq != null && !seen[s.para_seq]) { seen[s.para_seq] = 1; n++; }
    });
    return n;
  }

  /* 與當前 pid 有命中的段落號集合。
     ⚠️ 命中資訊**不從 /api/chapter 拿**（那会让 564 篇每篇都带上全部 marks，
     payload 翻十几倍）。人物頁渲染時已經拿到這個人的 mentions（帶 uid），
     在這裡把 uid 記進 readerState.hitUids，開篩選時才反查段落——
     數據來源是同一份，沒有第二個真相。 */
  function hitParas() {
    var out = {};
    if (!readerState.pid) return out;
    var uids = readerState.hitUids;
    (readerState.sents || []).forEach(function (s) {
      if (!uids) return;                    // 沒數據 → 不篩（寧可全顯示）
      if (uids[s.uid]) out[s.para_seq] = 1;
    });
    return out;
  }

  function renderReader() {
    var hp = readerState.hitsOnly ? hitParas() : null;
    readerBody.innerHTML = renderParagraphs(readerState.sents, readerState.targetUid, hp);
    var total = paraCount();
    jumpBox.hidden = total < JUMP_MIN;
    jumpTotal.textContent = total ? " / " + total + " 段" : "";
    btnHits.hidden = !readerState.pid;
    btnHits.classList.toggle("on", !!readerState.hitsOnly);
    btnHits.textContent = readerState.hitsOnly ? "顯示全部段落" : "只看相關段落";
  }

  function jumpToPara(pno) {
    // 段號不在「只看相關」的範圍內時，先切回全文——否則定位不到
    if (readerState.hitsOnly) {
      var hp = hitParas();
      if (!(pno in hp)) { readerState.hitsOnly = false; renderReader(); }
    }
    var node = readerBody.querySelector('p[data-para="' + pno + '"]');
    if (!node) return false;
    readerBody.scrollTop += node.getBoundingClientRect().top -
                            readerBody.getBoundingClientRect().top -
                            readerBody.clientHeight * 0.3;
    var old = readerBody.querySelector("p.target");
    if (old) old.classList.remove("target");
    node.classList.add("target");
    return true;
  }
  // 離線快照是只讀的：沒有服務端可寫，重建按鈕留著只會讓人點了空轉
  if (OFF) { btnRebuild.hidden = true; btnRebuild.disabled = true; }

  function requestPost(path, body) {
    if (OFF) return Promise.reject(new Error("離線版是只讀快照，改動請用聯機版"));
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) {
        if (!r.ok) throw new Error(b.message || ("請求失敗（" + r.status + "）"));
        return b;
      });
    });
  }

  function syncEdstat(msg) {
    var n = Object.keys(pending).length;
    if (msg) { edstat.hidden = false; edstat.textContent = msg; return; }
    edstat.hidden = n === 0;
    edstat.textContent = n ? "已記錄 " + n + " 條編輯，重建後生效" : "";
    btnRebuild.hidden = n === 0;
  }

  /* 拆分不彈窗填數字，而是**點字選斷點**：想在哪裡斷，就點那個字。
     比輸入偏移直覺得多，也不容易填錯。 */
  function beginPick(p) {
    if (p.classList.contains("picking")) {   // 再點一次＝取消
      p.innerHTML = p.getAttribute("data-html") || p.innerHTML;
      p.classList.remove("picking");
      return;
    }
    var t = p.getAttribute("data-text") || "";
    p.setAttribute("data-html", p.innerHTML);
    p.classList.add("picking");
    p.innerHTML = t.split("").map(function (c, i) {
      return "<span class=\"ch\" data-i=\"" + (i + 1) + "\">" + esc(c) + "</span>";
    }).join("") + "<span class=\"acts\"><button data-act=\"cancel\">取消</button></span>";
  }

  function submitEdit(uid, action, at, p) {
    requestPost("/api/sentence/edit", { uid: uid, action: action, at: at || 0 })
      .then(function () {
        pending[uid] = action;
        syncEdstat();
        if (p) {
          p.classList.remove("picking");
          p.classList.add("edited");
        }
      })
      .catch(function (e) {
        syncEdstat("失敗：" + ((e && e.message) || e));
      });
  }

  readerBody.addEventListener("click", function (ev) {
    var p = ev.target.closest ? ev.target.closest("p[data-uid]") : null;
    if (!p) return;
    var uid = p.getAttribute("data-uid");
    var btn = ev.target.closest ? ev.target.closest(".acts button") : null;
    if (btn) {
      var act = btn.getAttribute("data-act");
      if (act === "cancel") { beginPick(p); return; }
      if (act === "split") { beginPick(p); return; }
      submitEdit(uid, act, 0, p);
      return;
    }
    var ch = ev.target.closest ? ev.target.closest(".ch") : null;
    if (ch && p.classList.contains("picking")) {
      submitEdit(uid, "split", parseInt(ch.getAttribute("data-i"), 10), p);
    }
  });

  /* 重建狀態要同時落到**兩個地方**：原文層頭上的 #edstat（句級編輯那套）
     與人物頁的 .ovbar（糾錯那套）。重建入口有兩個，兩邊都可能點，
     只寫一個的話從另一個入口點就是 30 秒靜默等待。 */
  function rebuildStatus(msg) {
    syncEdstat(msg);
    ovStatus(msg, currentPid);
  }

  /* 重建約 40 秒，後台跑、前端輪詢；跑完自動重開原文層 */
  function pollRebuild() {
    return request("/api/rebuild/status").then(function (s) {
      if (s.running) {
        var last = (s.log && s.log.length) ? s.log[s.log.length - 1] : "";
        rebuildStatus("重建中…" + String(last).slice(0, 24));
        return new Promise(function (r) { setTimeout(r, 1500); }).then(pollRebuild);
      }
      if (s.ok === false) {
        rebuildStatus("重建失敗，看服務端日誌");
        btnRebuild.disabled = false;
        return;
      }
      pending = {};
      btnRebuild.disabled = false;
      rebuildStatus("重建完成");
      if (readerCid) openChapter(readerCid);
      // 糾錯/編輯生效後當前頁是舊的（命中還按舊歸屬顯示），要重取一次
      if (typeof onRebuilt === "function") { var f = onRebuilt; onRebuilt = null; f(); }
    });
  }
  // 重建入口有兩處（原文層的按鈕 / 人物頁糾錯條），共用同一段，別抄第二遍
  function startRebuild() {
    if (btnRebuild.disabled) return;
    btnRebuild.disabled = true;
    rebuildStatus("正在啟動重建…");
    requestPost("/api/rebuild", {}).then(pollRebuild).catch(function (e) {
      rebuildStatus("重建失敗：" + ((e && e.message) || e));
      btnRebuild.disabled = false;
    });
  }
  btnRebuild.addEventListener("click", startRebuild);

  /* ---------- 原文層 ---------- */
  /* 跨句對話的續接標記（docs/21 §13 選 A 的改良版）：
     古籍一句裡常有多處「。！？」，按句讀斷就會把一對引號拆到兩句——
     這是**原文的本來面目**，不是 bug。所以這裡**只做顯示層**：
     承接上一句的段落給淡淡的續接標記，一句話沒說完的段落下方不留白。
     數據層（切分結果）一個字都不動。 */
  function renderParagraphs(sentences, targetUid, hitMap) {
    var open = 0;
    return (sentences || []).map(function (s) {
      var t = s.text || "";
      // 段落過濾（只看相關段落）：不在命中段裡的句子直接不渲染。
      // ⚠️ 續接標記的 open 計數**不能**被跳過的句子打斷——那會讓對話的
      // 引號計數錯位（後面全是「未收口」）。所以先掃全量算 open，
      // 再決定渲染哪些。
      var o = (t.match(/「/g) || []).length;
      var c = (t.match(/」/g) || []).length;
      var cont = open > 0;                 // 承接上一句尚未收口的對話
      open += o - c;
      if (open < 0) open = 0;              // 單句裡閉引號多於開引號，不往下傳
      if (hitMap && !(s.para_seq in hitMap)) return "";
      var cls = [];
      if (cont) cls.push("q-cont");
      if (open > 0) cls.push("q-open");
      if (s.uid === targetUid) cls.push("target");
      if (hitMap) cls.push("hitpara");
      // data-text 存原文：選斷點時要把句子拆成單字，那時 p 裡還混著按鈕文字
      return "<p data-uid=\"" + esc(s.uid) + "\" data-para=\"" +
        esc(String(s.para_seq == null ? "" : s.para_seq)) +
        "\" data-text=\"" + esc(t) + "\"" +
        (cls.length ? " class=\"" + cls.join(" ") + "\"" : "") + ">" +
        esc(t) + ACTS + "</p>";
    }).join("");
  }

  /* 每句 hover 出的三個動作。按鈕文案一律繁體（check_trad F 閘會掃）。
     離線版不給這三個按鈕——它們 POST 到服務端，離線寫不了，給了就是空頭支票。 */
  var ACTS = OFF ? "" : "<span class=\"acts\">" +
    "<button data-act=\"split\">拆分</button>" +
    "<button data-act=\"merge\">併下句</button>" +
    "<button data-act=\"dead\">棄用</button>" +
    "</span>";

  function openChapter(cid, uid, pid) {
    readerCid = cid;
    return request("/api/chapter/" + encodeURIComponent(cid)).then(function (d) {
      readerTitle.textContent = (d.chapter && d.chapter.full_title) || cid;
      readerState.sents = d.sentences || [];
      readerState.targetUid = uid || null;
      readerState.pid = pid || null;
      readerState.hitsOnly = false;
      renderReader();
      reader.classList.add("on");
      if (uid) {
        var el = readerBody.querySelector('p[data-uid="' + uid + '"]');
        if (el && el.scrollIntoView) el.scrollIntoView({ block: "center" });
      }
      syncBack();
    });
  }
  function closeReader() {
    if (!reader.classList.contains("on")) return;
    reader.classList.remove("on");
    syncBack();
  }
  reader.addEventListener("click", function (ev) {
    if (ev.target === reader) closeReader();
  });
  reader.querySelector('.reader-head button[data-act="close"]')
    .addEventListener("click", closeReader);
  reader.querySelector('.reader-head button[data-act="jump"]')
    .addEventListener("click", function () {
      var n = parseInt(jumpInput.value, 10);
      if (!(n > 0)) { jumpInput.focus(); return; }
      if (!jumpToPara(n)) {
        // 段號超出範圍：提示實際段數，别靜默無反應
        jumpInput.value = "";
        jumpInput.placeholder = "超出範圍";
      }
    });
  jumpInput.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") {
      ev.preventDefault();
      reader.querySelector('.reader-head button[data-act="jump"]').click();
    }
  });
  btnHits.addEventListener("click", function () {
    readerState.hitsOnly = !readerState.hitsOnly;
    renderReader();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeReader();
  });

  /* ---------- 回退：hash 路由（file:// 下 pushState 會拋異常，故一律走 hash）---------- */
  var lastWritten = null;
  function routeHash() {
    if (currentPid) return "#/person/" + currentPid;
    if (lastQuery) return "#/q/" + encodeURIComponent(lastQuery) + "/" + mode;
    return "#/";
  }
  function syncBack() {
    var onReader = reader.classList.contains("on");
    backBtn.hidden = !(history.length > 1 || currentPid || onReader);
    backBtn.textContent = onReader ? "← 關閉原文" : "← 返回";
  }
  /* ⚠️ hash 的正規化：**守衛與路由解析必須吃同一份**，否則兩邊打架。
     這裡踩過兩個坑，都很難查：
     1. `location.hash` 會把中文**百分號編碼**（鴻門 → %E9%B4%BB%E9%96%80），
        拿它跟自己寫的字串直接比**永遠不等**——「自己寫的不重渲染」這條守衛形同虛設，
        每次中文檢索都被當成「改了地址」再渲染一遍，把使用者剛點開的標籤頁頂回去。
     2. 只改守衛、沒同步改解析，或反之：`#/q/舜操/person` 這種形狀，
        正則裡的 `([^?]+)` 貪婪會把 `/person` 一起吞進查詢詞，
        於是下一輪寫出 `#/q/舜操%2Fperson/person`——**每點一次長一段**，
        最後 `/api/search?q=舜操/person/person/…` 超過 64 字上限變 422。
        （第 1 個坑一直遮著第 2 個：守衛失效時根本走不到解析那行，所以解析壞了沒人發現。）
     file:// 下還會把 "/" 也編成 %2F，所以解碼後再把 %2F 換回 "/"。
     解碼失敗就當地址被人手改壞了，用原值往下走，別讓它把頁面搞崩。 */
  function normHash(s) {
    try { return decodeURIComponent(s).replace(/%2F/gi, "/"); }
    catch (e) { return s; }
  }
  function hashOf() {
    return normHash(location.hash || "");
  }

  function writeHash() {
    var h = routeHash();
    // ⚠️ lastWritten 必須**兩條路徑都設**。以前只在下面寫 location.hash 那條設，
    // 結果「hash 已經是對的」而提前 return 時，lastWritten 留著**上一次**的值；
    // 而上一次寫入觸發的 hashchange 是異步到貨的，它拿著舊 lastWritten 對不上
    // → 被當成使用者改地址 → 又渲染一遍，把剛點的標籤頁頂回去。
    lastWritten = h;                       // 自己寫的不重渲染，只有後退/改地址才渲染
    if (hashOf() === normHash(h)) { syncBack(); return; }
    location.hash = h;
    syncBack();
  }
  function applyHash() {
    var h = hashOf();
    if (lastWritten && h === normHash(lastWritten)) {
      lastWritten = null; syncBack(); return;
    }
    lastWritten = null;
    // ⚠️ [^?#/]+：**不能讓查詢詞吞掉後面的 /person**（見 normHash 上方的坑 2）
    var m = /^#\/(person|q)(?:\/([^?#/]+))?(?:\/(fts|person))?$/.exec(h);
    if (!m) { currentPid = null; lastQuery = ""; return; }
    if (m[1] === "person" && m[2]) {
      renderPerson(decodeURIComponent(m[2])).then(syncBack).catch(showErr);
    } else if (m[1] === "q" && m[2]) {
      var q = decodeURIComponent(m[2]);
      mode = m[3] || "person";
      setModeUI();
      qEl.value = q;
      search(q);
    }
  }
  window.addEventListener("hashchange", applyHash);
  backBtn.addEventListener("click", function () {
    if (reader.classList.contains("on")) { closeReader(); return; }
    if (history.length > 1) history.back();
    else { location.hash = "#/"; }
  });

  /* ---------- 關係卡片：圖 + 列表 + 三個旋鈕 ----------
     有向邊在這裡最容易讀反：規範是 (a, rel, b) = 「a 是 b 的 rel」，
     所以**站在 a 的頁面上**，對方要叫「女 / 弟」，不能还写「父 / 兄」
     （「劉邦 之父 魯元公主」是拿父親的頭銜去稱呼女兒，docs/28 P0-1）。
     這個視角用詞由後端算好（`rel_view`），前端不自己維護第二份詞表。 */
  var relState = { degree: 1, minConf: 0 };

  function knob(label, on, k, v) {
    return "<span class=\"knob" + (on ? " on" : "") + "\" data-k=\"" + k +
      "\" data-v=\"" + v + "\">" + label + "</span>";
  }

  function relCardInner(pid, rel, st) {
    var nEdge = (rel.edges || []).length;
    var h = "<div class=\"person-head\">" +
      "<span class=\"name\" style=\"font-size:16px\">關係</span>" +
      "<span class=\"dyn\">" + nEdge + " 條</span>" +
      "<span class=\"rel-knobs\">" +
      knob("一跳", st.degree === 1, "degree", 1) +
      knob("二跳", st.degree === 2, "degree", 2) +
      knob("只看有證據", st.minConf >= 0.5, "minconf", 0.5) +
      "</span></div>";
    if (!nEdge) {
      return h + "<p class=\"summary\">尚無關係資料" +
        "（權威源 workbook/relations.xlsx）。</p>";
    }
    h += renderGraph(rel, { center: pid, width: 660 });
    var nameOf = {};
    (rel.nodes || []).forEach(function (n) { nameOf[n.id] = n; });
    h += "<div class=\"rel-list\">" + rel.edges.map(function (e) {
      var other = (e.source === pid) ? e.target : e.source;
      var n = nameOf[other] || {};
      var conf = (e.confidence == null) ? "" : "　" + e.confidence.toFixed(1);
      // 來源要看得見：手訂的與「從簡介自動抽的」不是一回事（docs/28 P2-3）
      var org = (e.origin === "auto-summary") ? "　簡介" :
        ((e.origin === "manual") ? "　手訂" : "");
      return "<div class=\"rel-row\" data-pid=\"" + esc(other) + "\">" +
        "<span class=\"rel\">" + esc(e.rel_view || e.rel || "") + "</span>" +
        "<span class=\"name\">" + esc(n.name || other) + "</span>" +
        "<span class=\"meta\">" + esc(n.dynasty || "") + conf + org + "</span>" +
        evTag(e) + "</div>";
    }).join("") + "</div>";
    return h;
  }

  /* 旋鈕是真的在用的：`/api/person/{pid}/relations` 的四個密度參數
     （docs/21 §12.4.1）以前一個都點不到，等於死參數（docs/28 P1-5）。 */
  function loadRelations(pid) {
    var st = relState;
    var url = "/api/person/" + encodeURIComponent(pid) +
      "/relations?degree=" + st.degree +
      (st.minConf ? "&min_conf=" + st.minConf : "");
    return request(url).then(function (d) {
      var box = document.getElementById("relcard");
      if (box) box.innerHTML = relCardInner(pid, d, st);
    });
  }

  /* ---------- 關係圖（P6-3）----------
     刻意**不引 ECharts**：本機離線工具不該有 CDN 依賴；單人局部圖多半不到十個節點，
     同心圓放射佈局就夠讀；自繪 SVG 也才能跟這套宣紙／朱砂的配色完全一致。
     輸入仍是 `{nodes, edges}`（docs/25 §五的契約），將來換引擎不影響上層。

     線的形狀帶資訊：**虛線＝無證據或低置信（推斷）**，實線＋箭頭＝規範邊有方向。
     點節點看那個人，點線上的關係詞跳證據原句。 */
  var NODE_H = 30;

  function evTag(e) {
    /* 一條關係可以有多條出處（docs/28 P1-6）：實測 12/62 條邊有 ≥2 句可用候選，
       只留主證據那一句等於丟證據。多條時逐條列出，每一條都點得開原文。 */
    var evs = e.evidences || [];
    if (evs.length > 1) {
      return evs.map(function (x, i) {
        var tag = "證據" + (i + 1);
        if (x.valid === 1) {
          return "<span class=\"rel-ev\" data-uid=\"" + esc(x.uid) +
            "\" data-chapter=\"" + esc(x.chapter || "") + "\">" + tag + "</span>";
        }
        return "<span class=\"rel-noev\">" + tag + "·句已改</span>";
      }).join("");
    }
    if (e.evidence_valid === 1) {
      return "<span class=\"rel-ev\" data-uid=\"" + esc(e.evidence_uid) +
        "\" data-chapter=\"" + esc(e.evidence_chapter || "") + "\">看證據</span>";
    }
    if (e.evidence_state === "dead" || e.evidence_state === "merged") {
      return "<span class=\"rel-noev\">證據句已改</span>";
    }
    if (e.evidence_state === "missing") {
      return "<span class=\"rel-noev\">證據句已失</span>";
    }
    return "<span class=\"rel-noev\">無證據</span>";
  }

  function nodeBox(n, id) {
    var full = (n && n.name) || id;
    var t = full.length > 6 ? full.slice(0, 6) + "…" : full;
    return { t: t, full: full, w: t.length * 15 + 18, h: NODE_H };
  }

  /* 軸對齊矩形與射線的交點：線要接在框邊上，不能插進框裡 */
  function edgePoint(p, b, ux, uy) {
    var hw = b.w / 2 + 4, hh = b.h / 2 + 4;
    var tx = Math.abs(ux) > 1e-6 ? hw / Math.abs(ux) : 1e9;
    var ty = Math.abs(uy) > 1e-6 ? hh / Math.abs(uy) : 1e9;
    var t = Math.min(tx, ty);
    return { x: p.x + ux * t, y: p.y + uy * t };
  }

  function renderGraph(adjacency, options) {
    options = options || {};
    var nodes = (adjacency && adjacency.nodes) || [];
    var edges = (adjacency && adjacency.edges) || [];
    if (!edges.length) return "";

    var byId = {}, center = null;
    nodes.forEach(function (n) {
      byId[n.id] = n;
      if (n.degree === 0 || n.id === options.center) center = n;
    });
    if (!center) center = nodes[0];
    if (!center) return "";

    /* 佈局：一跳均分內環，二跳掛在父節點外側（±0.42 弧度錯開）。
       deterministic，不做力導向——節點少，穩定比「好看」重要，
       且每次渲染位置一樣，才敢指著圖跟人講。 */
    var seen = {}; seen[center.id] = 1;
    var lvl1 = [];
    edges.forEach(function (e) {
      var o = (e.source === center.id) ? e.target
        : ((e.target === center.id) ? e.source : null);
      if (o && !seen[o]) { seen[o] = 1; lvl1.push(o); }
    });
    var R1 = 118, R2 = 214;
    var W = options.width || 660;
    var H = 2 * (lvl1.length > 8 ? R1 + 46 : R1) + 76;
    var cx = W / 2, cy = H / 2;
    var pos = {};
    pos[center.id] = { x: cx, y: cy };
    lvl1.forEach(function (id, i) {
      var ang = (-90 + (lvl1.length === 1 ? 0 : i * 360 / lvl1.length)) * Math.PI / 180;
      pos[id] = { x: cx + R1 * Math.cos(ang), y: cy + R1 * Math.sin(ang), ang: ang };
    });
    var nChild = {};
    edges.forEach(function (e) {
      if (e.source === center.id || e.target === center.id) return;
      var par = pos[e.source] ? e.source : (pos[e.target] ? e.target : null);
      if (!par || !pos[par].ang) return;
      var child = (par === e.source) ? e.target : e.source;
      if (seen[child]) return;
      seen[child] = 1;
      nChild[par] = (nChild[par] || 0) + 1;
      var k = nChild[par];
      var ang = pos[par].ang + (k % 2 ? -1 : 1) * Math.ceil(k / 2) * 0.42;
      pos[child] = { x: cx + R2 * Math.cos(ang), y: cy + R2 * Math.sin(ang), ang: ang };
      H = Math.max(H, 2 * R2 + 60);
    });

    var svg = "<svg class=\"rel-svg\" viewBox=\"0 0 " + W + " " + H +
      "\" width=\"100%\" height=\"" + H + "\">" +
      "<defs><marker id=\"relarrow\" markerWidth=\"9\" markerHeight=\"7\" " +
      "refX=\"8\" refY=\"3.5\" orient=\"auto\">" +
      "<path d=\"M0,0 L8,3.5 L0,7 z\" fill=\"#7A756B\"/></marker></defs>";

    edges.forEach(function (e) {
      var pa = pos[e.source], pb = pos[e.target];
      if (!pa || !pb) return;
      var ba = nodeBox(byId[e.source], e.source), bb = nodeBox(byId[e.target], e.target);
      var dx = pb.x - pa.x, dy = pb.y - pa.y;
      var len = Math.sqrt(dx * dx + dy * dy) || 1;
      var ux = dx / len, uy = dy / len;
      var s = edgePoint(pa, ba, ux, uy), t = edgePoint(pb, bb, -ux, -uy);
      var weak = (e.evidence_valid !== 1) ||
        (e.confidence != null && e.confidence < 0.5);
      var mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2;
      // rel_desc 是後端算好的完整句「A 是 B 之X」，不自己拼——拼就會讀反
      var tip = (e.rel_desc || "") +
        (e.evidence_valid === 1 ? "　（點一下看證據原句）" : "　（無證據，推斷）");
      svg += "<g class=\"rel-edge" + (weak ? " weak" : "") + "\" data-uid=\"" +
        esc(e.evidence_uid || "") + "\" data-chapter=\"" +
        esc(e.evidence_chapter || "") + "\">" +
        "<title>" + esc(tip) + "</title>" +
        "<line x1=\"" + s.x.toFixed(1) + "\" y1=\"" + s.y.toFixed(1) +
        "\" x2=\"" + t.x.toFixed(1) + "\" y2=\"" + t.y.toFixed(1) + "\"" +
        (e.symmetric ? "" : " marker-end=\"url(#relarrow)\"") + "/>" +
        /* 關係詞壓在線上，描邊同面板色「鏤空」，不然線會穿字 */
        "<text class=\"rel-label\" x=\"" + mx.toFixed(1) + "\" y=\"" +
        (my + 4).toFixed(1) + "\" text-anchor=\"middle\" " +
        "stroke=\"#FFFDF7\" stroke-width=\"3.5\" paint-order=\"stroke\">" +
        esc(e.rel_view || e.rel || "") + "</text></g>";
    });

    Object.keys(pos).forEach(function (id) {
      var p = pos[id], b = nodeBox(byId[id], id);
      var n = byId[id] || {};
      var isC = (id === center.id);
      svg += "<g class=\"rel-node" + (isC ? " is-center" : "") +
        "\" data-pid=\"" + esc(id) + "\">" +
        "<title>" + esc(b.full + (n.dynasty ? "（" + n.dynasty + "）" : "")) + "</title>" +
        "<rect x=\"" + (p.x - b.w / 2).toFixed(1) + "\" y=\"" +
        (p.y - b.h / 2).toFixed(1) + "\" width=\"" + b.w + "\" height=\"" + b.h +
        "\" rx=\"7\"/>" +
        "<text x=\"" + p.x.toFixed(1) + "\" y=\"" + (p.y + 5).toFixed(1) +
        "\" text-anchor=\"middle\">" + esc(b.t) + "</text></g>";
    });
    return svg + "</svg>";
  }
  window.renderGraph = renderGraph;

  /* 點關係線＝跳證據原句。沒有證據就**說清楚是推斷**，別默默不反應 */
  function openEvidence(g) {
    var uid = g.getAttribute("data-uid"), cid = g.getAttribute("data-chapter");
    if (!uid || !cid) {
      hint.textContent = "這條關係沒有證據句（取自人物簡介的推斷），圖上畫成虛線。";
      return;
    }
    openChapter(cid, uid).catch(showErr);
  }

  /* ---------- 互動 ---------- */
  function showErr(e) {
    out.innerHTML = "<div class=\"err\">" + esc((e && e.message) || e) + "</div>";
  }
  function setModeUI() {
    document.querySelectorAll(".modes span").forEach(function (el) {
      el.classList.toggle("on", el.getAttribute("data-mode") === mode);
    });
  }
  /* ---------- 書切換 + 快捷詞 + 四個標籤頁（對齊靜態版 web/）----------
     這四塊靜態版一直有，新版之前沒做——不是不想做，是 index.db 當初**漏了把
     地名命中入庫**（語料裡地名標記在 `pmarks`，建庫時只灌了人物的 `marks`），
     於是庫裡查不到任何地名計數，地名索引只能繞開資料庫去讀 JSON。
     補上 place_mentions 表之後，這幾塊就能正經從 /api/index 一次取回了。 */
  /* ⚠️ era = 該書記載的時代區間，值與 pipeline/annotate.py 的 era_index 同源。
     史記是通史，沒有區間（null）→ 全書不標「前朝」。
     這份常量與庫裡 books.era_from/era_to **必須一致**，verify_p3 [15] 會對一遍
     ——對不上不會報錯，只會標錯人（與 ALIAS_KINDS 順序同類型的壞）。 */
  var BOOKS = [
    { code: "sj", name: "史記", era: null },
    { code: "hs", name: "漢書", era: [8, 10] },
    { code: "hhs", name: "後漢書", era: [10, 11] },
    { code: "sgz", name: "三國志", era: [11, 12] },
    { code: "js", name: "晉書", era: [12, 15] }
  ];
  // 地名分組順序，與 pipeline/annotate_places.py 的 KIND_ORDER 一致
  var PLACE_KIND_ORDER = ["国", "郡", "县", "关", "山", "川", "湖", "域", "外"];

  var scopeBook = "";        // 空 = 全五書
  var currentTab = "search";
  var sortMode = "c";        // c = 篇數（默認），n = 次數
  var IDX = null;            // 索引資料緩存，換書才重取

  var bookbarEl = document.getElementById("books");
  var quickEl = document.getElementById("quick");

  function statText(n, c) {
    return (c || 0) + " 篇 / " + (n || 0).toLocaleString() + " 次";
  }

  function renderBookbar() {
    var h = '<span class="bk all' + (scopeBook === "" ? " on" : "") +
      '" data-book="">全部</span>';
    BOOKS.forEach(function (b) {
      h += '<span class="bk' + (scopeBook === b.code ? " on" : "") +
        '" data-book="' + b.code + '">' + esc(b.name) + "</span>";
    });
    bookbarEl.innerHTML = h;
  }

  /* 快捷詞按**當前書作用域**取（後端已按書算好 Top N）。
     換書後快捷詞跟著換——不會出現「選了漢書，頭一排全是漢書裡查不到的人」。 */
  function renderQuick() {
    if (!IDX) return;
    var q = IDX.quick || {};
    var h = (q.persons || []).map(function (p) {
      return '<span data-name="' + esc(p.name) + '">' + esc(p.name) +
        '<b class="qn">' + (p.n || 0).toLocaleString() + "</b></span>";
    }).join("");
    h += '<i class="sep"></i>';
    h += (q.places || []).map(function (p) {
      return '<span class="land" data-name="' + esc(p.name) + '">' + esc(p.name) +
        '<b class="qn">' + (p.n || 0).toLocaleString() + "</b></span>";
    }).join("");
    quickEl.innerHTML = h;
  }

  /* 「前朝」標記：斷代史裡出現的**前朝人**（《漢書》裡的孔子就是）。
     兩條不標的規矩：① 沒選書、或選的是通史（史記無區間）→ 不標；
     ② 人沒斷出時代（eraRank 為 null，169 人）→ 不標，**不猜**。
     ⚠️ 判斷放在前端：離線版沒有服務端，跟 aliasScopeN 同一個道理；
     數據（eraRank / 時代區間）則由後端給，前端只比大小。 */
  function isFormerEra(p) {
    var b = null;
    if (!scopeBook || p.eraRank == null) return false;
    BOOKS.forEach(function (x) { if (x.code === scopeBook) b = x; });
    return !!(b && b.era && p.eraRank < b.era[0]);
  }

  function indexGrid(items) {
    var h = '<div class="grid">';
    items.forEach(function (p) {
      h += '<div class="item" data-name="' + esc(p.name) + '" title="' +
        esc(p.summary || "") + '"><span class="n">' + esc(p.name) +
        (isFormerEra(p) ? '<i class="era-old" title="本書記載時代之前的' +
         '人物（前朝）">前朝</i>' : "") +
        '</span><span class="c">' + statText(p.n, p.c) + "</span></div>";
    });
    return h + "</div>";
  }

  function sortLabel() {
    return sortMode === "c" ? "按提及篇數排序" : "按提及次數排序";
  }
  /* 排序切換只在前端重排，不重新請求——資料已經在 IDX 裡了。 */
  function resort(items) {
    return items.slice().sort(function (a, b) {
      var ka = sortMode === "c" ? (a.c || 0) : (a.n || 0);
      var kb = sortMode === "c" ? (b.c || 0) : (b.n || 0);
      return kb - ka || (b.n || 0) - (a.n || 0);
    });
  }

  function renderPersonsIndex() {
    var items = resort(((IDX || {}).persons || {}).items || []);
    var h = '<div class="group-title">人物索引 <span class="count">' +
      items.length.toLocaleString() + ' 人 · <span class="sort-toggle" ' +
      'role="button" tabindex="0">' + sortLabel() + '</span> · 懸停看簡介</span></div>';
    h += indexGrid(items);
    out.innerHTML = h;
  }

  function renderPlacesIndex() {
    var items = resort(((IDX || {}).places || {}).items || []);
    var groups = {};
    items.forEach(function (p) {
      (groups[p.kind] = groups[p.kind] || []).push(p);
    });
    var h = "";
    PLACE_KIND_ORDER.forEach(function (k) {
      var one = groups[k];
      if (!one || !one.length) return;
      h += '<div class="group-title">' + esc((one[0].kindLabel) || k) +
        ' <span class="count">' + one.length.toLocaleString() + " 個</span></div>";
      h += indexGrid(one);
    });
    out.innerHTML = h;
  }

  /* 篇目一覽：書 → 類別 → 篇。
     為什麼書內還要按類別分：史記 130 篇一路平鋪下去，找「項羽本紀」要滾很久；
     本紀/世家/列傳/表/書/載記 是原書自己的分卷方式，沿用它最省力。 */
  var CAT_ORDER = ["本紀", "世家", "列傳", "表", "書", "載記", "其他"];

  function chapterRow(c) {
    // 篇主可能列了五六個（五帝本紀那種），標籤欄放不下——只留前三
    var tags = "";
    (c.mainPersons || []).slice(0, 3).forEach(function (n) {
      tags += '<span class="tag">' + esc(n) + "</span>";
    });
    if ((c.topPlaces || []).length) {
      tags += '<span class="tag">地：' + esc(c.topPlaces.join("、")) + "</span>";
    }
    return '<div class="chap-row" data-chapter="' + esc(c.id) + '">' +
      '<span class="n">' + esc(c.title) +
      (c.category ? '<span class="cat">' + esc(c.category) + "</span>" : "") +
      tags + '</span><span class="meta">' +
      (c.charCount || 0).toLocaleString() + " 字 · " +
      (c.sentenceCount || 0) + " 句</span></div>";
  }

  function renderChaptersIndex() {
    var items = (((IDX || {}).chapters) || {}).items || [];
    var byBook = {};
    items.forEach(function (c) {
      (byBook[c.book] = byBook[c.book] || []).push(c);
    });
    var h = "";
    BOOKS.forEach(function (b) {
      var one = byBook[b.code];
      if (!one || !one.length) return;
      h += '<div class="book-title">' + esc(b.name) +
        '<span class="count">' + one.length + " 篇</span></div>";
      var byCat = {};
      one.forEach(function (c) {
        (byCat[c.category || "其他"] = byCat[c.category || "其他"] || []).push(c);
      });
      CAT_ORDER.forEach(function (cat) {
        var cs = byCat[cat];
        if (!cs || !cs.length) return;
        h += '<div class="group-title">' + esc(cat) +
          ' <span class="count">' + cs.length + " 篇</span></div>";
        h += '<div class="card">' + cs.map(chapterRow).join("") + "</div>";
      });
    });
    out.innerHTML = h;
  }

  function renderCurrentTab() {
    if (currentTab === "persons") renderPersonsIndex();
    else if (currentTab === "places") renderPlacesIndex();
    else if (currentTab === "chapters") renderChaptersIndex();
  }

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".tabs span").forEach(function (el) {
      el.classList.toggle("on", el.getAttribute("data-tab") === tab);
    });
    if (tab === "search") {
      if (lastQuery) search(lastQuery);
      else search("劉邦");
      return;
    }
    if (!IDX) { loadIndex(renderCurrentTab); return; }
    renderCurrentTab();
  }

  /* 輸入框候選：靜態版一直有，新版補索引頁時漏了。
     共 3815 個 option（2240 人 + 1575 地），全量塞進 datalist 瀏覽器扛得住，
     而且換書時它跟著索引一起換——比另開一個 /api/names 端點省事。 */
  function fillDatalist() {
    var dl = document.getElementById("names");
    if (!dl) return;
    var h = "";
    (((IDX || {}).persons || {}).items || []).forEach(function (p) {
      h += '<option value="' + esc(p.name) + '">' +
        esc((p.dynasty || "") + (p.title ? " · " + p.title : "")) + "</option>";
    });
    (((IDX || {}).places || {}).items || []).forEach(function (p) {
      h += '<option value="' + esc(p.name) + '">' +
        esc("地名 · " + (p.kindLabel || p.kind)) + "</option>";
    });
    dl.innerHTML = h;
  }

  function loadIndex(cb) {
    request("/api/index?book=" + encodeURIComponent(scopeBook) +
            "&sort=" + sortMode).then(function (d) {
      IDX = d;
      renderQuick();
      fillDatalist();
      cb && cb();
    }).catch(showErr);
  }

  bookbarEl.addEventListener("click", function (ev) {
    var bk = ev.target.closest ? ev.target.closest(".bk[data-book]") : null;
    if (!bk) return;
    var code = bk.getAttribute("data-book");
    if (code === scopeBook) return;
    scopeBook = code;
    renderBookbar();
    // 換書後快捷詞要跟著換；索引頁也要重取（計數是按書算的）
    if (currentTab === "search") loadIndex();
    else loadIndex(renderCurrentTab);
  });

  quickEl.addEventListener("click", function (ev) {
    var sp = ev.target.closest ? ev.target.closest("span[data-name]") : null;
    if (!sp) return;
    switchTab("search");
    qEl.value = sp.getAttribute("data-name");
    search(qEl.value);
  });

  document.querySelectorAll(".tabs span").forEach(function (el) {
    el.addEventListener("click", function () {
      switchTab(el.getAttribute("data-tab"));
    });
  });

  function search(query) {
    query = (query || "").trim();
    if (!query) return;
    lastQuery = query;
    currentPid = null;
    var url = mode === "fts"
      ? "/api/fts?q=" + encodeURIComponent(query)
      : "/api/search?q=" + encodeURIComponent(query);
    request(url).then(function (d) {
      if (mode === "fts") renderFts(d.items || [], query);
      else renderResults(d.items || [], query);
      writeHash();
    }).catch(showErr);
  }

  document.querySelectorAll(".modes span").forEach(function (el) {
    el.addEventListener("click", function () {
      mode = el.getAttribute("data-mode");
      setModeUI();
      if (lastQuery) search(lastQuery);
    });
  });
  document.getElementById("btn").addEventListener("click", function () {
    search(qEl.value);
  });
  qEl.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") search(ev.target.value);
  });
  out.addEventListener("click", function (ev) {
    // 索引面板：點條目 = 拿這個名字去檢索（人物/地名都走同一個入口）
    var it = ev.target.closest ? ev.target.closest(".item[data-name]") : null;
    if (it) {
      qEl.value = it.getAttribute("data-name");
      search(qEl.value);
      return;
    }
    // 篇目一覽：點篇目 = 開原文層
    var cr = ev.target.closest ? ev.target.closest(".chap-row[data-chapter]") : null;
    if (cr) {
      openChapter(cr.getAttribute("data-chapter"), null).catch(showErr);
      return;
    }
    // 索引分組標題上的排序開關（篇數 ⇄ 次數）
    var tg = ev.target.closest ? ev.target.closest(".sort-toggle") : null;
    if (tg) {
      sortMode = sortMode === "c" ? "n" : "c";
      renderCurrentTab();
      return;
    }
    var row = ev.target.closest ? ev.target.closest(".row[data-pid]") : null;
    if (row) { renderPerson(row.getAttribute("data-pid")).then(writeHash).catch(showErr); return; }
    // 糾錯條上的「重建」
    var ovr = ev.target.closest ? ev.target.closest("button[data-act=\"ovrebuild\"]") : null;
    if (ovr) {
      onRebuilt = function () { renderPerson(currentPid); };
      startRebuild();
      return;
    }
    // 網頁「標錯」入口。⚠️ 必須排在「點句子開原文」**之前**——
    // 按鈕就在命中行裡，晚一步就被當成「點了句子」把原文層頂開。
    var actBtn = ev.target.closest ? ev.target.closest("button[data-act]") : null;
    var act = actBtn ? actBtn.getAttribute("data-act") : "";
    if (act === "flag") { openFixBox(actBtn.closest(".sent")); return; }
    if (act === "unflag") { submitUnflag(actBtn.closest(".sent")); return; }
    var box = ev.target.closest ? ev.target.closest(".fixbox") : null;
    if (box) {
      if (act === "cancel") { box.parentNode.removeChild(box); return; }
      if (act === "drop") { submitFlag(box, "drop"); return; }
      var cr = ev.target.closest ? ev.target.closest(".fix-cand-row") : null;
      if (cr) { submitFlag(box, "reassign", cr.getAttribute("data-pid")); return; }
      return;                      // 點在面板空白處：別冒泡去開原文
    }
    // 關係卡片的三個旋鈕（一跳 / 二跳 / 只看有證據）
    var kb = ev.target.closest ? ev.target.closest(".knob[data-k]") : null;
    if (kb) {
      var k = kb.getAttribute("data-k"), v = Number(kb.getAttribute("data-v"));
      if (k === "degree") relState.degree = (relState.degree === v) ? 1 : v;
      else relState.minConf = relState.minConf >= 0.5 ? 0 : (v || 0.5);
      loadRelations(currentPid).catch(showErr);
      return;
    }
    // 關係圖：點節點看人、點線看證據句（證據徽章同理，它在關係行裡）
    var evBtn = ev.target.closest ? ev.target.closest(".rel-ev[data-uid]") : null;
    if (evBtn) { openEvidence(evBtn); return; }
    var gNode = ev.target.closest ? ev.target.closest(".rel-node[data-pid]") : null;
    if (gNode) {
      renderPerson(gNode.getAttribute("data-pid")).then(writeHash).catch(showErr);
      return;
    }
    var gEdge = ev.target.closest ? ev.target.closest(".rel-edge") : null;
    if (gEdge) { openEvidence(gEdge); return; }
    // 關係行：點進去看那個人
    var relRow = ev.target.closest ? ev.target.closest(".rel-row[data-pid]") : null;
    if (relRow) { renderPerson(relRow.getAttribute("data-pid")).then(writeHash).catch(showErr); return; }
    var s = ev.target.closest ? ev.target.closest(".sent[data-chapter]") : null;
    if (s) {
      // 傳 currentPid：原文層才知道「只看相關段落」該留哪些段
      openChapter(s.getAttribute("data-chapter"), s.getAttribute("data-uid"),
                  currentPid).catch(showErr);
    }
  });

  /* ---------- 啟動 ---------- */
  request("/api/stats").then(function (s) {
    document.getElementById("sub").textContent =
      "史記 · 漢書 · 後漢書 · 三國志 · 晉書　—　" +
      s.persons.toLocaleString() + " 人 / " + s.sentences.toLocaleString() + " 句 / " +
      s.mentions.toLocaleString() + " 處命中" +
      (OFF ? "　·　離線快照（只讀）" : "");
  }).catch(function () { /* 統計拿不到就算了，不擋主流程 */ });

  renderBookbar();
  // 索引資料後台取，不擋首屏檢索（約 2 秒，取完快捷詞才出現）
  loadIndex();

  if (location.hash) applyHash();
  else search("劉邦");
})();
