#!/usr/bin/env bash
# =============================================================================
# 關卡 3／防止把綠界（ECPay）／歐買尬（OMG）的做法混進來
#
# 這道關卡守的承諾是：「歐付寶電子發票的加密是 AES-128-CBC/PKCS7，
# 不是 CheckMacValue／SHA256」。大型語言模型的訓練資料裡綠界範例遠多於歐付寶，
# 是最常見的污染來源；一旦混進 references 或 templates，使用者會直接抄錯。
#
# 兩層規則（兩層都要過，缺一即紅燈）：
#   第一層｜檔案允許清單：只有「對照說明用」的檔案可以出現這些字串，其餘檔案出現即紅燈。
#   第二層｜語境標記：**不論在哪個檔案**（允許清單內也一樣），每一處出現的上下 4 行內
#           必須有明確的對照字樣（綠界／ECPay／歐買尬／不適用／不是／別家…），
#           確保讀者不會誤以為那是歐付寶的做法。
#   第二層對允許清單內的檔案是「加嚴」，不是放寬：允許清單只解除檔案層級的禁令，
#   語境標記仍然逐處檢查。
#
# 用法：bash scripts/validate-not-ecpay-or-omg.sh
# 退出碼：0 = 全綠；1 = 有污染
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 3／綠界／歐買尬做法污染檢查"
echo "──────────────────────────────────────────────────────────────"

python3 - <<'PY'
import os, re, sys

# 禁用字串：這些都是別家（綠界 ECPay／歐買尬 OMG）的專有名詞或網域
BANNED = re.compile(
    r"CheckMacValue|AioCheckOut|ChoosePayment|funpoint\.com\.tw|payment\.ecpay\.com\.tw")

# 第一層：檔案允許清單（只有這些檔案可以在「對照段落」中提到別家做法）
ALLOWED_FILES = {
    "README.md",                      # 人類入口，需要說明「跟綠界不一樣」
    "SKILL.md",                       # AI 入口 §0 核心規則
    "llms.txt",                       # AI 爬蟲入口，與 SKILL.md 對稱，同樣要先講清楚「不是 CheckMacValue」
    "GLOSSARY.md",                    # 名詞對照
    "SETUP.md",                       # 安裝驗收題：AI 若答 CheckMacValue 代表沒讀到 Skill
    "MANIFESTO.md",                   # 專案理念，說明 AI 為何會答錯
    "docs/prompt-examples.md",        # 提示詞範例：要求 AI 自我檢查有無誤用
    "CLAUDE.md", "AGENTS.md", "GEMINI.md",
    "SKILL_OPENAI.md", "vscode_copilot.md", "google_AI_studio.md",  # 六份轉接檔
    "guides/28-troubleshooting.md",   # 疑難排解
    "references/encryption-aes.md",   # 加密規格，必須說明「不是 CheckMacValue」
    "docs/official-doc-issues.md",    # 官方文件問題清單：其中一條就是「官方文件混入綠界網域」，
                                      # 要指出這個問題就必須引用該字串本身作為證據。
}
ALLOWED_PREFIX = (
    "scripts/",    # 本關卡自己與其他腳本：規則定義處，必須寫得出被禁的字串
    ".github/",    # issue／PR 範本與 repo 簡介：對貢獻者說明「不要寫成綠界的做法」正是重點
    "commands/",   # slash command 指令：對 AI 下達「不要寫 CheckMacValue」的指示，本身就必須提到它
    "docs/audit/", # 獨立稽核報告：稽核項目之一就是「repo 有沒有把歐付寶加密講成 CheckMacValue」，
                   #               報告必須引用被檢查的字串與命中行才能作為證據。
                   #               ⚠️ 本前綴只放稽核報告，不得放實作或規格文件。
)

# 第二層：語境標記。每一處出現的上下 4 行內必須至少命中一個。
CONTEXT_MARK = re.compile(
    r"綠界|ECPay|ecpay|歐買尬|OMG|不適用|不是|別家|刪掉|沒有|錯誤答案|混淆|其他金流")
WINDOW = 4

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".ico", ".docx"}

errors = []
scanned = 0
occurrences = 0

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
        path = os.path.join(root, fn).replace("\\", "/")
        rel = path[2:] if path.startswith("./") else path
        if os.path.splitext(fn)[1].lower() in BINARY_EXT:
            continue
        try:
            lines = open(path, encoding="utf-8").read().split("\n")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        allowed = rel in ALLOWED_FILES or rel.startswith(ALLOWED_PREFIX)
        for i, line in enumerate(lines):
            m = BANNED.search(line)
            if not m:
                continue
            occurrences += 1
            if not allowed:
                errors.append(
                    f'{rel}:{i+1}｜出現別家做法字串「{m.group(0)}」，而本檔不在允許清單中\n'
                    f'       原文：{line.strip()[:100]}\n'
                    f'       怎麼修：歐付寶電子發票用 AES-128-CBC/PKCS7 加密整包 Data，'
                    f'沒有 CheckMacValue 這個欄位。請直接刪除這段，改引用 '
                    f'references/encryption-aes.md；若這確實是必要的對照說明，'
                    f'請在本腳本的 ALLOWED_FILES 加入本檔並寫明理由。')
                continue
            window = "\n".join(lines[max(0, i - WINDOW): i + WINDOW + 1])
            if not CONTEXT_MARK.search(window):
                errors.append(
                    f'{rel}:{i+1}｜「{m.group(0)}」出現在允許清單檔案中，'
                    f'但上下 {WINDOW} 行找不到對照標記\n'
                    f'       原文：{line.strip()[:100]}\n'
                    f'       怎麼修：在同一段補一句明確的對照，例如'
                    f'「（那是綠界 ECPay 的做法，歐付寶不適用）」，'
                    f'避免讀者誤以為歐付寶也要算 CheckMacValue。')

print(f"掃描範圍：{scanned} 個文字檔，共找到 {occurrences} 處別家做法字串（全部須為對照說明）")

# ---- 守門檢查 ---------------------------------------------------------------
if scanned == 0:
    print("❌ 守門檢查失敗：一個檔案都沒掃到，這道關卡形同虛設。")
    print("   怎麼修：確認在 repo 根目錄執行 bash scripts/validate-not-ecpay-or-omg.sh。")
    sys.exit(1)
if occurrences == 0:
    print("❌ 守門檢查失敗：連一處別家做法字串都沒掃到。")
    print("   本 repo 的 README／GLOSSARY／encryption-aes.md 依設計一定會提到綠界做法做對照，")
    print("   完全掃不到代表比對規則壞掉了（例如檔案編碼或 BANNED 正規表示式被改壞）。")
    print("   怎麼修：先手動 grep -rn CheckMacValue . 確認，再檢查本腳本的 BANNED 規則。")
    sys.exit(1)

print("")
if errors:
    print(f"❌ 關卡 3 未通過，共 {len(errors)} 個問題：")
    for i, msg in enumerate(errors, 1):
        print(f"  {i:>3}. {msg}")
    sys.exit(1)

print("✅ 關卡 3 通過：所有別家做法字串都落在允許清單檔案，且每一處都有明確的對照標記。")
PY
