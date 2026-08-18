#!/usr/bin/env bash
# =============================================================================
# 關卡 4／正式環境安全檢查
#
# 這道關卡守的承諾是：「正式環境健康檢查不得使用 Issue / OfflineIssue」。
# 用開立類 API 做健康檢查會產生真實發票、消耗字軌號碼、且只能作廢不能刪除，
# 那是稅務資料污染，比金流的假訂單嚴重得多。
#
# 檢查範圍：templates/ 全部檔案 + guides/24-prod-monitoring.md
#
# 檢查項目：
#   1. 守門：確認掃到 > 0 個檔案，且至少有 1 個檔案落入「健康檢查語境」
#   2. 主檢查：檔案同時出現「健康檢查語境關鍵字」與「正式 host einvoice.opay.tw」時，
#      該檔中每一處開立類 endpoint（Issue / OfflineIssue / Invalid / Allowance /
#      DelayIssue / VoidWithReIssue / OfflineInvalid）的上下 5 行內
#      必須有明確的禁止字樣，否則紅燈。
#      比對用完整單字邊界，所以 GetIssue / GetInvalid / AllowanceInvalid 這類
#      唯讀或衍生名稱不會誤判。
#   3. 附加（獨立於上一項）：範本的 .env.example 不得把 OPAY_HOST 預設指向正式環境。
#
# 用法：bash scripts/validate-prod-safety.sh
# 退出碼：0 = 全綠；1 = 有正式環境風險
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 4／正式環境安全檢查（禁止用開立類 API 做健康檢查）"
echo "──────────────────────────────────────────────────────────────"

python3 - <<'PY'
import os, re, sys

PROD_HOST = "einvoice.opay.tw"
STAGE_HOST = "einvoice-stage.opay.tw"

HEALTH_CTX = re.compile(r"healthcheck|health_check|health-check|monitor|probe|探測|健康檢查", re.I)
# 開立／變更狀態類 endpoint。用單字邊界，避免 GetIssue、AllowanceInvalid 被誤判。
WRITE_EP = re.compile(
    r"(?<![A-Za-z])(OfflineIssue|OfflineInvalid|DelayIssue|VoidWithReIssue|"
    r"Issue|Invalid|Allowance)(?![A-Za-z])")
BAN_WORD = re.compile(r"禁止|不得|嚴禁|絕不|不可|❌|🚫|絕對不")
WINDOW = 5

targets = []
for root, dirs, files in os.walk("templates"):
    dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".venv"}]
    for fn in files:
        targets.append(os.path.join(root, fn).replace("\\", "/"))
if os.path.isfile("guides/24-prod-monitoring.md"):
    targets.append("guides/24-prod-monitoring.md")

print(f"掃描範圍：{len(targets)} 個檔案（templates/ 全部 + guides/24-prod-monitoring.md）")

# ---- 守門檢查：一定要掃得到檔案 ---------------------------------------------
if not targets:
    print("❌ 守門檢查失敗：掃描範圍內一個檔案都沒有。")
    print("   怎麼修：確認在 repo 根目錄執行，且 templates/ 存在。")
    sys.exit(1)
if not os.path.isfile("guides/24-prod-monitoring.md"):
    print("❌ 守門檢查失敗：找不到 guides/24-prod-monitoring.md。")
    print("   那份指南就是本關卡最主要的檢查對象，缺了這道關卡等於沒跑。")
    sys.exit(1)

errors = []
in_scope = []

def prod_host_hits(text):
    # 把 stage host 先挖掉，避免 einvoice-stage.opay.tw 被當成正式 host
    return PROD_HOST in text.replace(STAGE_HOST, "")

for path in targets:
    try:
        text = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        continue
    if not HEALTH_CTX.search(text):
        continue
    if not prod_host_hits(text):
        continue
    in_scope.append(path)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = WRITE_EP.search(line)
        if not m:
            continue
        window = "\n".join(lines[max(0, i - WINDOW): i + WINDOW + 1])
        if not BAN_WORD.search(window):
            errors.append(
                f'{path}:{i+1}｜健康檢查語境的檔案中出現開立類 API「{m.group(1)}」，'
                f'但上下 {WINDOW} 行沒有任何禁止字樣\n'
                f'       原文：{line.strip()[:110]}\n'
                f'       怎麼修：正式環境健康檢查只能用唯讀 API（建議 GetInvoiceWordSetting，'
                f'它不需要任何既有資料當參數）。若這段本來就是在警告不要這樣做，'
                f'請把「禁止／不得／嚴禁」寫進同一段，讓讀者與 AI 都不會抄走錯誤示範。')

print(f"落入健康檢查語境（同時出現探測關鍵字與正式 host {PROD_HOST}）的檔案：{len(in_scope)} 個")
for p in in_scope:
    print(f"  · {p}")

# ---- 守門檢查：至少要有一個檔案落入語境 --------------------------------------
if not in_scope:
    print("❌ 守門檢查失敗：沒有任何檔案同時出現健康檢查關鍵字與正式 host。")
    print("   本 repo 的 guides/24-prod-monitoring.md 依設計一定會同時出現這兩者，")
    print("   完全掃不到代表比對規則壞掉了（例如關鍵字被改名、檔案被移走）。")
    print("   怎麼修：手動確認 guides/24-prod-monitoring.md 的內容，再檢查本腳本的 HEALTH_CTX 規則。")
    sys.exit(1)

# ---- 附加檢查：.env.example 不得預設指向正式環境 ------------------------------
env_checked = 0
for path in targets:
    if not os.path.basename(path).startswith(".env"):
        continue
    env_checked += 1
    for i, line in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
        if re.match(r"\s*OPAY_HOST\s*=", line) and prod_host_hits(line):
            errors.append(
                f'{path}:{i}｜範本的 OPAY_HOST 預設值指向正式環境\n'
                f'       原文：{line.strip()[:110]}\n'
                f'       怎麼修：範本一律預設 https://{STAGE_HOST}，'
                f'讓使用者是「刻意」切到正式環境，而不是複製貼上就打到正式環境。')
print(f"另檢查 {env_checked} 個 .env 範本的 OPAY_HOST 預設值")

print("")
if errors:
    print(f"❌ 關卡 4 未通過，共 {len(errors)} 個問題：")
    for i, msg in enumerate(errors, 1):
        print(f"  {i:>3}. {msg}")
    sys.exit(1)

print("✅ 關卡 4 通過：健康檢查語境中的每一處開立類 API 都帶有明確禁止字樣，"
      "且範本預設 host 均為測試環境。")
PY
