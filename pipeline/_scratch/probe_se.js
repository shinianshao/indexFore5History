/* 临时：用 Node 实测 JS 的 text.slice(s, e) 是否等于 surface。
   Python 侧 100% 成立，但非 BMP 字符会让 JS 偏移（UTF-16 码元 vs 码位）。
   数据从 stdin 读 JSON（可能很大，走文件）。 */
const fs = require("fs");
const rows = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let ok = 0, bad = 0;
const badSamples = [];
let idxDiff = 0;
for (const r of rows) {
  const text = r.text || "", surface = r.surface || "";
  if (r.s == null || r.e == null) { bad++; continue; }
  if (text.slice(r.s, r.e) === surface) ok++;
  else {
    bad++;
    if (badSamples.length < 10) badSamples.push([r.uid, r.s, r.e, surface, text.slice(r.s, r.e)]);
  }
  if (text.indexOf(surface) !== r.s) idxDiff++;
}
console.log("总数", rows.length, "| slice==surface", ok, "| 不等", bad,
            "| indexOf!=s", idxDiff);
for (const s of badSamples) console.log("  BAD", JSON.stringify(s));
