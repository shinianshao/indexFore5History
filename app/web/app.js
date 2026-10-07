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
  // 地名頁的當前地名。與 currentPid **分開兩個變數**，別複用：
  // 人物頁有「關係圖節點 → 跳另一個人」這類互相跳轉，一個字段頂兩個用會跳錯頁。
  var currentPlace = null;
  var lastQuery = "";
  // 原文層狀態。聲明放在這裡（而不是用它的函數附近），
  // 因為 renderPerson 在上面就會寫 hitUids —— 分散聲明只靠 var 提升才不出錯，
  // 順序一變就變成 undefined。
  var readerState = { sents: [], scope: null, hitsOnly: false, hitUids: null,
                      hitsByUid: null, targetUid: null, properNounsOn: true };

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
    var d = {
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
        // book：篩選器與「共 N 處」都要認書（chaps[篇] = [全名, 書號, start, end)）
        var bk = (D.chaps[s[1]] || [])[1] || "";
        return { chapter: CHAPT[s[1]] || "", chapter_id: s[1], uid: s[0],
                 text: s[2], surface: m[1], s: m[2], e: m[3], tier: m[4],
                 book: bk };
      }),
      // 全量分書分佈（聯機由 db.person_payload 給，離線由 export_static 的 pmbk 還原）。
      // ⚠️ 兩邊**同形**：都是 {書號: 次數}，前端只寫一套計數代碼。
      mentionByBook: mbkFromArray(D.pmbk && D.pmbk[pid]),
      eraNames: D.eraNames || [],
      // 注文：離線版與聯機版**同源**（同一份 pei-data.json / js-note-data.json），
      // 形狀也一樣，所以 notesSection 一段代碼兩邊都能用。
      notes: offNotes(pid),
      relations: offRel(pid, "1:0"),
      // 主要行跡與兵爭輿地交集
      topPlaces: ((D.p2pl || {})[pid] || []).map(function (item) {
        var pl = (D.pla || {})[item[0]];
        return {
          id: item[0],
          trad_name: pl ? pl[0] : item[0],
          name: pl ? pl[1] : item[0],
          kind: pl ? pl[2] : "",
          n: item[1],
          isStrategic: !!((D.strat || {})[item[0]])
        };
      }),
      // 涉足的全部 43 處兵爭要衝（無截斷）
      strategicHubs: ((D.p2strat || {})[pid] || []).map(function (item) {
        var pl = (D.pla || {})[item[0]];
        var st = (D.strat || {})[item[0]] || {};
        return {
          id: item[0],
          trad_name: pl ? pl[0] : item[0],
          name: pl ? pl[1] : item[0],
          n: item[1],
          zone: st.zone || "",
          connections: st.connections || []
        };
      })
    };
    d.sgzBreakdown = computeSgzBreakdown(d);
    return d;
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
  /* ---------- 地名（離線）----------
     形狀必須與聯機 `db.place_payload` **逐字一致**（同源同形是離線/聯機一致性的
     前提，見 MEMORY「響應體組裝放 db層」）。壓縮格式：
       D.pla[pid]  = [繁名, 簡名, 類, 類說明, 時代, 簡介]
       D.plalias   = {pid: [[寫法, 次數, {書: 次}], …]}
       D.pmen      = {pid: [[句下標, surface, s, e, tier], …]}   ← 句序指 D.sents 下標
       D.plbook[pid] = [{id: 書號, name: 書名, n: 次數}, …]
     ⚠️ 與 `offPerson` 一致：**mentions 不截斷**。人物側給全（曹操 2064 處），
     地名側也給全（單字「江」上千處）——「只多不少」是這裡的刻意差異，
     截一半反而會讓離線版比聯機版少，變成另一種分叉。 */
  function offPlace(pid) {
    var p = D.pla[pid];
    if (!p) return null;
    var topP = ((D.pl2p || {})[pid] || []).map(function (item) {
      var pr = (D.pers || {})[item[0]];
      return {
        id: item[0],
        trad_name: pr ? pr[0] : item[0],
        name: pr ? pr[1] : item[0],
        n: item[1]
      };
    });
    return {
      profile: { id: pid, trad_name: p[0], name: p[1], kind: p[2],
                 kindLabel: p[3], era: p[4], summary: p[5] },
      mentions: (D.pmen[pid] || []).map(function (m) {
        var s = D.sents[m[0]];
        if (!s) return null;          // 句被棄用後從 sents 消失，命中就懸空了
        return { chapter: CHAPT[s[1]] || "", chapter_id: s[1], uid: s[0],
                 text: s[2], surface: m[1], s: m[2], e: m[3], tier: m[4],
                 book: (D.chaps[s[1]] || [])[1] || "" };
      }).filter(Boolean),
      books: D.plbook[pid] || [],
      mentionByBook: mbkFromArray(D.plbk && D.plbk[pid]),
      eraNames: D.eraNames || [],
      aliases: (D.plalias[pid] || []).map(function (a) {
        return { w: a[0], n: a[1], byBook: a[2] || {} };
      }),
      strategic: (D.strat || {})[pid] || null,
      topPersons: topP
    };
  }

  /* 地名檢索：正名 / 簡名 / 異體寫法（異體是簡體能搜到的關鍵——
     places 主表的 name 與 trad_name 逐行相同，只比它們等於簡體輸入失明）。 */
  function offSearchPlaces(q, limit) {
    var got = [];
    for (var pid in D.pla) {
      var p = D.pla[pid];
      var hit = p[0].indexOf(q) >= 0 || p[1].indexOf(q) >= 0;
      if (!hit) {
        var al = D.plalias[pid] || [];
        for (var i = 0; !hit && i < al.length; i++) {
          if (al[i][0].indexOf(q) >= 0) hit = true;
        }
      }
      if (hit) {
        got.push({ id: pid, trad_name: p[0], name: p[1], kind: p[2],
                   kindLabel: p[3], era: p[4], summary: p[5],
                   n: (D.pmen[pid] || []).length,
                   books: (D.plbook[pid] || []).slice(0, 3) });
      }
    }
    got.sort(function (a, b) { return b.n - a.n; });
    return got.slice(0, limit);
  }

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
    // ⚠️ 形狀與聯機 `/api/search` 一致：{query, items, places}。
    return { query: q, items: got.slice(0, limit),
             places: offSearchPlaces(q, limit) };
  }

  function computeSgzBreakdown(d) {
    if (!d) return null;
    if (d.sgzBreakdown) return d.sgzBreakdown;
    var mentions = d.mentions || [];
    var pei = (d.notes && d.notes.pei) || null;
    var peiByChap = (pei && pei.byChapter) || {};

    var wei_main_n = 0, shu_main_n = 0, wu_main_n = 0;
    var wei_chaps = {}, shu_chaps = {}, wu_chaps = {};

    mentions.forEach(function (m) {
      var cid = m.chapter_id || "";
      if (cid.indexOf("sgz-") === 0) {
        var vol = parseInt(cid.split("-")[1], 10);
        if (vol >= 1 && vol <= 30) {
          wei_main_n++;
          wei_chaps[cid] = true;
        } else if (vol >= 31 && vol <= 45) {
          shu_main_n++;
          shu_chaps[cid] = true;
        } else if (vol >= 46 && vol <= 65) {
          wu_main_n++;
          wu_chaps[cid] = true;
        }
      }
    });

    var wei_main_c = Object.keys(wei_chaps).length;
    var shu_main_c = Object.keys(shu_chaps).length;
    var wu_main_c = Object.keys(wu_chaps).length;
    var main_tot_n = wei_main_n + shu_main_n + wu_main_n;
    var main_tot_c = wei_main_c + shu_main_c + wu_main_c;

    var wei_pei_n = 0, shu_pei_n = 0, wu_pei_n = 0;
    var wei_pei_c = 0, shu_pei_c = 0, wu_pei_c = 0;

    Object.keys(peiByChap).forEach(function (cid) {
      if (cid.indexOf("sgz-") === 0) {
        var vol = parseInt(cid.split("-")[1], 10);
        var cnt = Number(peiByChap[cid]) || 0;
        if (vol >= 1 && vol <= 30) {
          wei_pei_n += cnt;
          wei_pei_c++;
        } else if (vol >= 31 && vol <= 45) {
          shu_pei_n += cnt;
          shu_pei_c++;
        } else if (vol >= 46 && vol <= 65) {
          wu_pei_n += cnt;
          wu_pei_c++;
        }
      }
    });

    var pei_tot_n = wei_pei_n + shu_pei_n + wu_pei_n;
    var pei_tot_c = wei_pei_c + shu_pei_c + wu_pei_c;
    var comb_tot_n = main_tot_n + pei_tot_n;

    if (comb_tot_n === 0) return null;

    return {
      main: {
        wei: { n: wei_main_n, c: wei_main_c },
        shu: { n: shu_main_n, c: shu_main_c },
        wu: { n: wu_main_n, c: wu_main_c },
        total: { n: main_tot_n, c: main_tot_c }
      },
      pei: {
        wei: { n: wei_pei_n, c: wei_pei_c },
        shu: { n: shu_pei_n, c: shu_pei_c },
        wu: { n: wu_pei_n, c: wu_pei_c },
        total: { n: pei_tot_n, c: pei_tot_c }
      },
      combined: {
        wei: { n: wei_main_n + wei_pei_n },
        shu: { n: shu_main_n + shu_pei_n },
        wu: { n: wu_main_n + wu_pei_n },
        total: { n: comb_tot_n }
      }
    };
  }

  function offNarrowIndex(fullIdx, bkStr) {
    if (!fullIdx || !bkStr) return fullIdx;
    var bks = bkStr.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    if (!bks.length) return fullIdx;
    var bSet = {};
    bks.forEach(function (b) { bSet[b] = true; });

    var pItems = ((fullIdx.persons || {}).items || []).filter(function (p) {
      var bkList = (p.books || []).filter(function (b) { return bSet[b.id]; });
      if (!bkList.length) return false;
      var nAll = 0, cAll = 0;
      bkList.forEach(function (b) { nAll += (b.n || 0); cAll += (b.c || 0); });
      p.n = nAll;
      p.c = cAll;
      return nAll > 0;
    });

    var lItems = ((fullIdx.places || {}).items || []).slice();

    var cItems = ((fullIdx.chapters || {}).items || []).filter(function (c) {
      return bSet[c.book];
    });

    return {
      book: bkStr,
      sort: fullIdx.sort || "c",
      persons: { total: pItems.length, items: pItems },
      places: { total: lItems.length, items: lItems },
      chapters: { books: fullIdx.chapters.books, items: cItems },
      quick: fullIdx.quick || { persons: [], places: [] }
    };
  }

  function offlineGet(path) {
    var u = path.replace(/^\/?api\//, ""), m;
    if (u === "stats") return Promise.resolve(D.stats);
    if (u.indexOf("index") === 0) {
      var bk = (u.match(/book=([^&]*)/) || [0, ""])[1];
      bk = decodeURIComponent(bk);
      if (D.idx[bk]) return Promise.resolve(D.idx[bk]);
      if (bk && D.idx[""]) {
        return Promise.resolve(offNarrowIndex(D.idx[""], bk));
      }
      return Promise.resolve(D.idx[""]);
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
    // ⚠️ 必须排在 `person/` 之后无关（路由不同名），但**别漏**：
    //    漏了的话离线版点地名条会掉到最后的 reject，点任何地名都报「離線版沒有這個接口」。
    if ((m = u.match(/^place\/([^/?]+)/))) {
      var plid = decodeURIComponent(m[1]);
      var pd = offPlace(plid);
      return pd ? Promise.resolve(pd)
                : Promise.reject(new Error("查無此地：" + plid));
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

  /* 標色位置必須**用庫給的 s/e**，不能 indexOf。
     為什麼：同一句裡同一個詞可能出現多次（「舜…堯…舜」），indexOf 恆落第一處，
     會標到不相干的語境上。實測 182128 條命中裡 8319 條（4.6%）標錯位置。

     （此數字由 app/tools/verify_p3_mark.py 每次全量重算，改動前先跑一次，別手抄。）

     ⚠️ 但**也不能只改成 text.slice(s, e)**：`s`/`e` 是 Python 算的**碼位**下標，
     JS 的 slice 按 **UTF-16 碼元**——古籍裡有非 BMP 字（U+24CF9、U+23D40 這類
     罕用異體字），一個字算兩個碼元，位置就整個偏了。實測會新造 63 條錯標。
     所以三級回退，每一級都以「切出來的字串 === surface」為判據：
       A. text.slice(s, e)          —— 快，覆蓋 182065/182128（99.97%）
       B. Array.from(text) 按碼位切 —— 修那63 條非 BMP
       C. indexOf(surface)          —— 最後兜底（s/e 缺失或兩級都不符時）
     判據是**字串相等**不是「下標看著對」——錯了不報錯，只會悄悄標到別處。

     ⚠️ 回傳的是**切好的三段字串**而不是下標：路徑 B 的下標是碼位，
     交給調用方再 slice 就又變回碼元切了，等於沒修（還修了一個更難發現的版本）。 */
  function hitSpan(text, surface, s, e) {
    text = String(text || "");
    surface = surface == null ? "" : String(surface);
    if (!surface) return null;
    var a = Number(s), b = Number(e);
    var ok = (a === a && b === b && a >= 0 && b > a);
    // A：快路徑。注意要先 Number()——前端拿到過字串 "99"，slice 會靜默截成 0
    if (ok && b <= text.length && text.slice(a, b) === surface) {
      return [text.slice(0, a), surface, text.slice(b)];
    }
    // B：按碼位切。Array.from 按碼位展開，不是碼元——正好對齊 Python 的下標
    if (ok) {
      var cp = Array.from(text);
      if (b <= cp.length && cp.slice(a, b).join("") === surface) {
        return [cp.slice(0, a).join(""), surface, cp.slice(b).join("")];
      }
    }
    // C：兜底。老實說這是錯的（落第一處），但寧可標錯位置也不能不標。
    //    真走到這裡說明 s/e 與 text 不同源，屬於要修的數據問題，不是前端能補的。
    var i = text.indexOf(surface);
    return i < 0 ? null : [text.slice(0, i), surface, text.slice(i + surface.length)];
  }

  function markSentence(text, surface, tier, s, e) {
    var sp = hitSpan(text, surface, s, e);
    if (!sp) return esc(text);
    var cls = (tier && tier !== "core") ? "guess" : "";
    var html = esc(sp[0]) +
      "<mark class=\"" + cls + "\">" + esc(sp[1]) + "</mark>" +
      esc(sp[2]);
    var note = TIER_NOTE[tier];
    return html + (note ? "<span class=\"tier-note\">？" + note + "</span>" : "");
  }

  /* ---------- 渲染：結果列表 ---------- */
  /* ---------- 渲染：檢索結果（人物 + 地名）----------
     ⚠️ 两个数组**分开渲染**，不要合并成一张表：
       人物之间要消歧（同名異人），地名没有这个问题（实测无重名），
       混在一起那套「序號徽章 + 見於哪本書」的逻辑会误导地名。 */
  function renderResults(items, query, places) {
    places = places || [];
    if (!items.length && !places.length) {
      out.innerHTML = "<div class=\"empty\">查不到「" + esc(query) + "」</div>";
      return;
    }
    var html = "";
    if (items.length) {
      var many = items.length > 1;
      html += "<div class=\"card\"><div class=\"person-head\">" +
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
        var mReal = (p.summary || "").match(/^【本名：([^】]+)】/);
        var realNameHtml = mReal ? "<span class=\"realname-badge\">本名：" + esc(mReal[1]) + "</span>" : "";
        html += "<div class=\"row\" data-pid=\"" + esc(p.id) + "\">" +
          "<span class=\"name\">" + idx + esc(p.trad_name) +
          (p.name && p.name !== p.trad_name ? "（" + esc(p.name) + "）" : "") +
          realNameHtml + "</span>" +
          "<span class=\"meta\">" + esc(p.dynasty || "") +
          (p.title ? " · " + esc(p.title) : "") + " · " + p.n + " 處" +
          (bk ? "　<span class=\"books\">" + bk + "</span>" : "") + "</span></div>";
      });
      html += "</div>";
    }
    if (places.length) {
      html += "<div class=\"card\"><div class=\"person-head\">" +
        "<span class=\"name\">「" + esc(query) + "」</span>" +
        "<span class=\"dyn\">共 " + places.length + " 地</span></div>";
      places.forEach(function (p) {
        var bk = (p.books && p.books.length)
          ? "見於 " + p.books.map(function (b) { return esc(b.name); }).join(" · ")
          : "";
        html += "<div class=\"row land\" data-place=\"" + esc(p.id) + "\">" +
          "<span class=\"name\">" + esc(p.trad_name) +
          (p.era ? "<span class=\"land-kind\">" + esc(p.era) + "</span>" : "") +
          "</span>" +
          "<span class=\"meta\">" + esc(p.kindLabel || p.kind || "") +
          " · " + count(p.n) + " 處" +
          (bk ? "　<span class=\"books\">" + bk + "</span>" : "") + "</span></div>";
      });
      html += "</div>";
    }
    out.innerHTML = html;
    hint.textContent = items.length > 1
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
          "<b class=\"open-full\" data-chapter=\"" + esc(id) + "\">披覽全篇 ›</b>" +
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
          // ⚠️ 用 != null 不能用真值判斷：源頭 annotate_pei.py 的預設值是 0，
          //    pseq=0 會被真值判斷吃掉 → 屬性不出現 → 點擊只開篇不跳段（靜默）。
          (it.pseq != null ? " data-pseq=\"" + esc(String(it.pseq)) + "\"" : "") +
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
    if (pei && pei.n && peiOn) {
      // 【裴N】標記擺在正文命中旁邊：讓用戶一眼看到這是另一層文本的數字。
      // ⚠️ 這裡**不做 n + pei.n 的相加**（紅線：注文不進 mentionCount）。
      h += "<div class=\"note-sum\">正文命中 <b>" + count(mainN) +
        "</b> 處　＋　注文另計 <b class=\"note-chip\">【裴" +
        count(pei.n) + "】</b></div>";
    }
    var titles = notes.chapterTitles || {};
    if (peiOn) {
      h += noteBlock(pei, "三國志裴松之注明細", "三國志", true, titles);
    }
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
    if (scopeBook.indexOf(",") >= 0) {
      var sum = 0;
      scopeBook.split(",").forEach(function (c) { sum += (bb[c] || 0); });
      return sum;
    }
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
          "\n" + (scopeBook ? "在所選典籍出現 " : "五書合計出現 ") + count(n) +
          // 文案要跟著作用域走：全五書下叫「一律未用」才準確，不能說「本書」
          " 次" + (n ? "" : (scopeBook ? "（所選典籍未用）" : "（五書均未出現）"));
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

  var currentPersonData = null;
  var currentSgzView = "combined"; // "combined" | "main" | "pei"

  function renderSgzBreakdownCard(bk) {
    if (!bk) return "";
    var m = bk.main || {};
    var p = bk.pei || {};
    var c = bk.combined || {};

    var cur = (currentSgzView === "main") ? m :
              (currentSgzView === "pei") ? p : c;

    var weiN = Number((cur.wei && cur.wei.n) || 0);
    var shuN = Number((cur.shu && cur.shu.n) || 0);
    var wuN = Number((cur.wu && cur.wu.n) || 0);
    var totN = Number((cur.total && cur.total.n) || (weiN + shuN + wuN));

    var weiPct = totN > 0 ? ((weiN / totN) * 100).toFixed(1) : "0.0";
    var shuPct = totN > 0 ? ((shuN / totN) * 100).toFixed(1) : "0.0";
    var wuPct = totN > 0 ? ((wuN / totN) * 100).toFixed(1) : "0.0";

    var h = '<div class="sgz-card" id="sgzCard">';
    h += '<div class="sgz-head">';
    h += '<div><span class="sgz-title">《三國志》魏蜀吳分卷與裴松之注統計</span>' +
         '<div class="sgz-sub">陳壽正文六十五卷 · 裴松之注全景對照</div></div>';

    // 三重視角切換按鈕
    h += '<div class="sgz-view-bar">';
    h += '<span class="sgz-view-pill' + (currentSgzView === "combined" ? " on" : "") + '" data-sgzview="combined">正裴合璧</span>';
    h += '<span class="sgz-view-pill' + (currentSgzView === "main" ? " on" : "") + '" data-sgzview="main">陳壽正文</span>';
    h += '<span class="sgz-view-pill' + (currentSgzView === "pei" ? " on" : "") + '" data-sgzview="pei">裴松之注</span>';
    h += '</div>';
    h += '</div>';

    // 三國比重條
    h += '<div class="sgz-bar-box">';
    h += '<div class="sgz-bar-label">';
    h += '<span class="c-wei">《魏書》<b>' + count(weiN) + ' 處 (' + weiPct + '%)</b></span>';
    h += '<span class="c-shu">《蜀書》<b>' + count(shuN) + ' 處 (' + shuPct + '%)</b></span>';
    h += '<span class="c-wu">《吳書》<b>' + count(wuN) + ' 處 (' + wuPct + '%)</b></span>';
    h += '</div>';
    h += '<div class="sgz-bar-track">';
    h += '<div class="sgz-bar-seg wei" style="width:' + weiPct + '%" title="魏書 ' + weiPct + '%"></div>';
    h += '<div class="sgz-bar-seg shu" style="width:' + shuPct + '%" title="蜀書 ' + shuPct + '%"></div>';
    h += '<div class="sgz-bar-seg wu" style="width:' + wuPct + '%" title="吳書 ' + wuPct + '%"></div>';
    h += '</div>';
    h += '</div>';

    // 四列網格卡片（魏 / 蜀 / 吳 / 全書）
    h += '<div class="sgz-grid">';
    // 魏書
    h += '<div class="sgz-col">' +
         '<div class="vol-name">《魏書》<span class="vol-meta">卷1-30</span></div>' +
         '<div class="vol-num">' + count(weiN) + '</div>' +
         '<div class="vol-meta">正文 ' + count(m.wei ? m.wei.n : 0) + ' 處 (' + (m.wei ? m.wei.c : 0) + '篇)<br>' +
         '裴注 ' + count(p.wei ? p.wei.n : 0) + ' 處 (' + (p.wei ? p.wei.c : 0) + '篇)</div>' +
         '</div>';
    // 蜀書
    h += '<div class="sgz-col">' +
         '<div class="vol-name">《蜀書》<span class="vol-meta">卷31-45</span></div>' +
         '<div class="vol-num">' + count(shuN) + '</div>' +
         '<div class="vol-meta">正文 ' + count(m.shu ? m.shu.n : 0) + ' 處 (' + (m.shu ? m.shu.c : 0) + '篇)<br>' +
         '裴注 ' + count(p.shu ? p.shu.n : 0) + ' 處 (' + (p.shu ? p.shu.c : 0) + '篇)</div>' +
         '</div>';
    // 吳書
    h += '<div class="sgz-col">' +
         '<div class="vol-name">《吳書》<span class="vol-meta">卷46-65</span></div>' +
         '<div class="vol-num">' + count(wuN) + '</div>' +
         '<div class="vol-meta">正文 ' + count(m.wu ? m.wu.n : 0) + ' 處 (' + (m.wu ? m.wu.c : 0) + '篇)<br>' +
         '裴注 ' + count(p.wu ? p.wu.n : 0) + ' 處 (' + (p.wu ? p.wu.c : 0) + '篇)</div>' +
         '</div>';
    // 全書合計
    h += '<div class="sgz-col tot">' +
         '<div class="vol-name">《三國志》<span class="vol-meta">全65卷</span></div>' +
         '<div class="vol-num">' + count(totN) + '</div>' +
         '<div class="vol-meta">正文合計 ' + count(m.total ? m.total.n : 0) + ' 處<br>' +
         '裴注合計 ' + count(p.total ? p.total.n : 0) + ' 處</div>' +
         '</div>';
    h += '</div>';
    return h;
  }

  /* ---------- 古典宗藩世系傳承鏈條（Round 4 · 六大封國世系導航）---------- */
  var FEOFF_LINEAGES = [
    {
      id: "liang",
      name: "梁國世系",
      title: "梁國宗藩傳承",
      sub: "楚漢相爭 · 西漢文景 · 東漢宗室 · 蜀漢鼎立 · 西晉宗藩",
      members: [
        { pid: "p_pengyue", name: "彭越", title: "梁王", note: "高祖五年封梁王，都定陶" },
        { pid: "p_liuhui", name: "劉恢", title: "梁王", note: "高祖少子，高祖十一年徙封梁王" },
        { pid: "p_liuyi_hs", name: "劉揖", title: "梁懷王", note: "文帝少子，賈誼太傅，好書墜馬" },
        { pid: "p_liuwu", name: "劉武", title: "梁孝王", note: "竇太后少子，景帝弟，平七國之亂" },
        { pid: "p_liuyong_hhs", name: "劉永", title: "梁王", note: "更始元年紹封梁王，都睢陽" },
        { pid: "p_liuchang_hhs", name: "劉暢", title: "梁節王", note: "漢明帝子，徙封梁，諡節" },
        { pid: "p_liuli_sg", name: "劉理", title: "蜀漢梁王", note: "昭烈帝少子，章武元年策拜梁王" },
        { pid: "p_simaxing", name: "司馬肜", title: "西晉梁王", note: "宣帝第八子，泰始元年封梁王" }
      ]
    },
    {
      id: "qi",
      name: "齊國世系",
      title: "齊國宗藩傳承",
      sub: "秦楚之際 · 漢初宗藩 · 武帝齊王 · 東漢割據 · 魏晉封藩",
      members: [
        { pid: "p_tian_dan", name: "田儋", title: "齊王", note: "秦末狄縣起兵自立齊王" },
        { pid: "p_tian_rong", name: "田榮", title: "齊王", note: "從弟榮起兵擊項羽自立齊王" },
        { pid: "p_tian_heng", name: "田橫", title: "齊王", note: "田榮弟，高祖召見，五百義士" },
        { pid: "p_hanxin", name: "韓信", title: "齊王", note: "破齊七十餘城，高祖拜假齊王" },
        { pid: "p_liufei", name: "劉肥", title: "齊悼惠王", note: "高祖庶長子，封齊國七十城" },
        { pid: "p_liuxiang", name: "劉襄", title: "齊哀王", note: "悼惠王長子，起兵合謀誅諸呂" },
        { pid: "p_liucijing", name: "劉次景", title: "齊厲王", note: "主父偃查治齊王，畏罪自殺" },
        { pid: "p_liuhong", name: "劉閎", title: "齊懷王", note: "武帝次子，王夫人所生，早卒" },
        { pid: "p_liuyan_hhs", name: "劉縯", title: "齊武王", note: "光武長兄，舂陵起兵，追尊齊武王" },
        { pid: "p_zhangbu", name: "張步", title: "齊王", note: "東漢初割據琅邪，劉永拜齊王" },
        { pid: "p_caofang", name: "曹芳", title: "魏齊王", note: "魏明帝養子，司馬師廢為齊王" },
        { pid: "p_simajiong", name: "司馬冏", title: "西晉齊王", note: "齊獻王攸子，起兵討趙王倫" }
      ]
    },
    {
      id: "chu",
      name: "楚國世系",
      title: "楚國宗藩傳承",
      sub: "西楚霸王 · 韓信楚王 · 楚元王傳系 · 東漢楚王",
      members: [
        { pid: "p_yidi", name: "熊心", title: "楚義帝", note: "項梁立楚懷王孫心，後尊義帝" },
        { pid: "p_xiangyu", name: "項羽", title: "西楚霸王", note: "巨鹿大破秦軍，自號西楚霸王" },
        { pid: "p_hanxin", name: "韓信", title: "楚王", note: "高祖五年徙楚王都下邳，偽游被執" },
        { pid: "p_liujiao", name: "劉交", title: "楚元王", note: "高祖弟，好詩書，受詩於浮丘伯" },
        { pid: "p_liuyingke", name: "劉郢客", title: "楚夷王", note: "元王子，初封上邳侯，恭儉篤行" },
        { pid: "p_liuwu_chu", name: "劉戊", title: "楚王", note: "與吳王濞通謀發吳楚七國之亂" },
        { pid: "p_liuli", name: "劉禮", title: "楚文王", note: "元王子，平陸侯，景帝復立楚王" },
        { pid: "p_chuxiaowang", name: "劉囂", title: "楚孝王", note: "宣帝子，好經書禮讓，成帝敬重" },
        { pid: "p_chusiwang", name: "劉衍", title: "楚思王", note: "楚孝王子，襲封楚王" },
        { pid: "p_liuying", name: "劉英", title: "東漢楚王", note: "光武子，許美人所生，喜浮屠齋戒" }
      ]
    },
    {
      id: "zhao",
      name: "趙國世系",
      title: "趙國宗藩傳承",
      sub: "秦楚趙歇 · 張耳張敖 · 高祖三趙王 · 諸呂吳楚 · 西晉趙王",
      members: [
        { pid: "p_zhaoxie", name: "趙歇", title: "趙王", note: "秦末趙歇，張耳陳餘立為趙王" },
        { pid: "p_zhang_er", name: "張耳", title: "趙王", note: "常山王歸漢，高祖四年封趙王" },
        { pid: "p_zhangao", name: "張敖", title: "趙王", note: "張耳子，尚魯元公主，貫高謀刺廢" },
        { pid: "p_liuruyi", name: "劉如意", title: "趙隱王", note: "戚夫人子，周昌相趙，呂后毒殺" },
        { pid: "p_liuyou", name: "劉友", title: "趙幽王", note: "高祖子，徙趙，幽禁於邸餓死" },
        { pid: "p_liuhui", name: "劉恢", title: "趙共王", note: "高祖子，梁王徙趙，殉情自殺" },
        { pid: "p_lvlu", name: "呂祿", title: "趙王", note: "呂后姪，封趙王，佩趙王印居北軍" },
        { pid: "p_liu_sui", name: "劉遂", title: "趙王", note: "幽王子，景帝削地，發七國之亂自刎" },
        { pid: "p_zhaojiewang", name: "劉栩", title: "趙節王", note: "東漢光武叔父趙孝王良之子，嗣趙王" },
        { pid: "p_simalun", name: "司馬倫", title: "西晉趙王", note: "宣帝第九子，結孫秀廢賈后稱帝" }
      ]
    },
    {
      id: "yan",
      name: "燕國世系",
      title: "燕國宗藩傳承",
      sub: "秦末起兵 · 漢初封藩 · 武帝宗室 · 東漢彭寵 · 魏晉遼東",
      members: [
        { pid: "p_han_guang", name: "韓廣", title: "燕王", note: "趙王武臣使略燕，自立為燕王" },
        { pid: "p_zangtu", name: "臧荼", title: "燕王", note: "救趙項羽封燕王，降漢復叛高祖征之" },
        { pid: "p_luwan", name: "盧綰", title: "燕王", note: "與高祖同日生，親愛封燕王，亡入匈奴" },
        { pid: "p_liujian", name: "劉建", title: "燕靈王", note: "高祖少子，封燕王十五年薨" },
        { pid: "p_liuze", name: "劉澤", title: "燕敬王", note: "高祖遠房從弟，文帝即位封燕王" },
        { pid: "p_liudan", name: "劉旦", title: "燕剌王", note: "武帝子，與上官桀謀反事發自縊" },
        { pid: "p_peng宠", name: "彭寵", title: "東漢燕王", note: "漁陽太守助光武平王郎，後怨望自稱燕王" },
        { pid: "p_caoyu", name: "曹宇", title: "魏燕王", note: "曹操子，曹奐生父，魏明帝託孤重臣" },
        { pid: "p_gongsunyuan", name: "公孫淵", title: "燕王", note: "遼東太守自立燕王改元紹漢，司馬懿征平" }
      ]
    },
    {
      id: "dai",
      name: "代國世系",
      title: "代國宗藩傳承",
      sub: "戰國公子嘉 · 秦末陳餘 · 文帝入繼 · 漢代宗王 · 東漢盧芳",
      members: [
        { pid: "p_gongzijia", name: "公子嘉", title: "代王嘉", note: "趙王遷降秦，嘉逃入代郡自立代王" },
        { pid: "p_chenyu", name: "陳餘", title: "代王", note: "項羽分封代王，韓信背水戰斬陳餘" },
        { pid: "p_hanwendi", name: "劉恆", title: "代王", note: "薄姬子，都中都太原，諸呂之亂迎立文帝" },
        { pid: "p_liucan_hs", name: "劉參", title: "代孝王", note: "文帝第三子，遷封代王，並故代地" },
        { pid: "p_lufang", name: "盧芳", title: "東漢代王", note: "冒稱武帝玄孫，匈奴烏桓立為代王" }
      ]
    }
  ];

  function renderFeoffLineageCard(pid) {
    if (!pid) return "";
    var targetLineage = null;
    var curIdx = -1;
    for (var i = 0; i < FEOFF_LINEAGES.length; i++) {
      var lin = FEOFF_LINEAGES[i];
      for (var j = 0; j < lin.members.length; j++) {
        if (lin.members[j].pid === pid) {
          targetLineage = lin;
          curIdx = j;
          break;
        }
      }
      if (targetLineage) break;
    }
    if (!targetLineage) return "";

    var prevMem = curIdx > 0 ? targetLineage.members[curIdx - 1] : null;
    var curMem = targetLineage.members[curIdx];
    var nextMem = curIdx < targetLineage.members.length - 1 ? targetLineage.members[curIdx + 1] : null;

    var h = '<div class="lineage-card">';
    h += '<div class="lineage-header">';
    h += '<span class="lineage-badge">宗藩世系傳承</span>';
    h += '<span class="lineage-title">' + esc(targetLineage.title) + '</span>';
    h += '<span class="lineage-sub">' + esc(targetLineage.sub) + '</span>';
    h += '</div>';

    // 三柱樞紐導航（上任 ──► 本任 ──► 繼任）
    h += '<div class="lineage-nav-trio">';
    // 上任
    if (prevMem) {
      h += '<div class="lineage-pill prev" data-pid="' + esc(prevMem.pid) + '" title="' + esc(prevMem.note) + '">' +
           '<span class="lp-tag">【前任】</span>' +
           '<span class="lp-name">' + esc(prevMem.name) + '</span>' +
           '<span class="lp-title">' + esc(prevMem.title) + '</span>' +
           '</div>';
    } else {
      h += '<div class="lineage-pill disabled"><span class="lp-tag">【始封】</span><span class="lp-name">本封開國受封</span></div>';
    }

    // 連線箭頭
    h += '<div class="lineage-arrow">──►</div>';

    // 本任
    h += '<div class="lineage-pill current" title="' + esc(curMem.note) + '">' +
         '<span class="lp-tag gold">【本任】</span>' +
         '<span class="lp-name bold">' + esc(curMem.name) + '</span>' +
         '<span class="lp-title">' + esc(curMem.title) + '</span>' +
         '</div>';

    // 連線箭頭
    h += '<div class="lineage-arrow">──►</div>';

    // 繼任
    if (nextMem) {
      h += '<div class="lineage-pill next" data-pid="' + esc(nextMem.pid) + '" title="' + esc(nextMem.note) + '">' +
           '<span class="lp-tag">【繼任】</span>' +
           '<span class="lp-name">' + esc(nextMem.name) + '</span>' +
           '<span class="lp-title">' + esc(nextMem.title) + '</span>' +
           '</div>';
    } else {
      h += '<div class="lineage-pill disabled"><span class="lp-tag">【末任】</span><span class="lp-name">無嗣國除或國除為郡</span></div>';
    }
    h += '</div>';

    // 全景傳承軌
    h += '<div class="lineage-track-box">';
    h += '<div class="lineage-track-lbl">全景傳承軌（點擊任意王侯可快速切換）：</div>';
    h += '<div class="lineage-track">';
    for (var k = 0; k < targetLineage.members.length; k++) {
      var m = targetLineage.members[k];
      var isCur = (k === curIdx);
      if (k > 0) h += '<span class="lt-step">►</span>';
      h += '<span class="lineage-node' + (isCur ? ' active' : '') + '" data-pid="' + esc(m.pid) + '" title="' + esc(m.name + ' · ' + m.title + '：' + m.note) + '">' +
           esc(m.name) + '<small>(' + esc(m.title) + ')</small>' +
           '</span>';
    }
    h += '</div>';
    h += '</div>';

    h += '</div>';
    return h;
  }

  function renderPerson(pid) {
    if (!isNavigatingBack && (currentPid !== pid || currentPlace || currentTab !== "search" || lastQuery)) {
      pushNavState(currentNavState());
    }
    resetMFilter("p:" + pid);
    return Promise.all([
      // ⚠️ 篩選要**帶在請求裡**讓服務端篩：客戶端只拿到 200 條，本地再篩
      //    只是「從這 200 條裡挑」，用戶會以為「漢書只有 12 處」。
      //    離線版忽略查詢串（路由是 `person/([^/?]+)`），所以那邊靠
      //    `filterMentions` 本地篩全量——「只多不少」的快照正好篩得動。
      request("/api/person/" + encodeURIComponent(pid) + mfQuery()),
      loadOverrides()
    ]).then(function (rs) {
      var d = rs[0];
      var p = d.profile;
      currentPersonData = d;
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
      // ⚠️ 用**篩選後**的 rows：篩到漢書時「只看相關段落」也該只認漢書那些段。
      var rows = filterMentions(d.mentions || []);
      var uids = {};
      var hitsByUid = {};
      rows.forEach(function (m) {
        if (m.uid) {
          uids[m.uid] = 1;
          hitsByUid[m.uid] = hitsByUid[m.uid] || [];
          hitsByUid[m.uid].push({
            surface: m.surface, s: m.s, e: m.e, tier: m.tier,
            kind: "person", id: pid, name: p.trad_name || p.name,
            dynasty: p.dynasty || "", title: p.title || ""
          });
        }
      });
      readerState.hitUids = uids;
      readerState.hitsByUid = hitsByUid;
      var mReal = (p.summary || "").match(/^【本名：([^】]+)】/);
      var realNameBadge = mReal ? "<span class=\"realname-badge\">本名：" + esc(mReal[1]) + "</span>" : "";
      var html = "<div class=\"card\">" +
        "<div class=\"person-head\"><span class=\"name\">" + esc(p.trad_name) + "</span>" +
        realNameBadge +
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

      // 三國志魏蜀吳分卷與裴注統計卡片（三重視角）
      var sgzBk = d.sgzBreakdown || computeSgzBreakdown(d);
      if (sgzBk) {
        html += renderSgzBreakdownCard(sgzBk);
      }

      // 古典宗藩世系傳承鏈條導航卡片（兩漢梁齊楚趙燕代等封國）
      html += renderFeoffLineageCard(pid);

      // 主要行跡與兵爭輿地交集
      if ((d.topPlaces && d.topPlaces.length) || (d.strategicHubs && d.strategicHubs.length)) {
        var allStratHubs = (d.strategicHubs && d.strategicHubs.length)
          ? d.strategicHubs.map(function (h) { return h.id; })
          : (d.topPlaces || []).filter(function (tpl) { return tpl.isStrategic; }).map(function (tpl) { return tpl.id; });
        var itinBtn = allStratHubs.length
          ? "<button class=\"map-view-btn\" data-act=\"view-itinerary\" data-pname=\"" + esc(p.trad_name || p.name) + "\" data-hubs=\"" + esc(allStratHubs.join(",")) + "\">在形勝輿圖上檢視行跡（涉足 " + allStratHubs.length + " 處要塞） ➔</button>"
          : "";
        html += "<div class=\"group-title\">主要行跡 · 兵爭與輿地交集 <span class=\"count\">" + (d.topPlaces ? d.topPlaces.length : 0) + " 處</span>" + itinBtn + "</div>" +
          "<div class=\"card\"><div class=\"footprint-grid\">" +
          (d.topPlaces || []).map(function (tpl) {
            var cls = tpl.isStrategic ? "footprint-pill strat" : "footprint-pill";
            return "<span class=\"" + cls + "\" data-plid=\"" + esc(tpl.id) + "\">" +
              (tpl.isStrategic ? "<i class=\"strat-dot\">★</i>" : "") +
              esc(tpl.trad_name || tpl.name) +
              (tpl.kind ? "<small class=\"kind\">(" + esc(tpl.kind) + ")</small>" : "") +
              "<b class=\"qn\">" + count(tpl.n) + "</b></span>";
          }).join("") +
          "</div></div>";
      }

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
      html += mentionFilterBar(d, rows.length);
      var groups = [], byId = {};
      rows.forEach(function (m) {
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
            markSentence(m.text, m.surface, m.tier, m.s, m.e) +
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
      // ⚠️ 這裡的「正文命中 N 處」**不能**用 mentions.length——那被 limit 截到
      //    200，顯示出來就是「正文命中 200 處」，而搜索卡說 2,064 處，
      //    兩個真數字挨在一起自相矛盾（docs/34 P0-3）。改用全量分佈算。
      //    篩選生效時給篩選後的條數，與下面列表的口徑一致。
      html += notesSection(pid, d.notes || {}, mbSelected(d));

      /* 關係：資料來自 workbook/relations.xlsx，後端已轉成 {nodes, edges}。
         圖 + 列表並存：**虛線＝無證據的推斷**，實線＝語料裡有原句可跳，
         別讓推斷看起來像事實（docs/25 §四）。 */
      relState = { degree: 1, minConf: 0 };
      html += "<div class=\"card\" id=\"relcard\" style=\"margin-top:14px\">" +
        relCardInner(pid, d.relations || { nodes: [], edges: [] }, relState) + "</div>";

      out.innerHTML = html;
      hint.textContent = "實線表示正名或字號直接命中；虛線標記泛稱推定，備學者審度。";
      currentPid = pid;
      currentPlace = null;
    });
  }

  /* ---------- 渲染：地名詳情 ----------
     ⚠️ 刻意與 `renderPerson` **同構**（同樣的分篇標題 / 命中標色 / 點句進原文層），
     因為兩邊的 payload 形狀是一樣的（`db.place_payload` 照 `db.person_payload`
     的結構寫）。寫第二套渲染不是省事，是**多一處會悄悄分叉的地方**。
     地名側沒有的：稱謂表（人物特有）、關係圖（人物特有）、注文（裴注只跟人）。 */
  function renderPlace(plid) {
    if (!isNavigatingBack && (currentPlace !== plid || currentPid || currentTab !== "search" || lastQuery)) {
      pushNavState(currentNavState());
    }
    resetMFilter("l:" + plid);
    return Promise.all([
      request("/api/place/" + encodeURIComponent(plid) + mfQuery()),
      loadOverrides()
    ]).then(function (rs) {
      var d = rs[0];
      var p = d.profile;
      if (ovMsgFor && ovMsgFor !== plid) { ovMsg = ""; ovMsgFor = ""; }
      ovMap = {};
      (rs[1].items || []).forEach(function (r) {
        ovMap[ovKeyOf(r.uid, r.s, r.e, r.surface)] = r;
      });
      ovPending = rs[1].pending || 0;

      // 原文層的「只看相關段落」靠它（與人物頁同一個機制）
      var rows = filterMentions(d.mentions || []);
      var uids = {};
      var hitsByUid = {};
      rows.forEach(function (m) {
        if (m.uid) {
          uids[m.uid] = 1;
          hitsByUid[m.uid] = hitsByUid[m.uid] || [];
          hitsByUid[m.uid].push({
            surface: m.surface, s: m.s, e: m.e, tier: m.tier,
            kind: "place", id: plid, name: p.trad_name || p.name,
            kindLabel: p.kindLabel || p.kind || "", era: p.era || ""
          });
        }
      });
      readerState.hitUids = uids;
      readerState.hitsByUid = hitsByUid;
      currentPid = null;
      currentPlace = plid;

      var stratBadge = d.strategic ? ("<span class=\"strat-badge\">〔兵爭要地 · " + esc(d.strategic.zone) + "〕</span>") : "";
      var html = "<div class=\"card\">" +
        "<div class=\"person-head\"><span class=\"name\">" + esc(p.trad_name) + "</span>" +
        stratBadge +
        "<span class=\"dyn\">" + esc(p.kindLabel || p.kind || "") +
        (p.era ? " · " + esc(p.era) : "") + "</span></div>";
      if (p.summary) html += "<p class=\"summary\">" + esc(p.summary) + "</p>";

      /* 見於哪些書 —— 與人物的「分書收窄」同一份數據口徑。
         ⚠️ 這裡顯示的是**全五書合計**，不隨當前書作用域變（與 aliasScopeN 同理：
         離線版沒有服務端可問，數字必須由前端從 byBook 算）。 */
      if ((d.books || []).length) {
        html += "<div class=\"alias-note\">見於 " + d.books.map(function (b) {
          return esc(b.name) + " " + count(b.n) + " 處";
        }).join(" · ") + "</div>";
      }
      /* 寫法清單：**必須顯示**。places 主表的 name 與 trad_name 逐行相同，
         簡體名藏在異體表裡；不列出來，用戶輸「邯郸」搜不到會以為此地不存在。 */
      if ((d.aliases || []).length > 1) {
        html += "<div class=\"group-title\">寫法 <span class=\"count\">" +
          d.aliases.length + " 種</span></div><div class=\"card\"><div class=\"alias-note\">" +
          d.aliases.map(function (a) {
            return "<span class=\"alias-tag\">" + esc(a.w) +
              (a.n ? "<b class=\"qn\">" + count(a.n) + "</b>" : "") + "</span>";
          }).join("") + "</div></div>";
      }
      html += "</div>";

      // 宋杰三國兩漢兵爭要地與戰略樞紐考據卡片
      if (d.strategic) {
        var st = d.strategic;
        html += "<div class=\"card strat-card\">" +
          "<div class=\"strat-head\">" +
          "<div><span class=\"strat-title\">" + esc(st.strat_title) + "</span>" +
          "<span class=\"strat-zone\" style=\"margin-left:8px;\">" + esc(st.zone) + "</span></div>" +
          "<button class=\"map-view-btn\" data-act=\"locate-on-map\" data-plid=\"" + esc(plid) + "\">在形勝輿圖中定位 ➔</button>" +
          "</div>" +
          "<div class=\"strat-desc\"><p>" + esc(st.strat_desc) + "</p></div>" +
          "<div class=\"strat-evolution\"><b>古今沿革：</b>" + esc(st.evolution) + "</div>" +
          (st.battles && st.battles.length ? ("<div class=\"strat-battles\"><b>關聯戰事：</b>" + st.battles.map(function (bt) { return "<span class=\"battle-pill\">" + esc(bt) + "</span>"; }).join("") + "</div>") : "") +
          "</div>";
      }

      // 駐跸征戰 · 歷史人物榜
      if (d.topPersons && d.topPersons.length) {
        html += "<div class=\"group-title\">駐跸征戰 · 歷史人物榜 <span class=\"count\">" + d.topPersons.length + " 位</span></div>" +
          "<div class=\"card\"><div class=\"footprint-grid\">" +
          d.topPersons.map(function (tp) {
            return "<span class=\"footprint-pill\" data-pid=\"" + esc(tp.id) + "\">" +
              esc(tp.trad_name || tp.name) +
              "<b class=\"qn\">" + count(tp.n) + "</b></span>";
          }).join("") +
          "</div></div>";
      }

      if (!OFF && ovPending > 0) {
        html += "<div class=\"ovbar\"><span class=\"ovtxt\">" +
          esc(ovMsg || ("有 " + ovPending + " 條標錯記錄待重建生效")) +
          "</span>" +
          (OFF || !ovPending ? "" : "<button data-act=\"ovrebuild\">重建</button>") +
          "</div>";
      } else if (!OFF && ovMsg) {
        html += "<div class=\"ovbar\"><span class=\"ovtxt\">" +
          esc(ovMsg) + "</span></div>";
      }

      var groups = [], byId = {};
      html += mentionFilterBar(d, rows.length);
      rows.forEach(function (m) {
        var key = m.chapter_id;
        if (!byId[key]) { byId[key] = { title: m.chapter, rows: [] }; groups.push(byId[key]); }
        byId[key].rows.push(m);
      });
      if (!groups.length) {
        html += "<div class=\"empty\">此地名在目前語料裡沒有命中。</div>";
      }
      groups.forEach(function (g) {
        html += "<div class=\"chapter-title\">" + esc(g.title || "") +
          " · " + g.rows.length + " 處</div>";
        g.rows.forEach(function (m) {
          var ov = ovMap[ovKeyOf(m.uid, m.s, m.e, m.surface)];
          var flag = OFF ? "" : (ov
            ? flagBadge(ov)
            : "<span class=\"acts\"><button data-act=\"flag\">標錯</button></span>");
          html += "<div class=\"sent\" data-chapter=\"" + esc(m.chapter_id) +
            "\" data-uid=\"" + esc(m.uid) +
            "\" data-s=\"" + m.s + "\" data-e=\"" + m.e +
            "\" data-surface=\"" + esc(m.surface) +
            "\" data-pid=\"" + esc(plid) +
            "\" data-place=\"" + esc(plid) + "\">" +
            flag + markSentence(m.text, m.surface, m.tier, m.s, m.e) + "</div>";
        });
      });

      out.innerHTML = html;
      hint.textContent = "";
    });
  }

  /* 標錯面板：不彈窗，就地展開一行——彈窗要管焦點與層級，
     而這裡只需要「輸入人名/地名 → 點候選」兩下。 */
  function openFixBox(row) {
    var old = row.parentNode ? row.parentNode.querySelector(".fixbox") : null;
    if (old) { old.parentNode.removeChild(old); }
    var surface = row.getAttribute("data-surface") || "";
    var pid = row.getAttribute("data-pid") || "";
    var isPlace = !!row.getAttribute("data-place") || pid.startsWith("pl_");
    var box = document.createElement("div");
    box.className = "fixbox";
    ["uid", "s", "e", "surface", "pid"].forEach(function (k) {
      box.setAttribute("data-" + k, row.getAttribute("data-" + k) || "");
    });
    box.setAttribute("data-is-place", isPlace ? "1" : "0");
    box.innerHTML =
      "<div class=\"fix-head\">這處判為「" + esc(surface) + "」</div>" +
      "<div class=\"fix-line\"><input class=\"fix-input\" " +
      "placeholder=\"" + (isPlace ? "改歸給哪個地名？輸入地名，如 洛陽" : "改歸給誰？輸入人名，如 項羽") + "\" autocomplete=\"off\">" +
      "<button data-act=\"cancel\">取消</button></div>" +
      "<div class=\"fix-cand\"></div>" +
      "<div class=\"fix-alt\">或者 <button data-act=\"drop\">" + (isPlace ? "不是此地（這處不算）" : "不是他（這處不算）") + "</button>" +
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
    var isPlace = box.getAttribute("data-is-place") === "1";
    clearTimeout(fixTimer);
    // 防抖：每敲一個字就查一次，古籍人名兩三個字，會連著查三次
    fixTimer = setTimeout(function () {
      request("/api/search?q=" + encodeURIComponent(q)).then(function (r) {
        var candItems = [];
        if (isPlace) {
          (r.places || []).slice(0, 5).forEach(function (x) {
            candItems.push({
              id: x.id,
              name: x.trad_name,
              meta: (x.kindLabel || x.kind || "地名") + (x.era ? " · " + x.era : "") + " · " + x.n + " 處"
            });
          });
          (r.items || []).slice(0, 3).forEach(function (x) {
            candItems.push({
              id: x.id,
              name: x.trad_name,
              meta: "人名 · " + (x.dynasty || "") + (x.title ? " · " + x.title : "") + " · " + x.n + " 處"
            });
          });
        } else {
          (r.items || []).slice(0, 5).forEach(function (x) {
            candItems.push({
              id: x.id,
              name: x.trad_name,
              meta: (x.dynasty || "") + (x.title ? " · " + x.title : "") + " · " + x.n + " 處"
            });
          });
          (r.places || []).slice(0, 3).forEach(function (x) {
            candItems.push({
              id: x.id,
              name: x.trad_name,
              meta: "地名 · " + (x.kindLabel || x.kind || "") + (x.era ? " · " + x.era : "") + " · " + x.n + " 處"
            });
          });
        }
        cand.innerHTML = candItems.length
          ? candItems.map(function (x) {
              return "<div class=\"fix-cand-row\" data-pid=\"" + esc(x.id) + "\">" +
                "<span class=\"nm\">" + esc(x.name) + "</span>" +
                "<span class=\"mt\">" + esc(x.meta) + "</span></div>";
            }).join("")
          : "<div class=\"fix-empty\">查不到「" + esc(q) + "」</div>";
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
      var refresh = currentPlace ? renderPlace(currentPlace) : renderPerson(currentPid);
      return refresh.then(function () {
        // ⚠️ overrides.py 在 Excel 被別人占著（.new.xlsx 已寫、退出碼還是 0）時
        // 會回 warning。不顯示的話介面說「已記錄」而權威源裡根本沒有。
        ovStatus(r.warning ? "⚠️ " + r.warning : "已記錄，重建後生效", currentPlace || currentPid);
      });
    }).catch(function (e) {
      var alt = box.querySelector(".fix-hint");
      if (alt) { alt.textContent = "　失敗：" + ((e && e.message) || e); }
    });
  }

  function submitUnflag(row) {
    requestPost("/api/override/revoke", { uid: row.getAttribute("data-uid") })
      .then(function () {
        if (currentPlace) return renderPlace(currentPlace);
        return renderPerson(currentPid);
      })
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
  var btnPnToggle = document.getElementById("btnPnToggle");
  var JUMP_MIN = 40;        // 少於這麼段就不顯示跳段控件（加了是噪聲）

  function paraCount() {
    var seen = {}, n = 0;
    (readerState.sents || []).forEach(function (s) {
      if (s.para_seq != null && !seen[s.para_seq]) { seen[s.para_seq] = 1; n++; }
    });
    return n;
  }

  /* 與當前作用域（人物或地名）有命中的段落號集合。
     ⚠️ 命中資訊**不從 /api/chapter 拿**（那会让 564 篇每篇都带上全部 marks，
     payload 翻十几倍）。人物頁／地名頁渲染時已經拿到這個人的 mentions（帶 uid），
     在這裡把 uid 記進 readerState.hitUids，開篩選時才反查段落——
     數據來源是同一份，沒有第二個真相。
     ⚠️ 字段叫 `scope` 不叫 `pid`：它**只當布爾用**（「有沒有篩選上下文」），
     人物頁與地名頁都能往裡塞 id。叫 pid 卻存地名 id 是撒謊，
     下次有人寫 `if (state.pid) 查人物表` 就會靜默查空。 */
  function hitParas() {
    var out = {};
    if (!readerState.scope) return out;
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
    btnHits.hidden = !readerState.scope;
    btnHits.classList.toggle("on", !!readerState.hitsOnly);
    btnHits.textContent = readerState.hitsOnly ? "顯示全部段落" : "只看相關段落";
    if (btnPnToggle) {
      btnPnToggle.hidden = !readerState.scope;
      btnPnToggle.classList.toggle("on", !!readerState.properNounsOn);
    }
  }

  function jumpToPara(pno) {
    // 段號不在「只看相關」的範圍內時，先切回全文——否則定位不到
    if (readerState.hitsOnly) {
      var hp = hitParas();
      if (!(pno in hp)) { readerState.hitsOnly = false; renderReader(); }
    }
    var node = readerBody.querySelector('p[data-para="' + pno + '"]');
    var cur = pno;
    while (!node && cur > 1) {
      cur--;
      node = readerBody.querySelector('p[data-para="' + cur + '"]');
    }
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
    // 專名號標點點擊穿透：點擊人名線/地名線直接打開該實體
    var pnPers = ev.target.closest ? ev.target.closest(".pn-person[data-pid]") : null;
    if (pnPers) {
      var targetPid = pnPers.getAttribute("data-pid");
      if (targetPid) {
        closeReader();
        renderPerson(targetPid).then(writeHash).catch(showErr);
        return;
      }
    }
    var pnPl = ev.target.closest ? ev.target.closest(".pn-place[data-place]") : null;
    if (pnPl) {
      var targetPlace = pnPl.getAttribute("data-place");
      if (targetPlace) {
        closeReader();
        renderPlace(targetPlace).then(writeHash).catch(showErr);
        return;
      }
    }

    var p = ev.target.closest ? (ev.target.closest("[data-uid]") || ev.target.closest("p[data-uid]")) : null;
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
  /* 古漢語專名號標點（人名實線 / 地名浪線）與句子內容渲染
     根據點校本文獻規範：
     - 人名專名號：在人名下方標以朱砂實線（.pn-person）
     - 地名專名號：在地名下方標以石青波浪線（.pn-place）
     利用命中切片（s, e, surface）或 hitSpan 進行碼位級無損替換。 */
  function formatSentenceWithProperNouns(s, targetUid) {
    var text = String((s && s.text) || "");
    if (!text) return "";
    var uid = s && s.uid;
    var hits = (readerState.hitsByUid && uid && readerState.hitsByUid[uid]) || [];

    // 若未開啟專名號或無命中切片，直接返回轉義正文
    if (!readerState.properNounsOn || !hits.length) {
      return esc(text);
    }

    var intervals = [];
    hits.forEach(function (h) {
      var surface = h.surface;
      if (!surface) return;
      var span = hitSpan(text, surface, h.s, h.e);
      if (span) {
        var start = span[0].length;
        var end = start + span[1].length;
        intervals.push({
          start: start,
          end: end,
          surface: surface,
          kind: h.kind || "person",
          id: h.id || "",
          name: h.name || surface,
          meta: (h.dynasty ? h.dynasty + " · " : "") + (h.title || h.kindLabel || "")
        });
      }
    });

    if (!intervals.length) return esc(text);

    // 長名優先
    intervals.sort(function (a, b) {
      return a.start - b.start || (b.end - b.start) - (a.end - a.start);
    });

    var nonOverlapping = [];
    var lastEnd = 0;
    intervals.forEach(function (inv) {
      if (inv.start >= lastEnd) {
        nonOverlapping.push(inv);
        lastEnd = inv.end;
      }
    });

    var res = "";
    var curPos = 0;
    nonOverlapping.forEach(function (inv) {
      if (inv.start > curPos) {
        res += esc(text.slice(curPos, inv.start));
      }
      var cls = inv.kind === "place" ? "pn-place" : "pn-person";
      var attr = inv.kind === "place" ? ' data-place="' + esc(inv.id) + '"' : ' data-pid="' + esc(inv.id) + '"';
      var tip = (inv.kind === "place" ? "【地名】" : "【人名】") + inv.name + (inv.meta ? "（" + inv.meta + "）" : "") + " · 點擊披覽";
      res += '<span class="' + cls + '"' + attr + ' title="' + esc(tip) + '">' + esc(inv.surface) + '</span>';
      curPos = inv.end;
    });
    if (curPos < text.length) {
      res += esc(text.slice(curPos));
    }
    return res;
  }

  /* 原文層：古漢語自然段落排版與助讀裝幀（Round 5）
     按史書自然段號（para_seq）聚攏各句，段首全角二字縮進，行距寬綽溫潤；
     段內單句以流式行內容器（.reader-sent）排布，目標句伴隨朱砂金石呼吸燈提示；
     人名地名專名號（實線/浪線）精準標點。 */
  function renderParagraphs(sentences, targetUid, hitMap) {
    if (!sentences || !sentences.length) return "";
    var open = 0;
    var paras = [], byPara = {};
    sentences.forEach(function (s) {
      var pseq = (s.para_seq == null) ? 0 : s.para_seq;
      if (!byPara[pseq]) {
        byPara[pseq] = { pseq: pseq, sents: [] };
        paras.push(byPara[pseq]);
      }
      byPara[pseq].sents.push(s);
    });

    var html = "";
    paras.forEach(function (p) {
      if (hitMap && !(p.pseq in hitMap)) return;
      var isHitPara = hitMap && (p.pseq in hitMap);
      var pCls = ["reader-para"];
      if (isHitPara) pCls.push("hitpara");

      var pHtml = '<p class="' + pCls.join(" ") + '" data-para="' + esc(String(p.pseq)) + '">';
      if (p.pseq > 0) {
        pHtml += '<span class="para-badge" title="第 ' + p.pseq + ' 段">〔' + p.pseq + '〕</span>';
      }

      p.sents.forEach(function (s) {
        var t = s.text || "";
        var o = (t.match(/「/g) || []).length;
        var c = (t.match(/」/g) || []).length;
        var cont = open > 0;
        open += o - c;
        if (open < 0) open = 0;

        var sCls = ["reader-sent"];
        if (cont) sCls.push("q-cont");
        if (open > 0) sCls.push("q-open");
        if (s.uid === targetUid) sCls.push("target pulse");

        var sentBody = formatSentenceWithProperNouns(s, targetUid);
        pHtml += '<span class="' + sCls.join(" ") + '" data-uid="' + esc(s.uid) +
                 '" data-para="' + esc(String(s.para_seq == null ? "" : s.para_seq)) +
                 '" data-text="' + esc(t) + '">' +
                 sentBody + ACTS + '</span>';
      });

      pHtml += '</p>';
      html += pHtml;
    });
    return html;
  }

  /* 每句 hover 出的三個動作。按鈕文案一律繁體（check_trad F 閘會掃）。
     離線版不給這三個按鈕——它們 POST 到服務端，離線寫不了，給了就是空頭支票。 */
  var ACTS = OFF ? "" : "<span class=\"acts\">" +
    "<button data-act=\"split\">拆分</button>" +
    "<button data-act=\"merge\">併下句</button>" +
    "<button data-act=\"dead\">棄用</button>" +
    "</span>";

  /* pseq = 直接跳到某一段（段號）。注文明細行用：它的 data-pseq 是**段號**
     ——注意注文與正文的切分體系不同（MEMORY 紅線），所以**不能**拿它當 uid 定位，
     只能按段號跳。段落不存在時別出錯，只是不跳（原文層照樣開）。 */
  function openChapter(cid, uid, scope, pseq) {
    readerCid = cid;
    return request("/api/chapter/" + encodeURIComponent(cid)).then(function (d) {
      readerTitle.textContent = (d.chapter && d.chapter.full_title) || cid;
      readerState.sents = d.sentences || [];
      readerState.targetUid = uid || null;
      readerState.scope = scope || null;
      readerState.hitsOnly = false;
      renderReader();
      reader.classList.add("on");
      if (pseq != null) jumpToPara(Number(pseq));
      if (uid) {
        var el = readerBody.querySelector('p[data-uid="' + uid + '"]') || readerBody.querySelector('[data-uid="' + uid + '"]');
        if (el && el.scrollIntoView) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.classList.add("pulse");
        }
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
  if (btnPnToggle) {
    btnPnToggle.addEventListener("click", function () {
      readerState.properNounsOn = !readerState.properNounsOn;
      btnPnToggle.classList.toggle("on", !!readerState.properNounsOn);
      renderReader();
    });
  }
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeReader();
  });

  /* ---------- 回退：应用内导航历史栈 + hash 路由 ---------- */
  var lastWritten = null;
  function routeHash() {
    if (currentPid) return "#/person/" + currentPid;
    // ⚠️ 地名路由排在 q 之前：currentPlace 與 lastQuery 可能同時有值
    //    （從地名頁點快捷詞時），先判 pid 再判 place 最後才判 query。
    if (currentPlace) return "#/place/" + currentPlace;
    if (lastQuery) return "#/q/" + encodeURIComponent(lastQuery) + "/" + mode;
    return "#/";
  }

  // ── 应用内导航历史栈（精准支持“回到上一步”） ──
  var navStack = [];
  var isNavigatingBack = false;

  function currentNavState() {
    if (currentPid) {
      return { type: "person", id: currentPid };
    }
    if (currentPlace) {
      return { type: "place", id: currentPlace };
    }
    if (currentTab === "search" && lastQuery) {
      return { type: "search", query: lastQuery, mode: mode };
    }
    return { type: "tab", tab: currentTab };
  }

  function pushNavState(st) {
    if (isNavigatingBack || !st) return;
    if (navStack.length > 0) {
      var top = navStack[navStack.length - 1];
      if (top.type === st.type &&
          (top.id || "") === (st.id || "") &&
          (top.tab || "") === (st.tab || "") &&
          (top.query || "") === (st.query || "")) {
        return;
      }
    }
    navStack.push(st);
    if (navStack.length > 50) navStack.shift();
    syncBack();
  }

  function restoreNavState(st) {
    if (!st) return;
    isNavigatingBack = true;
    try {
      if (st.type === "person" && st.id) {
        currentPlace = null;
        renderPerson(st.id).then(function () {
          writeHash();
        }).finally(function () {
          isNavigatingBack = false;
          syncBack();
        });
      } else if (st.type === "place" && st.id) {
        currentPid = null;
        renderPlace(st.id).then(function () {
          writeHash();
        }).finally(function () {
          isNavigatingBack = false;
          syncBack();
        });
      } else if (st.type === "search") {
        currentPid = null;
        currentPlace = null;
        switchTab("search");
        mode = st.mode || "person";
        setModeUI();
        qEl.value = st.query || "";
        if (st.query) {
          search(st.query).finally(function () {
            isNavigatingBack = false;
            syncBack();
          });
        } else {
          isNavigatingBack = false;
          writeHash();
          syncBack();
        }
      } else if (st.type === "tab") {
        currentPid = null;
        currentPlace = null;
        switchTab(st.tab);
        writeHash();
        isNavigatingBack = false;
        syncBack();
      } else {
        isNavigatingBack = false;
        syncBack();
      }
    } catch (e) {
      isNavigatingBack = false;
      syncBack();
      showErr(e);
    }
  }

  function goBackStep() {
    // 1. 若当前正开着原文阅读层，第一优先级：关闭原文，回到正文详情
    if (reader.classList.contains("on")) {
      closeReader();
      return;
    }
    // 2. 若内部导航历史栈中有上一步记录，弹出并恢复
    while (navStack.length > 0) {
      var prev = navStack.pop();
      var curr = currentNavState();
      if (prev.type === curr.type &&
          (prev.id || "") === (curr.id || "") &&
          (prev.tab || "") === (curr.tab || "") &&
          (prev.query || "") === (curr.query || "")) {
        continue;
      }
      restoreNavState(prev);
      return;
    }
    // 3. 栈已空，但当前在详情页：退回检索结果或篇目一览
    if (currentPid || currentPlace) {
      currentPid = null;
      currentPlace = null;
      if (lastQuery) {
        switchTab("search");
        search(lastQuery);
      } else {
        switchTab("chapters");
      }
      writeHash();
      syncBack();
      return;
    }
    // 4. 当前在搜索结果页但没有更早历史：退回篇目一览
    if (currentTab === "search" && lastQuery) {
      lastQuery = "";
      qEl.value = "";
      switchTab("chapters");
      writeHash();
      syncBack();
      return;
    }
    // 5. 兜底回退
    if (history.length > 1) {
      history.back();
    } else {
      location.hash = "#/";
    }
  }

  function syncBack() {
    var onReader = reader.classList.contains("on");
    var canGoBack = onReader || navStack.length > 0 || currentPid || currentPlace || (currentTab === "search" && !!lastQuery);
    backBtn.hidden = !canGoBack;
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
    //    `place` 與 `person` 同一組捕獲，改路由時**三處要同步**：
    //    routeHash（寫）／applyHash（讀）／offlineGet（離線派發）。
    var m = /^#\/(person|place|q)(?:\/([^?#/]+))?(?:\/(fts|person))?$/.exec(h);
    if (!m) {
      currentPid = null;
      currentPlace = null;
      if (lastQuery) {
        switchTab("search");
        search(lastQuery);
      } else if (currentTab !== "search") {
        switchTab(currentTab);
      } else {
        switchTab("chapters");
      }
      syncBack();
      return;
    }
    if (m[1] === "person" && m[2]) {
      renderPerson(decodeURIComponent(m[2])).then(syncBack).catch(showErr);
    } else if (m[1] === "place" && m[2]) {
      renderPlace(decodeURIComponent(m[2])).then(syncBack).catch(showErr);
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
    goBackStep();
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
        (e.evidence_valid === 1 ? "　（實線：正典證據句可披覽）" : "　（虛線：泛稱推定，備學者審度）");
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
    { code: "sj", name: "史記", era: null, chapterCount: 130, author: "司馬遷", eraName: "西漢" },
    { code: "hs", name: "漢書", era: [8, 10], chapterCount: 100, author: "班固", eraName: "東漢" },
    { code: "hhs", name: "後漢書", era: [10, 11], chapterCount: 120, author: "范曄", eraName: "南朝宋" },
    { code: "sgz", name: "三國志", era: [11, 12], chapterCount: 65, author: "陳壽", eraName: "西晉" },
    { code: "js", name: "晉書", era: [12, 15], chapterCount: 130, author: "房玄齡等", eraName: "唐" }
  ];
  // 地名分組順序，與 pipeline/annotate_places.py 的 KIND_ORDER 一致
  var PLACE_KIND_ORDER = ["国", "州", "郡", "县", "关", "山", "川", "湖", "域", "外"];


  /* ---------- 命中篩選（按書 / 按時代）----------
     聯機 `mentions` 有 200 條上限，離線給全量（docs/29 §六「只多不少」的刻意差異）。
     兩個數挨在同一屏上就自相矛盾：搜索卡說 2,064 處、人物頁說 200 處，
     而 200 緊挨著旁邊的【裴726】——用戶會讀成「200 + 726」（docs/34 P0-3）。

     解法不是把上限調大，是三件事一起做：
       ① 「共 N 處」永遠取**全量分佈** mentionByBook，不取 mentions.length；
       ② 列表被截斷時明白寫「已顯示 200 / 共 2,064」，不截斷就不寫這行；
       ③ 給篩選器，讓這 200 條花在用戶要看的那本書 / 那個時代上。

     ⚠️ 時代桶由**前端**從 byBook + BOOKS[].era 推導：原始數據只有一份（後端給），
        兩份前端跑同一段代碼。若讓後端把時代分佈也算出來，離線版就得再抄一遍
        ——「離線路由忽略查詢串」意味著它根本問不到後端（MEMORY 的老坑）。
     ⚠️ 時代篩選**不含史記**：它是通史（era = null），若當成「含全部時代」，
        每個時代桶都會被它灌滿，篩選就失去意義。要看史記請用「按書」。 */
  var mFilter = { who: "", book: "", era: "" };   // who = 當前實體 id（換人就重置）

  /* ⚠️ 離線的 pmbk / plbk 是**緊湊陣列**（省體積），第 i 位屬於哪本書
     由**導出時的順序**決定：`export_static.py` 用 `SELECT code FROM books
     ORDER BY code`，也就是 hhs / hs / js / sgz / sj。
     而常量 BOOKS 是**成書先後**順序（sj / hs / hhs / sgz / js）——兩者**不一樣**。
     照 BOOKS 的下標還原會把漢書的數記到史記頭上，**總數卻一模一樣**
     （求和對置換不變），所以不報錯、只是每本書的數全錯。
     → 一律拿快照自己的 `books` 當尺；尺跟著數據走，任一端改順序都不會錯位。 */
  function mbkCodes() {
    if (OFF && D && D.books && D.books.length) {
      return D.books.map(function (b) { return b[0]; });
    }
    return BOOKS.map(function (b) { return b.code; });
  }
  function mbkFromArray(arr) {
    var o = {}, cs = mbkCodes();
    if (!arr) return o;
    for (var i = 0; i < cs.length && i < arr.length; i++) {
      o[cs[i]] = Number(arr[i]) || 0;
    }
    return o;
  }
  function mbOf(d) { return (d && d.mentionByBook) || {}; }
  function mbTotal(d) {
    var m = mbOf(d), t = 0;
    for (var k in m) { t += (Number(m[k]) || 0); }
    return t;
  }
  function booksOfEra(e) {
    return BOOKS.filter(function (b) {
      return b.era && e >= b.era[0] && e <= b.era[1];
    }).map(function (b) { return b.code; });
  }
  /** 當前篩選下的**全量**條數（不是本次載入了多少條）。 */
  function mbSelected(d) {
    var m = mbOf(d);
    if (mFilter.book) return Number(m[mFilter.book]) || 0;
    if (mFilter.era !== "") {
      var n = 0;
      booksOfEra(Number(mFilter.era)).forEach(function (c) {
        n += (Number(m[c]) || 0);
      });
      return n;
    }
    return mbTotal(d);
  }
  /** 離線才用得上：聯機的 mentions 已被服務端篩過，本地再篩沒有意義。 */
  function filterMentions(rows) {
    if (!OFF) return rows;
    if (mFilter.book) {
      return rows.filter(function (m) { return m.book === mFilter.book; });
    }
    if (mFilter.era !== "") {
      var cs = booksOfEra(Number(mFilter.era));
      return rows.filter(function (m) { return cs.indexOf(m.book) >= 0; });
    }
    return rows;
  }
  function mentionFilterBar(d, shown) {
    var m = mbOf(d), tot = mbTotal(d), sel = mbSelected(d);
    var h = '<div class="mfbar">';
    h += '<select class="mf" data-mf="book"><option value="">全五書（' +
      tot.toLocaleString() + ' 處）</option>';
    BOOKS.forEach(function (b) {
      var n = Number(m[b.code]) || 0;
      // 0 處的書不列：下拉裡躺著一排「0 處」只會讓人以為索引壞了
      if (!n) return;
      h += '<option value="' + b.code + '"' +
        (mFilter.book === b.code ? " selected" : "") + '>《' + esc(b.name) +
        '》· ' + n.toLocaleString() + ' 處</option>';
    });
    h += "</select>";
    var eras = (d && d.eraNames) || [];
    h += '<select class="mf" data-mf="era"><option value="">全部時代</option>';
    eras.forEach(function (nm, e) {
      var n = 0;
      booksOfEra(e).forEach(function (c) { n += (Number(m[c]) || 0); });
      if (!n) return;
      h += '<option value="' + e + '"' +
        (String(mFilter.era) === String(e) ? " selected" : "") +
        '>〔' + esc(nm) + '〕· ' + n.toLocaleString() + ' 處</option>';
    });
    h += "</select>";
    // ⚠️ 只在**真的被截斷**時才寫這行：沒截斷還寫「已顯示 189 / 共 189」
    //    是把一個真數字說得像被砍過，那也是騙人。
    h += '<span class="mfcount">';
    if (shown < sel) {
      h += "已顯示 " + shown.toLocaleString() + " / 共 " + sel.toLocaleString() + " 處";
    } else {
      h += "共 " + sel.toLocaleString() + " 處";
    }
    h += "</span>";
    if (mFilter.book || mFilter.era !== "") {
      h += '<button class="mf" data-act="mfclear">清除篩選</button>';
    }
    h += "</div>";
    return h;
  }
  function resetMFilter(who) {
    if (mFilter.who !== who) { mFilter = { who: who, book: "", era: "" }; }
  }
  /** 篩選條件的查詢串（離線版會被路由忽略，那邊走本地篩）。 */
  function mfQuery() {
    if (mFilter.book) return "?book=" + encodeURIComponent(mFilter.book);
    if (mFilter.era !== "") return "?era=" + encodeURIComponent(mFilter.era);
    return "";
  }
  /** 篩選器被動了 → 重新渲染當前實體（聯機重新請求，離線本地篩）。 */
  function onMFilterChange(kind, val) {
    if (kind === "book") { mFilter.book = val; mFilter.era = ""; }
    else { mFilter.era = val; mFilter.book = ""; }
    var who = mFilter.who || "";
    if (who.indexOf("p:") === 0) {
      renderPerson(who.slice(2)).catch(showErr);
    } else if (who.indexOf("l:") === 0) {
      renderPlace(who.slice(2)).catch(showErr);
    }
  }

  var ALL_BOOK_CODES = ["sj", "hs", "hhs", "sgz", "js"];
  var selectedBooks = ["sj", "hs", "hhs", "sgz", "js"];
  var scopeBook = "";        // 空 = 全五書
  var peiOn = true;          // 默認顯示裴注（三國志裴松之注）
  var currentTab = "search";
  var sortMode = "c";        // c = 篇數（默認），n = 次數
  var IDX = null;            // 索引資料緩存，換書才重取

  var PRESET_CAPSULES = [
    { id: "all5", name: "五書通檢", books: ["sj", "hs", "hhs", "sgz", "js"], title: "全五書通檢（5/5）" },
    { id: "pre4", name: "前四史", books: ["sj", "hs", "hhs", "sgz"], title: "史記·漢書·後漢書·三國志（4/5）" },
    { id: "twohan", name: "兩漢書", books: ["hs", "hhs"], title: "漢書·後漢書（2/5）" },
    { id: "weijin", name: "魏晉史", books: ["sgz", "js"], title: "三國志·晉書（2/5）" }
  ];

  function syncScopeBook() {
    if (selectedBooks.length === 5 || selectedBooks.length === 0) {
      scopeBook = "";
    } else {
      var sorted = ALL_BOOK_CODES.filter(function (c) {
        return selectedBooks.indexOf(c) >= 0;
      });
      scopeBook = sorted.join(",");
    }
  }

  var bookbarEl = document.getElementById("books");
  var quickEl = document.getElementById("quick");

  function statText(n, c) {
    return (c || 0) + " 篇 / " + (n || 0).toLocaleString() + " 次";
  }

  function renderBookbar() {
    var h = "";
    BOOKS.forEach(function (b) {
      var on = selectedBooks.indexOf(b.code) >= 0;
      var title = esc("《" + b.name + "》（" + (b.eraName || "") + "·" + (b.author || "") + "）· " +
                      (b.chapterCount || "") + " 篇");
      h += '<span class="bk' + (on ? " on" : "") + '" data-book="' + b.code + '" title="' + title + '">' +
        esc("《" + b.name + "》") + "<em>" + (b.chapterCount || "") + " 篇</em></span>";
      /* 三國志後緊跟裴注小膠囊（三國志裴松之注） */
      if (b.code === "sgz") {
        h += '<span class="bk pei-chip' + (peiOn ? " on" : "") + '" data-book="pei"' +
          ' title="三國志裴松之注·開啟後統計包含注文【裴N】；關閉則只計正文">' +
          '三國志裴松之注</span>';
      }
    });

    // 四大常用預設膠囊
    h += '<span class="preset-group">';
    PRESET_CAPSULES.forEach(function (ps) {
      var isMatch = (ps.books.length === selectedBooks.length) &&
        ps.books.every(function (c) { return selectedBooks.indexOf(c) >= 0; });
      h += '<span class="preset-pill' + (isMatch ? " on" : "") + '" data-preset="' + ps.id +
        '" title="' + esc(ps.title) + '">' + esc(ps.name) + '</span>';
    });
    h += '</span>';

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
    if (!scopeBook || p.eraRank == null) return false;
    if (scopeBook.indexOf(",") >= 0) {
      var minEra = 999;
      var hasAnyEra = true;
      var curCodes = scopeBook.split(",");
      BOOKS.forEach(function (x) {
        if (curCodes.indexOf(x.code) >= 0) {
          if (!x.era) hasAnyEra = false;
          else if (x.era[0] < minEra) minEra = x.era[0];
        }
      });
      return hasAnyEra && p.eraRank < minEra;
    }
    var b = null;
    BOOKS.forEach(function (x) { if (x.code === scopeBook) b = x; });
    return !!(b && b.era && p.eraRank < b.era[0]);
  }

  /* ⚠️ `isPlace` 決定條目帶 `data-name` 還是 `data-place`：
     人物條目點了去檢索（同名異人要靠搜索消歧），地名條目**直接進詳情頁**——
     地名無重名（實測 trad_name 無重複），沒必要繞一圈搜索。
     以前兩者都帶 data-name，點地名會落到人物搜索上 → 空（這就是「地名點不動」的根因）。 */
  /* ---------- 人物六大類分類體系（Round 2）---------- */
  var FEMALE_PIDS = {
    p_fuhuanghou: 1, p_fuzhaoyi: 1, p_zhuowenjun: 1, p_bianshi_sg: 1, p_lvhou: 1, p_daji: 1,
    p_qifuren: 1, p_mingdema: 1, p_caohuanghou: 1, p_lifuren: 1, p_liangna: 1, p_wangzhi: 1,
    p_wangzhengjun: 1, p_wangzhaojun: 1, p_banjieyu: 1, p_banzhao: 1, p_zhenshi_sg: 1,
    p_dou_taihou: 1, p_zhangdedou: 1, p_caiwenji: 1, p_caiyan_wj: 1, p_bo_ji: 1, p_yumengmu: 1,
    p_weizifu: 1, p_xishi: 1, p_xiedaoyun: 1, p_zhaohede: 1, p_zhaofeiyan: 1, p_guonvwang_sg: 1,
    p_guoshengtong: 1, p_dengsui: 1, p_zhengxiu: 1, p_gouyifuren: 1, p_yanji: 1, p_yinlihua: 1,
    p_chenhuanghou: 1, p_lingsihe: 1, p_fengzhaoyi: 1, p_liji: 1, p_luyuangongzhu: 1,
    p_piaomu: 1, p_lvzhu: 1, p_caoe: 1, p_yueyangziqi: 1, p_shuxianxiong: 1, p_huangfuguiqi: 1
  };

  var FOREIGN_PIDS = {
    p_modu: 1, p_huhanye: 1, p_wuzhuliu: 1, p_laoshang: 1, p_junchen: 1, p_zhizhi: 1,
    p_touman: 1, p_jinmidi: 1, p_wuzhu: 1, p_yushan: 1, p_zhaotuo: 1
  };

  var SIXTEEN_KINGDOM_NAMES = {
    "劉淵": 1, "劉聰": 1, "劉曜": 1, "石勒": 1, "石虎": 1, "石遵": 1, "石鑒": 1, "石祗": 1, "冉閔": 1,
    "慕容廆": 1, "慕容皝": 1, "慕容儁": 1, "慕容暐": 1, "慕容垂": 1, "慕容寶": 1, "慕容盛": 1, "慕容熙": 1, "慕容德": 1, "慕容超": 1,
    "苻洪": 1, "苻健": 1, "苻生": 1, "苻堅": 1, "苻丕": 1, "苻登": 1,
    "姚弋仲": 1, "姚襄": 1, "姚萇": 1, "姚興": 1, "姚泓": 1,
    "李特": 1, "李流": 1, "李雄": 1, "李班": 1, "李期": 1, "李壽": 1, "李勢": 1,
    "張軌": 1, "張寔": 1, "張茂": 1, "張駿": 1, "張重華": 1, "張祚": 1, "張玄靚": 1, "張天錫": 1,
    "呂光": 1, "呂纂": 1, "呂隆": 1, "禿髮烏孤": 1, "禿髮利鹿孤": 1, "禿髮傉檀": 1,
    "乞伏國仁": 1, "乞伏乾歸": 1, "乞伏熾磐": 1, "沮渠蒙遜": 1, "馮跋": 1, "馮弘": 1, "赫連勃勃": 1
  };

  var EMPEROR_NAMES = {
    "黃帝": 1, "炎帝": 1, "顓頊": 1, "帝喾": 1, "帝嚳": 1, "堯": 1, "舜": 1, "禹": 1, "啟": 1, "湯": 1, "太甲": 1, "盤庚": 1, "武丁": 1, "紂": 1, "帝辛": 1,
    "周文王": 1, "周武王": 1, "周成王": 1, "周康王": 1, "周昭王": 1, "周穆王": 1, "周共王": 1, "周懿王": 1, "周孝王": 1, "周夷王": 1, "周厲王": 1, "周宣王": 1, "周幽王": 1, "周平王": 1, "周桓王": 1, "周莊王": 1, "周釐王": 1, "周惠王": 1, "周襄王": 1, "周頃王": 1, "周匡王": 1, "周定王": 1, "周簡王": 1, "周靈王": 1, "周景王": 1, "周悼王": 1, "周敬王": 1, "周元王": 1, "周貞定王": 1, "周哀王": 1, "周思王": 1, "周考王": 1, "周威烈王": 1, "周安王": 1, "周烈王": 1, "周顯王": 1, "周慎靚王": 1, "周赧王": 1,
    "秦始皇": 1, "嬴政": 1, "秦二世": 1, "胡亥": 1, "子嬰": 1, "王莽": 1,
    "劉邦": 1, "漢高祖": 1, "漢惠帝": 1, "劉盈": 1, "漢文帝": 1, "劉恆": 1, "漢景帝": 1, "劉啟": 1, "漢武帝": 1, "劉徹": 1, "漢昭帝": 1, "劉弗陵": 1, "漢宣帝": 1, "劉詢": 1, "漢元帝": 1, "劉奭": 1, "漢成帝": 1, "劉驁": 1, "漢哀帝": 1, "劉欣": 1, "漢平帝": 1, "劉衎": 1, "孺子嬰": 1, "更始帝": 1, "劉玄": 1,
    "光武帝": 1, "劉秀": 1, "漢明帝": 1, "劉莊": 1, "漢章帝": 1, "劉炟": 1, "漢和帝": 1, "劉肇": 1, "漢殤帝": 1, "劉隆": 1, "漢安帝": 1, "劉祜": 1, "漢順帝": 1, "劉保": 1, "漢沖帝": 1, "劉炳": 1, "漢質帝": 1, "劉纘": 1, "漢桓帝": 1, "劉志": 1, "漢靈帝": 1, "劉宏": 1, "少帝辯": 1, "劉辯": 1, "漢獻帝": 1, "劉協": 1,
    "曹丕": 1, "曹叡": 1, "曹芳": 1, "曹髦": 1, "曹奐": 1,
    "劉備": 1, "劉禪": 1,
    "孫權": 1, "孫亮": 1, "孫休": 1, "孫皓": 1,
    "司馬炎": 1, "司馬衷": 1, "司馬熾": 1, "司馬鄴": 1, "司馬睿": 1, "司馬紹": 1, "司馬衍": 1, "司馬岳": 1, "司馬聃": 1, "司馬丕": 1, "司馬奕": 1, "司馬昱": 1, "司馬曜": 1, "司馬德宗": 1, "司馬德文": 1,
    "曹操": 1, "司馬懿": 1, "司馬師": 1, "司馬昭": 1, "孫堅": 1, "孫策": 1
  };

  var SCHOLAR_NAMES = {
    "孔子": 1, "老子": 1, "莊子": 1, "孟子": 1, "荀子": 1, "墨子": 1, "韓非子": 1, "管子": 1, "晏子": 1, "孫子": 1, "曾子": 1, "有子": 1, "列子": 1, "尸子": 1, "慎子": 1,
    "屈原": 1, "司馬相如": 1, "揚雄": 1, "東方朔": 1, "禰衡": 1, "嚴光": 1, "管寧": 1, "華佗": 1, "張仲景": 1, "扁鵲": 1, "淳于意": 1, "倉公": 1,
    "皇甫謐": 1, "葛洪": 1, "郭璞": 1, "陶淵明": 1, "陶潛": 1, "嵇康": 1, "阮籍": 1, "山濤": 1, "向秀": 1, "劉伶": 1, "阮咸": 1, "王戎": 1,
    "左思": 1, "潘岳": 1, "陸機": 1, "陸雲": 1, "干寶": 1, "束晳": 1, "張華": 1, "摯虞": 1, "夏侯湛": 1, "杜預": 1, "裴秀": 1,
    "公西赤": 1, "子路": 1, "顏回": 1, "子貢": 1, "子夏": 1, "子游": 1, "閔子騫": 1, "冉伯牛": 1, "仲弓": 1, "宰我": 1, "端木賜": 1, "冉有": 1, "季路": 1, "言偃": 1, "卜商": 1, "顓孫師": 1, "澹臺滅明": 1, "原憲": 1, "公冶長": 1, "南宮适": 1, "樊遲": 1
  };

  function isFemale(p) {
    if (!p) return false;
    if (FEMALE_PIDS[p.id]) return true;
    var t = p.title || "";
    if (t === "夏后氏" || t === "夏后啟") return false;
    if (/(后|太后|皇后|元后|高后|妃|姬|公主|長公主|翁主|夫人|婕妤|昭儀|貴人)$/.test(t)) {
      var n = p.name || "";
      if (["后羿", "后稷", "夏后啟", "蚩尤", "申公"].indexOf(n) < 0) return true;
    }
    return false;
  }

  function isForeign(p) {
    if (!p) return false;
    if (FOREIGN_PIDS[p.id]) return true;
    var t = p.title || "", s = p.summary || "", n = p.name || "";
    if (/(單于|可汗|左賢王|右賢王|休屠王|渾邪王|昆彌|歸義侯|邑君|夜郎王|滇王)$/.test(t)) return true;
    if (s.indexOf("匈奴單于") >= 0 || s.indexOf("鮮卑首領") >= 0 || s.indexOf("烏桓首領") >= 0 ||
        s.indexOf("西域城郭諸國") >= 0 || s.indexOf("羌族首領") >= 0 || s.indexOf("氐族首領") >= 0 ||
        s.indexOf("西南夷首領") >= 0 || s.indexOf("烏孫昆彌") >= 0) return true;
    if (/(單于|呼韓邪|冒頓|軍臣|伊稚斜|烏維|且鞮侯|狐鹿姑|郅支|烏珠留|頭曼)$/.test(n)) return true;
    return false;
  }

  function isEmperor(p) {
    if (!p) return false;
    var n = p.name || "", t = p.title || "", s = p.summary || "";
    if (EMPEROR_NAMES[n] || SIXTEEN_KINGDOM_NAMES[n]) return true;
    if (/(皇帝|天子|世祖|太祖|高祖|太宗|世宗|中宗|顯宗|肅宗|烈祖|昭烈帝|大帝)$/.test(t)) {
      if (!/(後|妃|女|母)$/.test(t)) return true;
    }
    if (/(帝|天子|皇帝)$/.test(t) && !/(後|妃|女|母)$/.test(t)) return true;
    if (s.indexOf("開國皇帝") >= 0 || s.indexOf("皇帝，") >= 0 || s.indexOf("西漢皇帝") >= 0 ||
        s.indexOf("東漢皇帝") >= 0 || s.indexOf("曹魏皇帝") >= 0 || s.indexOf("蜀漢皇帝") >= 0 ||
        s.indexOf("東吳皇帝") >= 0 || s.indexOf("西晉皇帝") >= 0 || s.indexOf("東晉皇帝") >= 0 ||
        s.indexOf("追尊為帝") >= 0 || s.indexOf("追尊為武帝") >= 0 || s.indexOf("追尊為文帝") >= 0 ||
        s.indexOf("追尊為宣帝") >= 0 || s.indexOf("追尊為景帝") >= 0 || s.indexOf("追尊為高帝") >= 0) return true;
    if (s.indexOf("五帝之首") >= 0 || s.indexOf("五帝之一") >= 0 || s.indexOf("三皇之一") >= 0 ||
        s.indexOf("夏朝開國君主") >= 0 || s.indexOf("商朝開國君主") >= 0 || s.indexOf("周朝開國君主") >= 0) return true;
    return false;
  }

  function isScholar(p) {
    if (!p) return false;
    var n = p.name || "", t = p.title || "", s = p.summary || "";
    if (SCHOLAR_NAMES[n]) return true;
    if (s.indexOf("儒家創始人") >= 0 || s.indexOf("道家代表人物") >= 0 || s.indexOf("法家代表人物") >= 0 ||
        s.indexOf("墨家創始人") >= 0 || s.indexOf("著名醫學家") >= 0 || s.indexOf("著名文學家") >= 0 ||
        s.indexOf("著名經學家") >= 0 || s.indexOf("著名隱士") >= 0 || s.indexOf("方士") >= 0 ||
        s.indexOf("術士") >= 0 || s.indexOf("高士") >= 0 || s.indexOf("隱逸") >= 0 ||
        s.indexOf("孔門十哲") >= 0 || s.indexOf("孔門弟子") >= 0 || s.indexOf("七十二賢") >= 0 ||
        s.indexOf("竹林七賢") >= 0 || s.indexOf("建安七子") >= 0) {
      if (!/(皇帝|丞相|太尉|大將軍)$/.test(t)) return true;
    }
    if (/(文士|先賢|名士|處士|高士|隱士)$/.test(t)) return true;
    return false;
  }

  function isMinister(p) {
    if (!p) return false;
    var t = p.title || "", s = p.summary || "", n = p.name || "";
    if (/(相|將軍|太守|刺史|尚書|大夫|侍郎|都尉|中郎將|司馬|太尉|司徒|司空|令|僕射|尹|尉|校尉|御史|謀士|重臣|名臣|名將)$/.test(t)) return true;
    if (s.indexOf("丞相") >= 0 || s.indexOf("大將軍") >= 0 || s.indexOf("名將") >= 0 ||
        s.indexOf("謀臣") >= 0 || s.indexOf("名相") >= 0 || s.indexOf("重臣") >= 0 ||
        s.indexOf("大臣") >= 0 || s.indexOf("將領") >= 0 || s.indexOf("刺史") >= 0 ||
        s.indexOf("太守") >= 0 || s.indexOf("尚書") >= 0 || s.indexOf("開國功臣") >= 0) return true;
    if (["曹操", "司馬懿", "司馬師", "司馬昭", "王莽", "金日磾", "劉秀", "劉邦", "孫策", "孫堅"].indexOf(n) >= 0) return true;
    if (!isFemale(p) && !isForeign(p) && !isEmperor(p)) return true;
    return false;
  }

  function isLord(p) {
    if (!p) return false;
    var s = p.summary || "";
    if (s.indexOf("【本名：") === 0) return true;
    var n = p.name || "";
    if (n.indexOf("公子") === 0 || n.indexOf("公孫") === 0 || n.indexOf("公孙") === 0) return true;
    if (["孟嘗君", "孟尝君", "信陵君", "平原君", "春申君"].indexOf(n) >= 0) return true;
    if (/(公|侯|伯|王|君)$/.test(n) && !/(孔子|孟子|荀子|老子|莊子|庄子|韓非子|韩非子|墨子|管子|晏子|孫子|孙子|曾子|有子|列子|尸子|慎子)$/.test(n)) {
      return true;
    }
    return false;
  }

  // 漢初異姓諸侯王（高祖分封之開國異姓王及趙王張敖等）
  var HET_KING_PIDS = {
    p_hanxin: 1, p_pengyue: 1, p_qingbu: 1, p_zhang_er: 1, p_zhangao: 1,
    p_luwan: 1, p_zangtu: 1, p_hanwangxin: 1, p_wu_rui: 1
  };
  var HET_KING_NAMES = {
    "韓信": 1, "彭越": 1, "英布": 1, "黥布": 1, "張耳": 1, "張敖": 1,
    "盧綰": 1, "韓王信": 1, "吳芮": 1, "臧荼": 1
  };

  function getRealName(p) {
    var s = (p && p.summary) || "";
    if (s.indexOf("【本名：") >= 0) {
      return s.split("【本名：")[1].split("】")[0].trim();
    }
    if (s.indexOf("【本名:") >= 0) {
      return s.split("【本名:")[1].split("】")[0].trim();
    }
    return (p && p.name) || "";
  }

  function getLordSubCat(p) {
    if (!isLord(p)) return "";
    var id = (p && p.id) || "", n = (p && p.name) || "", d = (p && p.dynasty) || "";
    var rn = getRealName(p);

    // 1. 漢初異姓諸侯王
    if (HET_KING_PIDS[id] || HET_KING_NAMES[n] || HET_KING_NAMES[rn]) return "han_het";

    // 2. 先秦列國諸侯（春秋、戰國、先秦、西周、東周、商）
    if (["春秋", "戰國", "先秦", "西周", "東周", "商"].indexOf(d) >= 0) return "pre_qin";

    // 3. 三國魏晉宗室（三國、西晉、東晉、十六國）
    if (["三國", "西晉", "東晉", "十六國"].indexOf(d) >= 0) return "sg_jin";

    // 4. 兩漢劉氏宗藩（西漢、東漢、漢、新，且為劉氏）
    if (["西漢", "東漢", "漢", "新"].indexOf(d) >= 0) {
      if (rn.indexOf("劉") === 0 || n.indexOf("劉") === 0) return "han_liu";
      return "merit_marquis";
    }

    return "merit_marquis";
  }

  function indexGrid(items, isPlace) {
    var h = '<div class="grid">';
    items.forEach(function (p) {
      var attr = isPlace
        ? 'data-place="' + esc(p.id) + '"'
        : 'data-name="' + esc(p.name) + '"';

      var badges = "";
      if (!isPlace) {
        if (isEmperor(p)) badges += '<i class="emp-badge" title="天子君主·割據僭號·追尊帝號">帝皇</i>';
        if (isFemale(p)) badges += '<i class="fem-badge" title="巾幗女性·后妃名媛">巾幗</i>';
        if (isForeign(p)) badges += '<i class="for-badge" title="四夷君長·部落首領">外族</i>';
        if (isScholar(p)) badges += '<i class="sch-badge" title="諸子百家·高士文豪·名醫方伎">文士</i>';
        if (isLord(p)) {
          var sub = getLordSubCat(p);
          if (sub === "han_het") {
            badges += '<i class="het-badge" title="漢初開國異姓諸侯王">異姓王</i>';
          } else if (sub === "han_liu") {
            badges += '<i class="liu-badge" title="兩漢劉氏宗室諸侯王">宗王</i>';
          } else if (sub === "sg_jin") {
            badges += '<i class="sgj-badge" title="三國魏晉宗室諸王">宗室</i>';
          } else if (sub === "merit_marquis") {
            badges += '<i class="mar-badge" title="秦漢功臣名將封侯">列侯</i>';
          } else {
            badges += '<i class="lord-badge" title="先秦列國諸侯公侯">諸侯</i>';
          }
        }
        if (isFormerEra(p)) badges += '<i class="era-old" title="本書記載時代之前的人物（前代先賢）">前代</i>';
      }

      h += '<div class="item" ' + attr + ' title="' +
        esc(p.summary || "") + '"><span class="n">' + esc(p.name) +
        badges +
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

  var currentPersonCat = "all";   // all | emperor | lord | minister | female | foreign | scholar
  var currentLordSub = "all";     // all | pre_qin | han_het | han_liu | sg_jin | merit_marquis
  var currentPersonEra = "all";   // all | current | former

  function renderPersonsIndex() {
    var allItems = resort(((IDX || {}).persons || {}).items || []);

    // 計算各大類人數
    var empCount = 0, lordCount = 0, minCount = 0, femCount = 0, forCount = 0, schCount = 0;
    allItems.forEach(function (p) {
      if (isEmperor(p)) empCount++;
      if (isLord(p)) lordCount++;
      if (isMinister(p)) minCount++;
      if (isFemale(p)) femCount++;
      if (isForeign(p)) forCount++;
      if (isScholar(p)) schCount++;
    });

    // 計算公侯子類別計數
    var lordItems = allItems.filter(isLord);
    var preQinCount = 0, hanHetCount = 0, hanLiuCount = 0, sgJinCount = 0, marCount = 0;
    lordItems.forEach(function (p) {
      var sub = getLordSubCat(p);
      if (sub === "pre_qin") preQinCount++;
      else if (sub === "han_het") hanHetCount++;
      else if (sub === "han_liu") hanLiuCount++;
      else if (sub === "sg_jin") sgJinCount++;
      else if (sub === "merit_marquis") marCount++;
    });

    // 1. 分類過濾
    var catItems = allItems;
    if (currentPersonCat === "emperor") catItems = allItems.filter(isEmperor);
    else if (currentPersonCat === "lord") {
      catItems = lordItems;
      if (currentLordSub !== "all") {
        catItems = catItems.filter(function (p) { return getLordSubCat(p) === currentLordSub; });
      }
    }
    else if (currentPersonCat === "minister") catItems = allItems.filter(isMinister);
    else if (currentPersonCat === "female") catItems = allItems.filter(isFemale);
    else if (currentPersonCat === "foreign") catItems = allItems.filter(isForeign);
    else if (currentPersonCat === "scholar") catItems = allItems.filter(isScholar);

    // 計算當前分類下的前代與當世人數
    var formerCount = 0;
    catItems.forEach(function (p) { if (isFormerEra(p)) formerCount++; });
    var currentCount = catItems.length - formerCount;

    // 2. 時空切片過濾
    var filteredItems = catItems;
    if (currentPersonEra === "current") {
      filteredItems = catItems.filter(function (p) { return !isFormerEra(p); });
    } else if (currentPersonEra === "former") {
      filteredItems = catItems.filter(isFormerEra);
    }

    var h = '<div class="group-title">人物索引 <span class="count">' +
      filteredItems.length.toLocaleString() + ' 人 · <span class="sort-toggle" ' +
      'role="button" tabindex="0">' + sortLabel() + '</span> · 懸停看簡介</span></div>';

    // 6 大主體分類欄
    h += '<div class="person-cat-bar">' +
      '<span class="cat-pill' + (currentPersonCat === "all" ? " on" : "") + '" data-pcat="all">全部 (' + allItems.length.toLocaleString() + ')</span>' +
      '<span class="cat-pill' + (currentPersonCat === "emperor" ? " on" : "") + '" data-pcat="emperor">帝皇君主 (' + empCount.toLocaleString() + ')</span>' +
      '<span class="cat-pill' + (currentPersonCat === "lord" ? " on" : "") + '" data-pcat="lord">諸侯公侯 · 公侯名錄 (' + lordCount.toLocaleString() + ')</span>' +
      '<span class="cat-pill' + (currentPersonCat === "minister" ? " on" : "") + '" data-pcat="minister">名臣將相 · 文武百僚 (' + minCount.toLocaleString() + ')</span>' +
      '<span class="cat-pill' + (currentPersonCat === "female" ? " on" : "") + '" data-pcat="female">巾幗女性 (' + femCount.toLocaleString() + ')</span>' +
      '<span class="cat-pill' + (currentPersonCat === "foreign" ? " on" : "") + '" data-pcat="foreign">異域外族 (' + forCount.toLocaleString() + ')</span>' +
      '<span class="cat-pill' + (currentPersonCat === "scholar" ? " on" : "") + '" data-pcat="scholar">文人方伎 · 隱逸 (' + schCount.toLocaleString() + ')</span>' +
      '</div>';

    // 公侯政體二級切片欄（僅在選中「諸侯公侯」時呈現）
    if (currentPersonCat === "lord") {
      h += '<div class="person-subcat-bar">' +
        '<span class="subcat-label">公侯政體：</span>' +
        '<span class="subcat-pill' + (currentLordSub === "all" ? " on" : "") + '" data-plsub="all">全部公侯 (' + lordItems.length.toLocaleString() + ')</span>' +
        '<span class="subcat-pill' + (currentLordSub === "pre_qin" ? " on" : "") + '" data-plsub="pre_qin">先秦列國諸侯 (' + preQinCount.toLocaleString() + ')</span>' +
        '<span class="subcat-pill' + (currentLordSub === "han_het" ? " on" : "") + '" data-plsub="han_het">漢初異姓諸侯王 (' + hanHetCount.toLocaleString() + ')</span>' +
        '<span class="subcat-pill' + (currentLordSub === "han_liu" ? " on" : "") + '" data-plsub="han_liu">兩漢劉氏宗藩 (' + hanLiuCount.toLocaleString() + ')</span>' +
        '<span class="subcat-pill' + (currentLordSub === "sg_jin" ? " on" : "") + '" data-plsub="sg_jin">三國魏晉宗室 (' + sgJinCount.toLocaleString() + ')</span>' +
        '<span class="subcat-pill' + (currentLordSub === "merit_marquis" ? " on" : "") + '" data-plsub="merit_marquis">秦漢名臣封侯 (' + marCount.toLocaleString() + ')</span>' +
        '</div>';
    }

    // 時空歸屬二級切片欄
    h += '<div class="person-era-bar">' +
      '<span class="era-label">時空歸屬：</span>' +
      '<span class="era-pill' + (currentPersonEra === "all" ? " on" : "") + '" data-pera="all">古今通覽 (' + catItems.length.toLocaleString() + ')</span>' +
      '<span class="era-pill' + (currentPersonEra === "current" ? " on" : "") + '" data-pera="current">本朝當世 (' + currentCount.toLocaleString() + ')</span>' +
      '<span class="era-pill' + (currentPersonEra === "former" ? " on" : "") + '" data-pera="former">前代先賢 (' + formerCount.toLocaleString() + ')</span>' +
      '</div>';

    h += indexGrid(filteredItems, false);
    out.innerHTML = h;
  }

  /* =========================================================================
     兩漢三國兵爭形勝輿圖引擎（方案 A · 古典宣紙矢量地圖 SVG）
     依據宋杰教授三大專著考據與譚其驤歷史地圖集，純原生 SVG 繪製古山川形勝與戰略攻守網絡
     ========================================================================= */
  var MAP_BOUNDS = {
    lngMin: 102.0, lngMax: 122.5,
    latMin: 26.5, latMax: 43.2,
    w: 1000, h: 680,
    padX: 0, padY: 0
  };

  function parseViewBox(str) {
    var parts = (str || "0 0 1000 680").trim().split(/\s+/).map(Number);
    return { x: parts[0] || 0, y: parts[1] || 0, w: parts[2] || 1000, h: parts[3] || 680 };
  }

  var mapState = {
    zone: "all",
    curVb: { x: 0, y: 0, w: 1000, h: 680 },
    showRoutes: true,
    showTerrain: true,
    selectedHub: null,
    itineraryPerson: null,
    itineraryPlaces: [],
    lastDragTime: 0
  };

  var MAP_VIEWBOXES = {
    "all": "0 0 1000 680",
    "sb": "480 30 460 290",
    "hl": "310 250 500 160",
    "ls": "30 260 510 210",
    "jx": "420 420 240 220",
    "jh": "640 400 240 180"
  };

  var ZONE_COLORS = {
    "塞北邊疆戰區": "#4a5568",
    "荊襄戰區": "#2f6d7a",
    "江淮戰區": "#a8382b",
    "秦嶺隴蜀戰區": "#2d6a4f",
    "中原河洛戰區": "#8c6239",
    "中原河北戰區": "#8c6239"
  };

  function projectCoord(lng, lat) {
    var usW = MAP_BOUNDS.w - MAP_BOUNDS.padX * 2;
    var usH = MAP_BOUNDS.h - MAP_BOUNDS.padY * 2;
    var x = MAP_BOUNDS.padX + ((lng - MAP_BOUNDS.lngMin) / (MAP_BOUNDS.lngMax - MAP_BOUNDS.lngMin)) * usW;
    var y = MAP_BOUNDS.padY + ((MAP_BOUNDS.latMax - lat) / (MAP_BOUNDS.latMax - MAP_BOUNDS.latMin)) * usH;
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
  }

  var RIVER_COORDS = {
    "changjiang": [
      [109.8, 31.0], [110.5, 30.9], [111.29, 30.70], [111.8, 30.4],
      [112.19, 30.35], [112.9, 29.8], [113.90, 29.87], [114.13, 30.34],
      [114.30, 30.55], [114.89, 30.40], [115.90, 29.68], [116.8, 30.5],
      [117.3, 30.7], [117.88, 31.39], [118.5, 31.55], [118.78, 32.06],
      [119.45, 32.20], [120.5, 31.9]
    ],
    "huanghe": [
      [109.8, 34.6], [110.25, 34.55], [111.2, 34.8], [112.45, 34.82],
      [113.4, 34.95], [113.8, 35.0], [114.20, 35.15], [114.98, 35.48],
      [115.3, 36.4], [116.0, 37.0], [117.2, 37.5]
    ],
    "hanshui": [
      [106.94, 33.00], [107.5, 33.2], [108.2, 33.0], [109.1, 32.7],
      [110.8, 32.6], [112.14, 32.01], [112.6, 31.5], [113.0, 30.7],
      [113.8, 30.6], [114.30, 30.55]
    ],
    "huaishui": [
      [113.4, 32.4], [114.8, 32.4], [115.6, 32.5], [116.78, 32.58],
      [117.3, 32.9], [118.5, 33.0], [119.5, 33.4]
    ]
  };

  function buildRiverPath(pts) {
    if (!pts || !pts.length) return "";
    var projs = pts.map(function (p) { return projectCoord(p[0], p[1]); });
    var d = "M " + projs[0][0] + " " + projs[0][1];
    for (var i = 1; i < projs.length; i++) {
      if (i === 1) {
        d += " L " + projs[1][0] + " " + projs[1][1];
      } else {
        var p0 = projs[i - 1], p1 = projs[i];
        d += " Q " + p0[0] + " " + p0[1] + " " + p1[0] + " " + p1[1];
      }
    }
    return d;
  }

  function renderStrategicMap(strats) {
    strats = strats || {};
    var stratKeys = Object.keys(strats);
    if (!stratKeys.length) return "";

    if (!mapState.curVb) {
      mapState.curVb = parseViewBox(MAP_VIEWBOXES[mapState.zone] || MAP_VIEWBOXES["all"]);
    }
    var vb = mapState.curVb;
    var vbStr = [Math.round(vb.x), Math.round(vb.y), Math.round(vb.w), Math.round(vb.h)].join(" ");
    var zoomPct = Math.round((1000 / vb.w) * 100);

    var h = '<div class="strat-map-wrap" id="stratMapWrap">';

    if (mapState.itineraryPerson) {
      h += '<div class="map-itin-bar">' +
        '<span><b>【平生行跡模式】</b>正在檢視<b>「' + esc(mapState.itineraryPerson) + '」</b>之兵爭與輿地交集（共標記 ' +
        mapState.itineraryPlaces.length + ' 處要塞）</span>' +
        '<button class="map-itin-close" data-act="map-itin-close">✕ 退出行跡模式</button>' +
        '</div>';
    }

    h += '<div class="strat-map-bar">' +
      '<div class="strat-map-title-box">' +
      '<span class="strat-map-title">兩漢三國兵爭形勝輿圖</span>' +
      '<span class="strat-map-sub">宋杰兵爭考據 · 塞北與中原南北五大戰區戰略拓撲</span>' +
      '</div>' +
      '<div class="strat-map-controls">' +
      '<span class="map-pill' + (mapState.zone === "all" ? " on" : "") + '" data-map-zone="all">全景通覽</span>' +
      '<span class="map-pill' + (mapState.zone === "sb" ? " on" : "") + '" data-map-zone="sb">塞北幽燕</span>' +
      '<span class="map-pill' + (mapState.zone === "hl" ? " on" : "") + '" data-map-zone="hl">中原河洛</span>' +
      '<span class="map-pill' + (mapState.zone === "ls" ? " on" : "") + '" data-map-zone="ls">漢中隴蜀</span>' +
      '<span class="map-pill' + (mapState.zone === "jx" ? " on" : "") + '" data-map-zone="jx">荊襄戰區</span>' +
      '<span class="map-pill' + (mapState.zone === "jh" ? " on" : "") + '" data-map-zone="jh">淮南江東</span>' +
      '<span class="map-pill' + (mapState.showRoutes ? " on" : "") + '" data-map-toggle="routes">' +
      (mapState.showRoutes ? "攻守通道：開" : "攻守通道：關") + '</span>' +
      '<span class="map-pill' + (mapState.showTerrain ? " on" : "") + '" data-map-toggle="terrain">' +
      (mapState.showTerrain ? "⛰️ 地形底圖：開" : "⛰️ 地形底圖：關") + '</span>' +
      '<span class="map-pill" data-map-reset="true" title="復位全景並清除選中">復位</span>' +
      '</div>' +
      '</div>';

    h += '<div class="strat-map-body" id="stratMapBody">';
    h += '<svg class="strat-map-svg" id="stratMapSvg" viewBox="' + vbStr + '" preserveAspectRatio="xMidYMid meet">';

    // 1. 底圖紋理背景與真實立體自然地形底圖
    h += '<rect x="0" y="0" width="1000" height="680" fill="#FAF7F0"/>';
    if (mapState.showTerrain) {
      h += '<image href="terrain_basemap.jpg" x="0" y="0" width="1000" height="680" preserveAspectRatio="none" opacity="0.88" class="map-terrain-layer"/>';
    }

    // 2. 戰區宏觀浮水印
    h += '<g class="map-watermarks">' +
      '<text class="map-zone-label" x="720" y="70" fill="#4a5568">【塞北幽燕戰區】</text>' +
      '<text class="map-zone-label" x="140" y="270" fill="#2d6a4f">【秦嶺隴蜀戰區】</text>' +
      '<text class="map-zone-label" x="510" y="260" fill="#8c6239">【中原河洛與河北戰區】</text>' +
      '<text class="map-zone-label" x="510" y="580" fill="#2f6d7a">【荊襄戰區】</text>' +
      '<text class="map-zone-label" x="790" y="520" fill="#a8382b">【江淮戰區】</text>' +
      '</g>';

    // 3. 主要山脈形勝（沿立體山脈主脊走向橫貫排布，低對比度水墨古典字距，與城邑要塞分層解耦）
    h += '<g class="map-mountains">' +
      '<text class="map-mountain-range" x="730" y="96" text-anchor="middle">── 燕　山　山　脈 ──</text>' +
      '<text class="map-mountain-range" x="525" y="225" text-anchor="middle">▲ 太　行　山</text>' +
      '<text class="map-mountain-range qinling" x="295" y="394" text-anchor="middle">── 秦　嶺　山　脈 ──</text>' +
      '<text class="map-mountain-range" x="220" y="452" text-anchor="middle">── 大　巴　山 ──</text>' +
      '<text class="map-mountain-range" x="670" y="488" text-anchor="middle">── 大　別　山 ──</text>' +
      '</g>';

    // 4. 古山川水系
    var pathCJ = buildRiverPath(RIVER_COORDS["changjiang"]);
    var pathHH = buildRiverPath(RIVER_COORDS["huanghe"]);
    var pathHS = buildRiverPath(RIVER_COORDS["hanshui"]);
    var pathHU = buildRiverPath(RIVER_COORDS["huaishui"]);

    h += '<g class="map-rivers">' +
      '<path d="' + pathCJ + '" fill="none" stroke="#527588" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>' +
      '<text class="map-water-label" x="830" y="460">大江（長江）→</text>' +
      '<path d="' + pathHH + '" fill="none" stroke="#b08d57" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.62"/>' +
      '<text class="map-water-label" x="650" y="310">古黃河 →</text>' +
      '<path d="' + pathHS + '" fill="none" stroke="#688f9e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>' +
      '<text class="map-water-label" x="470" y="450">漢水</text>' +
      '<path d="' + pathHU + '" fill="none" stroke="#688f9e" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>' +
      '<text class="map-water-label" x="730" y="440">淮水</text>' +
      '</g>';

    // 5. 攻守通道連線
    if (mapState.showRoutes) {
      h += '<g class="map-routes">';
      var drawnEdges = {};
      stratKeys.forEach(function (k) {
        var it = strats[k];
        if (!it || !it.coords) return;
        var p0 = projectCoord(it.coords[0], it.coords[1]);
        (it.connections || []).forEach(function (tgtId) {
          if (!strats[tgtId] || !strats[tgtId].coords) return;
          var edgeKey = (k < tgtId) ? (k + "|" + tgtId) : (tgtId + "|" + k);
          if (drawnEdges[edgeKey]) return;
          drawnEdges[edgeKey] = true;
          var p1 = projectCoord(strats[tgtId].coords[0], strats[tgtId].coords[1]);
          var isLineActive = (mapState.selectedHub === k || mapState.selectedHub === tgtId);
          h += '<line x1="' + p0[0] + '" y1="' + p0[1] + '" x2="' + p1[0] + '" y2="' + p1[1] + '" ' +
            'class="map-route-line' + (isLineActive ? " active" : "") + '"/>';
        });
      });
      h += '</g>';
    }

    // 6. 人物行跡流動連線（基於戰略攻守通道拓撲走廊網絡）
    if (mapState.itineraryPerson && mapState.itineraryPlaces.length >= 2) {
      h += '<g class="map-itinerary-layer">';
      var itinSet = {};
      mapState.itineraryPlaces.forEach(function (pid) { itinSet[pid] = true; });
      var itinDrawn = {};
      var validEdgesCount = 0;

      // 優先繪製人物涉足要塞之間的所有攻守走廊
      mapState.itineraryPlaces.forEach(function (pid) {
        var it = strats[pid];
        if (!it || !it.coords) return;
        var p0 = projectCoord(it.coords[0], it.coords[1]);
        (it.connections || []).forEach(function (tgtId) {
          if (itinSet[tgtId] && strats[tgtId] && strats[tgtId].coords) {
            var eKey = (pid < tgtId) ? (pid + "_" + tgtId) : (tgtId + "_" + pid);
            if (!itinDrawn[eKey]) {
              itinDrawn[eKey] = true;
              validEdgesCount++;
              var p1 = projectCoord(strats[tgtId].coords[0], strats[tgtId].coords[1]);
              h += '<line x1="' + p0[0] + '" y1="' + p0[1] + '" x2="' + p1[0] + '" y2="' + p1[1] + '" class="map-flow-line"/>';
            }
          }
        });
      });

      // 兜底：若要塞間無直接通道連線（離散要塞），則串聯主幹連線
      if (validEdgesCount === 0) {
        for (var pi = 0; pi < mapState.itineraryPlaces.length - 1; pi++) {
          var idA = mapState.itineraryPlaces[pi], idB = mapState.itineraryPlaces[pi + 1];
          if (strats[idA] && strats[idB] && strats[idA].coords && strats[idB].coords) {
            var pa = projectCoord(strats[idA].coords[0], strats[idA].coords[1]);
            var pb = projectCoord(strats[idB].coords[0], strats[idB].coords[1]);
            h += '<line x1="' + pa[0] + '" y1="' + pa[1] + '" x2="' + pb[0] + '" y2="' + pb[1] + '" class="map-flow-line"/>';
          }
        }
      }
      h += '</g>';
    }

    // 7. 43 處兵爭要衝節點打點
    h += '<g class="map-hubs">';
    stratKeys.forEach(function (k) {
      var it = strats[k];
      if (!it || !it.coords) return;
      var pt = projectCoord(it.coords[0], it.coords[1]);
      var zColor = ZONE_COLORS[it.zone] || "#a8382b";
      var isMuted = mapState.itineraryPerson && (mapState.itineraryPlaces.indexOf(k) < 0);
      var isSel = (mapState.selectedHub === k);
      var isItinMatch = mapState.itineraryPerson && (mapState.itineraryPlaces.indexOf(k) >= 0);

      var hubClasses = "map-hub";
      if (isMuted) hubClasses += " muted";
      if (isSel) hubClasses += " selected";

      var battlesStr = (it.battles || []).slice(0, 3).join("、");

      h += '<g class="' + hubClasses + '" data-plid="' + esc(k) + '" ' +
        'data-name="' + esc(it.trad_name) + '" data-zone="' + esc(it.zone) + '" ' +
        'data-title="' + esc(it.strat_title) + '" data-battles="' + esc(battlesStr) + '">';

      // 寬大透明命中感應區（全面包裹圓點與文字，杜絕游標在筆畫間移動造成閃爍）
      h += '<rect x="' + (pt[0] - 24) + '" y="' + (pt[1] - 22) + '" width="48" height="42" rx="10" class="hub-hitarea"/>';

      if (isSel || isItinMatch) {
        h += '<circle cx="' + pt[0] + '" cy="' + pt[1] + '" r="6" stroke="' + (isSel ? "#9B3326" : zColor) + '" fill="none" class="map-pulse-ring"/>';
      }

      h += '<circle cx="' + pt[0] + '" cy="' + pt[1] + '" r="' + (isSel ? "7.5" : "5.5") + '" ' +
        'stroke="' + zColor + '" class="hub-ring"/>';
      h += '<circle cx="' + pt[0] + '" cy="' + pt[1] + '" r="' + (isSel ? "3.5" : "2.5") + '" ' +
        'fill="' + zColor + '" class="hub-dot"/>';

      var textX = pt[0];
      var textY = pt[1] - (isSel ? 10 : 8);
      if (k === "pl_fancheng") { textY = pt[1] - 9; }
      else if (k === "pl_xiangyang") { textY = pt[1] + 16; }
      else if (k === "pl_dingjunshan") { textY = pt[1] + 15; }
      else if (k === "pl_chenggao") { textY = pt[1] + 15; }
      else if (k === "pl_xiling") { textY = pt[1] + 15; }

      h += '<text x="' + textX + '" y="' + textY + '" text-anchor="middle" ' +
        'class="hub-text" fill="#2c2825">' + esc(it.trad_name) + '</text>';

      h += '</g>';
    });
    h += '</g>';

    h += '</svg>';
    h += '<div class="map-zoom-tools">' +
      '<button class="map-zoom-btn" data-map-zoom="in" title="放大（亦可滾輪放大）">＋</button>' +
      '<button class="map-zoom-btn" data-map-zoom="reset" title="復位當前戰區視野">⟲</button>' +
      '<button class="map-zoom-btn" data-map-zoom="out" title="縮小（亦可滾輪縮小）">－</button>' +
      '<div class="map-zoom-level" id="mapZoomLevel">' + zoomPct + '%</div>' +
      '</div>';
    h += '<div class="map-tooltip" id="mapTooltip"></div>';
    h += '</div>';
    h += '</div>';
    return h;
  }

  function renderPlacesIndex() {
    var items = resort(((IDX || {}).places || {}).items || []);
    var strats = (IDX || {}).strategicPlaces || (window.BOOKINDEX_DATA && window.BOOKINDEX_DATA.strat) || {};
    var stratKeys = Object.keys(strats);
    var h = "";

    // 兵爭要地 · 五大戰區形勝輿圖與專欄（宋杰先生軍事地理考據精華）
    if (stratKeys.length) {
      h += '<div class="group-title">兩漢三國兵爭形勝圖 <span class="count">' + stratKeys.length + ' 處要塞</span></div>';
      h += renderStrategicMap(strats);

      // 如果有當前選中的要衝，渲染專屬考據卡片
      if (mapState.selectedHub && strats[mapState.selectedHub]) {
        var sh = strats[mapState.selectedHub];
        h += '<div class="card strat-card" id="selectedHubCard" style="border-left: 4px solid var(--accent); margin-bottom: 16px;">' +
          '<div class="strat-head">' +
          '<div><span class="strat-title">【選中要衝考據】' + esc(sh.trad_name) + ' · ' + esc(sh.strat_title) + '</span>' +
          '<span class="strat-zone" style="margin-left: 8px;">' + esc(sh.zone) + '</span></div>' +
          '<button class="map-view-btn" data-place="' + esc(mapState.selectedHub) + '">進入「' + esc(sh.trad_name) + '」輿地檢索 ➔</button>' +
          '</div>' +
          '<div class="strat-desc"><p>' + esc(sh.strat_desc) + "</p></div>" +
          '<div class="strat-evolution"><b>古今沿革：</b>' + esc(sh.evolution) + "</div>" +
          (sh.battles && sh.battles.length ? ('<div class="strat-battles"><b>關聯戰事：</b>' + sh.battles.map(function (bt) { return '<span class="battle-pill">' + esc(bt) + "</span>"; }).join("") + "</div>") : "") +
          '</div>';
      }

      var zoneOrder = ["塞北邊疆戰區", "中原河洛戰區", "中原河北戰區", "秦嶺隴蜀戰區", "荊襄戰區", "江淮戰區"];
      var byZone = {};
      stratKeys.forEach(function (k) {
        var it = strats[k];
        var z = it.zone || "其他";
        (byZone[z] = byZone[z] || []).push({ id: k, data: it });
      });

      h += '<div class="group-title">兵爭要地 · 五大戰區要衝一覽 <span class="count">' + stratKeys.length + ' 處</span></div>';
      h += '<div class="card strat-index-card">';
      h += '<div class="strat-intro"><p>依據宋杰先生《三國兵爭要地與戰略》《中國古代戰爭的地理樞紐》考訂。點選地圖節點或下方要塞，可檢視學術考據與人地共現。</p></div>';

      zoneOrder.forEach(function (z) {
        var list = byZone[z];
        if (!list || !list.length) return;
        h += '<div class="zone-block">';
        h += '<div class="zone-name">【' + esc(z) + '】<span class="sub-count">' + list.length + ' 處</span></div>';
        h += '<div class="zone-pills">';
        list.forEach(function (node) {
          var isCur = (mapState.selectedHub === node.id);
          h += '<span class="strat-pill' + (isCur ? " on" : "") + '" data-map-hub="' + esc(node.id) + '">' +
            esc(node.data.trad_name) + '</span>';
        });
        h += '</div></div>';
      });
      h += '</div>';
    }

    var groups = {};
    items.forEach(function (p) {
      (groups[p.kind] = groups[p.kind] || []).push(p);
    });
    PLACE_KIND_ORDER.forEach(function (k) {
      var one = groups[k];
      if (!one || !one.length) return;
      h += '<div class="group-title">' + esc((one[0].kindLabel) || k) +
        ' <span class="count">' + one.length.toLocaleString() + " 個</span></div>";
      h += indexGrid(one, true);
    });
    out.innerHTML = h;
    bindMapInteractions();
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
    if (!isNavigatingBack && (currentTab !== tab || currentPid || currentPlace)) {
      pushNavState(currentNavState());
    }
    currentTab = tab;
    currentPid = null;
    currentPlace = null;
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
    writeHash();
    syncBack();
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
    var ps = ev.target.closest ? ev.target.closest(".preset-pill[data-preset]") : null;
    if (!bk && !ps) return;

    if (ps) {
      var pid = ps.getAttribute("data-preset");
      var target = null;
      PRESET_CAPSULES.forEach(function (x) { if (x.id === pid) target = x; });
      if (target) {
        selectedBooks = target.books.slice();
        syncScopeBook();
        renderBookbar();
        if (currentTab === "search") loadIndex();
        else loadIndex(renderCurrentTab);
      }
      return;
    }

    var code = bk.getAttribute("data-book");
    if (code === "pei") {
      peiOn = !peiOn;
      renderBookbar();
      if (currentTab === "search" && currentPid) {
        renderPerson(currentPid).catch(showErr);
      }
      return;
    }

    // 點擊典籍膠囊：自由切換勾選狀態（至少保留 1 本）
    var idx = selectedBooks.indexOf(code);
    if (idx >= 0) {
      if (selectedBooks.length <= 1) return;
      selectedBooks.splice(idx, 1);
    } else {
      selectedBooks.push(code);
    }
    syncScopeBook();
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
    if (!query) return Promise.resolve();
    if (!isNavigatingBack && (lastQuery !== query || currentPid || currentPlace || currentTab !== "search")) {
      pushNavState(currentNavState());
    }
    lastQuery = query;
    currentPid = null;
    currentPlace = null;
    var url = mode === "fts"
      ? "/api/fts?q=" + encodeURIComponent(query)
      : "/api/search?q=" + encodeURIComponent(query);
    return request(url).then(function (d) {
      // ⚠️ fts 模式**不分人物/地名**（它就是全文檢索），別把 places 塞進去——
      //    那會讓「全文」模式裡冒出一堆只有名字的地名行，語義不對。
      if (mode === "fts") renderFts(d.items || [], query);
      else renderResults(d.items || [], query, d.places || []);
      writeHash();
      syncBack();
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
  // 命中篩選器的下拉：必須單獨聽 change——click 委派只管得著按鈕，
  // 而 `<select>` 選完不一定冒泡出可辨識的 click（有的瀏覽器根本不發）。
  out.addEventListener("change", function (ev) {
    var sel = ev.target.closest ? ev.target.closest("select.mf[data-mf]") : null;
    if (!sel) return;
    onMFilterChange(sel.getAttribute("data-mf"), sel.value);
  });
  out.addEventListener("click", function (ev) {
    // 「清除篩選」——排在最後會被當成別的東西（它可能落在卡片空白處），
    // 所以這裡**第一個**認它。
    if (ev.target.closest && ev.target.closest("button[data-act=\"mfclear\"]")) {
      onMFilterChange("book", "");
      return;
    }
    // 兩漢三國兵爭形勝輿圖控制：戰區切換、通道開關、全景復位、退出行跡、放大縮小
    var mz = ev.target.closest ? ev.target.closest(".map-pill[data-map-zone]") : null;
    if (mz) {
      var z = mz.getAttribute("data-map-zone");
      if (z) {
        mapState.zone = z;
        mapState.curVb = parseViewBox(MAP_VIEWBOXES[z] || MAP_VIEWBOXES["all"]);
        renderPlacesIndex();
      }
      return;
    }
    var mzb = ev.target.closest ? ev.target.closest("[data-map-zoom]") : null;
    if (mzb) {
      var zAct = mzb.getAttribute("data-map-zoom");
      if (zAct === "in") {
        zoomMapByCenter(0.80);
      } else if (zAct === "out") {
        zoomMapByCenter(1.25);
      } else if (zAct === "reset") {
        mapState.curVb = parseViewBox(MAP_VIEWBOXES[mapState.zone] || MAP_VIEWBOXES["all"]);
        updateMapSvgViewBox();
      }
      return;
    }
    var mr = ev.target.closest ? ev.target.closest(".map-pill[data-map-toggle=\"routes\"]") : null;
    if (mr) {
      mapState.showRoutes = !mapState.showRoutes;
      renderPlacesIndex();
      return;
    }
    var mt = ev.target.closest ? ev.target.closest(".map-pill[data-map-toggle=\"terrain\"]") : null;
    if (mt) {
      mapState.showTerrain = !mapState.showTerrain;
      renderPlacesIndex();
      return;
    }
    var mres = ev.target.closest ? ev.target.closest(".map-pill[data-map-reset]") : null;
    if (mres) {
      mapState.zone = "all";
      mapState.curVb = parseViewBox(MAP_VIEWBOXES["all"]);
      mapState.selectedHub = null;
      mapState.itineraryPerson = null;
      mapState.itineraryPlaces = [];
      renderPlacesIndex();
      return;
    }
    var mic = ev.target.closest ? ev.target.closest(".map-itin-close, [data-act=\"map-itin-close\"]") : null;
    if (mic) {
      mapState.itineraryPerson = null;
      mapState.itineraryPlaces = [];
      renderPlacesIndex();
      return;
    }
    // 形勝圖節點與下方戰區要塞膠囊點選：選中/取消選中要衝並展開考據卡片
    var mhub = ev.target.closest ? ev.target.closest(".map-hub[data-plid], .strat-pill[data-map-hub]") : null;
    if (mhub) {
      // 正在拖拽地圖或剛拖拽結束（220ms 內），不觸發要衝選中
      if (mapState.lastDragTime && (Date.now() - mapState.lastDragTime < 220)) {
        return;
      }
      var hubId = mhub.getAttribute("data-plid") || mhub.getAttribute("data-map-hub");
      if (hubId) {
        mapState.selectedHub = (mapState.selectedHub === hubId) ? null : hubId;
        renderPlacesIndex();
        if (mapState.selectedHub) {
          var sc = document.getElementById("selectedHubCard");
          if (sc && sc.scrollIntoView) {
            try { sc.scrollIntoView({ behavior: "smooth", block: "nearest" }); } catch (e) {}
          }
        }
      }
      return;
    }
    // 人物頁/地名頁/選中考據卡片上的形勝跳轉按鈕
    var itBtn = ev.target.closest ? ev.target.closest(".map-view-btn[data-act=\"view-itinerary\"]") : null;
    if (itBtn) {
      var pname = itBtn.getAttribute("data-pname") || "";
      var hubsStr = itBtn.getAttribute("data-hubs") || "";
      var hubs = hubsStr.split(",").filter(Boolean);
      mapState.itineraryPerson = pname;
      mapState.itineraryPlaces = hubs;
      mapState.zone = "all";
      mapState.curVb = parseViewBox(MAP_VIEWBOXES["all"]);
      mapState.selectedHub = hubs[0] || null;
      switchTab("places");
      var mw = document.getElementById("stratMapWrap");
      if (mw && mw.scrollIntoView) {
        try { mw.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) {}
      }
      return;
    }
    var locBtn = ev.target.closest ? ev.target.closest(".map-view-btn[data-act=\"locate-on-map\"]") : null;
    if (locBtn) {
      var plid = locBtn.getAttribute("data-plid");
      if (plid) {
        mapState.selectedHub = plid;
        var strats = (IDX || {}).strategicPlaces || (window.BOOKINDEX_DATA && window.BOOKINDEX_DATA.strat) || {};
        var item = strats[plid];
        if (item && item.zone) {
          if (item.zone === "江淮戰區") mapState.zone = "jh";
          else if (item.zone === "荊襄戰區") mapState.zone = "jx";
          else if (item.zone === "秦嶺隴蜀戰區") mapState.zone = "ls";
          else if (item.zone.indexOf("河洛") >= 0 || item.zone.indexOf("河北") >= 0) mapState.zone = "hl";
        }
        mapState.curVb = parseViewBox(MAP_VIEWBOXES[mapState.zone] || MAP_VIEWBOXES["all"]);
        switchTab("places");
        var mw2 = document.getElementById("stratMapWrap");
        if (mw2 && mw2.scrollIntoView) {
          try { mw2.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) {}
        }
      }
      return;
    }
    var pbtn = ev.target.closest ? ev.target.closest(".map-view-btn[data-place]") : null;
    if (pbtn) {
      renderPlace(pbtn.getAttribute("data-place")).then(writeHash).catch(showErr);
      return;
    }
    // 地名條目 → 直接進地名詳情頁（**必須排在人物條目之前**）
    var pit = ev.target.closest ? ev.target.closest(".item[data-place]") : null;
    if (pit) {
      renderPlace(pit.getAttribute("data-place")).then(writeHash).catch(showErr);
      return;
    }
    // 檢索結果裡的地名行（`.row[data-place]`）
    var prow = ev.target.closest ? ev.target.closest(".row[data-place]") : null;
    if (prow) {
      renderPlace(prow.getAttribute("data-place")).then(writeHash).catch(showErr);
      return;
    }
    // 歷史人物足跡膠囊 → 點擊跳轉人物詳情
    var fpP = ev.target.closest ? ev.target.closest(".footprint-pill[data-pid]") : null;
    if (fpP) {
      renderPerson(fpP.getAttribute("data-pid")).then(writeHash).catch(showErr);
      return;
    }
    // 輿地足跡膠囊 / 兵爭要地膠囊 → 點擊跳轉地名詳情
    var fpPl = ev.target.closest ? ev.target.closest(".footprint-pill[data-plid], .strat-pill[data-plid]") : null;
    if (fpPl) {
      renderPlace(fpPl.getAttribute("data-plid")).then(writeHash).catch(showErr);
      return;
    }
    // 索引面板：點人物條目 = 拿這個名字去檢索（同名異人靠搜索消歧）
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
    // 人物索引分類切換（全部 / 諸侯公侯 · 公侯名錄 / 名臣將相 · 文武百僚）
    var cp = ev.target.closest ? ev.target.closest(".cat-pill[data-pcat]") : null;
    if (cp) {
      var pcat = cp.getAttribute("data-pcat");
      if (pcat && pcat !== currentPersonCat) {
        currentPersonCat = pcat;
        currentLordSub = "all";
        renderPersonsIndex();
      }
      return;
    }
    // 公侯政體切換（全部公侯 / 先秦諸侯 / 漢初異姓王 / 兩漢宗藩 / 魏晉宗室 / 秦漢列侯）
    var lsp = ev.target.closest ? ev.target.closest(".subcat-pill[data-plsub]") : null;
    if (lsp) {
      var plsub = lsp.getAttribute("data-plsub");
      if (plsub && plsub !== currentLordSub) {
        currentLordSub = plsub;
        renderPersonsIndex();
      }
      return;
    }
    // 人物時空歸屬切換（古今通覽 / 本朝當世 / 前代先賢）
    var ep = ev.target.closest ? ev.target.closest(".era-pill[data-pera]") : null;
    if (ep) {
      var pera = ep.getAttribute("data-pera");
      if (pera && pera !== currentPersonEra) {
        currentPersonEra = pera;
        renderPersonsIndex();
      }
      return;
    }
    // 三國志分卷視角切換（正裴合璧 / 陳壽正文 / 裴松之注）
    var vp = ev.target.closest ? ev.target.closest(".sgz-view-pill[data-sgzview]") : null;
    if (vp) {
      var view = vp.getAttribute("data-sgzview");
      if (view && view !== currentSgzView) {
        currentSgzView = view;
        var card = document.getElementById("sgzCard");
        if (card && currentPersonData) {
          card.outerHTML = renderSgzBreakdownCard(currentPersonData.sgzBreakdown);
        }
      }
      return;
    }
    // 宗藩世系傳承鏈條節點跳轉（上任 / 繼任 / 全景軌節點）
    var lp = ev.target.closest ? ev.target.closest(".lineage-pill[data-pid], .lineage-node[data-pid]") : null;
    if (lp) {
      var targetPid = lp.getAttribute("data-pid");
      if (targetPid) {
        renderPerson(targetPid).then(writeHash).catch(showErr);
        return;
      }
    }
    var row = ev.target.closest ? ev.target.closest(".row[data-pid]") : null;
    if (row) { renderPerson(row.getAttribute("data-pid")).then(writeHash).catch(showErr); return; }
    // 糾錯條上的「重建」
    var ovr = ev.target.closest ? ev.target.closest("button[data-act=\"ovrebuild\"]") : null;
    if (ovr) {
      onRebuilt = function () {
        if (currentPlace) renderPlace(currentPlace);
        else renderPerson(currentPid);
      };
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
    // 注文（裴注 / 晉書舊史注）的兩個入口——**排在「點句子開原文」之前**。
    // 這裡以前只渲染不接線：`.open-full` 與 `.pei-line` 都帶 data-chapter，
    // 點了什麼都不發生（審查 docs/34 P0-2）。元素在、點不動，最典型的死按鈕。
    // 兩個入口的差別在**要不要跳段**：讀全篇只開篇；明細行的 data-pseq 是段號。
    // ⚠️ 注文的 pseq 是**段號**不是正文 uid（注文與正文切分體系不同，紅線），
    //    所以別拿它去查 p[data-uid]——查不到還好，錯位就麻煩了。
    var ofEl = ev.target.closest ? ev.target.closest(".open-full[data-chapter]") : null;
    if (ofEl) {
      openChapter(ofEl.getAttribute("data-chapter"), null, currentPid).catch(showErr);
      return;
    }
    var plEl = ev.target.closest ? ev.target.closest(".pei-line[data-chapter]") : null;
    if (plEl) {
      var pseq = plEl.getAttribute("data-pseq");
      openChapter(plEl.getAttribute("data-chapter"), null, currentPid,
                  pseq == null ? null : Number(pseq)).catch(showErr);
      return;
    }
    var s = ev.target.closest ? ev.target.closest(".sent[data-chapter]") : null;
    if (s) {
      // 傳作用域（人物**或**地名）：原文層才知道「只看相關段落」該留哪些段。
      // ⚠️ 別只傳 currentPid——地名頁裡它是 null，篩選按鈕會跟著消失。
      openChapter(s.getAttribute("data-chapter"), s.getAttribute("data-uid"),
                  currentPid || currentPlace).catch(showErr);
    }
  });

  // 兩漢三國兵爭形勝輿圖：縮放（Zoom）與平移（Pan）核心交互引擎
  function updateMapSvgViewBox() {
    var svg = document.getElementById("stratMapSvg");
    if (!svg || !mapState.curVb) return;
    var vb = mapState.curVb;
    svg.setAttribute("viewBox", [Math.round(vb.x), Math.round(vb.y), Math.round(vb.w), Math.round(vb.h)].join(" "));
    var lvl = document.getElementById("mapZoomLevel");
    if (lvl) {
      var pct = Math.round((1000 / vb.w) * 100);
      lvl.textContent = pct + "%";
    }
  }

  function zoomMapByCenter(factor) {
    if (!mapState.curVb) return;
    var vb = mapState.curVb;
    var centerX = vb.x + vb.w / 2;
    var centerY = vb.y + vb.h / 2;
    var newW = vb.w * factor;
    var newH = vb.h * factor;
    if (newW < 90 || newW > 1400) return;
    vb.x = centerX - (vb.w * factor) / 2;
    vb.y = centerY - (vb.h * factor) / 2;
    vb.w = newW;
    vb.h = newH;
    updateMapSvgViewBox();
  }

  function bindMapInteractions() {
    var svg = document.getElementById("stratMapSvg");
    var body = document.getElementById("stratMapBody");
    if (!svg || !body) return;
    if (svg._zoomPanBound) return;
    svg._zoomPanBound = true;

    // 1. 滑鼠滾輪縮放（以指針位置為中心縮放）
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      var rect = svg.getBoundingClientRect();
      var vb = mapState.curVb;
      var mouseSvgX = vb.x + ((e.clientX - rect.left) / rect.width) * vb.w;
      var mouseSvgY = vb.y + ((e.clientY - rect.top) / rect.height) * vb.h;
      var factor = e.deltaY < 0 ? 0.82 : 1.22;
      var newW = vb.w * factor;
      var newH = vb.h * factor;
      if (newW < 90 || newW > 1400) return;
      vb.x = mouseSvgX - ((mouseSvgX - vb.x) * factor);
      vb.y = mouseSvgY - ((mouseSvgY - vb.y) * factor);
      vb.w = newW;
      vb.h = newH;
      updateMapSvgViewBox();
    }, { passive: false });

    // 2. 滑鼠左鍵拖拽平移
    var isDragging = false;
    var startClientX = 0, startClientY = 0;
    var startVb = null;
    var totalDragDist = 0;

    body.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      isDragging = true;
      totalDragDist = 0;
      startClientX = e.clientX;
      startClientY = e.clientY;
      startVb = { x: mapState.curVb.x, y: mapState.curVb.y, w: mapState.curVb.w, h: mapState.curVb.h };
      body.classList.add("panning");
    });

    window.addEventListener("mousemove", function (e) {
      if (!isDragging || !startVb) return;
      var dx = e.clientX - startClientX;
      var dy = e.clientY - startClientY;
      totalDragDist = Math.hypot(dx, dy);
      var rect = svg.getBoundingClientRect();
      var svgDx = dx * (startVb.w / rect.width);
      var svgDy = dy * (startVb.h / rect.height);
      mapState.curVb.x = startVb.x - svgDx;
      mapState.curVb.y = startVb.y - svgDy;
      updateMapSvgViewBox();
    });

    window.addEventListener("mouseup", function (e) {
      if (isDragging) {
        isDragging = false;
        body.classList.remove("panning");
        if (totalDragDist > 4) {
          mapState.lastDragTime = Date.now();
        }
      }
    });

    // 3. 移動端觸摸雙指縮放與單指平移
    var touchDist = 0;
    var touchVb = null;
    var touchStartX = 0, touchStartY = 0;

    body.addEventListener("touchstart", function (e) {
      if (e.touches.length === 1) {
        isDragging = true;
        totalDragDist = 0;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        startVb = { x: mapState.curVb.x, y: mapState.curVb.y, w: mapState.curVb.w, h: mapState.curVb.h };
      } else if (e.touches.length === 2) {
        isDragging = false;
        touchDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        touchVb = { x: mapState.curVb.x, y: mapState.curVb.y, w: mapState.curVb.w, h: mapState.curVb.h };
      }
    }, { passive: true });

    body.addEventListener("touchmove", function (e) {
      if (e.touches.length === 1 && isDragging && startVb) {
        var dx = e.touches[0].clientX - touchStartX;
        var dy = e.touches[0].clientY - touchStartY;
        totalDragDist = Math.hypot(dx, dy);
        var rect = svg.getBoundingClientRect();
        var svgDx = dx * (startVb.w / rect.width);
        var svgDy = dy * (startVb.h / rect.height);
        mapState.curVb.x = startVb.x - svgDx;
        mapState.curVb.y = startVb.y - svgDy;
        updateMapSvgViewBox();
      } else if (e.touches.length === 2 && touchVb && touchDist > 0) {
        var curDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        if (curDist > 0) {
          var factor = touchDist / curDist;
          var newW = touchVb.w * factor;
          var newH = touchVb.h * factor;
          if (newW >= 90 && newW <= 1400) {
            var midClientX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
            var midClientY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
            var rect2 = svg.getBoundingClientRect();
            var midSvgX = touchVb.x + ((midClientX - rect2.left) / rect2.width) * touchVb.w;
            var midSvgY = touchVb.y + ((midClientY - rect2.top) / rect2.height) * touchVb.h;
            mapState.curVb.x = midSvgX - (midSvgX - touchVb.x) * factor;
            mapState.curVb.y = midSvgY - (midSvgY - touchVb.y) * factor;
            mapState.curVb.w = newW;
            mapState.curVb.h = newH;
            updateMapSvgViewBox();
          }
        }
      }
    }, { passive: true });

    body.addEventListener("touchend", function (e) {
      if (totalDragDist > 4) {
        mapState.lastDragTime = Date.now();
      }
      isDragging = false;
    });
  }

  // 兩漢三國兵爭形勝輿圖：懸停氣泡 Tooltip 動態跟隨（帶防抖、要衝狀態鎖定與平滑防閃）
  var mapTipTimer = null;
  var currentTipHub = null;

  out.addEventListener("mouseover", function (ev) {
    var hub = ev.target.closest ? ev.target.closest(".map-hub[data-plid]") : null;
    var tip = document.getElementById("mapTooltip");
    if (!hub || !tip) return;
    var plid = hub.getAttribute("data-plid");
    if (mapTipTimer) { clearTimeout(mapTipTimer); mapTipTimer = null; }
    if (currentTipHub === plid && tip.style.display === "block") return;
    currentTipHub = plid;
    var name = hub.getAttribute("data-name") || "";
    var zone = hub.getAttribute("data-zone") || "";
    var title = hub.getAttribute("data-title") || "";
    var battles = hub.getAttribute("data-battles") || "";
    tip.innerHTML = '<div class="tt-head"><span class="tt-name">' + esc(name) + '</span><span class="tt-zone">' + esc(zone) + '</span></div>' +
      (title ? '<div class="tt-title">' + esc(title) + '</div>' : '') +
      (battles ? '<div class="tt-battles"><b>關聯戰事：</b>' + esc(battles) + '</div>' : '') +
      '<div class="tt-foot">點擊選中要衝 · 檢視考據</div>';
    tip.style.display = "block";
  });

  out.addEventListener("mousemove", function (ev) {
    var tip = document.getElementById("mapTooltip");
    if (!tip || tip.style.display === "none") return;
    var body = tip.parentElement;
    if (!body) return;
    var rect = body.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var y = ev.clientY - rect.top;
    tip.style.left = Math.max(70, Math.min(rect.width - 70, x)) + "px";
    tip.style.top = Math.max(25, y - 16) + "px";
  });

  out.addEventListener("mouseout", function (ev) {
    var hub = ev.target.closest ? ev.target.closest(".map-hub[data-plid]") : null;
    if (!hub) return;
    var rel = ev.relatedTarget ? (ev.relatedTarget.closest ? ev.relatedTarget.closest(".map-hub[data-plid]") : null) : null;
    if (rel === hub) return;
    currentTipHub = null;
    var tip = document.getElementById("mapTooltip");
    if (tip) {
      if (mapTipTimer) clearTimeout(mapTipTimer);
      mapTipTimer = setTimeout(function () {
        if (!currentTipHub) tip.style.display = "none";
      }, 100);
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
