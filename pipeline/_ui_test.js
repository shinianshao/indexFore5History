/* 无头 UI 自测：用 jsdom 打开本地页面，模拟点击，验证
     1. 人物页的「全部称谓」表
     2. 读全篇（曾经因为 moreNode 被移除后空指针，根本打不开）
     3. 只看与 TA 有关的段落 / 一次显示全部
     4. 从原句跳进正文并定位到目标段
   用法（依赖 jsdom，装在隔离目录里，不污染本工程）：
     1) 起服务：cd web && python -m http.server 8770 --bind 127.0.0.1
     2) 跑测试：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules node pipeline/_ui_test.js
   为什么要有它：读全篇曾经因为「moreNode 渲染完被移除后仍去 addEventListener」
   直接抛空指针，阅读器整个打不开——这类错误浏览器控制台才看得到，
   用无头 DOM 跑一遍就能在提交前发现。 */
const fs = require("fs");
const path = require("path");
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

  await new Promise((r) => window.addEventListener("load", r));
  await sleep(400);

  const out = doc.getElementById("out");

  console.log("\n【1】人物页 · 全部称谓");
  ok("默认渲染刘邦（界面已繁体，断言繁体名）", out.textContent.indexOf("劉邦") >= 0);
  const groups = out.querySelectorAll(".alias-group");
  const kinds = [...out.querySelectorAll(".alias-group .kind")].map((e) => e.textContent);
  ok("称谓表已分组渲染", groups.length >= 3, "组数 " + groups.length);
  ok("含本名/职衔/其他等分组", kinds.join(",").indexOf("本名") >= 0 && kinds.join(",").indexOf("職銜") >= 0,
     kinds.join("|"));
  const chips = [...out.querySelectorAll(".chip")].map((e) => e.textContent);
  ok("刘邦称谓不少于 7 条", chips.length >= 7, chips.length + "：" + chips.join(" "));
  ok("显示出现次数", chips.some((c) => /×\d/.test(c)), chips.join(" "));
  ok("标出「未用」的写法（词收录了，当前选中的书没这么写）",
     chips.some((c) => c.indexOf("未用") >= 0), chips.join(" "));
  ok("已移除只显示 6 条的旧版「原文中写作」", out.querySelectorAll(".alias-item").length === 0);

  console.log("\n【2】泛称人物的称谓表与归属依据");
  const q = doc.getElementById("q");
  q.value = "刘恒";
  click(doc.getElementById("btn"));
  await sleep(60);
  const gen = [...out.querySelectorAll(".chip.gen")].map((e) => e.textContent);
  ok("刘恒的泛称称号「代王」带泛称样式", gen.some((t) => t.indexOf("代王") >= 0), gen.join(" "));
  ok("有泛称归属依据栏", out.textContent.indexOf("泛稱稱號歸屬依據") >= 0);
  ok("依据写明分级（本篇主人公等）", /本篇主人公|同段共现|本篇共现|同句共现/.test(out.textContent));

  console.log("\n【3】读全篇 · 从「整篇讲述」进入");
  const prows = out.querySelectorAll(".primary-row");
  ok("有整篇讲述条目", prows.length > 0, prows.length + " 条");
  click(prows[0]);
  await sleep(600);
  const reader = doc.getElementById("reader");
  ok("阅读器已打开（旧版在这里空指针导致打不开）", reader.classList.contains("on"));
  const rbody = doc.getElementById("readerBody");
  ok("正文已渲染", rbody.querySelectorAll("p").length > 0, rbody.querySelectorAll("p").length + " 段");
  ok("标题含篇名", doc.getElementById("readerTitle").textContent.length > 4,
     doc.getElementById("readerTitle").textContent.slice(0, 40));
  ok("正文有高亮标记", rbody.querySelectorAll("mark").length > 0,
     rbody.querySelectorAll("mark").length + " 个");
  ok("运行时无脚本错误", errors.length === 0, errors.slice(0, 2).join(" | "));

  console.log("\n【3b】注文分色 + 两端对齐");
  const gcs = (el) => window.getComputedStyle(el);
  const pStyle = rbody.querySelector("p");
  ok("正文段 text-align 含 justify",
     pStyle && gcs(pStyle).textAlign === "justify",
     pStyle ? gcs(pStyle).textAlign : "无段落");
  // 打开一卷含裴注/脚注的正文（sgz 或 hhs）
  q.value = "诸葛亮";
  click(doc.getElementById("btn"));
  await sleep(60);
  const zglPrimary = out.querySelector(".primary-row");
  if (zglPrimary) {
    click(zglPrimary);
    await sleep(600);
    const annotN = rbody.querySelectorAll("span.annot").length;
    const fnN = rbody.querySelectorAll("span.fn-mark").length + rbody.querySelectorAll("p.fn").length;
    ok("裴注/夹注 span.annot 或脚注样式存在", annotN + fnN > 0,
       "annot=" + annotN + " fn=" + fnN);
    const ps2 = rbody.querySelector("p");
    ok("诸葛亮篇正文仍两端对齐",
       ps2 && gcs(ps2).textAlign === "justify",
       ps2 ? gcs(ps2).textAlign : "无");
    click(doc.querySelector('#readerTools [data-act="close"]'));
    await sleep(30);
  }

  console.log("\n【3c】裴注人物索引（独立）");
  q.value = "刘备";
  click(doc.getElementById("btn"));
  await sleep(80);
  // 简繁：搜简体应命中劉備
  const lrow = out.querySelector(".primary-row") || out.querySelector(".candidate .name");
  if (lrow) {
    click(lrow);
    await sleep(400);
  } else {
    // 直接搜繁体
    q.value = "劉備";
    click(doc.getElementById("btn"));
    await sleep(80);
    const l2 = out.querySelector(".primary-row") || out.querySelector(".candidate .name");
    if (l2) { click(l2); await sleep(400); }
  }
  const peiHead = [...out.querySelectorAll(".group-title")]
    .find((e) => e.textContent.indexOf("裴松之注") >= 0);
  ok("人物页出现「三國志裴松之注」分组（有命中时）", !!peiHead,
     peiHead ? peiHead.textContent.slice(0, 60) : "未找到；PEI_DATA=" +
       (typeof window.PEI_DATA));
  if (peiHead) {
    ok("裴注分组写明已计入合计",
       peiHead.textContent.indexOf("已計入") >= 0 ||
       peiHead.textContent.indexOf("裴N") >= 0 ||
       peiHead.textContent.indexOf("合計") >= 0,
       peiHead.textContent.slice(0, 80));
    // 后续 card 至少有分篇行
    const after = peiHead.nextElementSibling;
    ok("裴注分组下有内容卡片", !!after && after.classList.contains("card"),
       after ? after.className : "无");
  }
  ok("PEI_DATA 已加载且 mentionCount>0",
     window.PEI_DATA && (window.PEI_DATA.meta.mentionCount | 0) > 0,
     window.PEI_DATA ? window.PEI_DATA.meta.mentionCount : "missing");

  console.log("\n【4】只看与 TA 有关的段落");
  const filterBtn = doc.querySelector('#readerTools [data-act="filter"]');
  ok("存在筛选按钮", !!filterBtn);
  ok("默认是全文（按钮未激活）", filterBtn && !filterBtn.classList.contains("on"));
  if (filterBtn) {
    const before = rbody.querySelectorAll("p").length;
    click(filterBtn);
    await sleep(60);
    const after = rbody.querySelectorAll("p").length;
    ok("筛选后段落变少", after < before, before + " → " + after);
    ok("筛选态按钮高亮", doc.querySelector('#readerTools [data-act="filter"]').classList.contains("on"));
    click(doc.querySelector('#readerTools [data-act="filter"]'));
    await sleep(60);
    ok("可切回全文", rbody.querySelectorAll("p").length === before);
  }

  console.log("\n【5】关闭阅读器");
  click(doc.querySelector('#readerTools [data-act="close"]'));
  await sleep(30);
  ok("已关闭", !reader.classList.contains("on"));

  console.log("\n【6】从原句跳进正文并定位");
  const sents = out.querySelectorAll(".sentence");
  ok("有原句条目", sents.length > 0);
  const target = sents[0];
  const sid = target.getAttribute("data-sid");
  const wantPara = parseInt(sid.split("-")[2], 10);
  click(target);
  await sleep(600);
  ok("阅读器已打开", reader.classList.contains("on"));
  const marked = rbody.querySelector("p.target");
  ok("定位到目标段", !!marked && parseInt(marked.getAttribute("data-para"), 10) === wantPara,
     "期望 " + wantPara + "，实际 " + (marked ? marked.getAttribute("data-para") : "无"));

  console.log("\n【7】超长篇目（sj-014 十二诸侯年表 3267 段）");
  click(doc.querySelector('#readerTools [data-act="close"]'));
  click(doc.querySelector('.tabs span[data-tab="chapters"]'));
  await sleep(60);
  const big = doc.querySelector('.chap-row[data-chapter="sj-014"]');
  ok("篇目一览里有 sj-014", !!big);
  if (big) {
    click(big);
    await sleep(1200);
    const n = rbody.querySelectorAll("p").length;
    ok("渲染了首批段落", n > 0, n + " 段");
    const more = doc.getElementById("readerMore");
    ok("存在「继续显示余下」", !!more, more ? more.textContent.slice(0, 40) : "无");
    if (more) {
      click(more);
      await sleep(80);
      ok("点击后追加了段落", rbody.querySelectorAll("p").length > n,
         "→ " + rbody.querySelectorAll("p").length);
    }
    const allBtn = doc.querySelector('#readerTools [data-act="all"]');
    ok("存在「一次显示全部」", !!allBtn);
    if (allBtn) {
      click(allBtn);
      await sleep(1500);
      ok("全部段落已展开", rbody.querySelectorAll("p").length === 3267,
         rbody.querySelectorAll("p").length + " 段");
      ok("展开后按钮消失", doc.getElementById("readerMore") === null);
    }
  }

  console.log("\n【8】其他篇目提及卡片上的「读全篇」");
  click(doc.querySelector('#readerTools [data-act="close"]'));
  click(doc.querySelector('.tabs span[data-tab="search"]'));
  await sleep(60);
  q.value = "韩信";
  click(doc.getElementById("btn"));
  await sleep(60);
  const link = out.querySelector(".open-full");
  ok("提及卡片上有读全篇入口", !!link);
  if (link) {
    const cid = link.getAttribute("data-chapter");
    const wantTitle = out.querySelector(".card[data-chapter='" + cid + "'] .mention-head .name").textContent;
    click(link);
    await sleep(600);
    ok("点它确实打开了阅读器", reader.classList.contains("on"));
    ok("打开的是对应篇目", doc.getElementById("readerTitle").textContent.indexOf(wantTitle) >= 0,
       "期望含「" + wantTitle + "」，实际「" +
       doc.getElementById("readerTitle").textContent.slice(0, 30) + "」");
    ok("卡片没被连带展开（各管各的）",
       out.querySelector(".card[data-chapter='" + cid + "'] .body .sentence") !== null);
  }

  console.log("\n【9】「处」与「句」· 句内重复只列一次");
  /* 一句话可以多次提到同一个人（「沛公…沛公」），索引里就是多个标记。
     结果列表按句去重后这句只出现一次，但「处」数不能跟着缩水——
     旧版按句子条数累加，这里显示的数比索引页的 mentionCount 少（刘邦少 88）。
     期望值一律从数据现场算，不写死数字。 */
  if (reader.classList.contains("on")) {
    click(doc.querySelector('#readerTools [data-act="close"]'));
    await sleep(50);
  }
  const D = window.BOOK_DATA;
  const expectOf = (pid) => {
    const primary = new Set();
    D.chapters.forEach((c) => (c.mainPersons || []).forEach((x) => {
      if (x === pid) primary.add(c.id);
    }));
    let om = 0, os = 0;
    D.sentences.forEach((s) => {
      let n = 0;
      (s.marks || []).forEach((m) => { if (m.pid === pid) n++; });
      if (n && !primary.has(s.chapterId)) { om += n; os += 1; }
    });
    // 界面用 toLocaleString 带千分位，期望值也要同口径（两书合计后过千才会暴露）
    const fmt = (n) => n.toLocaleString();
    return { om: om, os: os,
             text: om === os ? fmt(om) + " 處"
                             : fmt(om) + " 處 / " + fmt(os) + " 句",
             bodyText: om === os ? "正文 " + fmt(om) + " 處"
                             : "正文 " + fmt(om) + " 處 / " + fmt(os) + " 句" };
  };
  // 这里刻意用**简体**查询：界面与数据已是繁体，但简体输入必须照样命中，
  // 所以这一组同时是「简繁双向」的回归测试。
  for (const pair of [["刘邦", "p_liubang"], ["韩信", "p_hanxin"]]) {
    const word = pair[0];
    q.value = word;
    click(doc.getElementById("btn"));
    await sleep(80);
    const e = expectOf(pair[1]);
    ok(word + "：统计行含正文处/句「" + e.bodyText + "」（处＝标记数）",
       out.textContent.indexOf(e.bodyText) >= 0,
       (out.textContent.match(/其他篇目提及[\s\S]{0,40}/) || [""])[0].replace(/\s+/g, " "));
    const mt = [...out.querySelectorAll(".more")].map((x) => x.textContent);
    ok(word + "：「显示全部」报句数、不报处数",
       mt.length > 0 && mt.every((t) => t.indexOf("句") >= 0 && t.indexOf("處") < 0),
       mt.slice(0, 2).join(" | ") || "无 more 节点");
    [...out.querySelectorAll(".mention-head")].forEach(click);
    await sleep(350);
    const ids = [...out.querySelectorAll(".sentence")].map((n) => n.getAttribute("data-sid"));
    ok(word + "：展开后 " + e.os + " 句，且无一句重复",
       ids.length === e.os && new Set(ids).size === e.os,
       "共 " + ids.length + " 句 / 去重后 " + new Set(ids).size);
    const mk = out.querySelectorAll(".sentence mark").length;
    ok(word + "：高亮总数＝" + e.om + " 处（处数没被句子去重吃掉）",
       mk === e.om, "高亮 " + mk + " 处");
  }

  /* 繁体化必须同时满足两件事，缺一件就是倒退：
       ① 界面与数据确实是繁体（劉邦／史記／篇目一覽）；
       ② 用户照**简体**或照**正文异体**写法输入，仍然查得到。
     ② 靠两处：别名表里同时保留繁简两套（词典层），
        以及 meta.variants 把查询做一次异体归一（前端 normQuery()）。
     「髙祖」是异体形（髙≠高），词典只收「高祖」——不归一就查不到，
     所以这一条正是 normQuery 的回归测试。 */
  console.log("\n【10】繁体界面 · 简繁双向 · 异体归一");
  const runQuery = async (text) => {
    doc.getElementById("q").value = text;
    click(doc.getElementById("btn"));
    await sleep(90);
    return out.textContent;
  };
  ok("繁体输入命中（劉邦）", (await runQuery("劉邦")).indexOf("劉邦") >= 0);
  ok("简体输入命中同一条目（刘邦 → 劉邦）", (await runQuery("刘邦")).indexOf("劉邦") >= 0);
  ok("正文异体「髙祖」归一后命中（髙 → 高）", (await runQuery("髙祖")).indexOf("劉邦") >= 0);
  ok("正文异体「荆軻」归一后命中（荆 → 荊）", (await runQuery("荆軻")).indexOf("荊軻") >= 0);
  ok("界面文案已繁体（篇目一覽）", doc.body.textContent.indexOf("篇目一覽") >= 0);
  ok("界面无残留简体界面词（篇目一览）", doc.body.textContent.indexOf("篇目一览") < 0);

  console.log("\n【12】索引排序 · 默认按篇数、可切换按次数");
  const extractStats = () =>
    [...out.querySelectorAll(".grid .item")].map((el) => {
      const m = ((el.querySelector(".c") || el).textContent || "")
        .match(/(\d+)\s*篇\s*\/\s*([\d,]+)/);
      return m ? { c: +m[1], n: +(m[2].replace(/,/g, "")) } : null;
    }).filter(Boolean);

  click(doc.querySelector('.tabs span[data-tab="persons"]'));
  await sleep(150);
  const s0 = extractStats();
  ok("人物索引渲染条目", s0.length > 0, s0.length + " 条");
  let okC = true;
  for (let i = 1; i < s0.length; i++) if (s0[i].c > s0[i - 1].c) { okC = false; break; }
  ok("默认按篇数降序", okC, "前 5 篇数：" + s0.slice(0, 5).map((x) => x.c).join(","));
  ok("开关文案为「按提及篇數排序」",
     out.textContent.indexOf("按提及篇數排序") >= 0,
     (out.textContent.match(/按提及[篇次]數排序/) || [""])[0]);
  const tog = out.querySelector(".sort-toggle");
  ok("有排序开关", !!tog, tog ? tog.textContent : "无 .sort-toggle");
  if (tog) {
    click(tog);
    await sleep(150);
    const s1 = extractStats();
    let okN = true;
    for (let i = 1; i < s1.length; i++) if (s1[i].n > s1[i - 1].n) { okN = false; break; }
    ok("切换后按次数降序", okN, "前 5 次数：" + s1.slice(0, 5).map((x) => x.n).join(","));
    ok("开关文案切换为「按提及次數排序」",
       out.textContent.indexOf("按提及次數排序") >= 0);
    click(tog);
    await sleep(150);
    const s2 = extractStats();
    ok("再点切回篇数降序",
       s2.length < 2 || s2[0].c >= s2[1].c, "前 2 篇数：" + s2.slice(0, 2).map((x) => x.c).join(","));
  }

  console.log("\n【11】运行期错误汇总");
  ok("全程无 jsdom 错误", errors.length === 0, errors.slice(0, 3).join(" | "));

  console.log("\n" + "=".repeat(46));
  console.log("通过 " + pass + " / 失败 " + fail);
  dom.window.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error("测试异常:", e); process.exit(2); });
