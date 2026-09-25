// 多书界面的截图：书选择器 + 单书检索 + 多书合检。
// 运行：NODE_PATH=<workspace>/node_modules node pipeline/_shot_books.js
const { chromium } = require("playwright-core");
const path = require("path");
const fs = require("fs");

const OUT = process.env.SHOT_OUT || path.join(__dirname, "..", "shots");
const URL = process.env.SHOT_URL || "http://127.0.0.1:8770/";
const CHROME = process.env.SHOT_CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1080 },
    deviceScaleFactor: 2,
  });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));

  await page.goto(URL, { waitUntil: "load" });
  await page.waitForTimeout(800);

  // 1) 默认＝多书合检，书选择器在最上面
  await page.screenshot({ path: path.join(OUT, "10-books-multi.png") });

  // 2) 多书合检下的篇目一覽：按书分节
  await page.click('.tabs span[data-tab="chapters"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "11-books-chapters.png") });

  // 3) 只选《汉书》：条目列表与计数都收缩到这一本
  await page.click('#books .bk[data-book="sj"]');
  await page.waitForTimeout(500);
  await page.click('.tabs span[data-tab="search"]');
  await page.waitForTimeout(300);
  await page.fill("#q", "蘇武");
  await page.click("#btn");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "12-books-han-only.png") });

  // 4) 回到多书合检看人物索引（条目数从 793 变回 911）
  await page.click("#books .bk.all");
  await page.waitForTimeout(500);
  await page.click('.tabs span[data-tab="persons"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "13-books-persons-multi.png") });

  await browser.close();
  console.log("pageerrors: " + errs.length + (errs.length ? "\n" + errs.join("\n") : ""));
  console.log("shots -> " + OUT);
}

main().catch((e) => {
  console.error("FAILED: " + e);
  process.exit(1);
});
