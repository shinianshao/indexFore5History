#!/usr/bin/env bash
# P0-甲 注入驗證：把 app.js 改成三種壞寫法，每種都必須讓 verify_p3_mark 變紅。
# 判據是「故意注入错误，断言必须变红」——不验这一步，
# 上面那 7 条 OK 说明不了任何事（恒真断言最贵）。
#
# ⚠️ 每次注入都必须**按函数体边界**定位，不能 replace(old,new,1)：
#    app.js 里 indexOf 有多处，那样会改到搜索那几处，注入根本不生效而断言全绿。
set -u
cd "$(dirname "$0")/../.." || exit 1
PY="C:/Users/dell/AppData/Local/Programs/Python/Python312/python.exe"
APP="app/web/app.js"
BAK="C:/Users/dell/AppData/Local/Temp/bi_app_mark_bak.js"
# ⚠️ 備份只做一次（見 verify_p3_note_inject.sh 的同樣教訓）：
#    restore() 裡若重備份，連續注入會「越還原越壞」，最後 trap 還報成功。
cp "$APP" "$BAK"
restore() { cp "$BAK" "$APP"; }
trap restore EXIT

# ⚠️ 要看**全部** FAIL 行，不能 tail -3：核心判据（「落點全對」）必须自己也红，
#    只靠辅助断言红等于没验到点子上（同「宽松选择器恒真」那一类）。
run() { "$PY" app/tools/verify_p3_mark.py 2>&1 | grep -E "FAIL|通過" | tr -d '\r'; }

inject() { # $1=名字 $2=新函数体文件
  "$PY" - "$2" <<'PYEOF'
import sys, io
new = io.open(sys.argv[1], encoding="utf-8").read()
p = "app/web/app.js"
src = io.open(p, encoding="utf-8").read()
a = src.index("  function hitSpan(")
b = src.index("  /* ---------- 渲染：結果列表 ---------- */", a)
io.open(p, "w", encoding="utf-8").write(src[:a] + new + src[b:])
print("   已注入", len(new), "字元")
PYEOF
}

expect_red() { # $1=名字
  out=$(run)
  if echo "$out" | grep -q "FAIL\|0/7\|1/7\|2/7"; then
    echo "   ✔ $1 → 變紅 ✔"
    echo "$out" | sed 's/^/      /'
  else
    echo "   ✘ $1 → **仍是綠**（斷言無效）"
    echo "$out" | sed 's/^/      /'
    FAILED=1
  fi
}

FAILED=0

echo "=== 注入 1：退回 indexOf（審查報告描述的舊寫法，應錯約 8319 條） ==="
cat > /c/Users/dell/AppData/Local/Temp/bi_bad1.jsfrag <<'EOF'
  function hitSpan(text, surface, s, e) {
    text = String(text || "");
    surface = surface == null ? "" : String(surface);
    var i = text.indexOf(surface);
    return i < 0 ? null : [text.slice(0, i), surface, text.slice(i + surface.length)];
  }

  function markSentence(text, surface, tier, s, e) {
    var sp = hitSpan(text, surface, s, e);
    if (!sp) return esc(text);
    var cls = (tier && tier !== "core") ? "guess" : "";
    var html = esc(sp[0]) + "<mark class=\"" + cls + "\">" + esc(sp[1]) + "</mark>" + esc(sp[2]);
    var note = TIER_NOTE[tier];
    return html + (note ? "<span class=\"tier-note\">？" + note + "</span>" : "");
  }

EOF
inject "indexOf" /c/Users/dell/AppData/Local/Temp/bi_bad1.jsfrag
expect_red "indexOf 版"
restore

echo
echo "=== 注入 2：天真的 slice(s,e)（審查報告的建議改法，應錯約 63 條） ==="
cat > /c/Users/dell/AppData/Local/Temp/bi_bad2.jsfrag <<'EOF'
  function hitSpan(text, surface, s, e) {
    text = String(text || "");
    surface = surface == null ? "" : String(surface);
    var a = Number(s), b = Number(e);
    if (!(a === a && b === b && a >= 0 && b > a)) {
      var i = text.indexOf(surface);
      return i < 0 ? null : [text.slice(0, i), surface, text.slice(i + surface.length)];
    }
    return [text.slice(0, a), surface, text.slice(b)];
  }

  function markSentence(text, surface, tier, s, e) {
    var sp = hitSpan(text, surface, s, e);
    if (!sp) return esc(text);
    var cls = (tier && tier !== "core") ? "guess" : "";
    var html = esc(sp[0]) + "<mark class=\"" + cls + "\">" + esc(sp[1]) + "</mark>" + esc(sp[2]);
    var note = TIER_NOTE[tier];
    return html + (note ? "<span class=\"tier-note\">？" + note + "</span>" : "");
  }

EOF
inject "naive slice" /c/Users/dell/AppData/Local/Temp/bi_bad2.jsfrag
expect_red "天真 slice 版"
restore

echo
echo "=== 注入 3：B 路徑回傳碼位下標（我自己第一版的 bug，交給調用方碼元 slice） ==="
cat > /c/Users/dell/AppData/Local/Temp/bi_bad3.jsfrag <<'EOF'
  function hitSpan(text, surface, s, e) {
    text = String(text || "");
    surface = surface == null ? "" : String(surface);
    var a = Number(s), b = Number(e);
    var ok = (a === a && b === b && a >= 0 && b > a);
    if (ok && b <= text.length && text.slice(a, b) === surface) {
      return [a, b];
    }
    if (ok) {
      var cp = Array.from(text);
      if (b <= cp.length && cp.slice(a, b).join("") === surface) {
        return [a, b];
      }
    }
    var i = text.indexOf(surface);
    return i < 0 ? null : [i, i + surface.length];
  }

  function markSentence(text, surface, tier, s, e) {
    var sp = hitSpan(text, surface, s, e);
    if (!sp) return esc(text);
    var t = String(text || "");
    var cls = (tier && tier !== "core") ? "guess" : "";
    var html = esc(t.slice(0, sp[0])) + "<mark class=\"" + cls + "\">" + esc(t.slice(sp[0], sp[1])) + "</mark>" + esc(t.slice(sp[1]));
    var note = TIER_NOTE[tier];
    return html + (note ? "<span class=\"tier-note\">？" + note + "</span>" : "");
  }

EOF
inject "code-unit leak" /c/Users/dell/AppData/Local/Temp/bi_bad3.jsfrag
expect_red "碼元洩漏版"
restore

echo
echo "=== 還原後必須全綠 ==="
run
grep -q "7/7" <(run) && echo "✔ 還原後 7/7 綠" || { echo "✘ 還原後仍不綠"; FAILED=1; }

echo
if [ "$FAILED" = "0" ]; then echo "=== 全部注入驗證通過 ==="; else echo "=== 有注入沒被抓住（斷言無效）==="; fi
exit $FAILED
