/* 地名层无头 UI 自测：验证人名层之外新增的地名功能。
     1. 地名索引标签页能分组渲染，单字国名带 char-place 样式
     2. 具名地名「滎陽」→ 直接进地名页；异写（洛陽／雒陽）并成一条
     3. 单字国名「齊」→ 单字提示、正文里是虚线下划线 approx（非黄底）
     4. 同名多义「齊王」→ 弹候选列表；选中后进对应实体页
     5. 地名专篇为空时如实说明（「钜鹿」散见诸篇、从不作叙述主体）
     6. 地名页读全篇能打开，且高亮只落当前地名（不被同篇其他地名污染）
     7. 一句话多次提到同一地名 → 结果列表里这句只出现一次，但「处」数照实
   用法（依赖 jsdom，装在隔离目录里，不污染本工程）：
     1) 起服务：cd web && python -m http.server 8770 --bind 127.0.0.1
     2) 跑测试：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules node pipeline/_ui_test_places.js */
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
    runScripts: "dangerously",
    resources: "usable",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const { window } = dom;
  const doc = window.document;
  const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const out = doc.getElementById("out");
  const q = doc.getElementById("q");

  /* 期望值一律从数据现场算，不写死数字：
     收录的书从 1 本变 2 本后，所有绝对次数都会变，
     但「归并后相加」「处/句分报」这些口径不变——钉口径，不钉数字。 */
  let D = window.BOOK_DATA;          // 下面 load 完成后再取一次（此刻脚本还没跑完）
  const fmt = (n) => Number(n).toLocaleString();
  const placeByName = (name) => D.places.find((p) => p.name === name);
  /* 某地名在「专篇之外」的处数 om / 句数 os，以及逐篇分帐 */
  const expPlace = (pid) => {
    const P = D.places.find((p) => p.id === pid) || {};
    const main = new Set((P.mainChapters || []).map((r) => r.cid));
    let om = 0, os = 0;
    const byCh = {};
    D.sentences.forEach((s) => {
      let n = 0;
      (s.pmarks || []).forEach((m) => { if (m.pid === pid) n += 1; });
      if (!n || main.has(s.chapterId)) return;
      om += n; os += 1;
      const c = (byCh[s.chapterId] = byCh[s.chapterId] || { om: 0, os: 0 });
      c.om += n; c.os += 1;
    });
    return { om: om, os: os, byCh: byCh,
             text: om === os ? fmt(om) + " 處"
                             : fmt(om) + " 處（" + fmt(os) + " 句）" };
  };

  async function doSearch(word) {
    q.value = word;
    click(doc.getElementById("btn"));
    await sleep(120);
  }
  async function doTab(tab) {
    click(doc.querySelector('.tabs span[data-tab="' + tab + '"]'));
    await sleep(120);
  }

  await new Promise((r) => window.addEventListener("load", r));
  await sleep(500);
  D = window.BOOK_DATA;

  console.log("\n【1】地名索引标签页");
  ok("标签栏出现「地名索引」", !!doc.querySelector('.tabs span[data-tab="places"]'));
  await doTab("places");
  const items = out.querySelectorAll(".grid .item");
  ok("地名索引渲染出条目", items.length > 100, "条目数 " + items.length);
  const titles = [...out.querySelectorAll(".group-title")].map((e) => e.textContent);
  ok("按类型分组（國/郡/縣…，界面已繁体）", titles.some((t) => t.indexOf("國/朝代") >= 0) &&
     titles.some((t) => t.indexOf("郡") >= 0), titles.join(" | ").slice(0, 120));
  ok("单字国名带 char-place 标记", out.querySelectorAll(".grid .item.char-place").length > 30,
     "共 " + out.querySelectorAll(".grid .item.char-place").length + " 个");
  ok("悬停提示含地名说明", (items[0].getAttribute("title") || "").length > 0);

  console.log("\n【2】具名地名 · 滎陽");
  await doSearch("滎陽");
  ok("进入地名页", out.textContent.indexOf("滎陽") >= 0);
  ok("有「全部写法」表", !!out.querySelector(".alias-title"));
  ok("标出篇名含地名的专篇", out.textContent.indexOf("篇名含地名") >= 0);
  ok("给出「其他篇目提及」", out.textContent.indexOf("其他篇目提及") >= 0);
  ok("句子里有黄底高亮", out.querySelectorAll(".sentence mark").length > 0);
  ok("具名地名不误标 approx", out.querySelectorAll(".sentence mark.approx").length === 0);

  console.log("\n【3】异写归并 · 洛陽 / 雒陽");
  await doSearch("洛陽");
  ok("进入洛陽地名页", out.textContent.indexOf("洛陽") >= 0 || out.textContent.indexOf("雒陽") >= 0);
  // 写法表用「代表写法 + 次数」呈现，全部异写在悬停提示里，所以按行数判断归并
  const luoRows = [...out.querySelectorAll(".alias-group .chip")].filter((e) =>
    /^[洛雒]/.test(e.textContent));
  ok("洛陽/雒陽 并成一行（不是两行）", luoRows.length === 1,
     "匹配 " + luoRows.length + " 行：" + luoRows.map((e) => e.textContent).join(" | "));
  if (luoRows.length === 1) {
    const tip = luoRows[0].getAttribute("title") || "";
    ok("悬停提示列出洛陽、雒陽两种写法",
       tip.indexOf("洛陽") >= 0 && tip.indexOf("雒陽") >= 0, tip.replace(/\n/g, " / "));
    const n = parseInt((((luoRows[0].textContent.match(/×([\d,]+)/) || [])[1]) || "0").replace(/,/g, ""), 10);
    const luoP = placeByName("洛陽") || placeByName("雒陽");
    let want = 0;
    D.sentences.forEach((s) => (s.pmarks || []).forEach((m) => {
      if (m.pid !== luoP.id) return;
      want += 1;   // 后汉书简繁混排，正文写法不只洛陽/雒陽，还混有简体 洛阳/雒阳
    }));
    ok("合并后次数＝该地名全部写法之和（" + want + "）", n === want, "×" + n);
  }
  await doSearch("洛邑");
  const yiRows = [...out.querySelectorAll(".alias-group .chip")].filter((e) =>
    /^[洛雒]/.test(e.textContent));
  ok("洛邑/雒邑 也并成一行", yiRows.length === 1, "匹配 " + yiRows.length + " 行");

  console.log("\n【4】单字国名 · 齊");
  await doSearch("齊");
  ok("进入地名页（或候选）", out.textContent.indexOf("齊") >= 0);
  ok("提示这是单字地名", out.textContent.indexOf("單字地名") >= 0);
  const approx = out.querySelectorAll(".sentence mark.approx");
  ok("正文命中用 approx 虚线下划线", approx.length > 0, "approx 标记 " + approx.length + " 处");
  ok("单字命中的 mark 带 title 提示可能误收",
     [...approx].some((m) => (m.getAttribute("title") || "").indexOf("鄰字") >= 0));
  ok("单字地名与人物高亮不同色类（未用 guess）",
     out.querySelectorAll(".sentence mark.guess").length === 0);

  console.log("\n【5】同名多义 · 齊王（弹候选）");
  await doSearch("齊王");
  const cands = out.querySelectorAll(".candidate");
  ok("弹出候选列表", cands.length >= 3, "候选 " + cands.length + " 个");
  ok("候选标出实体类型", [...cands].every((c) => c.getAttribute("data-kind")), "缺 data-kind");
  if (cands.length) {
    const firstName = cands[0].querySelector(".name").textContent.replace(/人物.*/, "").trim();
    click(cands[0]);
    await sleep(150);
    ok("选中候选后进入该实体页", out.textContent.indexOf(firstName) >= 0, "期望含 " + firstName);
    ok("实体页有全部称谓表", !!out.querySelector(".alias-groups"));
  }

  console.log("\n【6】无专篇地名 · 钜鹿（如实说明）");
  await doSearch("鉅鹿");
  ok("进入钜鹿地名页", out.textContent.indexOf("钜鹿") >= 0 || out.textContent.indexOf("鉅鹿") >= 0);
  if (out.querySelector(".candidate")) { click(out.querySelector(".candidate")); await sleep(150); }
  ok("「整篇讲述」如实说明无专篇",
     out.textContent.indexOf("沒有以該地為主體的專篇") >= 0,
     "未见说明文案");
  ok("仍列出其他篇目提及", out.querySelectorAll(".mention-head").length > 0,
     out.querySelectorAll(".mention-head").length + " 篇");

  console.log("\n【7】地名页读全篇 · 高亮只落当前地名");
  await doSearch("秦");
  if (out.querySelector(".candidate")) { click(out.querySelector('.candidate[data-kind="place"]')); await sleep(150); }
  const rows = out.querySelectorAll(".primary-row");
  ok("秦有「整篇讲述」篇目", rows.length > 0, rows.length + " 篇");
  if (rows.length) {
    click(rows[0]);
    await sleep(800);
    const reader = doc.getElementById("reader");
    ok("阅读器打开", reader.classList.contains("on"));
    const body = doc.getElementById("readerBody");
    const head = doc.getElementById("readerTitle").textContent;
    ok("标题写明高亮含义", head.indexOf("虛線下劃線") >= 0, head.slice(0, 80));
    const marksInBody = [...body.querySelectorAll("mark")];
    ok("正文出现地名高亮", marksInBody.length > 0, marksInBody.length + " 处");
    // 高亮只应是「秦」相关写法，不应混入同篇其他地名
    const bad = marksInBody.filter((m) => {
      const t = m.textContent || "";
      return t && t.indexOf("秦") < 0;
    });
    ok("高亮未被同篇其他地名污染", bad.length === 0,
       bad.slice(0, 6).map((m) => m.textContent).join("、"));
    click(doc.querySelector('#readerTools [data-act="close"]'));
    await sleep(100);
  }

  console.log("\n【8】句内重复 · 同一句话只出现一次");
  /* 索引里一句多标是一句一标的：正文「舜耕歷山，歷山之人皆讓畔」里歷山出现两次，
     就有两个标记。结果列表若按标记罗列，这句话会原样排两遍。列表必须按句去重，
     但次数不能跟着丢——所以「处」（标记数）与「句」（去重后句子数）要分开报。 */
  const liP = placeByName("歷山");
  const eLi = expPlace(liP.id);
  await doSearch("历山");
  if (out.querySelector(".candidate")) { click(out.querySelector('.candidate[data-kind="place"]')); await sleep(150); }
  const liMeta = [...out.querySelectorAll(".mention-head .meta")].map((e) => e.textContent).join(" | ");
  /* 逐篇都要在「处≠句」时把两个数都报出来（只报处会让人以为漏了句子） */
  const liDupCh = Object.keys(eLi.byCh).filter((cid) => eLi.byCh[cid].om !== eLi.byCh[cid].os);
  ok("歷山：句內有重複的篇目同時報「處」與「句」",
     liDupCh.length > 0 && liDupCh.every((cid) => {
       const c = eLi.byCh[cid];
       return liMeta.indexOf(fmt(c.om) + " 處 · " + fmt(c.os) + " 句") >= 0;
     }),
     liDupCh.map((cid) => cid + " " + eLi.byCh[cid].om + "/" + eLi.byCh[cid].os).join(" ") +
     " ←→ " + liMeta.slice(0, 80));
  const liAllSmall = Object.keys(eLi.byCh).every((cid) => eLi.byCh[cid].os <= 3);
  ok("歷山：「顯示全部」只在單篇超過 3 句時出現（" + (liAllSmall ? "都 ≤3 句" : "有 >3 句的篇") + "）",
     liAllSmall ? out.querySelectorAll(".more").length === 0
                : out.querySelectorAll(".more").length > 0,
     [...out.querySelectorAll(".more")].map((e) => e.textContent).join(" | "));
  [...out.querySelectorAll(".mention-head")].forEach(click);
  await sleep(250);
  const liSids = [...out.querySelectorAll(".sentence")].map((n) => n.getAttribute("data-sid"));
  ok("展开后句数＝去重句数 " + eLi.os + "（重复句没排两遍）", liSids.length === eLi.os,
     "句 " + liSids.length);
  ok("句 id 无重复", new Set(liSids).size === liSids.length, liSids.join(" , "));
  const dupNode = out.querySelectorAll('.sentence[data-sid="sj-001-0021-007"]');
  ok("重复提到的那句只渲染一次", dupNode.length === 1, "找到 " + dupNode.length + " 个同名节点");
  ok("句内两处仍各自高亮（只去重句子，不去重标记）",
     dupNode.length === 1 && dupNode[0].querySelectorAll("mark").length === 2,
     dupNode.length ? dupNode[0].querySelectorAll("mark").length + " 处高亮" : "未找到该句");

  // 殷：专篇（殷本紀/周本紀/三代世表…）之外的处数/句数，一律现算
  const yinP = placeByName("殷");
  const eYin = expPlace(yinP.id);
  await doSearch("殷");
  if (out.querySelector(".candidate")) { click(out.querySelector('.candidate[data-kind="place"]')); await sleep(150); }
  ok("殷：统计写「" + eYin.text + "」", out.textContent.indexOf(eYin.text) >= 0,
     (out.textContent.match(/其他篇目提及[\s\S]{0,40}/) || [""])[0].replace(/\s+/g, " "));
  const moreTexts = [...out.querySelectorAll(".more")].map((e) => e.textContent);
  ok("「顯示全部」一律報句數（展開的是句子，不是處）",
     moreTexts.length > 0 && moreTexts.every((t) => /顯示全部 [\d,]+ 句/.test(t)),
     moreTexts.slice(0, 3).join(" | ") || "无 more 节点");
  const yinDup = Object.keys(eYin.byCh).filter((cid) => eYin.byCh[cid].om !== eYin.byCh[cid].os)[0];
  const yinCard = yinDup
    ? out.querySelector('.card[data-chapter="' + yinDup + '"] .mention-head .meta') : null;
  ok("同篇「N 處 · M 句」逐篇可见（" + yinDup + " 句内有重复）",
     !!yinCard && yinCard.textContent.indexOf(
       fmt(eYin.byCh[yinDup].om) + " 處 · " + fmt(eYin.byCh[yinDup].os) + " 句") >= 0,
     yinCard ? yinCard.textContent : "未找到 " + yinDup + " 卡片");
  [...out.querySelectorAll(".mention-head")].forEach(click);
  await sleep(500);
  const yinSids = [...out.querySelectorAll(".sentence")].map((n) => n.getAttribute("data-sid"));
  ok("殷：其他篇目共 " + eYin.os + " 句", yinSids.length === eYin.os, "句 " + yinSids.length);
  ok("殷：句 id 无重复", new Set(yinSids).size === yinSids.length,
     "去重后 " + new Set(yinSids).size + " / 共 " + yinSids.length);
  const yinMarks = out.querySelectorAll(".sentence mark").length;
  ok("殷：高亮总数＝" + eYin.om + " 处（处数没被句子去重吃掉）", yinMarks === eYin.om,
     "高亮 " + yinMarks + " 处");

  console.log("\n【9】人名闸门 · 姓氏不作地名");
  /* 「秦嘉」的「秦」是姓，不该标成秦国。它靠的既不是词典（秦嘉不在 388 人里），
     也不是守卫表（那按邻字写，写不完），而是审读过的人名阻断表 NAME_BLOCK。
     这条一旦回归，就会重新把一批姓氏误标成地名——而误标在人看来是"多了几条
     地名"，不像丢字那么显眼，所以必须有断言钉住。 */
  const BOOK = window.BOOK_DATA;
  const leak = [];
  for (const nm of ["秦嘉", "魏齊", "晉鄙", "周市", "雍齒", "鄭安平", "宋昌", "魏勃"]) {
    for (const s of BOOK.sentences) {
      let from = 0;
      for (;;) {
        const i = s.text.indexOf(nm, from);
        if (i < 0) break;
        from = i + 1;
        if ((s.pmarks || []).some((m) => m.s === i && m.e === i + 1)) {
          leak.push(nm + "@" + s.id);
        }
      }
    }
  }
  ok("人名首字不再被标成地名（秦嘉/魏齊/晉鄙…）", leak.length === 0,
     leak.slice(0, 6).join(" , ") + (leak.length > 6 ? " 等 " + leak.length + " 处" : ""));

  // 反向：守卫必须让「国+谥+爵」继续算地名，否则就是过挡（丢真实地名）
  const cao = BOOK.sentences.find((s) => s.text.indexOf("曹襄公") >= 0);
  const caoAt = cao ? cao.text.indexOf("曹襄公") : -1;
  ok("「曹襄公」的「曹」仍算地名（守卫认出这是国+谥+爵）",
     !!cao && (cao.pmarks || []).some((m) => m.s === caoAt && m.e === caoAt + 1),
     cao ? "该句地名标记 " + JSON.stringify(cao.pmarks) : "未找到含「曹襄公」的句子");
  const song = BOOK.sentences.find((s) => s.text.indexOf("宋襄公") >= 0);
  const songAt = song ? song.text.indexOf("宋襄公") : -1;
  const songMarked = !!song && (song.pmarks || []).some((m) => m.s === songAt);
  const songByPerson = !!song && (song.marks || []).some((m) => m.s === songAt);
  ok("「宋襄公」的「宋」未被切断（标注为人名或地名皆可，但不能两不管）",
     songMarked || songByPerson,
     song ? "地名标记 " + JSON.stringify(song.pmarks) + " / 人物标记 " + JSON.stringify(song.marks) : "未找到");

  console.log("\n【10】控制台无异常");
  ok("无 jsdomError", errors.length === 0, errors.slice(0, 3).join(" | "));

  console.log("\n================ 地名层 UI 测试：" + pass + " 通过 / " + fail + " 失败 ================");
  dom.window.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
