/* 全量渲染扫描：把词典里**每一个**地名与人物都点一遍，逐条校验两件事：
     1. 渲染是否健壮——个别条目字段缺失（aliasList 为空、mainChapters 缺失、
        topPlaces 里的 pid 对不上）会不会崩掉或渲染成空白。抽样测试覆盖不到。
     2. 计数是否诚实——展开后的句数＝去重后的句子数、高亮数＝标记数（处）。
        一句话多次提到同一实体时，句子只该列一次，但「处」不能跟着缩水。
        这两个数分别对应 mentionCount 与「去重句数」，逐个条目对账。
   用法：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules node pipeline/_ui_sweep.js */
const { JSDOM, VirtualConsole } = require("jsdom");

const BASE = process.env.BASE || "http://127.0.0.1:8770/index.html";

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
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const num = (n) => Number(n).toLocaleString();

  await new Promise((r) => window.addEventListener("load", r));
  await sleep(500);

  const D = window.BOOK_DATA;
  const out = doc.getElementById("out");
  const q = doc.getElementById("q");

  /* ---- 先算「标准答案」：每个实体在专篇之外的处数(om)与句数(os) ---- */
  const mainPerson = {};
  D.chapters.forEach((c) => (c.mainPersons || []).forEach((pid) => {
    (mainPerson[pid] = mainPerson[pid] || new Set()).add(c.id);
  }));
  const mainPlace = {};
  D.places.forEach((p) => {
    mainPlace[p.id] = new Set((p.mainChapters || []).map((r) => r.cid));
  });

  const exp = {};
  const bump = (id, isMain, n) => {
    const e = exp[id] = exp[id] || { om: 0, os: 0 };
    if (!isMain) { e.om += n; e.os += 1; }
  };
  D.sentences.forEach((s) => {
    // 同句同实体多标要先归并成「一句 n 处」，否则 os 会被重复计
    const byP = {}, byL = {};
    (s.marks || []).forEach((m) => { byP[m.pid] = (byP[m.pid] || 0) + 1; });
    (s.pmarks || []).forEach((m) => { byL[m.pid] = (byL[m.pid] || 0) + 1; });
    Object.keys(byP).forEach((pid) => bump(pid, (mainPerson[pid] || new Set()).has(s.chapterId), byP[pid]));
    Object.keys(byL).forEach((pid) => bump(pid, (mainPlace[pid] || new Set()).has(s.chapterId), byL[pid]));
  });

  async function render(word, wantKind, wantId) {
    q.value = word;
    click(doc.getElementById("btn"));
    await sleep(0);                       // 同步渲染，不需要等
    const cand = out.querySelector('.candidate[data-kind="' + wantKind + '"][data-id="' + wantId + '"]');
    if (cand) { click(cand); await sleep(0); }   // 这个词同时对应多人/多地，选准目标
  }

  const problems = [];
  let checked = 0;
  const t0 = Date.now();

  async function audit(kind, list) {
    for (const p of list) {
      await render(p.name, kind, p.id);
      const t = out.textContent.trim();
      const label = (kind === "place" ? "地名 " : "人物 ") + p.name;

      if (!t) { problems.push("空白: " + label); continue; }
      if (t.indexOf("未收錄") >= 0) { problems.push("未收录: " + label); continue; }
      if (kind === "place" && t.indexOf("沒有以該地為主體的專篇") < 0 &&
          t.indexOf("整篇講述") >= 0 && out.querySelectorAll(".primary-row").length === 0) {
        problems.push("有整篇讲述标题却无条目: " + label);
      }
      if (kind === "person" && out.querySelectorAll(".alias-group").length === 0) {
        problems.push("无称谓表: " + label); continue;
      }

      /* 统计行的「处 / 句」必须与数据对账。
         注意这里是**繁体文案**：界面已整体转繁，「處」不是「处」。 */
      const e = exp[p.id] || { om: 0, os: 0 };
      const want = num(e.om) + " 處" + (e.om === e.os ? "" : "（" + num(e.os) + " 句）");
      if (t.indexOf(want) < 0) {
        problems.push("统计口径不符: " + label + " 期望「" + want + "」");
      }

      /* 展开全部卡片：句子数必须＝去重句数，高亮数必须＝处数 */
      [...out.querySelectorAll(".mention-head")].forEach(click);
      await sleep(0);
      const nodes = out.querySelectorAll(".sentence");
      const ids = [...nodes].map((n) => n.getAttribute("data-sid"));
      if (nodes.length !== e.os) {
        problems.push("句数不符: " + label + " 屏上 " + nodes.length + " / 应为 " + e.os);
      }
      if (new Set(ids).size !== ids.length) {
        problems.push("句子重复: " + label + " 共 " + ids.length + " 句，去重后 " +
                      new Set(ids).size + " 句");
      }
      const mk = out.querySelectorAll(".sentence mark").length;
      if (mk !== e.om) {
        problems.push("处数不符: " + label + " 屏上 " + mk + " / 应为 " + e.om);
      }
      checked++;
    }
  }

  await audit("place", D.places);
  await audit("person", D.persons);

  console.log("扫描地名 " + D.places.length + " 个 / 人物 " + D.persons.length + " 个，逐条对账 " +
              checked + " 条，用时 " + ((Date.now() - t0) / 1000).toFixed(1) + "s");
  console.log("异常条目：" + problems.length);
  problems.slice(0, 30).forEach((p) => console.log("  ✗ " + p));
  console.log("运行期错误：" + errors.length);
  errors.slice(0, 5).forEach((e) => console.log("  ✗ " + e));

  dom.window.close();
  process.exit(problems.length || errors.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
