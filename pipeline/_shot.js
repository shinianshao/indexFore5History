// 用 playwright-core 驱动系统已装的 Chrome，给本地网页工具截图（不下载浏览器）。
// 运行：NODE_PATH=<workspace>/node_modules node pipeline/_shot.js
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
    viewport: { width: 1400, height: 1020 },
    deviceScaleFactor: 2,
  });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));

  await page.goto(URL, { waitUntil: "load" });
  await page.waitForTimeout(700);

  // 1) 检索「項羽」→ 人物页（整篇讲述 + 其他篇目提及）
  await page.fill("#q", "項羽");
  await page.click("#btn");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "01-xiangyu.png") });

  // 2) 完整称谓表——用劉邦做范例：本名「劉邦」全书 0 次，
  //    实际写作 高祖/髙祖(302)、沛公、漢王、劉季，最能体现"别名归一"
  await page.fill("#q", "劉邦");
  await page.click("#btn");
  await page.waitForTimeout(800);
  await page.evaluate(() => {
    const el = document.querySelector(".alias-groups");
    if (el) el.scrollIntoView({ block: "center" });
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, "02-alias-table.png") });

  // 3) 人物索引（388 人，按提及次数排序）
  await page.click('.tabs span[data-tab="persons"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "03-persons-index.png") });

  // 4) 地名索引（281 地，按 国/郡/县/关/山/川/湖/域/外 分组；单字国名青碧标记）
  await page.click('.tabs span[data-tab="places"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "04-places-index.png") });

  // 5) 篇目一览（130 篇，按 本纪/世家/列传/表/书 分组，标注主人公）
  await page.click('.tabs span[data-tab="chapters"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "05-chapters.png") });

  // 6) 读全篇：回检索结果，点「整篇讲述」的篇名 → 打开原文浮层（别名高亮）
  await page.click('.tabs span[data-tab="search"]');
  await page.waitForTimeout(400);
  await page.fill("#q", "項羽");
  await page.click("#btn");
  await page.waitForTimeout(800);
  const row = await page.$(".primary-row");
  if (row) {
    await row.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(OUT, "06-reader.png") });
  }

  // 7) 搜「鍾離眛」——本轮刚修好的那个人
  await page.evaluate(() => {
    const r = document.getElementById("reader");
    if (r) r.classList.remove("on");
  });
  await page.waitForTimeout(200);
  await page.fill("#q", "鍾離眛");
  await page.click("#btn");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "07-zhonglimo.png") });

  // 8) 搜「即墨」——地名页会把异写「卽墨」折进同一行（本轮修复的归并键效果）
  await page.fill("#q", "即墨");
  await page.click("#btn");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "08-jimo.png") });

  await browser.close();
  console.log("pageerrors: " + errs.length + (errs.length ? "\n" + errs.join("\n") : ""));
  console.log("shots -> " + OUT);
}

main().catch((e) => {
  console.error("FAILED: " + e);
  process.exit(1);
});
