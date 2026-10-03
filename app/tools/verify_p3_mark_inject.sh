#!/usr/bin/env bash
# P0-甲 注入验证：把 app.js 改成四种坏写法，每种都必须让 verify_p3_mark 变红。
# 判据是「故意注入错误，断言必须变红」——不验这一步，
# 上面那 N 条 OK 说明不了任何事（恒真断言最贵）。
#
# ⚠️ 每次注入都必须**按函数体边界**定位，不能 replace(old,new,1)：
#    app.js 里 indexOf 有多处，那样会改到搜索那几处，注入根本不生效而断言全绿。
#
# ⚠️ 注入 4（呼叫点漏传 s/e）是独立审查 P1-1 的产物：
#    只验「函数本身对不对」，呼叫点改回旧写法时 7/7 全绿而 8319 条错标复活。
set -u
cd "$(dirname "$0")/../.." || exit 1
PY="C:/Users/dell/AppData/Local/Programs/Python/Python312/python.exe"
APP="app/web/app.js"
BAK="C:/Users/dell/AppData/Local/Temp/bi_app_mark_bak.js"
# ⚠️ 备份只做一次（见 verify_p3_note_inject.sh 的同样教训）：
#    restore() 里若重备份，连续注入会「越还原越坏」，最后 trap 还报成功。
cp "$APP" "$BAK"
restore() { cp "$BAK" "$APP"; }
trap restore EXIT

# ⚠️ 要看**全部** FAIL 行，不能 tail -3：核心判据（「落點全對」）必须自己也红，
#    只靠辅助断言红等于没验到点子上（同「宽松选择器恒真」那一类）。
run() { "$PY" app/tools/verify_p3_mark.py 2>&1 | grep -E "FAIL|通過" | tr -d '\r'; }

# ⚠️ 不写死「7/7」——断言条数会随项目增长（本文件加了两条后已是 9）。
#    要断的是「没有 FAIL」且「通過数 == 总数」，写死数字会在加断言那天假红。
expect_red() { # $1=名字
  out=$(run)
  if echo "$out" | grep -q "FAIL"; then
    echo "   ✔ $1 → 變紅 ✔"
    echo "$out" | sed 's/^/      /'
  else
    echo "   ✘ $1 → **仍是綠**（斷言無效）"
    echo "$out" | sed 's/^/      /'
    FAILED=1
  fi
}

expect_green() { # $1=名字
  out=$(run)
  local tot
  tot=$(echo "$out" | grep -oE "[0-9]+/[0-9]+ 通過" | tail -1)
  if echo "$out" | grep -q "FAIL"; then
    echo "   ✘ $1 → **仍紅**（沒還原乾淨？）"
    echo "$out" | sed 's/^/      /'
    FAILED=1
    return
  fi
  local a b
  a=$(echo "$tot" | cut -d/ -f1); b=$(echo "$tot" | cut -d/ -f2 | cut -d' ' -f1)
  if [ -n "$tot" ] && [ "$a" = "$b" ]; then
    echo "   ✔ $1 → 全綠（$tot）"
  else
    echo "   ✘ $1 → 條數對不上（$tot）"
    FAILED=1
  fi
}

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

# ⚠️ 锚点必须先确认存在。否则 python 抛 ValueError 退出后 run/trap 照跑，
#    脚本会对着「注入根本没生效」的原码报「✔ 变红」（踩过）。
assert_anchor() { # $1=锚点串
  if grep -qF "$1" "$APP"; then :; else
    echo "   ✘ 錨點不存在，注入無法生效：$1"
    FAILED=1
    return 1
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
echo "=== 注入 4：呼叫點漏傳 s/e（獨立審查 P1-1） ==="
echo "    只改呼叫點、不動 hitSpan —— 沒有「呼叫點」那條斷言時這是 100% 綠的"
if assert_anchor "markSentence(m.text, m.surface, m.tier, m.s, m.e)"; then
  "$PY" - <<'PYEOF'
import io
p = "app/web/app.js"
src = io.open(p, encoding="utf-8").read()
old = "markSentence(m.text, m.surface, m.tier, m.s, m.e)"
n = src.count(old)
assert n == 2, "呼叫點應有 2 處，實得 %d" % n
io.open(p, "w", encoding="utf-8").write(src.replace(old, "markSentence(m.text, m.surface, m.tier)"))
print("   已注入：%d 處呼叫點改回三參數" % n)
PYEOF
  expect_red "呼叫點漏傳版"
  restore
else
  echo "   ✘ 錨點缺失，注入 4 跳過（這本身也是失敗）"
  FAILED=1
fi

echo
echo "=== 還原後必須全綠（不寫死條數） ==="
expect_green "還原後"

# ⚠️ P2-7：乙腳本結尾有位元組比對 + 錨點 grep，甲原本只有「7/7 綠」。
#    萬一 cp $BAK $APP 沒成功，甲會帶著**改壞的 app.js** 報成功。
echo
echo "=== 還原完整性：位元組比對 + 錨點 ==="
if diff -q <(tr -d '\r' < "$APP") <(tr -d '\r' < "$BAK") >/dev/null; then
  echo "   ✔ app.js 與備份逐位元組一致"
else
  echo "   ✘ app.js 與備份**不一致**（還原失敗）"
  FAILED=1
fi
for anc in '  function hitSpan(' 'function markSentence(text, surface, tier, s, e)' 'markSentence(m.text, m.surface, m.tier, m.s, m.e)'; do
  if grep -qF "$anc" "$APP"; then
    echo "   ✔ 錨點在：$anc"
  else
    echo "   ✘ 錨點丟失：$anc"
    FAILED=1
  fi
done

echo
if [ "$FAILED" = "0" ]; then echo "=== 全部注入驗證通過 ==="; else echo "=== 有注入沒被抓住（斷言無效）==="; fi
exit $FAILED
