#!/usr/bin/env bash
# 一键回归：数据断言 → 字面层守卫 → 无头 UI 四套（可选全量扫描）。
#
# 用法（Git Bash / bash）：
#   bash scripts/run_all.sh            # 常规回归（约 1-2 分钟）
#   bash scripts/run_all.sh --full     # 追加 _ui_sweep.js 全量扫描（慢，约 10 分钟+）
#   bash scripts/run_all.sh --no-ui    # 只跑 Python 侧（改词典时的快速回路）
#
# 环境变量可覆盖：PYTHON / NODE / NODE_PATH / PORT
#
# 为什么要有它：UI 测试原本要手工「起 http.server 8770 + 手设 NODE_PATH」，
# 三步里漏任何一步都会得到假的失败，久而久之就没人跑了。

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 默认端口 8770 → 8790：8770 被本机的 VPN 客户端（iKuuuVPNCore）占着，
# 每次回归都会卡在「服务未能在 12 秒内就绪」。换一个不常用的端口。
# 临时想换回来：PORT=8770 bash scripts/run_all.sh
PORT="${PORT:-8790}"
BASE="http://127.0.0.1:${PORT}/index.html"
RUN_FULL=0
RUN_UI=1

for arg in "$@"; do
  case "$arg" in
    --full)  RUN_FULL=1 ;;
    --no-ui) RUN_UI=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（支持 --full / --no-ui / --help）" >&2; exit 2 ;;
  esac
done

# ---------- 定位解释器（本机 python/node 都在隔离目录，不一定在 PATH 上）----------
# 注意：必须挑「装了 opencc 的那个 python」——check_trad.py / build*.py 强依赖它，
# 而 PATH 上排第一位的托管版 python 可能没装，直接拿来跑会得到假的失败。
find_python() {
  local cands=()
  [ -n "${PYTHON:-}" ] && cands+=("$PYTHON")
  cands+=(python python3)
  cands+=("/c/Users/dell/AppData/Local/Programs/Python/Python312/python.exe")
  cands+=("$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe")

  local first_ok="" c
  for c in "${cands[@]}"; do
    command -v "$c" >/dev/null 2>&1 || [ -x "$c" ] || continue
    [ -z "$first_ok" ] && first_ok="$c"
    if "$c" -c "import opencc" >/dev/null 2>&1; then echo "$c"; return; fi
  done
  # 都没装 opencc：退回第一个可用的，让 check_trad 自己报缺依赖
  echo "$first_ok"
}

find_node() {
  [ -n "${NODE:-}" ] && command -v "$NODE" >/dev/null 2>&1 && { echo "$NODE"; return; }
  command -v node >/dev/null 2>&1 && { echo node; return; }
  for p in "$HOME/.workbuddy/binaries/node/versions/22.22.2-3/node.exe" \
           "/c/Program Files/nodejs/node.exe"; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  echo ""
}

find_node_modules() {
  [ -n "${NODE_PATH:-}" ] && [ -d "${NODE_PATH}" ] && { echo "$NODE_PATH"; return; }
  for d in "$HOME/.workbuddy/binaries/node/workspace/node_modules"; do
    [ -d "$d" ] && { echo "$d"; return; }
  done
  echo ""
}

PY="$(find_python)"
NODE_BIN="$(find_node)"
NM="$(find_node_modules)"

[ -z "$PY" ] && { echo "找不到 python：请设 PYTHON=/path/to/python.exe" >&2; exit 2; }
echo "python : $PY"
echo "node   : ${NODE_BIN:-（未找到）}"
echo "modules: ${NM:-（未找到）}"

# ---------- 步骤记录 ----------
NAMES=()
RESULTS=()
SECONDS_TOTAL=0

run_step() {
  local name="$1"; shift
  printf '\n──────── %s ────────\n' "$name"
  local t0 rc
  t0=$(date +%s)
  "$@"
  rc=$?
  local dt=$(( $(date +%s) - t0 ))
  SECONDS_TOTAL=$(( SECONDS_TOTAL + dt ))
  NAMES+=("$name")
  RESULTS+=("$rc")
  if [ "$rc" -eq 0 ]; then
    printf '  → 通过（%ss）\n' "$dt"
  else
    printf '  → 失败（%ss，退出码 %s）\n' "$dt" "$rc"
  fi
  return 0
}

# ---------- 1-2：Python 侧 ----------
run_step "数据断言 verify.py --check" "$PY" pipeline/verify.py --check
run_step "字面层守卫 check_trad.py（A–G 七道闸）" "$PY" pipeline/check_trad.py

# ---------- 3：无头 UI ----------
SERVER_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
}
trap stop_server EXIT INT TERM

if [ "$RUN_UI" -eq 1 ]; then
  if [ -z "$NODE_BIN" ] || [ -z "$NM" ]; then
    echo "" >&2
    echo "跳过 UI 测试：node 或 jsdom 依赖目录缺失。" >&2
    echo "  设 NODE=<node.exe> NODE_PATH=<含 jsdom 的 node_modules>" >&2
    NAMES+=("UI 四套（未运行：环境缺失）"); RESULTS+=("1")
  else
    if [ ! -d "$NM/jsdom" ]; then
      echo "" >&2
      echo "跳过 UI 测试：$NM 里没有 jsdom。" >&2
      echo "  安装：cd <workspace> && npm i jsdom" >&2
      NAMES+=("UI 四套（未运行：缺 jsdom）"); RESULTS+=("1")
    else
      echo ""
      echo "──────── 启动本地服务 :$PORT ────────"
      "$PY" -m http.server "$PORT" --bind 127.0.0.1 --directory web >/dev/null 2>&1 &
      SERVER_PID=$!

      ready=0
      for i in $(seq 1 40); do
        if curl -sf -o /dev/null "$BASE"; then ready=1; break; fi
        sleep 0.3
      done
      if [ "$ready" -ne 1 ]; then
        echo "服务未能在 12 秒内就绪（端口 $PORT 可能被占用）" >&2
        NAMES+=("UI 四套（未运行：服务未就绪）"); RESULTS+=("1")
      else
        echo "  服务就绪：$BASE"
        export BASE
        export NODE_PATH="$NM"
        run_step "UI 人物页 _ui_test.js"       "$NODE_BIN" pipeline/_ui_test.js
        run_step "UI 多书检索 _ui_test_books.js" "$NODE_BIN" pipeline/_ui_test_books.js
        run_step "UI 地名层 _ui_test_places.js"  "$NODE_BIN" pipeline/_ui_test_places.js
        run_step "UI 样式表 _ui_csscheck.js"     "$NODE_BIN" pipeline/_ui_csscheck.js
        if [ "$RUN_FULL" -eq 1 ]; then
          run_step "UI 全量扫描 _ui_sweep.js（慢）" "$NODE_BIN" pipeline/_ui_sweep.js
        fi
      fi
    fi
  fi
fi

# ---------- 汇总 ----------
echo ""
echo "════════════════ 回归汇总 ════════════════"
pass=0; fail=0
for i in "${!NAMES[@]}"; do
  if [ "${RESULTS[$i]}" = "0" ]; then
    printf '  ✓ %s\n' "${NAMES[$i]}"; pass=$((pass+1))
  else
    printf '  ✗ %s\n' "${NAMES[$i]}"; fail=$((fail+1))
  fi
done
echo "──────────────────────────────────────────"
printf '  通过 %s / 失败 %s   总耗时 %ss\n' "$pass" "$fail" "$SECONDS_TOTAL"
[ "$fail" -eq 0 ] && exit 0 || exit 1
