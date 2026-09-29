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

  /* ---------- 請求層：錯誤要映射成人話，4xx 不重試、5xx 最多重試 3 次 ---------- */
  function request(path, retry) {
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
  function renderPerson(pid) {
    return request("/api/person/" + encodeURIComponent(pid)).then(function (d) {
      var p = d.profile;
      var html = "<div class=\"card\">" +
        "<div class=\"person-head\"><span class=\"name\">" + esc(p.trad_name) + "</span>" +
        "<span class=\"dyn\">" + esc(p.dynasty || "") +
        (p.title ? " · " + esc(p.title) : "") + "</span></div>";
      if (p.summary) html += "<p class=\"summary\">" + esc(p.summary) + "</p>";
      if (p.aliases && p.aliases.length) {
        html += "<div style=\"margin-top:10px\">" + p.aliases.map(function (a) {
          return "<span class=\"alias-tag\">" + esc(a) + "</span>";
        }).join("") + "</div>";
      }
      html += "</div>";

      // 命中按篇分組
      var groups = [], byId = {};
      (d.mentions || []).forEach(function (m) {
        var key = m.chapter_id;
        if (!byId[key]) { byId[key] = { title: m.chapter, rows: [] }; groups.push(byId[key]); }
        byId[key].rows.push(m);
      });
      if (!groups.length) {
        html += "<div class=\"empty\">此人在目前語料裡沒有命中。</div>";
      }
      groups.forEach(function (g) {
        html += "<div class=\"chapter-title\">" + esc(g.title || "") +
          " · " + g.rows.length + " 處</div>";
        g.rows.forEach(function (m) {
          html += "<div class=\"sent\" data-chapter=\"" + esc(m.chapter_id) +
            "\" data-uid=\"" + esc(m.uid) + "\">" +
            markSentence(m.text, m.surface, m.tier) + "</div>";
        });
      });

      html += "<div class=\"card\" style=\"margin-top:14px\">" +
        "<div class=\"person-head\"><span class=\"name\" style=\"font-size:16px\">關係圖</span>" +
        "<span class=\"dyn\">預留</span></div>" +
        "<p class=\"summary\">關係資料尚未灌入（relations 表已建好）。" +
        "確認關係範圍後即可顯示。</p></div>";

      out.innerHTML = html;
      hint.textContent = "實線＝正名或別名直接命中；虛線＋？＝泛稱推斷，待確認。";
      currentPid = pid;
    });
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

  function requestPost(path, body) {
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

  /* 重建約 40 秒，後台跑、前端輪詢；跑完自動重開原文層 */
  function pollRebuild() {
    return request("/api/rebuild/status").then(function (s) {
      if (s.running) {
        var last = (s.log && s.log.length) ? s.log[s.log.length - 1] : "";
        syncEdstat("重建中…" + String(last).slice(0, 24));
        return new Promise(function (r) { setTimeout(r, 1500); }).then(pollRebuild);
      }
      if (s.ok === false) {
        syncEdstat("重建失敗，看服務端日誌");
        btnRebuild.disabled = false;
        return;
      }
      pending = {};
      btnRebuild.disabled = false;
      syncEdstat("重建完成");
      if (readerCid) openChapter(readerCid);
    });
  }
  btnRebuild.addEventListener("click", function () {
    if (btnRebuild.disabled) return;
    btnRebuild.disabled = true;
    syncEdstat("正在啟動重建…");
    requestPost("/api/rebuild", {}).then(pollRebuild).catch(function (e) {
      syncEdstat("重建失敗：" + ((e && e.message) || e));
      btnRebuild.disabled = false;
    });
  });

  /* ---------- 原文層 ---------- */
  /* 跨句對話的續接標記（docs/21 §13 選 A 的改良版）：
     古籍一句裡常有多處「。！？」，按句讀斷就會把一對引號拆到兩句——
     這是**原文的本來面目**，不是 bug。所以這裡**只做顯示層**：
     承接上一句的段落給淡淡的續接標記，一句話沒說完的段落下方不留白。
     數據層（切分結果）一個字都不動。 */
  function renderParagraphs(sentences, targetUid) {
    var open = 0;
    return (sentences || []).map(function (s) {
      var t = s.text || "";
      var o = (t.match(/「/g) || []).length;
      var c = (t.match(/」/g) || []).length;
      var cont = open > 0;                 // 承接上一句尚未收口的對話
      open += o - c;
      if (open < 0) open = 0;              // 單句裡閉引號多於開引號，不往下傳
      var cls = [];
      if (cont) cls.push("q-cont");
      if (open > 0) cls.push("q-open");
      if (s.uid === targetUid) cls.push("target");
      // data-text 存原文：選斷點時要把句子拆成單字，那時 p 裡還混著按鈕文字
      return "<p data-uid=\"" + esc(s.uid) + "\" data-text=\"" + esc(t) + "\"" +
        (cls.length ? " class=\"" + cls.join(" ") + "\"" : "") + ">" +
        esc(t) + ACTS + "</p>";
    }).join("");
  }

  /* 每句 hover 出的三個動作。按鈕文案一律繁體（check_trad F 閘會掃）。 */
  var ACTS = "<span class=\"acts\">" +
    "<button data-act=\"split\">拆分</button>" +
    "<button data-act=\"merge\">併下句</button>" +
    "<button data-act=\"dead\">棄用</button>" +
    "</span>";

  function openChapter(cid, uid) {
    readerCid = cid;
    return request("/api/chapter/" + encodeURIComponent(cid)).then(function (d) {
      readerTitle.textContent = (d.chapter && d.chapter.full_title) || cid;
      readerBody.innerHTML = renderParagraphs(d.sentences, uid);
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
  function writeHash() {
    var h = routeHash();
    if (location.hash === h) { syncBack(); return; }
    lastWritten = h;                       // 自己寫的不重渲染，只有後退/改地址才渲染
    location.hash = h;
    syncBack();
  }
  function applyHash() {
    var h = location.hash || "";
    if (lastWritten && h === lastWritten) { lastWritten = null; syncBack(); return; }
    lastWritten = null;
    var m = /^#\/(person|q)(?:\/([^?]+))?(?:\/(fts|person))?$/.exec(h);
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

  /* ---------- 關係圖預留：接口先定死，將來換 ECharts 不影響上層 ---------- */
  function renderGraph(adjacency, options) {
    // 目前無資料。將來這裡接 ECharts，輸入固定為 { nodes, edges }。
    return adjacency;
  }
  window.renderGraph = renderGraph;

  /* ---------- 互動 ---------- */
  function showErr(e) {
    out.innerHTML = "<div class=\"err\">" + esc((e && e.message) || e) + "</div>";
  }
  function setModeUI() {
    document.querySelectorAll(".modes span").forEach(function (el) {
      el.classList.toggle("on", el.getAttribute("data-mode") === mode);
    });
  }
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
    var row = ev.target.closest ? ev.target.closest(".row[data-pid]") : null;
    if (row) { renderPerson(row.getAttribute("data-pid")).then(writeHash).catch(showErr); return; }
    var s = ev.target.closest ? ev.target.closest(".sent[data-chapter]") : null;
    if (s) {
      openChapter(s.getAttribute("data-chapter"), s.getAttribute("data-uid")).catch(showErr);
    }
  });

  /* ---------- 啟動 ---------- */
  request("/api/stats").then(function (s) {
    document.getElementById("sub").textContent =
      "史記 · 漢書 · 後漢書 · 三國志 · 晉書　—　" +
      s.persons.toLocaleString() + " 人 / " + s.sentences.toLocaleString() + " 句 / " +
      s.mentions.toLocaleString() + " 處命中";
  }).catch(function () { /* 統計拿不到就算了，不擋主流程 */ });

  if (location.hash) applyHash();
  else search("劉邦");
})();
