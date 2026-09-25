// 后汉书页面截图（R5 验收门第 6 条）。自带 http server，跑完即关。
const { chromium } = require("playwright-core");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const OUT = process.env.SHOT_OUT || path.join(__dirname, "..", "shots");
const PORT = 8771;
const CHROME = process.env.SHOT_CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";

function startServer() {
  const p = spawn("python", ["-m", "http.server", String(PORT), "--bind", "127.0.0.1"], {
    cwd: path.join(__dirname, "..", "web"), stdio: "ignore",
  });
  return p;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const srv = startServer();
  await sleep(1200);
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1080 }, deviceScaleFactor: 2 });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));

  try {
    await page.goto("http://127.0.0.1:" + PORT + "/", { waitUntil: "load" });
    await page.waitForTimeout(900);

    // 1) 三书全选（默认）+ 书选择器
    await page.screenshot({ path: path.join(OUT, "30-hhs-books.png") });

    // 注意：书选择器是 toggle，初始已全选 3 本；点 hhs 反而会**取消**后汉书。
    // 所以这里不点书选择器，直接在多书合检下检索后汉书人物。

    // 2) 检索后汉书核心人物「光武帝」（只在后汉书出现）
    await page.fill("#q", "光武帝");
    await page.click("#btn");
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(OUT, "31-hhs-guangwudi.png") });

    // 4) 简体检索「刘邦」命中（简繁双向）
    await page.fill("#q", "刘邦");
    await page.click("#btn");
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(OUT, "32-hhs-simp.png") });

    // 5) 人物索引（默认篇数排序 + 排序开关）
    await page.click('.tabs span[data-tab="persons"]');
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(OUT, "33-hhs-persons.png") });

    // 6) 地名索引（郡国志新县就位）
    await page.click('.tabs span[data-tab="places"]');
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(OUT, "34-hhs-places.png") });

    await browser.close();
    console.log("pageerrors: " + errs.length + (errs.length ? "\n" + errs.join("\n") : ""));
    console.log("shots -> " + OUT);
  } finally {
    try { srv.kill(); } catch (e) { /* ignore */ }
  }
}

main().catch((e) => { console.error("FAILED: " + e); process.exit(1); });
