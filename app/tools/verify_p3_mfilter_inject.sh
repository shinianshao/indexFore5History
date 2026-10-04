#!/usr/bin/env bash
# [19] 組（P0-丙 命中數口徑與篩選）的注入驗證。
#
#   故意改壞 → 快速版必須變紅 → 還原 → 必須變綠 → 還原後比對位元組。
#
# 三處注入，各守一種「壞了不報錯」的形態：
#   A. 前端把緊湊陣列的尺換回常量 BOOKS  → 總數不變、每本書的數全錯、不報錯
#   B. 後端不再給 mentionByBook          → 篩選桶與「共 N 處」靜默消失
#   C. 前端把「正文命中 N 處」改回 mentions.length → 聯機又說 200（P0-丙本體）
#
# ⚠️ 三條老規矩（踩過才寫在這裡）：
#   ① 備份只在開頭做一次 —— 在 restore() 裡重備份會「越還原越壞」；
#   ② 注入前先 assert 錨點存在 —— 否則 sed 什麼也沒改，腳本照報「✔ 變紅」；
#   ③ 還原後比對位元組 —— 只看測試綠不算數。
set -u
cd "$(dirname "$0")/../.." || exit 1

PY="${PYTHON:-C:/Users/dell/AppData/Local/Programs/Python/Python312/python.exe}"
RUNNER="pipeline/_scratch/_run_with_tmp.py"
FAST="app/tools/verify_p3_mfilter.py"
APPJS="app/web/app.js"
DBPY="app/server/db.py"
BAK=".tmp_probe/mfilter-inject"

mkdir -p "$BAK"
# ① 備份只在這裡做一次
cp -f "$APPJS" "$BAK/app.js" || exit 1
cp -f "$DBPY"  "$BAK/db.py"  || exit 1
echo "備份 → $BAK/（app.js $(wc -c < "$BAK/app.js") 位元組 / db.py $(wc -c < "$BAK/db.py") 位元組）"

run_fast() {   # 回傳 0=綠 1=紅
  "$PY" "$RUNNER" "$FAST" >"$BAK/last.txt" 2>&1
  local rc=$?
  tail -1 "$BAK/last.txt" | sed 's/^/    /'
  return $rc
}

inject() {     # $1=標籤 $2=檔案 $3=sed 表達式 $4=錨點（正則）
  local tag="$1" f="$2" expr="$3" anchor="$4"
  # ② 錨點必須存在
  #    ⚠️ 一律用 -F（固定字串）：`-E` 會把 `()` `{}` 當成分組/區間，
  #    `mbkCodes();` 這種錨點會被解成 `mbkCodes;` → 永遠匹配不上 →
  #    sed 什麼也沒改，腳本卻報「✔ 變紅」（假綠，比紅還危險）。
  if ! grep -qF "$anchor" "$f"; then
    echo "✗ $tag：錨點『$anchor』不在 $f 裡，注入沒落下（別讓這條假裝通過）"
    return 2
  fi
  sed -i "$expr" "$f"
  if ! diff -q "$f" "$BAK/$(basename "$f")" >/dev/null; then
    echo "  · $tag 已注入"
  else
    echo "✗ $tag：sed 沒改動任何東西"
    return 2
  fi
  return 0
}

restore() {    # ③ 只從開頭那份備份還原
  cp -f "$BAK/app.js" "$APPJS"
  cp -f "$BAK/db.py"  "$DBPY"
}

FAILED=0
expect() {     # $1=標籤 $2=期望（red|green）
  local tag="$1" want="$2"
  if run_fast; then got="green"; else got="red"; fi
  if [ "$want" = "$got" ]; then
    echo "  ✔ $tag：$got（如預期）"
  else
    echo "  ✗ $tag：期望 $want、實得 $got —— 斷言沒抓住這個壞法"
    grep -E "FAIL|✗" "$BAK/last.txt" | head -5 | sed 's/^/      /'
    FAILED=1
  fi
}

echo
echo "── A. 前端的尺換回常量 BOOKS（書序錯位：總數不變、每本全錯）──"
inject "A" "$APPJS" \
  's/mbkCodes()/BOOKS.map(function (b2) { return b2.code; })/' \
  'var o = {}, cs = mbkCodes();' && expect "A" red
restore

echo
echo "── B. 後端不再給 mentionByBook（篩選桶靜默消失）──"
inject "B" "$DBPY" \
  's/^        "mentionByBook": mention_by_book(pid),$/        # INJECTED-REMOVED/' \
  '"mentionByBook": mention_by_book(pid),' && expect "B" red
restore

echo
echo "── C. 前端「正文命中 N 處」改回 mentions.length（P0-丙本體）──"
inject "C" "$APPJS" \
  's/notesSection(pid, d\.notes || {}, mbSelected(d))/notesSection(pid, d.notes || {}, (d.mentions || []).length)/' \
  'notesSection(pid, d.notes || {}, mbSelected(d))' && expect "C" red
restore

echo
echo "── 還原後必須全綠 ──"
expect "還原" green

echo
echo "── 還原後比對位元組 ──"
for f in "$APPJS:$BAK/app.js" "$DBPY:$BAK/db.py"; do
  a="${f%%:*}"; b="${f##*:}"
  if cmp -s "$a" "$b"; then echo "  ✔ $(basename "$a") 與備份一致"
  else echo "  ✗ $(basename "$a") 沒還原乾淨"; FAILED=1; fi
done

echo
[ "$FAILED" -eq 0 ] && echo "注入驗證通過：三種壞法都變紅、還原後變綠且位元組一致" \
                    || echo "注入驗證失敗"
exit $FAILED
