// 验证《地理志》郡县补录后的检索：以「回浦」为例。
// 运行：NODE_PATH=<workspace>/node_modules node pipeline/_shot_huipu.js
const { chromium } = require("playwright-core");
const path = require("path");
const fs = require("fs");

const OUT = process.env.SHOT_OUT || path.join(__dirname, "..", "shots");
const URL = process.env.SHOT_URL || "http://127.0.0.1:8770/";
const CHROME = process.env.SHOT_CHROME ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1000 },
    deviceScaleFactor: 2,
  });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));
  await page.goto(URL, { waitUntil: "load" });
  await page.waitForTimeout(900);

  async function search(q) {
    await page.fill("#q", q);
    await page.click("#btn");
    await page.waitForTimeout(700);
  }

  // 1) 多书合检搜「回浦」
  await search("回浦");
  await page.screenshot({ path: path.join(OUT, "20-huipu-multi.png") });
  const cand = await page.$$eval(".candidate", (ns) =>
    ns.map((n) => n.textContent.replace(/\s+/g, " ").trim()));
  const outText = await page.$eval("#out", (n) =>
    n.textContent.replace(/\s+/g, " ").trim());
  console.log("【多书合检】候选：", JSON.stringify(cand));
  console.log("【多书合检】结果：", outText.slice(0, 260));
  if (cand.length) {
    await page.click('.candidate[data-kind="place"]');
    await page.waitForTimeout(700);
    const head = await page.$eval("#out", (n) =>
      n.textContent.replace(/\s+/g, " ").slice(0, 400));
    console.log("【详情】", head);
    const marks = await page.$$eval("#out .sentence mark", (ns) =>
      ns.map((n) => n.textContent));
    console.log("【高亮】", JSON.stringify(marks));
    await page.screenshot({ path: path.join(OUT, "21-huipu-detail.png") });
  }

  // 2) 只选《史记》：回浦不应出现
  await page.click('#books .bk[data-book="hs"]');
  await page.waitForTimeout(400);
  await search("回浦");
  const sjOnly = await page.$eval("#out", (n) =>
    n.textContent.replace(/\s+/g, " ").slice(0, 200));
  console.log("【只选史记】", sjOnly);
  await page.screenshot({ path: path.join(OUT, "22-huipu-sj-only.png") });

  // 3) 只选《汉书》：回浦应出现
  await page.click('#books .bk[data-book="sj"]');
  await page.waitForTimeout(300);
  await page.click('#books .bk[data-book="hs"]');
  await page.waitForTimeout(400);
  await search("回浦");
  const hsOnly = await page.$eval("#out", (n) =>
    n.textContent.replace(/\s+/g, " ").slice(0, 300));
  console.log("【只选汉书】", hsOnly);
  await page.screenshot({ path: path.join(OUT, "23-huipu-hs-only.png") });

  // 4) 地名索引条目数
  await page.click('#books .bk.all');
  await page.waitForTimeout(400);
  await page.click('.tabs span[data-tab="places"]');
  await page.waitForTimeout(900);
  const cnt = await page.$eval("#out", (n) =>
    (n.textContent.match(/[\d,]+/) || [""])[0]);
  console.log("【地名索引】首屏数字：", cnt);
  await page.screenshot({ path: path.join(OUT, "24-places-index.png") });

  console.log("页面异常：", errs.length ? errs : "无");
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
