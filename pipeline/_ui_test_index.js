/* 无头 UI 自测 · 索引四块（书切换 / 快捷词 / 人物索引 / 地名索引 / 篇目一覽）

   这几块静态版 web/ 一直有，新版 app/web/ 之前没有——补回来之后要有断言守着，
   否则下次改前端又会悄悄消失（本次正是因为「没有测试」才拖了这么久）。

   验证：
     1. 书切换条渲染出「全部 + 五书」，且默认停在「全部」
     2. 快捷词分人物 / 地名两段，地名带 .land 分色（与人物不同色）
     3. 四个标签页都能渲染出内容（不空、不是报错）
     4. 换书后索引条目数**变少**（按书计数真的生效，不是全量冒充）
     5. 换书后快捷词跟着换（三國志 的头一个应是曹操，不是孔子）
     6. 排序开关（篇数 ⇄ 次数）点了会换文案
     7. 检索框候选（datalist）有人有地，换书后跟着收窄
     8. 点索引条目 → 进检索；点篇目 → 开原文层
     9. 完整称谓表：分组 / ×N / 未用 / 泛称分色 / 换书后由 byBook 收窄
    10. 「前朝」小标记：断代史标、通史（史記）不标
    11. 网页「标错」入口：hover 出按钮 → 搜人名 → 点选写入 → 徽章 → 撤銷
    12. 地名检索与详情：输简体搜得到 → 点地名行进详情 → 点句进原文层
    13. 无 JS 报错

   用法（依赖 jsdom，装在隔离目录里，不污染本工程）：
     1) 起服务：PORT=8811 python app/server/main.py
     2) 跑测试：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules \
                 node pipeline/_ui_test_index.js
*/
const { JSDOM, VirtualConsole } = require("jsdom");

const BASE = process.env.BASE || "http://127.0.0.1:8811/";
let pass = 0, fail = 0;

