// 三国志 R5 截图：人物 / 地名 / 篇目 / 读全篇
const { chromium } = require("playwright-core");
const path = require("path");
const fs = require("fs");

const OUT = process.env.SHOT_OUT || path.join(__dirname, "..", "shots");
const URL = process.env.SHOT_URL || "http://127.0.0.1:8770/";
const CHROME =
  process.env.SHOT_CHROME ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1020 },
    deviceScaleFactor: 2,
  });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));

  await page.goto(URL, { waitUntil: "load" });
  await page.waitForTimeout(800);

  // 1) 诸葛亮（三国志核心人物）
  await page.fill("#q", "諸葛亮");
  await page.click("#btn");
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "40-sgz-zhuge.png") });

  // 2) 读全篇（整篇讲述优先点）
  const row = await page.$(".primary-row");
  if (row) {
    await row.click();
    await page.waitForTimeout(1100);
    await page.screenshot({ path: path.join(OUT, "41-sgz-reader.png") });
    await page.evaluate(() => {
      const r = document.getElementById("reader");
      if (r) r.classList.remove("on");
    });
    await page.waitForTimeout(300);
  }

  // 3) 地名索引（含章安/临海一类）
  await page.click('.tabs span[data-tab="places"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "42-sgz-places.png") });

  // 4) 篇目一览（四书分节）
  await page.click('.tabs span[data-tab="chapters"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "43-sgz-chapters.png") });

  // 5) 多书合检下搜 刘备
  await page.click('.tabs span[data-tab="search"]');
  await page.waitForTimeout(300);
  await page.fill("#q", "劉備");
  await page.click("#btn");
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "44-sgz-liubei.png") });

  console.log("pageerrors", errs.length, errs.slice(0, 3));
  console.log("shots →", OUT);
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
