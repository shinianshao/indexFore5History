#!/usr/bin/env bash
# P0-乙 注入驗證：把 app.js 裡注文的兩個點擊分派刪掉，
# _ui_test_offline.js 必須變紅（那三條新斷言就是為此而加）。
#
# ⚠️ 這裡是**刪代碼**而不是改壞，所以按上下文邊界定位；
#    .open-full 出現在渲染處(noteBlock)與分派處(openChapter)，
#    只按字串 replace(...,1) 會改到渲染處 → 測試一樣綠（元素還在）。
set -u
cd "$(dirname "$0")/../.." || exit 1
PY="C:/Users/dell/AppData/Local/Programs/Python/Python312/python.exe"
NODE="C:/Users/dell/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
export NODE_PATH="C:/Users/dell/.workbuddy/binaries/node/workspace/node_modules"
# ⚠️ 必須設：注入後前端是壞的，waitFor 會等不到而吃滿 60s。
#    離線快照全在記憶體裡，正常是毫秒級，3s 綽綽有餘；不設的話一輪要十幾分鐘。
export BI_UI_TIMEOUT=8000
APP="app/web/app.js"
BAK="C:/Users/dell/AppData/Local/Temp/bi_app_note_bak.js"
# ⚠️ 備份只在最開始做一次。之前 restore() 每次都重備份，結果是
#    「注入1 → 還原（備份被覆蓋成注入1 後的樣子）→ 注入2 → 還原（= 注入1 後的樣子）」
#    ——plEl 分派就此永久丟失，而 trap 還報了「成功」。
#    連續注入時還原必須永遠回到**同一個**原始狀態。
cp "$APP" "$BAK"
restore() { cp "$BAK" "$APP"; "$PY" app/tools/export_static.py >/dev/null 2>&1; }
trap restore EXIT

run() { "$NODE" pipeline/_ui_test_offline.js 2>&1 | grep -E "✗|失败" | tr -d '\r'; }

FAILED=0

# 注入前先確認**錨點真的找得到**。找不到時 Python 會 ValueError 退出、
# 但後面的 run照樣跑、trap 照樣還原、腳本照樣報「✔ 變紅」——
# 等於把「注入沒生效」和「斷言抓到了」混為一談（我第一版就這樣假綠了）。
assert_anchor() { # $1=要刪的起點 $2=要刪的終點
  "$PY" - "$1" "$2" <<'PYEOF'
import io, sys
p = "app/web/app.js"
s = io.open(p, encoding="utf-8").read()
for m in sys.argv[1:]:
    if m not in s:
        print("   ✘ 錨點不存在: " + m[:50]); sys.exit(2)
print("   錨點 OK")
PYEOF
}

echo "=== 注入 1：刪掉 .open-full 分派（「讀全篇」變死按鈕） ==="
assert_anchor '    var ofEl = ev.target.closest' '    var plEl = ev.target.closest' || { FAILED=1; restore; }
"$PY" - <<'PYEOF' || FAILED=1
import io
p = "app/web/app.js"
s = io.open(p, encoding="utf-8").read()
a = s.index('    var ofEl = ev.target.closest')
b = s.index('    var plEl = ev.target.closest', a)
assert b > a, "終點在前，錨點寫反了"
io.open(p, "w", encoding="utf-8").write(s[:a] + s[b:])
print("   已刪", b - a, "字元")
PYEOF
"$PY" app/tools/export_static.py >/dev/null 2>&1
out=$(run)
if echo "$out" | grep -q "✗"; then
  echo "   ✔ 變紅 ✔"; echo "$out" | sed 's/^/      /'
else
  echo "   ✘ 仍是綠（斷言無效）"; FAILED=1
fi
restore

echo
echo "=== 注入 2：刪掉 .pei-line 分派（明細行變死按鈕） ==="
assert_anchor '    var plEl = ev.target.closest' '    var s = ev.target.closest' || { FAILED=1; restore; }
"$PY" - <<'PYEOF' || FAILED=1
import io
p = "app/web/app.js"
s = io.open(p, encoding="utf-8").read()
a = s.index('    var plEl = ev.target.closest')
b = s.index('    var s = ev.target.closest', a)
assert b > a, "終點在前，錨點寫反了"
io.open(p, "w", encoding="utf-8").write(s[:a] + s[b:])
print("   已刪", b - a, "字元")
PYEOF
"$PY" app/tools/export_static.py >/dev/null 2>&1
out=$(run)
if echo "$out" | grep -q "✗"; then
  echo "   ✔ 變紅 ✔"; echo "$out" | sed 's/^/      /'
else
  echo "   ✘ 仍是綠（斷言無效）"; FAILED=1
fi
restore

echo
echo "=== 注入 3：openChapter 不跳段（明細行開篇但不定位） ==="
"$PY" - <<'PYEOF'
import io
p = "app/web/app.js"
s = io.open(p, encoding="utf-8").read()
old = "      if (pseq != null) jumpToPara(Number(pseq));\n"
assert old in s, "找不到 pseq 那行"
io.open(p, "w", encoding="utf-8").write(s.replace(old, "", 1))
print("   已刪跳段那一行")
PYEOF
"$PY" app/tools/export_static.py >/dev/null 2>&1
out=$(run)
if echo "$out" | grep -q "✗"; then
  echo "   ✔ 變紅 ✔"; echo "$out" | sed 's/^/      /'
else
  echo "   ✘ 仍是綠（斷言無效）"; FAILED=1
fi
restore

echo
echo "=== 還原後必須全綠，且**文件真的回到原樣** ==="
out=$(run)
echo "$out" | sed 's/^/      /'
if echo "$out" | grep -q "失败 0"; then echo "✔ 還原後全綠"; else echo "✘ 還原後仍不綠"; FAILED=1; fi
# ⚠️ 測試綠**不足以**證明還原成功——注入若根本沒生效，測試會一直綠。
#   所以要比對字節：dist/app.js 是從app/web/app.js 複製的，兩者必須一致。
if diff <(tr -d '\r' < app/web/app.js) <(tr -d '\r' < dist/app.js) >/dev/null; then
  echo "✔ app/web 與 dist 已一致（確實跑過導出）"
else
  echo "✘ app/web 與 dist 不一致（還原流程有問題）"; FAILED=1
fi
for anchor in 'var ofEl = ev.target.closest' 'var plEl = ev.target.closest' \
              'if (pseq != null) jumpToPara'; do
  if grep -q "$anchor" app/web/app.js; then
    echo "✔ 錨點在: $anchor"
  else
    echo "✘ 錨點丟了: $anchor"; FAILED=1
  fi
done

echo
if [ "$FAILED" = "0" ]; then echo "=== 全部注入驗證通過 ==="; else echo "=== 有注入沒被抓住 ==="; fi
exit $FAILED