function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + name); }
  else { fail++; console.log("  ✗ " + name + (extra ? "  → " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const vc = new VirtualConsole();
  const errs = [];
  vc.on("jsdomError", (e) => errs.push(String(e.message)));
  vc.on("error", (m) => errs.push(String(m)));

  const dom = await JSDOM.fromURL(BASE, {
    runScripts: "dangerously", resources: "usable",
    pretendToBeVisual: true, virtualConsole: vc,
    // jsdom 不带 fetch，而 app.js 全程靠它取数——必须在脚本执行**之前**塞进去
    beforeParse(w) { w.fetch = (u, o) => fetch(new URL(u, BASE), o); },
  });
  const { window } = dom;
  const doc = window.document;
  const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const out = doc.getElementById("out");
  const q = doc.getElementById("q");
  const bookbar = doc.getElementById("books");
  const quick = doc.getElementById("quick");

  const tab = (name) => [...doc.querySelectorAll(".tabs span")]
    .find((el) => el.getAttribute("data-tab") === name);
  const bk = (code) => [...bookbar.querySelectorAll(".bk")]
    .find((el) => el.getAttribute("data-book") === code);

  /* ⚠️ 两条等待纪律（都踩过）：
     1. 页面脚本是异步跑的，JSDOM.fromURL 返回时 IIFE 可能还没执行完——
        一上来就断言会得到「0 个按钮」这种假失败，先等渲染。
     2. 换书后 /api/index 要重算（约 2~4 秒），**不能只等「非空」**——
        旧数据也是非空，于是 waitIndex 立刻返回，测的其实是旧值。
        要等到**值真的变了**才算数。 */
  async function waitFor(cond, timeout = 20000) {
    for (let i = 0; i < timeout / 200; i++) {
      if (cond()) return true;
      await sleep(200);
    }
    return false;
  }
  async function waitIndex(timeout = 15000) {
    return waitFor(() => quick.querySelectorAll("span[data-name]").length > 0, timeout);
  }

  console.log("\n【1】书切换条");
  // 先等脚本把书切换条渲染出来，再断言
  const gotBar = await waitFor(() => bookbar.querySelectorAll(".bk").length === 6, 10000);
  ok("书切换条在超时前渲染出来了", gotBar,
    "实得 " + bookbar.querySelectorAll(".bk").length + " 个");
  ok("渲染出「全部 + 五书」共 6 个按钮",
    bookbar.querySelectorAll(".bk").length === 6,
    "实得 " + bookbar.querySelectorAll(".bk").length);
  ok("默认停在「全部」（带 on）",
    bk("") && bk("").classList.contains("on"));

  console.log("\n【2】快捷词");
  const gotQuick = await waitIndex();
  ok("快捷词在超时前渲染出来了（/api/index 回来了）", gotQuick);
  const qp = [...quick.querySelectorAll("span[data-name]")];
  const qLand = [...quick.querySelectorAll("span.land[data-name]")];
  ok("快捷词不为空", qp.length > 0, "实得 " + qp.length);
  ok("地名段带 .land 分色（与人物视觉可区分）", qLand.length > 0,
    "land=" + qLand.length + " / 共 " + qp.length);
  ok("人物段多于地名段（默认 20 人 + 10 地）",
    qp.length - qLand.length > qLand.length,
    "人 " + (qp.length - qLand.length) + " / 地 " + qLand.length);
  // 输入框候选是同一份 /api/index 填的，全量 2240 人 + 1575 地
  const dlEl = doc.getElementById("names");
  const allOpts = dlEl ? dlEl.querySelectorAll("option").length : 0;

  console.log("\n【3】四个标签页都能渲染");
  click(tab("persons"));
  await sleep(300);
  const personItems = out.querySelectorAll(".item[data-name]").length;
  ok("人物索引渲染出条目", personItems > 0, "实得 " + personItems);
  ok("人物索引带分组标题（含計數與排序開關）",
    out.querySelector(".group-title") && out.querySelector(".sort-toggle"));

  click(tab("places"));
  await sleep(300);
  /* ⚠️ 这里原来写的是 `.item[data-name]`。2026-10-03 地名条目改带 `data-place`
     （点地名直接进详情页，不再绕人物搜索——那才是「地名点不動」的根因），
     所以选择器跟着换。**别把断言删掉**：写成 `.item` 的话人物条目也会被算进来，
     数字照样 > 0，断言就废了。 */
  const placeItems = out.querySelectorAll(".item[data-place]").length;
  ok("地名索引渲染出条目", placeItems > 0, "实得 " + placeItems);
  ok("地名条目不带 data-name（別又落回人物檢索那條路）",
    out.querySelectorAll(".item[data-name]").length === 0,
    "实得 " + out.querySelectorAll(".item[data-name]").length);
  // ⚠️ 必须在**点之前**量：下面点开详情页后 #out 就不是索引页了，
  //    到那时再量 group-title 只会得到 0（分组标题是索引页才有的）。
  const groups = out.querySelectorAll(".group-title").length;
  ok("地名按類型分組（不止一組）", groups > 1, "實得 " + groups + " 組");
  /* ⚠️ 这里要**真的点一条**（2026-10-03 审查 P0-1）。
     地名有**两条**点击分派：索引页的 `.item[data-place]` 与检索结果的
     `.row[data-place]`。此前只有后者有测试覆盖（【12】从检索页点进去），
     于是把前者的 `if (pit) {...}` 整段删掉，全套测试照样全绿——
     症状是「在地名索引里点条目 → hash 停在索引态、命中 0 条、零报错」。
     两条分派必须各有一条断言，它们是**不同的代码路径**。 */
  {
    const pit = out.querySelector(".item[data-place]");
    const wantName = pit ? pit.getAttribute("data-place") : "";
    if (pit) click(pit);
    /* 等地名页独有的东西。别等 `.person-head .name`（索引页卡片头也有）。 */
    const gotIdxPlace = await waitFor(
      () => out.querySelectorAll(".sent[data-place]").length > 0, 20000);
    const idxName = out.querySelector(".person-head .name");
    ok("地名索引里点条目 → 進地名詳情頁（.item[data-place] 分派有覆盖·P0-1）",
      gotIdxPlace && !!idxName && wantName
      && (window.location.hash || "").indexOf("#/place/" + wantName) === 0,
      "实得「" + (idxName ? idxName.textContent : "") + "」hash="
      + window.location.hash);
    /* P0-3：分篇标题**要有篇名**。原来只断过「有 .chapter-title」，
       而 chapter 字段被删掉时标题会退化成「 · 2 處」——仍然「有」，断言照样绿。
       所以判据必须是「去掉次数后还剩字」。 */
    const ct0 = out.querySelector(".chapter-title");
    const ct0t = ((ct0 || {}).textContent || "").replace(/^[\s·0-9]+處$/, "").trim();
    ok("地名詳情分篇標題有篇名（chapter 欄位沒丟·P0-3）",
      !!ct0 && ct0t.length > 0, "实得「" + ((ct0 || {}).textContent || "") + "」");
  }

  click(tab("chapters"));
  await sleep(300);
  const chapRows = out.querySelectorAll(".chap-row[data-chapter]").length;
  ok("篇目一覽渲染出篇目", chapRows > 0, "实得 " + chapRows);
  ok("篇目按書分節（有 .book-title）",
    out.querySelectorAll(".book-title").length > 0);
  // 564 篇是五书合计，书目不增不减；写成「>500」而不是写死 564，
  // 免得将来接新史书时这条断言变成假失败。
  ok("篇目總數在合理量級（>500）", chapRows > 500, "实得 " + chapRows);
  const chapCats = out.querySelectorAll(".group-title").length;
  ok("篇目書內按類別分節（本紀/世家/列傳…）", chapCats >= 5,
    "实得 " + chapCats + " 个类别标题");
  const chapTags = out.querySelectorAll(".chap-row .tag").length;
  ok("篇目行带篇主／地名标签（静态版有，补回来后要守住）", chapTags > 0,
    "实得 " + chapTags);

  console.log("\n【4】换书后索引真的按书收窄");
  click(tab("persons"));
  await sleep(300);
  const allCount = out.querySelectorAll(".item[data-name]").length;
  click(bk("sgz"));                       // 三國志
  // 等到条目数真的变了（换书后要重算，旧值也是「非空」，只等非空会测到旧数据）
  const changed = await waitFor(
    () => out.querySelectorAll(".item[data-name]").length !== allCount, 25000);
  ok("换书后索引在超时前完成重算", changed);
  const sgzCount = out.querySelectorAll(".item[data-name]").length;
  ok("换到三國志后人物索引条目变少（按書計數生效）",
    sgzCount > 0 && sgzCount < allCount,
    "全部 " + allCount + " → 三國志 " + sgzCount);
  ok("书切换条高亮跟着换到三國志",
    bk("sgz").classList.contains("on") && !bk("").classList.contains("on"));

  console.log("\n【5】换书后快捷词跟着换");
  const names = [...quick.querySelectorAll("span[data-name]")]
    .map((el) => el.getAttribute("data-name"));
  ok("三國志的快捷词头一个是曹操（不是孔子）",
    names[0] === "曹操", "实得 " + names.slice(0, 3).join("、"));
  ok("三國志的快捷词里有孫權/劉備",
    names.includes("孫權") && names.includes("劉備"),
    "前三 " + names.slice(0, 5).join("、"));

  console.log("\n【6】排序开关");
  const tog = out.querySelector(".sort-toggle");
  const before = tog ? tog.textContent : "";
  if (tog) click(tog);
  await sleep(300);
  const after = out.querySelector(".sort-toggle");
  ok("点排序开关后文案变了（篇數 ⇄ 次數）",
    after && after.textContent && after.textContent !== before,
    before + " → " + (after ? after.textContent : "无"));

  console.log("\n【7】检索框自动补全（datalist）");
  // 静态版一直有输入候选，新版补索引页时漏了；换书要跟着收窄，
  // 不能出现「选了三國志，还推荐一个只在晉書出现的人」。
  ok("输入框挂上了候选（datalist 有 option）", allOpts > 1000, "实得 " + allOpts);
  const hasLand = [...dlEl.querySelectorAll("option")]
    .some((o) => (o.textContent || "").indexOf("地名") === 0);
  ok("候选里区分人与地（地名 option 带「地名 ·」说明）", hasLand);
  const sgzOpts = dlEl.querySelectorAll("option").length;
  ok("换到三國志后候选跟着收窄", sgzOpts > 0 && sgzOpts < allOpts,
    "全部 " + allOpts + " → 三國志 " + sgzOpts);

  console.log("\n【8】点条目能进检索 / 开原文");
  click(tab("persons"));
  await sleep(300);
  const first = out.querySelector(".item[data-name]");
  if (first) click(first);
  // ⚠️ 这里原来写死 sleep(800)。修好 hash 守卫（app.js 的 hashOf）之后不再有
  // 「意外的第二次渲染」替我们兜底，那 800ms 就不够了——/api/search 一次 JOIN
  // 偶尔超时就红。**等条件，不等时间**（本文件开头第二条纪律）。
  const gotSearch = await waitFor(
    () => out.querySelectorAll(".row[data-pid], .empty").length > 0, 15000);
  ok("点人物索引条目 → 检索框被填入该名字",
    q.value && q.value.length > 0, "输入框=「" + q.value + "」");
  ok("点人物索引条目 → 检索结果渲染出来了", gotSearch,
    "out=" + out.innerHTML.slice(0, 60));

  click(tab("chapters"));
  await sleep(300);
  const chap = out.querySelector(".chap-row[data-chapter]");
  if (chap) click(chap);
  await sleep(1200);
  ok("点篇目 → 原文层打开",
    doc.getElementById("reader").classList.contains("on"));

  console.log("\n【9】完整称谓表（人物页）");
  /* 这张表是「这个别名靠不靠谱」的唯一依据：硬命中显示 ×N，词典收了但书里没出现
     的显示「未用」。它坏了页面**不报错**（renderPerson 有扁平别名兜底），
     所以必须盯着：分组渲染出来了、两组 marker（×N / 未用）都在、换书后收窄生效。 */
  const chipOf = (w) => [...doc.querySelectorAll(".alias-group .chip")]
    .find((el) => (el.textContent || "").indexOf(w) === 0);
  const chipText = (w) => { const c = chipOf(w); return c ? c.textContent : ""; };

  /* ⚠️ 换书的正确姿势：**先退出人物页再换，换完再进来**。
     两点原因：① 书切换会 `loadIndex(renderCurrentTab)` 重渲染当前标签页，
     站在人物页上换书等于把称谓表冲掉；② 人物页的数字是客户端按 byBook 算的，
     只有重新渲染一次才会刷新。另外必须先切回「全部」读基准——前面【4】
     已经把书切成了三國志，不切回来就是在跟收窄后的值比（踩过一次）。 */
  const reindexed = (expectCao) => () => {
    const ns = [...quick.querySelectorAll("span[data-name]")]
      .map((el) => el.getAttribute("data-name"));
    return ns.length > 0 && (expectCao ? ns[0] === "曹操" : ns[0] !== "曹操");
  };
  window.location.hash = "#/q/邦";
  await sleep(400);
  click(bk(""));
  await waitFor(reindexed(false), 25000);
  window.location.hash = "#/person/p_liubang";
  const gotAlias = await waitFor(
    () => out.querySelectorAll(".alias-group").length > 0, 20000);
  ok("人物页渲染出称谓分组表", gotAlias,
    "out=" + out.innerHTML.slice(0, 80));
  ok("分组不止一组（本名 / 職銜 / 泛稱…各成一行）",
    out.querySelectorAll(".alias-group").length >= 2,
    "实得 " + out.querySelectorAll(".alias-group").length + " 组");
  ok("每组有类别标签（本名 / 職銜…）",
    [...out.querySelectorAll(".alias-group .kind")]
      .some((el) => (el.textContent || "").indexOf("本名") >= 0),
    "实得 " + [...out.querySelectorAll(".alias-group .kind")]
      .map((el) => el.textContent).join("、"));

  const chips = [...out.querySelectorAll(".alias-group .chip")];
  ok("称谓 chip 渲染出来了", chips.length > 0, "实得 " + chips.length);
  ok("高频称谓带 ×N（「漢王 ×739」这种）",
    (chipText("漢王") || "").indexOf("×") > 0, "实得「" + chipText("漢王") + "」");
  ok("存在「未用」称谓（本名劉邦五书里一次没出现过）",
    chips.some((el) => (el.textContent || "").indexOf("未用") > 0
      && el.classList.contains("off")),
    "实得 " + chips.filter((el) => el.classList.contains("off")).length + " 条未用");
  ok("泛称单独一类、且视觉区分（带 .gen）",
    out.querySelectorAll(".alias-group .chip.gen").length > 0,
    "gen=" + out.querySelectorAll(".alias-group .chip.gen").length);
  ok("泛称有归属说明（不固定属于谁）",
    (out.querySelector(".alias-note") || {}).textContent
      && out.querySelector(".alias-note").textContent.indexOf("不固定屬於誰") >= 0,
    "实得「" + ((out.querySelector(".alias-note") || {}).textContent || "").slice(0, 30) + "」");

  // ⚠️ 换书要在**重新进人物页**之后才有意义：人物页的数字是客户端按 byBook 算的，
  // 只有重新渲染一次才会刷新。
  const wideTxt = chipText("漢王");
  ok("全部书下读到五书合计（「漢王 ×739」）", wideTxt.indexOf("×739") > 0,
    "实得「" + wideTxt + "」");
  click(bk("sgz"));
  const reIdx = await waitFor(reindexed(true), 25000);
  ok("切换到三國志后索引重算完成", reIdx);
  window.location.hash = "#/q/邦";
  await sleep(400);
  window.location.hash = "#/person/p_liubang";
  const narrowed = await waitFor(
    () => chipText("漢王") && chipText("漢王") !== wideTxt, 20000);
  ok("换书后称谓次数跟着收窄（客戶端按 byBook 算）", narrowed,
    wideTxt + " → " + chipText("漢王"));
  const num = (t) => parseInt(((t || "").match(/×([\d,]+)/) || [])[1]
    ? ((t).match(/×([\d,]+)/)[1]).replace(/,/g, "") : "0", 10);
  ok("三國志里的数字小于五书合计（不是全量冒充）",
    num(chipText("漢王")) > 0 && num(chipText("漢王")) < 739,
    wideTxt + " → " + chipText("漢王"));

  console.log("\n【10】「前朝」小标记（断代史里的前朝人）");
  /* 选了断代史才标：人的 eraRank 落在该书记载区间之前（如《漢書》里的孔子）。
     两条不标：史記是通史没有区间；人没断出时代（169 人）也不标、不猜。 */
  click(tab("persons"));
  await sleep(300);
  const eraMarks = () => out.querySelectorAll(".item .era-old");
  const nItem = () => out.querySelectorAll(".item[data-name]").length;
  /* ⚠️ 换书后**等条目数真的变了**再断言（本文件开头第 2 条纪律）：
     旧数据也是「非空」，只等非空就会把上一本书的 194 个标记当成史記的。 */
  const n0 = nItem();
  click(bk("sj"));                        // 通史：一律不标
  await waitFor(() => nItem() !== n0, 25000);
  ok("史記是通史 → 不标「前朝」", eraMarks().length === 0,
    "实得 " + eraMarks().length + " 个标记");

  const n1 = nItem();
  click(bk("hs"));                        // 漢書：区间 [8,10]，前朝人不少
  await waitFor(() => nItem() !== n1, 25000);
  const gotEra = await waitFor(() => eraMarks().length > 0, 25000);
  ok("選漢書 → 有人被标「前朝」", gotEra, "实得 " + eraMarks().length + " 个");
  ok("标了的条目占比合理（不是全员前朝）",
    eraMarks().length > 0
      && eraMarks().length < out.querySelectorAll(".item[data-name]").length,
    eraMarks().length + " / " + out.querySelectorAll(".item[data-name]").length);
  ok("标记文案是繁体「前朝」",
    [...eraMarks()].every((el) => (el.textContent || "") === "前朝"),
    "实得「" + [...eraMarks()].map((el) => el.textContent).slice(0, 3).join("、") + "」");

  console.log("\n【11】网页「标错」入口（人物页）");
  /* 这条链路的坏法是**不报错**的：nth 算错 → 改归落到别人头上，界面照样显示
     「已標錯」。所以这里守的是闭环：hover 出按钮 → 面板能搜到人 → 点选真的写进去
     → 徽章出现 → 撤銷后徽章消失。
     ⚠️ 写入落在**沙盒表**（run_all.sh 给临时服务设了 BOOKINDEX_OVERRIDES）——
     revoke 是改状态不删行，打真实权威源会让 workbook/overrides.xlsx 每次回归多两行。 */
  /* ⚠️ 先跳到检索页再进人物页：`location.hash` 设成**跟当前一样的值**不会触发
     hashchange（【9】末尾已经停在 #/person/p_liubang），页面就不会重渲染，
     断言得到的是上一屏（索引页）的 0 行命中——不是页面的 bug，是测试没换路由。 */
  window.location.hash = "#/q/邦";
  await sleep(400);
  window.location.hash = "#/person/p_liubang";
  const gotSents = await waitFor(
    () => out.querySelectorAll(".sent[data-uid]").length > 0, 20000);
  ok("人物页渲染出命中行", gotSents,
    "实得 " + out.querySelectorAll(".sent[data-uid]").length + " 行");
  const flagBtns = () => [...out.querySelectorAll('.sent button[data-act="flag"]')];
  ok("命中行带「標錯」按钮", flagBtns().length > 0, "实得 " + flagBtns().length + " 个");
  ok("命中行带定位用的 s / e / surface（后端靠它算 nth）",
    out.querySelector(".sent[data-uid]").getAttribute("data-surface") !== null
    && out.querySelector(".sent[data-uid]").getAttribute("data-s") !== null);
  /* 后面每一步都做空值保护：按钮一旦没了，应当**只红这一条**并继续跑完，
     而不是崩在 dispatchEvent 上把「控制台无异常」也一起吞掉（本文件【8】的写法）。 */
  if (flagBtns()[0]) click(flagBtns()[0]);
  const gotBox = await waitFor(() => out.querySelector(".fixbox"), 8000);
  ok("点「標錯」→ 就地展开面板（不弹窗）", !!gotBox);
  ok("面板有输入框（输人名，不是填 pid）", !!out.querySelector(".fixbox .fix-input"));
  ok("面板有「不是他」（这处不作数）按钮",
    !!out.querySelector('.fixbox button[data-act="drop"]'));

  const inp = out.querySelector(".fixbox .fix-input");
  if (inp) {
    inp.value = "項羽";
    inp.dispatchEvent(new window.Event("input", { bubbles: true }));
  }
  const gotCand = await waitFor(
    () => out.querySelectorAll(".fixbox .fix-cand-row").length > 0, 15000);
  ok("输入人名 → 出候选（不是要你手敲 pid）", gotCand);
  const cand0 = out.querySelector(".fixbox .fix-cand-row");
  ok("候选第一个就是項羽",
    (cand0 && (cand0.querySelector(".nm") || {}).textContent) === "項羽",
    "实得「" + (cand0 ? cand0.textContent : "") + "」");

  if (cand0) click(cand0);
  // ⚠️ waitFor 返回的是**布尔**，不是元素——拿它去读 textContent 会得到 ""，
  // 于是「徽章写明改归给谁」永远是空串（踩过一次的写法）。等完再重新取一次。
  const wrote = await waitFor(() => !!out.querySelector(".flag-badge"), 20000);
  const gotBadge = out.querySelector(".flag-badge");
  ok("点候选 → 真写进去了（命中行出现「已標錯」徽章）", wrote && !!gotBadge,
    "out=" + out.innerHTML.slice(0, 120));
  ok("徽章写明改归给谁（→ 項羽，不是 pid）",
    ((gotBadge || {}).textContent || "").indexOf("項羽") > 0,
    "实得「" + ((gotBadge || {}).textContent || "") + "」");
  const ovbar = out.querySelector(".ovbar");
  /* ⚠️ 断言的是「待重建」而不是「已記錄」：表里的行永远 active（revoke 只改状态），
     「是否已生效」是后端 db.override_states **算出来**的（applied 字段）。
     算错的话顶栏 N 永不归零 —— 界面一直骗你「重建後生效」，重建完还是这句。 */
  ok("顶部提示「有 N 條糾錯待重建」（不让人以为已改）",
    ovbar && ovbar.textContent.indexOf("糾錯待重建") > 0,
    "实得「" + ((ovbar || {}).textContent || "") + "」");
  ok("徽章此刻**不带** ✓（还没重建，别显示成已生效）",
    gotBadge && (gotBadge.textContent || "").indexOf("✓") < 0,
    "实得「" + ((gotBadge || {}).textContent || "") + "」");
  ok("徽章带撤銷出口（改错了能反悔）",
    !!out.querySelector('.flag-badge button[data-act="unflag"]'));
  /* 重建状态必须能在**人物页**看得见。原文层的 #edstat 在原文层头上，
     没开原文层时从人物页点重建就是 30 秒静默等待 —— 这条守的就是它。 */
  ok("顶栏留了 .ovtxt 給重建狀態（人物页按重建不静默）",
    !!(ovbar && ovbar.querySelector(".ovtxt")));
  ok("顶栏有「重建」按钮（纠错就地生效，不用跑去原文层）",
    !!out.querySelector('.ovbar button[data-act="ovrebuild"]'));

  const unflag = out.querySelector('.flag-badge button[data-act="unflag"]');
  if (unflag) click(unflag);
  const gone = await waitFor(() => !out.querySelector(".flag-badge"), 20000);
  ok("撤銷 → 徽章消失", gone, "还剩 " + out.querySelectorAll(".flag-badge").length + " 个");

  console.log("\n【12】地名檢索與詳情頁");
  /* 这一块是 2026-10-03 新加的。此前地名侧**根本没有入口**：
     输「長安」0 条、点地名条掉到人物搜索上、输「邯郸」也 0 条
     （places.name 与 trad_name 逐行相同，简体名只存在异体表里）。
     三种坏**都不报错**——界面只是「搜不到」「点不动」，所以必须断。 */
  /* ⚠️ 先把原文层关掉。【8】点篇目时打开过，一直没关：
     不关的话下面「点句 → 原文层打开」会**假通过**（本来就开着），
     而「只看相關段落」按鈕的可见性也会读到上一篇的殘留狀態。 */
  if (doc.getElementById("reader").classList.contains("on")) {
    const cb0 = doc.querySelector('.reader-head button[data-act="close"]');
    if (cb0) click(cb0);
    await sleep(300);
  }
  ok("原文層已關閉（下面兩條斷言的前提）",
    !doc.getElementById("reader").classList.contains("on"));

  // ⚠️ 检索靠**点按钮**触发（qEl 只绑了 keydown，没有 input 事件）。
  //    直接赋值 q.value 再等，是等不到的。
  click(bk(""));                             // 回到全部，免得上面停在三國志
  await sleep(600);
  /* ⚠️ 先清屏再等。上面【11】人物頁留着一堆命中行，而检索结果页与详情页
     共用 #out —— 不清的话「等 .row[data-place] 出现」有可能量到残留。
     判据写死「这一行里是邯鄲」，别只等「有一行地名」。 */
  out.innerHTML = "";
  q.value = "邯郸";                          // 简体：以前 0 条
  click(doc.getElementById("btn"));
  const gotPlaceRow = await waitFor(() => {
    const rows = [...out.querySelectorAll(".row[data-place]")];
    return rows.length > 0 && rows.some((r) => (r.textContent || "").indexOf("邯鄲") >= 0);
  }, 20000);
  ok("輸簡體「邯郸」搜得到地名（異體表是唯一出口）", gotPlaceRow,
    "out=" + out.innerHTML.slice(0, 100));
  const pRow = [...out.querySelectorAll(".row[data-place]")]
    .find((r) => (r.textContent || "").indexOf("邯鄲") >= 0);
  ok("地名行帶類別標記 .land-kind（與人物行分得開）",
    !!(pRow && pRow.querySelector(".land-kind")),
    "实得「" + (pRow ? pRow.textContent : "") + "」");
  ok("地名段與人物段**分卡呈現**（同一個詞的兩類實體）",
    out.querySelectorAll(".card").length >= 2
    && out.textContent.indexOf("共") > 0);

  // 点地名行 → 直接进详情页（不再绕搜索）
  if (pRow) click(pRow);
  /* ⚠️ 等待条件必须是**地名页独有**的东西，不能等 `.person-head .name`：
     检索结果页也有这个类（`.person-head` 是共用的卡片头），条件立刻成立，
     断言全读到**检索页**——详情页看起来「什么都不对」，而点击其实是好的。
     教训与本文件开头第二条纪律同源：**等条件要等对东西**。
     地名页独有：`.sent[data-place]`（命中行带地名 id）。 */
  const gotPlace = await waitFor(
    () => out.querySelectorAll(".sent[data-place]").length > 0, 20000);
  const pName = out.querySelector(".person-head .name");
  ok("点地名行 → 進地名詳情頁（不是人物搜索）", gotPlace
    && pName && pName.textContent.indexOf("邯鄲") === 0,
    "实得「" + (pName ? pName.textContent : "") + "」");
  ok("詳情頁頭部帶類型說明（縣/郡/國…）",
    !!(out.querySelector(".person-head .dyn")
       && /縣|郡|國|山|川|關|湖|域|外/.test(
         out.querySelector(".person-head .dyn").textContent)),
    "实得「" + ((out.querySelector(".person-head .dyn") || {}).textContent || "")
    + "」");
  ok("詳情頁列出寫法（含「邯郸」異體，否則用戶以為此地不存在）",
    out.textContent.indexOf("邯郸") > 0 && !!out.querySelector(".alias-tag"));
  const bookNote = out.querySelector(".alias-note");
  ok("詳情頁有「見於哪些書」（地名側的分書判據）", !!bookNote,
    "实得「" + ((bookNote || {}).textContent || "") + "」");
  const pSents = out.querySelectorAll(".sent[data-chapter]").length;
  ok("詳情頁渲染出命中句（點句可進原文層）", pSents > 0, "实得 " + pSents);
  ok("命中句帶原文層入口 data-chapter + data-uid",
    !!out.querySelector(".sent[data-chapter][data-uid]"));
  // P0-3 的同款判据（【3】那条守的是「从索引页进来」这条路径）：
  // 分篇标题去掉次数后必须还剩篇名，否则 chapter 字段被丢掉时看不出来。
  const ctP = out.querySelector(".chapter-title");
  const ctPt = ((ctP || {}).textContent || "").replace(/^[\s·0-9]+處$/, "").trim();
  ok("分篇標題有篇名（檢索→詳情這條路徑上也是·P0-3）",
    !!ctP && ctPt.length > 0, "实得「" + ((ctP || {}).textContent || "") + "」");

  // 進原文層：「只看相關段落」在地名頁也要能開（作用域是地名不是人物）
  const ps = out.querySelector(".sent[data-chapter]");
  if (ps) click(ps);
  const gotReader = await waitFor(
    () => doc.getElementById("reader").classList.contains("on"), 20000);
  ok("点地名命中句 → 開原文層", gotReader);
  const btnHits = doc.getElementById("btnHits");
  const hitsVisible = btnHits && !btnHits.hidden;
  ok("原文層的「只看相關段落」在地名頁也在（別只認人物 pid）",
    !!hitsVisible, "按钮=" + (btnHits ? (btnHits.hidden ? "hidden" : "可见")
      : "找不到"));
  if (hitsVisible && btnHits) {
    click(btnHits);
    await sleep(400);
    ok("「只看相關段落」篩選後仍有段落（篩選沒把內容全濾掉）",
      doc.querySelectorAll("#readerBody p").length > 0,
      "实得 " + doc.querySelectorAll("#readerBody p").length + " 段");
  }
  const closeBtn = doc.querySelector('.reader-head button[data-act="close"]');
  if (closeBtn) click(closeBtn);
  await sleep(300);

  // 路由：地名页有自己的 hash，刷新/后退能回来
  ok("地名頁路由是 #/place/{id}（與人物頁分開）",
    (window.location.hash || "").indexOf("#/place/") === 0,
    "实得 " + window.location.hash);

  console.log("\n【13】控制台无异常");
  ok("无 jsdomError", errs.length === 0, errs.slice(0, 2).join(" | "));

  console.log("\n=============== 索引四块 UI 测试：" + pass + " 通过 / " + fail +
    " 失败 ================");
  dom.window.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error("测试崩溃：", e);
  process.exit(1);
});
