// 晋书 R5 截图：人物 / 载记篇目 / 读全篇
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

  // 1) 王导
  await page.fill("#q", "王導");
  await page.click("#btn");
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "50-js-wangdao.png") });

  // 2) 谢安
  await page.fill("#q", "謝安");
  await page.click("#btn");
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "51-js-xiean.png") });

  // 3) 篇目一览（含載記）
  const chapTab = await page.$('.tabs span[data-tab="chapters"]');
  if (chapTab) {
    await chapTab.click();
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(OUT, "52-js-chapters.png") });
  }

  // 4) 读全篇·載記
  const zaiki = await page.$('.chap-row[data-chapter="js-123"]');
  if (zaiki) {
    await zaiki.click();
    await page.waitForTimeout(1100);
    await page.screenshot({ path: path.join(OUT, "53-js-zaiki-reader.png") });
    await page.evaluate(() => {
      const r = document.getElementById("reader");
      if (r) r.classList.remove("on");
    });
  }

  // 5) 五书胶囊
  await page.screenshot({ path: path.join(OUT, "54-js-books.png") });

  console.log("pageerrors", errs.length, errs.slice(0, 3));
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
