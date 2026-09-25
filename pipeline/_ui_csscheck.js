/* 校验新增 CSS 规则确实进了样式表，且没有因括号断裂破坏后续规则。
   DOM 断言查不出 CSS 语法问题（样式坏了元素照样在），所以要单独查一次。 */
const { JSDOM } = require("jsdom");
(async () => {
  const dom = await JSDOM.fromURL(process.env.BASE || "http://127.0.0.1:8770/index.html",
    { runScripts: "dangerously", resources: "usable", pretendToBeVisual: true });
  const w = dom.window, d = w.document;
  await new Promise((r) => w.addEventListener("load", r));
  const sheets = [...d.styleSheets];
  let rules = [];
  for (const s of sheets) {
    try { rules = rules.concat([...s.cssRules].map((r) => r.cssText)); }
    catch (e) { console.log("读取失败:", e.message); }
  }
  console.log("样式表 " + sheets.length + " 个 / 规则 " + rules.length + " 条");
  const need = [
    [".approx", "地名单字弱标记（青碧虚线）"],
    [".char-place", "索引面板单字地名"],
    ["span.land", "快捷词地名分色"],
    [".sep", "快捷词分隔线"],
    ["--place", "地名色变量"],
    [".guess", "人物弱标记（应仍在，未被覆盖）"],
    ["text-align: justify", "阅读正文两端对齐"],
    [".reader-body .annot", "裴注/夹注分色分号"],
    [".reader-body .fn-mark", "脚注标记分色分号"],
    [".reader-body p.fn", "整段脚注样式"],
  ];
  let bad = 0;
  for (const [sel, desc] of need) {
    const hit = rules.some((r) => r.indexOf(sel) >= 0);
    console.log((hit ? "  ✓ " : "  ✗ ") + sel + "  " + desc);
    if (!hit) bad++;
  }
  // 关键：文件尾部的 @media 还在 → 中间新增的规则没造成括号断裂
  const tail = rules.some((r) => r.indexOf("@media") >= 0 && r.indexOf("640px") >= 0);
  console.log((tail ? "  ✓ " : "  ✗ ") + " 尾部 @media(640px) 仍在（无括号断裂）");
  if (!tail) bad++;
  console.log("标签页: " + [...d.querySelectorAll(".tabs span")].map((e) => e.textContent).join(" / "));
  // 人物/地名两类弱标记的配色是否真的不同
  const guess = rules.filter((r) => r.indexOf(".guess") >= 0).join(" ");
  const approx = rules.filter((r) => r.indexOf(".approx") >= 0).join(" ");
  const diff = guess.indexOf("--accent") >= 0 && approx.indexOf("--place") >= 0;
  console.log((diff ? "  ✓ " : "  ✗ ") + " 两类弱标记配色不同（guess=赭石 / approx=青碧）");
  if (!diff) bad++;
  dom.window.close();
  process.exit(bad ? 1 : 0);
})();
