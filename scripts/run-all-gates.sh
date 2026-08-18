#!/usr/bin/env bash
# =============================================================================
# 全關卡總跑器
#
# 依序執行本 repo 所有獨立檢查機制，任一道紅燈即整體失敗（退出碼 1）。
# CI（.github/workflows/validate.yml）與本機都跑同一支，避免「本機綠、CI 紅」。
#
# 關卡順序（由「規格正確性」到「可執行性」）：
#   1. API 覆蓋率（69 支一支都不能漏）      7. 官方文件版本一致性
#   2. 機密外洩掃描                          8. AES 測試向量（Python）
#   3. 綠界／歐買尬做法污染                  9. AES 測試向量（Node.js）
#   4. 正式環境安全                         10. Python 語法檢查
#   5. 圖表無障礙與配色                     11. Node.js 語法檢查
#   6. 內部連結                             12. PHP 語法檢查（沒裝 php 則標示跳過）
#
# 用法：bash scripts/run-all-gates.sh
# 退出碼：0 = 全綠；1 = 至少一道紅燈
# =============================================================================
set -uo pipefail   # 刻意不用 -e：要讓每一道關卡都跑完才彙總，而不是第一道紅就中斷

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NAMES=()
RESULTS=()
ELAPSED_MS=()

now_ms() { python3 -c 'import time;print(int(time.time()*1000))'; }

run_gate() {
  local name="$1"; shift
  local start end
  echo ""
  echo "=============================================================="
  echo "▶ ${name}"
  echo "=============================================================="
  start="$(now_ms)"
  if "$@"; then
    RESULTS+=("PASS")
  else
    RESULTS+=("FAIL")
  fi
  end="$(now_ms)"
  NAMES+=("$name")
  ELAPSED_MS+=("$(( end - start ))")
}

skip_gate() {
  local name="$1" reason="$2"
  echo ""
  echo "=============================================================="
  echo "⏭ ${name} —— 跳過：${reason}"
  echo "=============================================================="
  NAMES+=("$name")
  RESULTS+=("SKIP")
  ELAPSED_MS+=("0")
}

# ---- 前置守門：確認我確實站在這個 repo 的根目錄上 ----------------------------
echo "──────────────────────────────────────────────────────────────"
echo "opay-invoice-skill 全關卡檢查"
echo "工作目錄：${REPO_ROOT}"
echo "──────────────────────────────────────────────────────────────"
MISSING=0
for must in references/api-coverage.json references guides templates test-vectors scripts; do
  if [[ ! -e "$must" ]]; then
    echo "❌ 前置守門失敗：找不到 ${must}"
    MISSING=1
  fi
done
if [[ "$MISSING" -ne 0 ]]; then
  echo "   怎麼修：請在 repo 根目錄執行 bash scripts/run-all-gates.sh。"
  exit 1
fi
SCRIPT_COUNT="$(find scripts -maxdepth 1 -name 'validate-*.sh' | wc -l | tr -d ' ')"
echo "前置守門通過：找到 ${SCRIPT_COUNT} 支 validate-*.sh 檢查腳本"
if [[ "$SCRIPT_COUNT" -lt 7 ]]; then
  echo "❌ 前置守門失敗：validate-*.sh 少於 7 支，代表有關卡被刪掉或改名。"
  echo "   怎麼修：從 git 還原缺少的腳本；關卡只能加嚴不能拿掉。"
  exit 1
fi

# ---- 靜態檢查關卡 -----------------------------------------------------------
run_gate "關卡 1／API 覆蓋率（69 支）"   bash scripts/validate-api-coverage.sh
run_gate "關卡 2／機密外洩掃描"          bash scripts/validate-no-leaks.sh
run_gate "關卡 3／綠界歐買尬做法污染"    bash scripts/validate-not-ecpay-or-omg.sh
run_gate "關卡 4／正式環境安全"          bash scripts/validate-prod-safety.sh
run_gate "關卡 5／圖表無障礙與配色"      bash scripts/validate-a11y-palette.sh
run_gate "關卡 6／內部連結"              bash scripts/validate-links.sh
run_gate "關卡 7／官方文件版本一致性"    bash scripts/validate-doc-versions.sh

# ---- 測試向量 ---------------------------------------------------------------
run_gate "關卡 8／AES 測試向量 Python"   python3 test-vectors/verify.py
if command -v node >/dev/null 2>&1; then
  run_gate "關卡 9／AES 測試向量 Node.js" node test-vectors/verify-node.js
else
  skip_gate "關卡 9／AES 測試向量 Node.js" "本機沒有 node（CI 一定有；本機請自行安裝）"
fi

