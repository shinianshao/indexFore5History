/* 无头 UI 自测 · 关系图（P6-3）：用 jsdom 打开本地服务页面，验证
     1. 关系卡片里**真的画出了 SVG**（不是空字符串、不是报错）
     2. 无证据的边画成 weak（虚线）、有证据的边是实线且带 uid + 篇 id
     3. 页面没有 JS 报错
   用法（依赖 jsdom，装在隔离目录里，不污染本工程）：
     1) 起服务：PORT=8800 python app/server/main.py
     2) 跑测试：NODE_PATH=<workbuddy>/binaries/node/workspace/node_modules \
                 node pipeline/_ui_test_rel.js
   为什么要有它：renderGraph 是纯字符串拼接，拼错了页面上是**一片空白**，
   控制台也不一定报错——只有真跑一遍 DOM 才知道有没有渲染出来。 */
const { JSDOM, VirtualConsole } = require("jsdom");

const BASE = process.env.BASE || "http://127.0.0.1:8800/";
// 有证据的关系（P6-3 自动取证落的那批），用它验证「实线 + 可跳原文」
const WITH_EV = process.env.WITH_EV || "p_qin_huiwang";
let pass = 0, fail = 0;

function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + name); }
  else { fail++; console.log("  ✗ " + name + (extra ? "  → " + extra : "")); }
}

async function boot() {
  const vc = new VirtualConsole();
  const errs = [];
  vc.on("jsdomError", (e) => errs.push(String(e.message)));
  vc.on("error", (m) => errs.push(String(m)));
  const dom = await JSDOM.fromURL(BASE, {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    virtualConsole: vc,
    // jsdom 不带 fetch，而 app.js 全程靠它取数——必须在脚本执行**之前**塞进去
    beforeParse(w) { w.fetch = (u, o) => fetch(new URL(u, BASE), o); },
  });
  return { dom, errs };
}

async function waitFor(dom, fn, ms = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (fn(dom.window.document)) return true;
    await new Promise((r) => setTimeout(r, 120));
  }
  return false;
}

(async () => {
  console.log("=== 关系图 UI 冒烟（P6-3）===");
  const { dom, errs } = await boot();
  const doc = dom.window.document;

  // 首屏是搜索结果页（没有关系卡片），要先点进一个人物页
  await dom.window.eval("location.hash = '#/person/p_liubang'");
  const got = await waitFor(dom, (d) => d.querySelector(".rel-list"));
  ok("人物页渲染出关系列表", got);
  let svg = doc.querySelector("svg.rel-svg");
  ok("画出关系图 SVG", !!svg);
  if (svg) {
    const edges = svg.querySelectorAll(".rel-edge");
    ok("图里有节点", svg.querySelectorAll(".rel-node").length >= 2,
      svg.querySelectorAll(".rel-node").length + " 个");
    ok("图里有边", edges.length >= 1, edges.length + " 条");
    ok("中心节点标了 is-center", !!svg.querySelector(".rel-node.is-center"));
    // ⚠️ 别写成「所有边都是 weak」：那等于假设刘邦**一条证据都没有**，
    // 补证据之后他有三条实线边，断言就红了（2026-10-01 踩到）。
    // 真正要断的是**没有证据的边必须画虚线**——有没有 uid 就是有没有证据。
    ok("无证据的边一律画成 weak（虚线）",
      edges.length > 0 &&
      [...edges].every((e) => e.classList.contains("weak") ||
        !!e.getAttribute("data-uid")));
    const weakN = [...edges].filter((e) => e.classList.contains("weak")).length;
    if (weakN && weakN < edges.length) {
      ok("虚实线并存时，实线都带证据 uid（不会指到空句）",
        [...edges].filter((e) => !e.classList.contains("weak"))
          .every((e) => !!e.getAttribute("data-uid")));
    }
    const vb = svg.getAttribute("viewBox");
    ok("viewBox 有尺寸（不会塌成 0 高）", /^0 0 \d+ \d+$/.test(vb || ""), vb);
  }

  // 换到有证据的那个人：出现实线，且带上证据 uid 与篇 id（点一下能跳原文）
  await dom.window.eval("location.hash = '#/person/" + WITH_EV + "'");
  const got2 = await waitFor(dom, (d) => {
    const s = d.querySelector("svg.rel-svg");
    return !!s && !!s.querySelector(".rel-edge:not(.weak)");
  });
  ok("有证据的边不是 weak（实线）", got2);
  svg = doc.querySelector("svg.rel-svg");
  const strong = svg && svg.querySelector(".rel-edge:not(.weak)");
  if (strong) {
    ok("实线带证据 uid 与篇 id（点一下能跳原文）",
      !!strong.getAttribute("data-uid") && !!strong.getAttribute("data-chapter"),
      strong.getAttribute("data-uid") + " @ " + strong.getAttribute("data-chapter"));
  } else {
    ok("实线带证据 uid 与篇 id（点一下能跳原文）", false, "没找到实线边");
  }
  ok("页面没有 JS 报错", errs.length === 0, errs[0] || "");

  console.log("\n  " + pass + "/" + (pass + fail) + " 通过");
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error("测试异常：", e.message);
  process.exit(1);
});
