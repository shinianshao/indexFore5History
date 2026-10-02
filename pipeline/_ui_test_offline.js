/* 无头 UI 自测 · **离线静态快照 dist/**（docs/29 §六-6）

   为什么要有这一套：dist/ 是「双击 index.html 就能开」的分发形态，
   而它跟联机版共用**同一份 app.js** —— 只靠「data.js 存在与否」切换数据源。
   这种「一套前端两个数据源」最怕的是离线那条路径悄悄坏掉：
   联机测试全绿，发出去的快照却是白屏。所以这里专门打 dist/，**并且不打服务**。

   怎么证明真的没走服务端：**不注入 fetch**。jsdom 本身没有 fetch，
   app.js 只要还在调 /api/*，就会抛 ReferenceError 被下面的报错闸接住。
   这是唯一能证明「离线」的方式——起个服务再测，证明不了任何事。

   验证：
     1. data.js 被加载（window.BOOKINDEX_DATA 存在）
     2. 首屏检索出结果（劉邦），副标题带「離線快照」标记
     3. 三个索引页（人物 / 地名 / 篇目）都能渲染，换书会收窄
     4. 人物详情：命中按篇分组
     5. 关系卡能出（离线层自己造的 {nodes,edges} 形状对得上）
     6. 全文检索（无 SQLite、无 FTS，纯内存扫）能出结果
     7. 原文层能开，句子有内容
     8. **只读**：没有拆分/併下句/棄用按钮，重建按钮隐藏
     9. 无 JS 报错（含误用 fetch 的 ReferenceError）

   用法（依赖 jsdom，装在隔离目录里，不污染本工程）：
     1) 导出：python app/tools/export_static.py
     2) 跑测试：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules \
                 node pipeline/_ui_test_offline.js
*/
const { JSDOM, VirtualConsole } = require("jsdom");
const path = require("path");
const fs = require("fs");

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + name); }
  else { fail++; console.log("  ✗ " + name + (extra ? "  → " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const distDir = path.resolve(__dirname, "..", "dist");
  const entry = path.join(distDir, "index.html");
  for (const f of ["index.html", "app.js", "data.js"]) {
    if (!fs.existsSync(path.join(distDir, f))) {
      console.error("× dist/ 里缺 " + f + "。先跑：python app/tools/export_static.py");
      process.exit(1);
    }
  }

  const vc = new VirtualConsole();
  const errs = [];
  vc.on("jsdomError", (e) => errs.push(String(e.message)));
  vc.on("error", (m) => errs.push(String(m)));

  /* 关键：**不注入 fetch**。联机版测试（_ui_test_index.js）必须注入它，
     这里必须不注入——注入了就分不清「离线可用」和「其实还在打服务」。 */
  const dom = await JSDOM.fromFile(entry, {
    runScripts: "dangerously", resources: "usable",
    pretendToBeVisual: true, virtualConsole: vc,
  });
  const { window } = dom;
  const doc = window.document;
  const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const out = doc.getElementById("out");
  const rbody = doc.getElementById("readerBody");   // 原文層，不在 #out 裡
  const q = doc.getElementById("q");
  const bookbar = doc.getElementById("books");
  const quick = doc.getElementById("quick");
  const sub = doc.getElementById("sub");

  async function waitFor(cond, timeout = 60000) {
    for (let i = 0; i < timeout / 200; i++) {
      if (cond()) return true;
      await sleep(200);
    }
    return false;
  }
  const tab = (name) => [...doc.querySelectorAll(".tabs span")]
    .find((el) => el.getAttribute("data-tab") === name);
  const bk = (code) => [...bookbar.querySelectorAll(".bk")]
    .find((el) => el.getAttribute("data-book") === code);

  console.log("\n【1】快照加载");
  const gotData = await waitFor(() => !!window.BOOKINDEX_DATA, 90000);
  ok("data.js 挂上了 window.BOOKINDEX_DATA（15MB 解析超时也算失败）", gotData);
  ok("数据是完整快照（有句子 / 人物 / 篇目 / 六份索引）",
    gotData && window.BOOKINDEX_DATA.sents.length > 90000 &&
    Object.keys(window.BOOKINDEX_DATA.pers).length > 2000 &&
    Object.keys(window.BOOKINDEX_DATA.chaps).length === 564 &&
    Object.keys(window.BOOKINDEX_DATA.idx).length === 6,
    gotData ? "sents=" + window.BOOKINDEX_DATA.sents.length : "无数据");

  console.log("\n【2】首屏检索（没起任何服务）");
  const gotRows = await waitFor(() => out.querySelectorAll(".row[data-pid]").length > 0, 60000);
  ok("检索在超时前出了结果", gotRows,
    "实得 " + out.querySelectorAll(".row[data-pid]").length + " 行");
  // ⚠️ 别断言输入框：search() 只在**点快捷词**时回填输入框，首屏那次不回填
  // （联机版也是这个行为）。要断的是「渲染出来的那一行就是劉邦」。
  // ⚠️ 也**不能只查 textContent 含「劉邦」**——「查不到「劉邦」」也含它，假绿。
  const firstRow = out.querySelector(".row[data-pid] .name");
  ok("首屏渲染的第一行就是劉邦",
    firstRow && (firstRow.textContent || "").indexOf("劉邦") >= 0,
    firstRow ? firstRow.textContent : "没有 .row");
  ok("副标题标了「離線快照（只讀）」",
    (sub.textContent || "").indexOf("離線快照") >= 0, sub.textContent);

  console.log("\n【3】索引三块 + 换书收窄");
  const gotBar = await waitFor(() => bookbar.querySelectorAll(".bk").length === 6, 30000);
  ok("书切换条渲染出来了", gotBar);
  const gotQuick = await waitFor(
    () => quick.querySelectorAll("span[data-name]").length > 0, 60000);
  ok("快捷词渲染出来了（索引数据到了）", gotQuick);

  click(tab("persons"));
  await sleep(400);
  const allPersons = out.querySelectorAll(".item[data-name]").length;
  ok("人物索引有条目", allPersons > 0, "实得 " + allPersons);
  click(tab("places"));
  await sleep(400);
  ok("地名索引有条目", out.querySelectorAll(".item[data-name]").length > 0);
  click(tab("chapters"));
  await sleep(400);
  const chapRows = out.querySelectorAll(".chap-row[data-chapter]").length;
  ok("篇目一覽有篇目（564 篇全在）", chapRows === 564, "实得 " + chapRows);

  click(tab("persons"));
  await sleep(400);
  click(bk("sgz"));
  const narrowed = await waitFor(() => {
    const n = out.querySelectorAll(".item[data-name]").length;
    return n > 0 && n < allPersons;
  }, 60000);
  const sgzPersons = out.querySelectorAll(".item[data-name]").length;
  ok("换到三國志后人物索引收窄", narrowed,
    "全部 " + allPersons + " → 三國志 " + sgzPersons);
  click(bk(""));
  await waitFor(() => out.querySelectorAll(".item[data-name]").length === allPersons, 60000);

  console.log("\n【4】人物详情");
  q.value = "劉邦";
  click(doc.getElementById("btn"));
  await waitFor(() => out.querySelectorAll(".row[data-pid]").length > 0, 60000);
  click(out.querySelector(".row[data-pid]"));
  const gotPerson = await waitFor(
    () => out.querySelectorAll(".sent[data-chapter]").length > 0, 60000);
  ok("点进人物后有命中句子", gotPerson,
    "实得 " + out.querySelectorAll(".sent[data-chapter]").length + " 条");
  ok("命中按篇分组（有 .chapter-title）", out.querySelectorAll(".chapter-title").length > 0);
  ok("档案里带别名标签", out.querySelectorAll(".alias-tag").length > 0,
    "实得 " + out.querySelectorAll(".alias-tag").length);

  console.log("\n【5】关系卡");
  const gotRel = await waitFor(() => !!doc.getElementById("relcard"), 60000);
  ok("关系卡渲染出来了", gotRel);
  const relRows = doc.querySelectorAll(".rel-row[data-pid]").length;
  ok("劉邦有关系边（离线图数据形状对得上）", relRows > 0, "实得 " + relRows);
  ok("关系图有节点", doc.querySelectorAll(".rel-node[data-pid]").length > 0,
    "实得 " + doc.querySelectorAll(".rel-node[data-pid]").length);

  console.log("\n【6】全文检索（无 SQLite / 无 FTS，纯内存扫）");
  const modeBtn = [...doc.querySelectorAll(".modes span")]
    .find((el) => el.getAttribute("data-mode") === "fts");
  click(modeBtn);
  q.value = "鴻門";
  click(doc.getElementById("btn"));
  const gotFts = await waitFor(() => out.querySelectorAll(".sent[data-chapter]").length > 0, 60000);
  ok("全文检索出了句子", gotFts, "实得 " + out.querySelectorAll(".sent[data-chapter]").length);
  ok("命中句里真的含「鴻門」",
    (out.textContent || "").indexOf("鴻門") >= 0);
  // 切回人物模式：它会**再跑一次 search()**（异步）。必须等它落定再点下一个标签页，
  // 否则上一次渲染会落在下一次渲染之后，把刚点开的页顶掉。
  // ⚠️ 这是**测试自己的排序问题**，不是页面的 bug——页面的 hash 守卫已经挡住了
  // hashchange 那条路径（联机版 29/29 就是证据）。连续 click 之间一定要 await。
  click([...doc.querySelectorAll(".modes span")]
    .find((el) => el.getAttribute("data-mode") === "person"));
  const settled = await waitFor(
    () => (out.textContent || "").indexOf("查不到") >= 0, 30000);
  ok("切回人物模式后那次异步检索落定了", settled);

  console.log("\n【7】原文层 + 只读");
  click(tab("chapters"));
  const gotChaps = await waitFor(
    () => out.querySelectorAll(".chap-row[data-chapter]").length > 0, 60000);
  ok("切回篇目頁有篇目可點", gotChaps);
  const firstChap = out.querySelector(".chap-row[data-chapter]");
  if (!firstChap) {
    console.log("   ……诊断：location.hash=" + JSON.stringify(window.location.hash) +
      " / out=" + String(out.innerHTML).slice(0, 120));
  }
  click(firstChap);
  const gotReader = await waitFor(
    () => doc.getElementById("reader").classList.contains("on"), 60000);
  ok("点篇目能开原文层", gotReader);
  const ps = doc.querySelectorAll("#readerBody p[data-uid]");
  ok("原文层有句子", ps.length > 0, "实得 " + ps.length);
  ok("句子有正文", ps.length > 0 && (ps[0].textContent || "").length > 0);
  // 只读：三个动作按钮不能出现（它们 POST 到服务端，离线写不了）
  ok("原文层没有拆分/棄用按钮（离線版只读）",
    doc.querySelectorAll("#readerBody .acts button").length === 0,
    "实得 " + doc.querySelectorAll("#readerBody .acts button").length + " 个");
  ok("重建按钮隐藏", doc.getElementById("btnRebuild").hidden === true);

  /* ---- 跳段 + 只看相关段落（docs/30 §五 第 3 项）----
     两者都是纯前端，数据来自 /api/chapter 已有的 para_seq。 */
  const jumpBox = doc.getElementById("jumpBox");
  const jumpInput = doc.getElementById("jumpInput");
  const jumpTotal = doc.getElementById("jumpTotal");
  ok("原文层有跳段控件（段号输入 + 總段數）",
    !!jumpBox && !!jumpInput && !!jumpTotal,
    "jumpBox=" + !!jumpBox);
  // 短篇（<40 段）应当隐藏跳段控件：加了是噪声
  const paraCount = (() => {
    const seen = new Set();
    rbody.querySelectorAll("p[data-para]").forEach(p => {
      if (p.getAttribute("data-para")) seen.add(p.getAttribute("data-para"));
    });
    return seen.size;
  })();
  ok("每段带 data-para（跳段的定位依据）", paraCount > 0, "段数 " + paraCount);
  ok("短篇不显示跳段控件（<40 段不加噪声）",
    paraCount >= 40 ? jumpBox.hidden === false : jumpBox.hidden === true,
    "段数 " + paraCount + " hidden=" + jumpBox.hidden);
  ok("總段數與實際段數一致",
    (jumpTotal.textContent || "").indexOf("/ " + paraCount + " 段") >= 0,
    "显示「" + jumpTotal.textContent + "」，实际 " + paraCount + " 段");

  // 跳段必須在**長篇**上測：短篇（<40 段）控件本來就隱藏，測它等於沒測。
  // 找段數最多的那一篇（hs-020 五行志下 929 段）—— 從篇目索引裡找。
  const chaps = [...out.querySelectorAll(".chap-row[data-chapter]")];
  ok("篇目索引有可點的篇目行（準備測長篇跳段）", chaps.length > 0,
    "實得 " + chaps.length + " 篇");
  let longChap = null;
  for (const cr of chaps) {
    const cid = cr.getAttribute("data-chapter");
    // 直接讀離線數據算段數：app.js 裡的 offChapter 是私有函數，拿不到。
    // 這也順帶驗了 dist 裡 sents 的第 4 位（段號）真的在。
    const c = window.BOOKINDEX_DATA.chaps[cid];
    if (!c) continue;
    const n = new Set();
    for (let i = c[2]; i < c[3]; i++) {
      const para = window.BOOKINDEX_DATA.sents[i][3];
      if (para != null) n.add(para);
    }
    if (n.size >= 40) { longChap = { node: cr, cid, n: n.size }; break; }
  }
  ok("能找���一段 ≥40 段的長篇（跳段控件的前提）", !!longChap,
    longChap ? longChap.cid + " 有 " + longChap.n + " 段" : "沒有");
  if (longChap) {
    click(longChap.node);
    await waitFor(() => doc.getElementById("reader").classList.contains("on"), 60000);
    await waitFor(() => rbody.querySelectorAll("p[data-para]").length > 0, 30000);
    ok("長篇裡跳段控件可見", jumpBox.hidden === false);
    const longN = new Set([...rbody.querySelectorAll("p[data-para]")]
      .map(x => x.getAttribute("data-para"))).size;
    ok("長篇的實際段數與控件顯示的一致",
      (jumpTotal.textContent || "").indexOf("/ " + longN + " 段") >= 0,
      "顯示「" + jumpTotal.textContent + "」/ 實際 " + longN);
    const beforeT = rbody.querySelectorAll("p.target").length;
    jumpInput.value = "3";
    doc.querySelector('.reader-head button[data-act="jump"]').click();
    const gotT = await waitFor(
      () => rbody.querySelectorAll("p.target").length > beforeT, 5000);
    ok("填段号能跳到该段并标记 target", gotT,
      "target 数 " + rbody.querySelectorAll("p.target").length);
    // 越界段號要有反饋（靜默無反應是最難查的一類壞）
    jumpInput.value = "99999";
    doc.querySelector('.reader-head button[data-act="jump"]').click();
    ok("段号越界会提示（不静默无反应）",
      (jumpInput.placeholder || "").indexOf("超出") >= 0,
      "placeholder=" + jumpInput.placeholder);
    jumpInput.placeholder = "段號";
  }

  /* 「只看相關段落」：要 currentPid，所以路徑是
     人物索引（.item[data-name]）→ 點人名填檢索框 → 搜索結果（.row[data-pid]）
     → 點進人物頁 → 點命中句 → 開原文層。
     ⚠️ 人物索引的條目**不是** .row[data-pid]（那是搜索結果行）——
     一開始寫錯了這裡，症狀是「等不到行」而不是報錯。 */
  click(tab("persons"));
  const gotItems = await waitFor(
    () => out.querySelectorAll(".item[data-name]").length > 0, 60000);
  ok("人物索引有人名可點（準備驗證段落篩選）", gotItems,
    "實得 " + out.querySelectorAll(".item[data-name]").length + " 人");
  const pitem = out.querySelector(".item[data-name]");
  if (pitem) {
    click(pitem);
    const gotRow = await waitFor(
      () => out.querySelectorAll(".row[data-pid]").length > 0, 60000);
    ok("點人名後出搜索結果行", gotRow,
      "實得 " + out.querySelectorAll(".row[data-pid]").length + " 行");
    click(out.querySelector(".row[data-pid]"));
    const onPerson = await waitFor(
      () => out.querySelectorAll(".sent[data-chapter]").length > 0, 60000);
    ok("人物頁有命中可點", onPerson,
      "命中行 " + out.querySelectorAll(".sent[data-chapter]").length);
    const sent = out.querySelector(".sent[data-chapter]");
    if (sent) {
      click(sent);
      await waitFor(
        () => doc.getElementById("reader").classList.contains("on"), 60000);
      const allPs = rbody.querySelectorAll("p[data-uid]").length;
      const btnHits = doc.getElementById("btnHits");
      ok("從人物頁進原文層時有「只看相關段落」按鈕",
        btnHits && btnHits.hidden === false);
      if (btnHits && btnHits.hidden === false) {
        click(btnHits);
        const hitPs = rbody.querySelectorAll("p[data-uid]").length;
        ok("開啟「只看相關段落」後句子變少（篩選生效）",
          hitPs > 0 && hitPs < allPs,
          "全部 " + allPs + " → 篩選 " + hitPs);
        ok("篩選後的句子都帶 hitpara 標記",
          hitPs > 0 &&
          rbody.querySelectorAll("p.hitpara").length === hitPs,
          "hitpara " + rbody.querySelectorAll("p.hitpara").length +
          " / 篩選後 " + hitPs);
        click(btnHits);
        const backAll = rbody.querySelectorAll("p[data-uid]").length;
        ok("再點一次恢復全部段落", backAll === allPs,
          "全部 " + allPs + " → 恢復 " + backAll);
      }
    }
  }

  console.log("\n【8】无 JS 报错");
  ok("全程无 JS 报错（误用 fetch 会在这里红）", errs.length === 0,
    errs.slice(0, 4).join(" | "));

  window.close();
  console.log("\n────────────────────────────");
  console.log(`  离线快照 UI：通过 ${pass} / 失败 ${fail}`);
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error("测试崩了：", e);
  process.exit(1);
});
