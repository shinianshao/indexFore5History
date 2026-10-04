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
     7. 地名检索与详情（**简体搜得到 / 点得进 / 命中句在**）——离线版以前是死的
     8. 原文层能开，句子有内容
     9. **只读**：没有拆分/併下句/棄用按钮，重建按钮隐藏
    10. 无 JS 报错（含误用 fetch 的 ReferenceError）

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

  /* ⚠️ 默認 60s 是給「資料要從磁碟讀」的寬限；離線快照全在記憶體裡，
     正常是毫秒級。注入驗證（verify_p3_note_inject.sh）故意改壞前端，
     每次等不到都吃滿 60s → 一輪注入要十幾分鐘。
     所以真正的超時值一律走 BI_UI_TIMEOUT（環境變數）**優先於**傳進來的參數——
     這樣 30 多處調用點不用逐個改，設了環境變數就全面生效。 */
  const _envTO = Number(process.env.BI_UI_TIMEOUT || 0);
  async function waitFor(cond, timeout) {
    timeout = _envTO || timeout || 60000;
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
  /* ⚠️ 选择器是 `.item[data-place]` 不是 `.item[data-name]`：
     2026-10-03 起地名条目直接进详情页（不再绕人物搜索，那才是「点不動」的根因）。
     写成 `.item` 也能过（人物条目混在里面），但那样这条断言就废了。 */
  ok("地名索引有条目", out.querySelectorAll(".item[data-place]").length > 0,
    "实得 " + out.querySelectorAll(".item[data-place]").length);
  /* ⚠️ 必须**真的点一条**（2026-10-03 审查 P0-1）。地名有**两条**点击分派：
     索引页的 `.item[data-place]` 与检索结果的 `.row[data-place]`。
     【7】只覆盖了后者，于是把前者的 `if (pit) {...}` 删掉全套测试照样全绿
     —— 症状是「离線版在地名索引里点条目 → 掉到人物搜索 → 空」，零报错。
     两条是**不同的代码路径**，各得一条断言。 */
  {
    const pit = out.querySelector(".item[data-place]");
    const wantId = pit ? pit.getAttribute("data-place") : "";
    if (pit) click(pit);
    /* 等地名页独有的东西。别等 `.person-head .name`（索引页卡片头也有）。 */
    const gotPit = await waitFor(
      () => out.querySelectorAll(".sent[data-place]").length > 0, 60000);
    ok("離線版地名索引里点條目 → 進詳情頁（.item[data-place] 分派有覆盖·P0-1）",
      gotPit && !!wantId
      && (window.location.hash || "").indexOf("#/place/" + wantId) === 0,
      "hash=" + window.location.hash + " id=" + wantId);
    /* P0-3：分篇标题**要有篇名**。`chapter` 字段被丢掉时标题退化成「 · 2 處」，
       「有 .chapter-title」照样成立 → 判据必须是「去掉次数后还剩字」。 */
    const ct0 = out.querySelector(".chapter-title");
    const ct0t = ((ct0 || {}).textContent || "").replace(/^[\s·0-9]+處$/, "").trim();
    ok("離線版地名詳情分篇標題有篇名（chapter 欄位沒丟·P0-3）",
      !!ct0 && ct0t.length > 0, "实得「" + ((ct0 || {}).textContent || "") + "」");
  }
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

  // 「前朝」小标记：离线版的索引是快照里的 /api/index 原样响应，
  // eraRank 必须跟着一起进了快照，否则离线版标不出、联机版标得出（悄悄分叉）。
  const eraMarks = () => out.querySelectorAll(".item .era-old").length;
  ok("未选书时不标「前朝」（全五书没有单一时代区间）", eraMarks() === 0,
    "实得 " + eraMarks());
  click(bk("hs"));
  const gotEra = await waitFor(() => eraMarks() > 0, 60000);
  ok("選漢書 → 离线版也标得出「前朝」（eraRank 进了快照）", gotEra,
    "实得 " + eraMarks() + " 个");
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
  /* 2026-10-03 起：档案里的扁平别名升级成**完整称谓表**（分组 + ×N / 未用）。
     ⚠️ 这条原来断 `.alias-tag`，换形状后自然是 0——不是坏了，是断言过期了。
     新形状要断得更细：分组在、双向 marker（×N 与「未用」）都在、泛称单独分色。
     离线版没有服务端，称谓表是 app.js 从快照的数组还原的，
     所以这里同时验证了「紧凑数组 → 物件」的还原没漏字段。 */
  ok("档案里带完整称谓表（分组）", out.querySelectorAll(".alias-group").length > 0,
    "实得 " + out.querySelectorAll(".alias-group").length + " 组");
  const offChips = [...out.querySelectorAll(".alias-group .chip")];
  ok("称谓 chip 渲染出来了（离线还原成功）", offChips.length > 0,
    "实得 " + offChips.length);
  ok("有带次数的称谓（还原到 n 字段了）",
    offChips.some((el) => (el.textContent || "").indexOf("×") > 0),
    "样例「" + (offChips[0] ? offChips[0].textContent : "") + "」");
  ok("有分書分帳的提示（还原到 byBook 了）",
    offChips.some((el) => (el.getAttribute("title") || "").indexOf("分書：") >= 0),
    "样例 title「" + ((offChips[0] || {}).getAttribute
      ? String(offChips[0].getAttribute("title") || "").slice(0, 40) : "") + "」");

  /* 離線版是只讀快照：標錯要 POST 到服務端，**給了就是空頭支票**。
     與原文層那三個按鈕同一個道理（【7】裡斷的是 .acts，這裡斷 .sent 上的那顆）。 */
  ok("人物页没有「標錯」按钮（离線版只读，寫不進 overrides）",
    out.querySelectorAll('.sent button[data-act="flag"]').length === 0,
    "实得 " + out.querySelectorAll('.sent button[data-act="flag"]').length + " 个");
  ok("人物页没有糾錯條（离线不加载 /api/overrides）",
    out.querySelectorAll(".ovbar").length === 0);

  /* P0-丙（2026-10-04）：命中數口徑 + 篩選。
     聯機 limit=200、離線給全量是**刻意差異**，但頁面不能把「本次載入了幾條」
     當成「這人有幾處」——搜索卡說 2,064、人物頁說 200，兩個真數字挨在同一屏，
     而且 200 緊挨著【裴726】，用戶會讀成「200 + 726」（docs/34 P0-3）。

     離線這裡斷三件事：
       ① 篩選條在（兩個 select.mf）；
       ② 「共 N 處」取自全量分佈 mentionByBook，不是 mentions.length；
       ③ 切到「按書：X」後，下拉裡寫的數 == 實際渲染的條數。
          ⚠️ 這條專門守「緊湊陣列的書序」：pmbk 用 ORDER BY code（hhs 打頭），
          常量 BOOKS 是成書先後（sj 打頭），還原錯位時**總和不變**，
          只有「按書後對不上」會紅。 */
  const mfbar = out.querySelector(".mfbar");
  ok("人物页有命中筛选条（.mfbar）", !!mfbar);
  const mfSel = mfbar ? mfbar.querySelectorAll("select.mf[data-mf]") : [];
  ok("筛選條有「按書」和「按時代」兩個下拉", mfSel.length === 2,
    "实得 " + mfSel.length + " 个");
  const mfcount = mfbar ? mfbar.querySelector(".mfcount") : null;
  const cntTxt = mfcount ? String(mfcount.textContent || "") : "";
  const cntNum = Number((cntTxt.match(/[\d,]+/) || ["0"])[0].replace(/,/g, ""));
  const shownRows = out.querySelectorAll(".sent[data-chapter]").length;
  ok("「共 N 處」寫的是全量數（不是被截斷的 200）", cntNum > 200,
    "实得「" + cntTxt + "」");
  ok("離線「共 N 處」與實際渲染條數一致（全量就該對得上）",
    cntNum > 0 && cntNum === shownRows,
    "共 " + cntNum + " / 渲染 " + shownRows);

  /* 按書篩選：下拉寫的數必須與篩完後真的渲染出來的數相等。 */
  const bookSel = mfbar ? mfbar.querySelector('select.mf[data-mf="book"]') : null;
  const bOpts = bookSel
    ? [...bookSel.querySelectorAll("option")].filter((o) => o.value) : [];
  ok("「按書」下拉裡有非零的書可選（0 處的書不列）", bOpts.length > 0,
    "实得 " + bOpts.length + " 项");
  if (bOpts.length) {
    const opt = bOpts[0];
    const labelN = Number((String(opt.textContent || "").match(/[\d,]+/) || ["0"])[0]
      .replace(/,/g, ""));
    bookSel.value = opt.value;
    bookSel.dispatchEvent(new window.Event("change", { bubbles: true }));
    await waitFor(
      () => out.querySelectorAll(".sent[data-chapter]").length !== shownRows, 30000);
    const after = out.querySelectorAll(".sent[data-chapter]").length;
    ok("切「按書」後真的換了一批命中（不是死下拉）", after > 0 && after !== shownRows,
      "篩後 " + after + " / 篩前 " + shownRows);
    ok("下拉寫的「N 處」與篩後渲染條數一致（書序錯位會在這紅）",
      labelN > 0 && labelN === after,
      "下拉 " + labelN + " / 渲染 " + after);
    /* ⚠️ 篩選會整塊重渲染 out，前面抓的 mfbar 已經脫離文檔、讀到的是**舊文案**
       （「等完要重新取元素」的同類坑）。這裡必須從 out 現取。 */
    const cnt2 = out.querySelector(".mfbar .mfcount");
    ok("篩選後「共 N 處」也跟著收窄（不是還掛著全量數）",
      !!cnt2 && Number((String(cnt2.textContent || "").match(/[\d,]+/) || ["0"])[0]
        .replace(/,/g, "")) === after,
      cnt2 ? "实得「" + cnt2.textContent + "」/ 渲染 " + after : "无");
    // 收尾：清掉篩選，別讓下一塊【5】關係卡在篩過的現場上跑
    const clr = out.querySelector('button[data-act="mfclear"]');
    if (clr) {
      click(clr);
      await waitFor(
        () => out.querySelectorAll(".sent[data-chapter]").length === shownRows, 30000);
    }
  }

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
  // hashchange 那条路径（联机版就是证据）。连续 click 之间一定要 await。
  click([...doc.querySelectorAll(".modes span")]
    .find((el) => el.getAttribute("data-mode") === "person"));
  /* ⚠️ 原来这里等的是「查不到」三个字（那时「鴻門」人物地名都搜不到）。
     2026-10-03 加了地名檢索之后，「鴻門」**本身就是一個地名**（關隘，26 處），
     页面正确地渲染出地名卡 → 永远等不到那三个字 → 假失败。
     教训与本文件开头那条同源：**别把「当前数据的偶然」写进等待条件**。
     判据应该是「渲染已落定」：有结果行或空态都算。 */
  const settled = await waitFor(
    () => out.querySelectorAll(".row[data-pid], .row[data-place], .empty").length > 0,
    30000);
  ok("切回人物模式后那次异步检索落定了", settled,
    "out=" + String(out.innerHTML).slice(0, 80));
  ok("「鴻門」在人物模式下落成**地名卡**（它本就是關隘，不該是空態）",
    out.querySelectorAll(".row[data-place]").length > 0,
    "地 " + out.querySelectorAll(".row[data-place]").length
    + " / 人 " + out.querySelectorAll(".row[data-pid]").length);

  console.log("\n【7】地名檢索與詳情（離線）");
  /* 这一块守的是**分发形态**：dist/ 是「双击 index.html 就能发给人」的产物，
     而它跟联机版共用同一份 app.js。此前离线版**能列地名、点不动**——
     `export_static.py` 只导了 places 主表，`place_mentions` 一点痕迹都没有，
     点了掉到人物搜索上 → 空。这种坏在联机测试里**永远看不到**。
     ⚠️ 这里同样不注入 fetch：只要 app.js 还在打 /api/*，就报 ReferenceError。 */
  // 先关掉原文层：【7】前面开过，不关的话下面「点句 → 原文层」会假通过
  if (doc.getElementById("reader").classList.contains("on")) {
    const cb0 = doc.querySelector('.reader-head button[data-act="close"]');
    if (cb0) click(cb0);
    await sleep(300);
  }
  // 简体：places.name 与 trad_name 逐行相同，简体名只在 plalias 里。
  // 漏导 plalias 的症状就是这一条——输「邯郸」零命中。
  /* ⚠️ 必须先**清屏**再等：上一块（【6】全文检索）切回人物模式时搜的是「鴻門」，
     而「鴻門」本身就是關隘 → 屏幕上留着一行 `.row[data-place]`。
     于是「等 .row[data-place] 出现」立刻成立，**量到的是上一屏的残留**——
     这条断言就成了恒真，注入 plalias 故障时它照样绿（实测踩过）。
     判据要写死「这一行里是邯郸」，而不是「有一行地名」。 */
  out.innerHTML = "";
  q.value = "邯郸";
  click(doc.getElementById("btn"));
  const gotLand = await waitFor(() => {
    const rows = [...out.querySelectorAll(".row[data-place]")];
    return rows.length > 0 && rows.some((r) => (r.textContent || "").indexOf("邯鄲") >= 0);
  }, 60000);
  ok("離線版輸簡體「邯郸」搜得到地名（plalias 進了快照）", gotLand,
    "out=" + String(out.innerHTML).slice(0, 100));
  const lrow = [...out.querySelectorAll(".row[data-place]")]
    .find((r) => (r.textContent || "").indexOf("邯鄲") >= 0);
  ok("地名行的名字是繁體正名（不是把簡體原樣回顯）",
    !!lrow && !!lrow.querySelector(".name")
    && lrow.querySelector(".name").textContent.indexOf("邯鄲") === 0
    && lrow.querySelector(".name").textContent.indexOf("邯郸") < 0,
    "实得「" + (lrow ? lrow.textContent : "") + "」");
  if (lrow) click(lrow);
  /* ⚠️ 等 `.sent[data-place]`（地名页独有），别等 `.person-head .name`——
     检索结果页也有那个类，条件会立刻成立，断言全读到检索页。 */
  const gotLandPage = await waitFor(
    () => out.querySelectorAll(".sent[data-place]").length > 0, 60000);
  const lname = out.querySelector(".person-head .name");
  ok("離線版點地名 → 進詳情頁（不是人物檢索）", gotLandPage
    && lname && (lname.textContent || "").indexOf("邯鄲") === 0,
    "实得「" + (lname ? lname.textContent : "") + "」");
  ok("離線版地名詳情有命中句（pmen 進了快照）",
    out.querySelectorAll(".sent[data-chapter]").length > 0,
    "实得 " + out.querySelectorAll(".sent[data-chapter]").length + " 句");
  ok("離線版地名詳情有寫法清單（异體在 plalias）",
    !!out.querySelector(".alias-tag")
    && out.textContent.indexOf("邯郸") > 0);
  ok("離線版地名詳情有「見於哪些書」（plbook 進了快照）",
    !!out.querySelector(".alias-note"));
  const lsent = out.querySelector(".sent[data-chapter]");
  if (lsent) click(lsent);
  const gotLandReader = await waitFor(
    () => doc.getElementById("reader").classList.contains("on"), 60000);
  ok("離線版地名命中句 → 能進原文層", gotLandReader);
  ok("地名頁的「只看相關段落」也在（scope 別只認人物 pid）",
    doc.getElementById("btnHits") && !doc.getElementById("btnHits").hidden,
    "按钮=" + (doc.getElementById("btnHits")
      ? (doc.getElementById("btnHits").hidden ? "hidden" : "可见") : "找不到"));
  const cb1 = doc.querySelector('.reader-head button[data-act="close"]');
  if (cb1) click(cb1);
  await sleep(300);

  console.log("\n【8】原文层 + 只读");
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
  ok("能找一段 ≥40 段的長篇（跳段控件的前提）", !!longChap,
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

  /* ---- 注文區塊（裴注 / 晉書舊史注）：獨立賬本（docs/30 §五 第 4 项）----
     後端斷的是「沒并進正文 mentions」，這裡斷**顯示層**：
     區塊在、標了【裴N】、正文與注文兩個數字分開擺著。 */
  click(tab("persons"));
  await waitFor(() => out.querySelectorAll(".item[data-name]").length > 0, 60000);
  // 找一個裴注命中多的人（曹操：正文 1,823 / 裴注 726）
  // ⚠️ 檢索是**點按鈕**觸發的（qEl 只綁了 keydown，沒綁 input）——
  // 我一開始派發 input事件，結果一行都沒出來，症狀是「等不到」不是報錯。
  q.value = "曹操";
  click(doc.getElementById("btn"));
  const gotRow2 = await waitFor(
    () => out.querySelectorAll(".row[data-pid]").length > 0, 60000);
  ok("搜到曹操（有大量裴注命中）", gotRow2,
    "結果 " + out.querySelectorAll(".row[data-pid]").length + " 行");
  click(out.querySelector(".row[data-pid]"));
  await waitFor(() => out.querySelectorAll(".note-sum").length > 0, 60000);
  ok("人物页有注文合計條（note-sum）", out.querySelectorAll(".note-sum").length > 0);
  const noteSum = out.querySelector(".note-sum");
  ok("合計條把正文與裴注**分開**標（【裴N】）",
    noteSum && noteSum.querySelector(".note-chip") &&
    /【裴[\d,]+】/.test(noteSum.textContent),
    "顯示「" + (noteSum ? noteSum.textContent.replace(/\s+/g, " ") : "") + "」");
  // ⚠️ 這兩條以前只斷「元素存在」（length > 0），而元素一直都在、點了沒反應——
  //   斷言寫著「可點」卻沒有一次點擊，等於給假綠（審查 docs/34 P0-2）。
  //   現在**真點開**並斷原文層真的起來了。
  const openFuls = out.querySelectorAll(".open-full[data-chapter]");
  ok("裴注區塊有篇級分布（讀全篇入口存在）", openFuls.length > 0,
    "可讀全篇 " + openFuls.length + " 處");
  const readerEl = doc.getElementById("reader");
  /* ⚠️⚠️ 斷「狀態轉移」而不是斷終態，否則這條是**恆真**的。
   *   上面【8】點篇目時把原文層打開了、**到這裡一直沒關**，
   *   所以 `reader.classList.contains("on")` 在點擊前就已經是 true——
   *   刪掉分派後這條斷言**照樣綠**（注入驗證親自抓出來的）。
   *   判據必須是「點之前 off、點之後 on」：先 ensureClosed()，再斷它變 on。
   *   這與「三段拼回原句」對indexOf 恆真是同一類錯。 */
  const closeReader = async () => {
    const cb = doc.querySelector('.reader-head button[data-act="close"]');
    if (cb) click(cb);
    await sleep(300);
  };
  const ensureClosed = async () => {
    if (readerEl.classList.contains("on")) await closeReader();
    return !readerEl.classList.contains("on");
  };
  if (openFuls.length) {
    const wasClosed = await ensureClosed();
    ok("（前提）點之前原文層是關著的", wasClosed,
      "reader.on=" + readerEl.classList.contains("on"));
    const wantCid = openFuls[0].getAttribute("data-chapter");
    click(openFuls[0]);
    const got = await waitFor(() => readerEl.classList.contains("on"), 60000);
    const ps0 = doc.querySelectorAll("#readerBody p[data-uid]");
    ok("點「讀全篇」**真的**打開原文層（不是死按鈕）", got && ps0.length > 0,
      "reader.on=" + readerEl.classList.contains("on") + " / 句 " + ps0.length +
      " / 要開的篇 " + wantCid);
    await closeReader();
  } else {
    ok("點「讀全篇」**真的**打開原文層（不是死按鈕）", false, "找不到入口，無法驗");
  }
  const peiLines = out.querySelectorAll(".pei-line[data-chapter]");
  ok("裴注明細行存在", peiLines.length > 0,
    "明細 " + peiLines.length + " 條");
  if (peiLines.length) {
    const wasClosed2 = await ensureClosed();
    ok("（前提）點明細行之前原文層是關著的", wasClosed2,
      "reader.on=" + readerEl.classList.contains("on"));
    const pl = peiLines[0];
    const wantCid2 = pl.getAttribute("data-chapter");
    const pseq = pl.getAttribute("data-pseq");
    // ⚠️ 這條必須單獨斷：下面「按段號定位」裹在 if (pseq != null) 裡，
    //    屬性一旦不見，它只是**不出現**，測試總數不變、失败 0、綠。
    ok("明細行帶 data-pseq（否則「按段號定位」那條會靜默不執行）", pseq != null,
      "data-pseq=" + pseq + " / 章 " + wantCid2);
    click(pl);
    const got2 = await waitFor(() => readerEl.classList.contains("on"), 60000);
    const ps2 = doc.querySelectorAll("#readerBody p[data-uid]");
    ok("點注文明細行**真的**打開原文層（不是死按鈕）", got2 && ps2.length > 0,
      "reader.on=" + readerEl.classList.contains("on") + " / 句 " + ps2.length +
      " / 要開的篇 " + wantCid2 + " / 段號 " + pseq);
    // 有 data-pseq 時應該定位到那一段（p.target 是 jumpToPara 落的標記）
    if (pseq != null && got2) {
      const hit = doc.querySelector("#readerBody p.target");
      ok("明細行按段號定位到該段（p.target 落在那一段）",
        !!hit && hit.getAttribute("data-para") === String(Number(pseq)),
        "段號 " + pseq + " / target=" +
        (hit ? hit.getAttribute("data-para") : "null"));
    }
    await closeReader();
  } else {
    ok("點注文明細行**真的**打開原文層（不是死按鈕）", false, "找不到明細行，無法驗");
  }
  ok("裴注區塊有千分位（曹操 726 處）",
    /[\d],[\d]{3}/.test(doc.body.textContent),
    "页面上有千分位數字");
  ok("標了「獨立賬本，不計入正文命中」",
    /獨立賬本|獨立帳本/.test(doc.body.textContent));

  console.log("\n【9】无 JS 报错");
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