# ---- 三語言語法檢查 ---------------------------------------------------------
check_python_syntax() {
  local files=()
  while IFS= read -r line; do files+=("$line"); done < <(
    find . -path ./.git -prune -o -path ./node_modules -prune -o \
           -path ./.venv -prune -o -name '*.py' -print | sort)
  echo "掃描範圍：${#files[@]} 個 .py 檔"
  if [[ "${#files[@]}" -eq 0 ]]; then
    echo "❌ 守門檢查失敗：掃不到任何 .py 檔，這道關卡形同虛設。"
    echo "   怎麼修：確認 templates/ 與 test-vectors/ 存在。"
    return 1
  fi
  local rc=0
  for f in "${files[@]}"; do
    if python3 -m py_compile "$f" 2>&1; then
      echo "  ok    $f"
    else
      echo "  ❌ 語法錯誤：$f｜怎麼修：依上面的 SyntaxError 行號修正。"
      rc=1
    fi
  done
  find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  return "$rc"
}

check_node_syntax() {
  local files=()
  while IFS= read -r line; do files+=("$line"); done < <(
    find . -path ./.git -prune -o -path ./node_modules -prune -o -name '*.js' -print | sort)
  echo "掃描範圍：${#files[@]} 個 .js 檔"
  if [[ "${#files[@]}" -eq 0 ]]; then
    echo "❌ 守門檢查失敗：掃不到任何 .js 檔，這道關卡形同虛設。"
    return 1
  fi
  local rc=0
  for f in "${files[@]}"; do
    if node --check "$f" 2>&1; then
      echo "  ok    $f"
    else
      echo "  ❌ 語法錯誤：$f"
      rc=1
    fi
  done
  return "$rc"
}

check_php_syntax() {
  local files=()
  while IFS= read -r line; do files+=("$line"); done < <(
    find . -path ./.git -prune -o -name '*.php' -print | sort)
  echo "掃描範圍：${#files[@]} 個 .php 檔"
  if [[ "${#files[@]}" -eq 0 ]]; then
    echo "❌ 守門檢查失敗：掃不到任何 .php 檔，這道關卡形同虛設。"
    return 1
  fi
  local rc=0
  for f in "${files[@]}"; do
    if php -l "$f" >/dev/null 2>&1; then
      echo "  ok    $f"
    else
      echo "  ❌ 語法錯誤：$f"
      php -l "$f" || true
      rc=1
    fi
  done
  return "$rc"
}

run_gate "關卡 10／Python 語法檢查" check_python_syntax
if command -v node >/dev/null 2>&1; then
  run_gate "關卡 11／Node.js 語法檢查" check_node_syntax
else
  skip_gate "關卡 11／Node.js 語法檢查" "本機沒有 node"
fi
if command -v php >/dev/null 2>&1; then
  run_gate "關卡 12／PHP 語法檢查" check_php_syntax
else
  skip_gate "關卡 12／PHP 語法檢查" "本機沒有 php（PHP 範本仍需在有 php 的環境驗證）"
fi

# ---- 彙總表 -----------------------------------------------------------------
# 用 python3 排版：中文字在終端機佔兩個字寬，printf 的 %-40s 以位元組計算會對不齊。
SUMMARY_TSV="$(mktemp)"
for i in "${!NAMES[@]}"; do
  printf '%s\t%s\t%s\n' "${NAMES[$i]}" "${RESULTS[$i]}" "${ELAPSED_MS[$i]}" >> "$SUMMARY_TSV"
done

python3 - "$SUMMARY_TSV" <<'PYSUMMARY'
import sys, unicodedata

rows = []
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        name, result, ms = line.split("\t")
        rows.append((name, result, int(ms)))

def width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)

def pad(s, n):
    return s + " " * max(0, n - width(s))

MARK = {"PASS": "✅ 通過", "FAIL": "❌ 紅燈", "SKIP": "⏭ 跳過"}
w = max([width(r[0]) for r in rows] + [width("關卡")]) + 2

print("")
print("─" * 62)
print("彙總表")
print("─" * 62)
print(pad("#", 4) + pad("關卡", w) + pad("結果", 10) + "      耗時")
print("─" * 62)
passed = failed = skipped = 0
for i, (name, result, ms) in enumerate(rows, 1):
    if result == "PASS":
        passed += 1
    elif result == "FAIL":
        failed += 1
    else:
        skipped += 1
    print(pad(str(i), 4) + pad(name, w) + pad(MARK[result], 10) + f"{ms / 1000:>9.2f}s")
print("─" * 62)
print(f"合計 {len(rows)} 道關卡：通過 {passed}、紅燈 {failed}、跳過 {skipped}")
PYSUMMARY

rm -f "$SUMMARY_TSV"

FAILED=0
for r in "${RESULTS[@]}"; do
  [[ "$r" == "FAIL" ]] && FAILED=$((FAILED + 1))
done
TOTAL="${#NAMES[@]}"

if [[ "$FAILED" -gt 0 ]]; then
  echo ""
  echo "❌ 整體未通過：${TOTAL} 道關卡中有 ${FAILED} 道紅燈。"
  echo "   往上捲動找 ❌ 開頭的訊息，每一則都寫了「怎麼修」。"
  echo "   提醒：關卡只能加嚴不能放寬。不要為了讓腳本變綠而改規則。"
  exit 1
fi

echo ""
echo "✅ 全部通過：${TOTAL} 道關卡全數綠燈（或已標示跳過）。"
