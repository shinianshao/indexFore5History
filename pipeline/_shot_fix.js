/* 验证本轮三处误标修复在界面上的实际效果：
   ① 桀：单书选《史記》应只剩夏桀（约 53 处），不再出现「豪桀／上官桀」等
   ② 老子：不再出现「父老子弟」
   ③ 韓王：战国篇（秦本紀/秦始皇本紀/老子韓非列傳）不再显示韩王信
   ④ 鄭袖：新补条目可检索            */
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const ROOT = "C:\\Users\\dell\\WorkBuddy\\WeChatAPP-BOOKINDEX";
const OUT = path.join(ROOT, "shots");
const BASE = "http://127.0.0.1:8770/index.html";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const html = await (await fetch(BASE)).text();
  const dom = new JSDOM(html, {
    url: BASE,
    runScripts: "dangerously",
    resources: "usable",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  await new Promise((r) => window.addEventListener("load", r));
  await sleep(900);
  const doc = window.document;
  const out = doc.getElementById("out");
  const q = doc.getElementById("q");

  async function search(word) {
    q.value = word;
    q.dispatchEvent(new window.Event("input", { bubbles: true }));
    await sleep(60);
    const form = q.closest("form") || doc.querySelector(".searchbar");
    const btn = doc.querySelector(".searchbar button");
    if (btn) btn.click();
    else form.dispatchEvent(new window.Event("submit", { bubbles: true }));
    await sleep(420);
  }

  function report(label) {
    const cand = [...out.querySelectorAll(".candidate")].map((n) =>
      n.textContent.replace(/\s+/g, " ").trim());
    const heads = [...out.querySelectorAll(".group-title")].map((n) =>
      n.textContent.replace(/\s+/g, " ").trim());
    console.log("\n【" + label + "】");
    console.log("  候选：" + (cand.length ? JSON.stringify(cand) : "（唯一命中，直接进详情）"));
    if (heads.length) console.log("  详情：" + JSON.stringify(heads));
    const note = doc.getElementById("note");
    if (note && note.textContent.trim()) {
      console.log("  统计：" + note.textContent.replace(/\s+/g, " ").trim().slice(0, 160));
    }
  }

  // 只看《史記》
  const books = [...doc.querySelectorAll("#books .bk")];
  console.log("书选择器按钮：" + books.map((b) => b.textContent.trim()).join(" | "));
  const sjBtn = books.find((b) => b.textContent.indexOf("史記") >= 0);
  const hsBtn = books.find((b) => b.textContent.indexOf("漢書") >= 0);
  if (sjBtn && hsBtn) {
    hsBtn.click(); await sleep(200);      // 取消漢書
    console.log("已切换为只看《史記》");
  }

  await search("桀");
  report("桀 · 只看史記");

  await search("老子");
  report("老子 · 只看史記");

  await search("韓王信");
  report("韓王信 · 只看史記");

  await search("鄭袖");
  report("鄭袖 · 只看史記");

  // 恢复双书，看《漢書》侧的桀
  if (hsBtn) { hsBtn.click(); await sleep(200); }
  if (sjBtn) { sjBtn.click(); await sleep(200); }
  if (sjBtn) { sjBtn.click(); await sleep(200); }
  await search("桀");
  report("桀 · 只看漢書");

  await search("韓王");
  report("韓王 · 只選單書（看候選提示）");

  fs.mkdirSync(OUT, { recursive: true });
  await search("桀");
  fs.writeFileSync(path.join(OUT, "30-fix-jie.html"),
    "<pre style='font:13px/1.7 monospace;padding:16px'>" +
    out.textContent.replace(/</g, "&lt;") + "</pre>");
  console.log("\n明细已写入 shots/30-fix-jie.html");
  dom.window.close();
})().catch((e) => { console.error("异常", e); process.exit(1); });
