/* 多書檢索專項回歸：書選擇器 + 單書內檢索 + 多書合檢。
   要釘的不是某個絕對數字（書會越加越多），而是三件不變的事：
     ① 每本書有自己的條目列表——選《史記》時，只在《漢書》出現的人不該列出來；
     ② 計數隨作用域走——同一個人在單書/多書下報的「篇 / 處」必須等於各書分帳之和；
     ③ 篇目一覽在多書時按書分節，單書時不分節。
   期望值一律從 app-data.js 現場算（meta.books / entity.byBook），不寫死數字。

   用法：
     1) 起服務：cd web && python -m http.server 8770 --bind 127.0.0.1
     2) 跑測試：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules node pipeline/_ui_test_books.js */
const { JSDOM, VirtualConsole } = require("jsdom");

const BASE = process.env.BASE || "http://127.0.0.1:8770/index.html";
let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + name); }
  else { fail++; console.log("  ✗ " + name + (extra ? "  → " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const vc = new VirtualConsole();
  const errors = [];
  vc.on("jsdomError", (e) => errors.push(e.message));
  vc.on("error", (...a) => errors.push(a.join(" ")));

  const dom = await JSDOM.fromURL(BASE, {
    runScripts: "dangerously", resources: "usable",
    pretendToBeVisual: true, virtualConsole: vc,
  });
  const { window } = dom;
  const doc = window.document;
  const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

  await new Promise((r) => window.addEventListener("load", r));
  await sleep(500);

  const D = window.BOOK_DATA;
  const M = D.meta;
  const out = doc.getElementById("out");
  const q = doc.getElementById("q");
  const fmt = (n) => Number(n).toLocaleString();

  const tab = async (name) => {
    click(doc.querySelector('.tabs span[data-tab="' + name + '"]'));
    await sleep(150);
  };
  const pill = (code) => doc.querySelector('#books .bk[data-book="' + code + '"]');
  const pickBook = async (code) => { click(pill(code)); await sleep(200); };
  /* 只留 target 一本书选中：先全选，再关掉其它书。
     三书及以后不能只「点掉一本」——否则作用域是 N-1 本，断言会假失败。 */
  const onlyBook = async (code) => {
    click(bar.querySelector(".bk.all"));
    await sleep(150);
    for (const b of M.books) {
      if (b.code === code) continue;
      if (pill(b.code) && pill(b.code).classList.contains("on")) {
        click(pill(b.code));
        await sleep(120);
      }
    }
    await sleep(150);
  };
  const indexItems = () => [...out.querySelectorAll(".grid .item")];
  const itemOf = (name) => indexItems().find((e) => e.getAttribute("data-name") === name);
  const personByName = (name) => D.persons.find((p) => p.name === name);
  const LB = personByName("劉邦");

  console.log("\n【1】書選擇器");
  const bar = doc.getElementById("books");
  ok("書選擇器已渲染", !!bar && bar.querySelectorAll(".bk").length >= M.books.length + 1,
     bar ? bar.querySelectorAll(".bk").length + " 個膠囊（含裴注）" : "無 #books");
  ok("每本書一個膠囊，書名取自 meta.books",
     M.books.every((b) => !!pill(b.code) && pill(b.code).textContent.indexOf(b.name) >= 0),
     M.books.map((b) => b.name).join("、"));
  ok("默認全選＝多書合檢（含裴注開關不得熄滅合檢燈）",
     M.books.every((b) => bar.querySelector(`.bk[data-book="${b.code}"]`)?.classList.contains("on")) &&
     bar.querySelector(".bk.all")?.classList.contains("on"),
     bar.querySelector(".bk.all")?.className || "無 .all");
  ok("裴注膠囊文案為「三國志裴松之注」",
     !!bar.querySelector('.bk[data-book="pei"]') &&
     bar.querySelector('.bk[data-book="pei"]').textContent.indexOf("三國志裴松之注") >= 0,
     bar.querySelector('.bk[data-book="pei"]')?.textContent || "無 pei");
  ok("默認裴注開啟", bar.querySelector('.bk[data-book="pei"]').classList.contains("on"));
  ok("多書合檢膠囊報「選中 2 / 2 本」",
     bar.querySelector(".bk.all").textContent.indexOf(
       "同時選中 " + M.books.length + " / " + M.books.length + " 本") >= 0,
     bar.querySelector(".bk.all").textContent);
  ok("副標題把兩本書都列出來",
     M.books.every((b) => doc.getElementById("sub").textContent.indexOf(b.name) >= 0),
     doc.getElementById("sub").textContent);
  ok("副標題報全 " + M.chapterCount + " 篇",
     doc.getElementById("sub").textContent.indexOf("全 " + M.chapterCount + " 篇") >= 0,
     doc.getElementById("sub").textContent);

  console.log("\n【2】多書合檢 · 篇目一覽按書分節");
  await tab("chapters");
  ok("按書分節（每本書一個標題）",
     out.querySelectorAll(".book-title").length === M.books.length,
     out.querySelectorAll(".book-title").length + " 節");
  ok("篇目共 " + M.chapterCount + " 篇",
     out.querySelectorAll(".chap-row").length === M.chapterCount,
     out.querySelectorAll(".chap-row").length + " 篇");
  M.books.forEach((b) => {
    const n = [...out.querySelectorAll(".chap-row")].filter((r) => r.getAttribute("data-chapter").indexOf(b.code + "-") === 0).length;
    ok("《" + b.name + "》占 " + b.chapterCount + " 篇", n === b.chapterCount, n + " 篇");
  });

  console.log("\n【3】多書合檢 · 計數＝各書分帳之和（先關裴注核對正文）");
  await tab("persons");
  const peiChip = bar.querySelector('.bk[data-book="pei"]');
  if (peiChip && peiChip.classList.contains("on")) { click(peiChip); await sleep(200); }
  const lbAll = itemOf("劉邦");
  const sumN = M.books.reduce((s, b) => s + ((LB.byBook[b.code] || {}).mentionCount || 0), 0);
  const sumC = M.books.reduce((s, b) => s + ((LB.byBook[b.code] || {}).mentionChapterCount || 0), 0);
  ok("關裴注：劉邦索引格報「" + sumC + " 篇 / " + fmt(sumN) + "」",
     !!lbAll && lbAll.querySelector(".c").textContent === sumC + " 篇 / " + fmt(sumN),
     lbAll ? lbAll.querySelector(".c").textContent : "未找到");
  /* 開裴注：合計＝正文+注文，後標【裴N】 */
  const PEI = (window.PEI_DATA && window.PEI_DATA.persons && window.PEI_DATA.persons[LB.id]) || null;
  if (peiChip) { click(peiChip); await sleep(200); }
  const lbPei = itemOf("劉邦");
  const peiN = (PEI && PEI.n) || 0;
  const JSN = (window.JS_NOTE_DATA && window.JS_NOTE_DATA.persons && window.JS_NOTE_DATA.persons[LB.id]) || null;
  const jsN = (JSN && JSN.n) || 0;
  const expPei = sumC + " 篇 / " + fmt(sumN + peiN + jsN) +
    ((peiN + jsN) ? "【裴" + fmt(peiN + jsN) + "】" : "");
  ok("開裴注：劉邦為正文+注文合計並標【裴N】＝「" + expPei + "」",
     !!lbPei && lbPei.querySelector(".c").textContent === expPei,
     lbPei ? lbPei.querySelector(".c").textContent : "未找到");
  ok("點多書合檢不強制關裴注", bar.querySelector('.bk[data-book="pei"]').classList.contains("on"));
  ok("懸停提示列出各書分帳",
     !!lbAll && M.books.every((b) => {
       const r = LB.byBook[b.code] || {};
       return (lbAll.getAttribute("title") || "").indexOf(
         "《" + b.name + "》" + r.mentionChapterCount + " 篇 / " + fmt(r.mentionCount) + " 處") >= 0;
     }),
     lbAll ? (lbAll.getAttribute("title") || "").replace(/\n/g, " | ") : "無");
  const livePersons = D.persons.filter((p) => {
    const bb = p.byBook || {};
    return M.books.some((b) => ((bb[b.code] || {}).mentionCount || 0) > 0);
  }).length;
  ok("人物索引條目數＝全書有命中 " + livePersons + " 人",
     indexItems().length === livePersons, indexItems().length + " / " + livePersons +
     "（詞典 " + M.personCount + "）");

  console.log("\n【4】單書檢索 · 只選《史記》");
  const SJ = M.books[0], HS = M.books[1];
  await tab("persons");
  await onlyBook(SJ.code);                        // 真正只留史記（兼容 N 本书）
  ok("《漢書》膠囊已取消選中", !pill(HS.code).classList.contains("on"));
  ok("《史記》膠囊仍選中", pill(SJ.code).classList.contains("on"));
  ok("其它書膠囊全部關掉",
     M.books.every((b) => b.code === SJ.code ||
       !pill(b.code).classList.contains("on")),
     M.books.map((b) => b.code + (pill(b.code).classList.contains("on") ? "✓" : "✗")).join(","));
  ok("副標題只報 " + SJ.chapterCount + " 篇",
     doc.getElementById("sub").textContent.indexOf("全 " + SJ.chapterCount + " 篇") >= 0,
     doc.getElementById("sub").textContent);
  const lbSj = itemOf("劉邦");
  const rSj = LB.byBook[SJ.code] || {};
  ok("劉邦在《史記》裡報「" + rSj.mentionChapterCount + " 篇 / " + fmt(rSj.mentionCount) + " 處」",
     !!lbSj && lbSj.querySelector(".c").textContent ===
       rSj.mentionChapterCount + " 篇 / " + fmt(rSj.mentionCount),
     lbSj ? lbSj.querySelector(".c").textContent : "未找到");
  /* 懸停提示保留各書分帳（這是發現性信息：告訴用戶「另一本書裡也有這個人」），
     但選中那一本的分帳必須與主計數嚴格一致——不能出現「主計數 938、提示 900」。 */
  ok("懸停分帳與主計數一致",
     !!lbSj && (lbSj.getAttribute("title") || "").indexOf(
       "《" + SJ.name + "》" + rSj.mentionChapterCount + " 篇 / " +
       fmt(rSj.mentionCount) + " 處") >= 0,
     lbSj ? (lbSj.getAttribute("title") || "").replace(/\n/g, " | ").slice(0, 90) : "無");
  ok("人物索引只剩《史記》的 " + SJ.personCount + " 人",
     indexItems().length === SJ.personCount, indexItems().length + " 條");
  await tab("chapters");
  ok("篇目一覽不再分節", out.querySelectorAll(".book-title").length === 0,
     out.querySelectorAll(".book-title").length + " 節");
  ok("篇目只剩 " + SJ.chapterCount + " 篇",
     out.querySelectorAll(".chap-row").length === SJ.chapterCount,
     out.querySelectorAll(".chap-row").length + " 篇");
  ok("沒有任何《漢書》篇目混入",
     ![...out.querySelectorAll(".chap-row")].some((r) => r.getAttribute("data-chapter").indexOf("hs-") === 0));

  console.log("\n【5】書作用域隔離 · 漢書獨有的人物");
  const hsOnly = D.persons.filter((p) => p.byBook && p.byBook.hs && !p.byBook.sj);
  ok("數據裡確有「只在《漢書》出現」的人物", hsOnly.length > 0, hsOnly.length + " 人");
  const probe = hsOnly[0];
  await tab("persons");
  ok("只選《史記》時，索引裡查不到「" + probe.name + "」", !itemOf(probe.name),
     "卻在索引裡出現了");
  q.value = probe.name;
  click(doc.getElementById("btn"));
  await sleep(150);
  ok("只選《史記》時直接搜也進不去（提示未收錄或不在選中的書）",
     out.textContent.indexOf(probe.name) < 0 || out.textContent.indexOf("未收錄") >= 0,
     out.textContent.slice(0, 60));
  click(bar.querySelector(".bk.all"));            // 回到多書合檢
  await sleep(200);
  await tab("persons");
  ok("多書合檢時「" + probe.name + "」回到索引", !!itemOf(probe.name));

  console.log("\n【6】單書檢索 · 只選《漢書》");
  await onlyBook(HS.code);                        // 真正只留漢書
  ok("只剩《漢書》一本（再點也不會清空）",
     pill(HS.code).classList.contains("on") &&
     M.books.every((b) => b.code === HS.code || !pill(b.code).classList.contains("on")),
     M.books.map((b) => b.code + (pill(b.code).classList.contains("on") ? "✓" : "✗")).join(","));
  click(pill(HS.code));                            // 試圖取消最後一本
  await sleep(150);
  ok("至少保留一本，不會全部取消", pill(HS.code).classList.contains("on"));
  /* 剛才試圖取消可能已把漢書關掉（若守衛未生效）——再确保只剩漢書后断言计数 */
  if (!pill(HS.code).classList.contains("on")) {
    await onlyBook(HS.code);
  }
  const lbHs = itemOf("劉邦");
  const rHs = LB.byBook[HS.code] || {};
  ok("劉邦在《漢書》裡報「" + rHs.mentionChapterCount + " 篇 / " + fmt(rHs.mentionCount) + " 處」",
     !!lbHs && lbHs.querySelector(".c").textContent ===
       rHs.mentionChapterCount + " 篇 / " + fmt(rHs.mentionCount),
     lbHs ? lbHs.querySelector(".c").textContent : "未找到");
  ok("人物索引＝《漢書》的 " + HS.personCount + " 人",
     indexItems().length === HS.personCount, indexItems().length + " 條");
  await tab("chapters");
  ok("篇目只剩 " + HS.chapterCount + " 篇",
     out.querySelectorAll(".chap-row").length === HS.chapterCount,
     out.querySelectorAll(".chap-row").length + " 篇");
  ok("沒有任何《史記》篇目混入",
     ![...out.querySelectorAll(".chap-row")].some((r) => r.getAttribute("data-chapter").indexOf("sj-") === 0));

  console.log("\n【7】切書後當前人物頁重算");
  click(bar.querySelector(".bk.all"));
  await sleep(150);
  q.value = "劉邦";
  click(doc.getElementById("btn"));
  await sleep(150);
  const statAll = (out.querySelector(".stats") || {}).textContent || "";
  await pickBook(HS.code);                          // → 只選史記
  await sleep(250);
  const statSj = (out.querySelector(".stats") || {}).textContent || "";
  ok("人物頁沒被切書清空", statSj.length > 0);
  ok("兩書合檢與單書的統計不一樣（說明確實按書重算）",
     statAll.length > 0 && statSj.length > 0 && statAll !== statSj,
     "多書「" + statAll.replace(/\s+/g, " ").slice(0, 40) + "」/ 單書「" +
     statSj.replace(/\s+/g, " ").slice(0, 40) + "」");
  const prSj = out.querySelectorAll(".primary-row").length;
  const sjPrimary = D.chapters.filter(
    (c) => c.bookId === SJ.code && (c.mainPersons || []).indexOf(LB.id) >= 0).length;
  ok("「整篇講述」只列《史記》的 " + sjPrimary + " 篇", prSj === sjPrimary, prSj + " 篇");

  console.log("\n【8】快捷詞隨書換");
  click(bar.querySelector(".bk.all"));
  await sleep(150);
  await onlyBook(SJ.code);                        // 只選史記（原逻辑点掉漢書在三书下不成立）
  await sleep(200);
  const quickNames = [...doc.querySelectorAll("#quick span[data-name]")].map((e) => e.getAttribute("data-name"));
  ok("快捷詞已渲染且有限條數", quickNames.length > 0 && quickNames.length <= 30,
     quickNames.length + " 條");
  ok("快捷詞裡每個人都在《史記》裡有命中",
     quickNames.every((n) => {
       const p = personByName(n);
       return !p || (p.byBook || {})[SJ.code];
     }),
     quickNames.filter((n) => {
       const p = personByName(n);
       return p && !(p.byBook || {})[SJ.code];
     }).join("、"));

  console.log("\n【9】運行期無異常");
  ok("全程無 jsdom 錯誤", errors.length === 0, errors.slice(0, 3).join(" | "));

  console.log("\n" + "=".repeat(46));
  console.log("多書檢索測試：通過 " + pass + " / 失敗 " + fail);
  dom.window.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error("測試異常:", e); process.exit(2); });
