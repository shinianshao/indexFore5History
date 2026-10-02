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
    11. 无 JS 报错

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
  const placeItems = out.querySelectorAll(".item[data-name]").length;
  ok("地名索引渲染出条目", placeItems > 0, "实得 " + placeItems);
  const groups = out.querySelectorAll(".group-title").length;
  ok("地名按類型分組（不止一組）", groups > 1, "實得 " + groups + " 組");

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

  console.log("\n【11】控制台无异常");
  ok("无 jsdomError", errs.length === 0, errs.slice(0, 2).join(" | "));

  console.log("\n=============== 索引四块 UI 测试：" + pass + " 通过 / " + fail +
    " 失败 ================");
  dom.window.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error("测试崩溃：", e);
  process.exit(1);
});
