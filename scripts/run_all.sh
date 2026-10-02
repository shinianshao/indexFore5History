#!/usr/bin/env bash
# 一键回归：数据断言 → 字面层守卫 → 无头 UI（可选全量扫描）。
#
# 用法（Git Bash / bash）：
#   bash scripts/run_all.sh            # 常规回归（约 4 分钟）
#   bash scripts/run_all.sh --full     # 追加静态版三套 + _ui_sweep.js 全量扫描（慢，约 15 分钟+）
#
# UI 分成两档：日常只跑**新版 app/web** 的三套（关系图 / 索引四块 / 样式表）；
# 打静态版 web/ 的三套已降频到 --full —— 静态版已冻结不再演进，天天跑是交税，
# 但它是「新版对齐」的参照物，不能完全删（docs/29 §六-1）。
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

# ---------- 0：前置检查 ----------
# verify_p3 里跑 rebuild.py 会**删库重建**；Windows 上 SQLite 被本地服务占着就删不掉，
# 退出码 1 但报错是 safe-delete 的，看不出真实原因。与其跑三分钟才红，不如开头说清楚。
# ⚠️ --noproxy 必须有：本机配了代理，curl 走代理会得到「upstream connect failed」假失败。
if curl -sf -o /dev/null --max-time 2 --noproxy '*' "http://127.0.0.1:8800/health" 2>/dev/null; then
  echo "" >&2
  echo "× 本地服务仍占着 index.db（127.0.0.1:8800 在跑）。" >&2
  echo "  一键回归会删库重建，Windows 上必然失败。请先停掉它：" >&2
  echo "    netstat -ano | findstr :8800   然后停掉对应 PID" >&2
  exit 2
fi

# ---------- 1-3：Python 侧 ----------
run_step "数据断言 verify.py --check" "$PY" pipeline/verify.py --check
run_step "字面层守卫 check_trad.py（A–G 七道闸）" "$PY" pipeline/check_trad.py
# ⚠️ verify_p3 是 P3–P6 新链路的 56 条断言（快照 / overrides / 句级编辑 / 关系 / 证据），
# 它跟 verify.py 是**两套**，不接进来就等于这 56 条从来没自动跑过（约 2 分钟）。
run_step "新链路断言 app/tools/verify_p3.py" "$PY" app/tools/verify_p3.py
# 权威源体检放在 verify_p3 之后：它要拿重建后的库判「证据句是否已失效」。
run_step "关系权威源体检 relations.py check" "$PY" pipeline/relations.py check
# 离线静态快照 dist/（docs/29 §六-6）：跟联机版**同一套前端**，只换数据源。
# 放在这里是因为它要读刚重建好的库；放在日常档而不是 --full，是因为
# 快照一旦过期就没人发现——而它恰恰是要发给别人的那份。
run_step "离线静态快照 export_static.py" "$PY" app/tools/export_static.py
# 「按书收窄」是导出提速 6 倍换来的假设（db._narrow），破了会产出跟联机版
# 对不上的快照且不报错——所以要有断言盯着它。慢（约 23s），只在 --full 跑。
if [ "$RUN_FULL" -eq 1 ]; then
  run_step "快照与联机等价 export_static.py --verify" "$PY" app/tools/export_static.py --verify
fi

# ---------- 3：无头 UI ----------
SERVER_PID=""
API_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  if [ -n "$API_PID" ]; then
    kill "$API_PID" 2>/dev/null
    wait "$API_PID" 2>/dev/null
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
        run_step "UI 样式表 _ui_csscheck.js"     "$NODE_BIN" pipeline/_ui_csscheck.js
        # ⚠️ 下面三套打的是**已冻结的静态版 web/**（docs/29 §六-1，用户 2026-10-02 定：降频）。
        #   它不再演进，天天为它跑等于给死掉的分支交税；但它是「新版对齐的参照物」，
        #   全删不安全——挪到 --full，改静态版或做对齐时再跑。
        if [ "$RUN_FULL" -eq 1 ]; then
          run_step "UI 人物页（静态版）_ui_test.js"       "$NODE_BIN" pipeline/_ui_test.js
          run_step "UI 多书检索（静态版）_ui_test_books.js" "$NODE_BIN" pipeline/_ui_test_books.js
          run_step "UI 地名层（静态版）_ui_test_places.js"  "$NODE_BIN" pipeline/_ui_test_places.js
        fi
        # 关系卡/关系图（P6-3）打的是 **FastAPI 版**（app/web），不是 web/ 静态页。
        # 静态页没有 /api，拿 BASE=静态页 去跑会得到「全红但其实打错靶」的假失败。
        # 所以这里单起一个 API 服务（独立端口，不与日常用的 8800 抢）。
        APIPORT="${APIPORT:-8811}"
        if "$PY" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
          PORT="$APIPORT" "$PY" app/server/main.py >/dev/null 2>&1 &
          API_PID=$!
          api_ready=0
          for i in $(seq 1 40); do
            if curl -sf -o /dev/null "http://127.0.0.1:${APIPORT}/health"; then
              api_ready=1; break
            fi
            sleep 0.3
          done
          if [ "$api_ready" -ne 1 ]; then
            echo "API 服务未能在 12 秒内就绪（端口 $APIPORT）" >&2
            NAMES+=("UI 关系图（未运行：API 未就绪）"); RESULTS+=("1")
          else
            run_step "UI 关系图 _ui_test_rel.js" \
              env BASE="http://127.0.0.1:${APIPORT}/" "$NODE_BIN" pipeline/_ui_test_rel.js
            # 索引四块（書切換 / 快捷詞 / 人物索引 / 地名索引 / 篇目一覽）同样是
            # app/web/ 的新页面，静态页没有——跟关系图一样打 APIPORT。
            run_step "UI 索引四块 _ui_test_index.js" \
              env BASE="http://127.0.0.1:${APIPORT}/" "$NODE_BIN" pipeline/_ui_test_index.js
            # ⚠️ 离线快照打的是 dist/，**刻意不起服务也不注入 fetch**——
            # 这是唯一能证明「双击就能开、不用跑 FastAPI」的方式。
            run_step "UI 离线快照 _ui_test_offline.js" \
              "$NODE_BIN" pipeline/_ui_test_offline.js
          fi
        else
          echo "跳过关系图测试：$PY 里没有 fastapi/uvicorn" >&2
          NAMES+=("UI 关系图（未运行：缺 fastapi）"); RESULTS+=("1")
        fi
        if [ "$RUN_FULL" -eq 1 ]; then
          run_step "UI 全量扫描 _ui_sweep.js（慢）" "$NODE_BIN" pipeline/_ui_sweep.js
        fi
      fi
    fi
  fi
fi

# ---------- 4：收尾清理 ----------
# 断言自造的测试行（revoke 只改状态不删行）**两套断言都会写**，跑了十几轮积了几十行
# dead 行，权威源永远脏着。统一在最后清一次：只删 dead + 命中测试标记的行。
run_step "清理斷言測試殘留（overrides / sentence-edits）" "$PY" -c \
  "import sys; sys.path.insert(0, 'app/tools'); import verify_p3; verify_p3.purge_test_rows()"

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
