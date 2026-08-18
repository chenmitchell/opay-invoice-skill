#!/usr/bin/env bash
# =============================================================================
# 關卡 2／機密外洩掃描
#
# 這道關卡守的承諾是：「金鑰只進 .env，不得進 git、不得進前端」。
#
# 設計重點：**比對「值的樣式」，不是只比對「變數名稱」**。
# 只比對名稱（例如找 HASHKEY 這個字）擋不住「HASHKEY 等號後面直接接一串 16 碼字面值」寫死在程式裡，
# 因為那種寫法名稱與值同時存在，真正危險的是「值」。所以本腳本一律對值做樣式比對。
#
# 檢查項目：
#   1. 守門：確認掃到 > 0 個檔案
#   2. 疑似 HashKey / HashIV 的 16 碼字面值（排除官方文件公開的測試值）
#   3. Telegram bot token 樣式
#   4. Discord token 樣式
#   5. GitHub token（ghp_ / github_pat_）樣式
#   6. AWS access key / secret key 樣式
#   7. 私鑰 PEM 標頭
#   8. .env（非 .env.example）被 git 追蹤或存在於工作目錄
#
# 用法：bash scripts/validate-no-leaks.sh
# 退出碼：0 = 全綠；1 = 疑似外洩
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 2／機密外洩掃描（比對值的樣式，不是變數名稱）"
echo "──────────────────────────────────────────────────────────────"

# ---- 守門檢查：先確認我真的掃得到檔案 ---------------------------------------
FILE_COUNT="$(find . \
  -path ./.git -prune -o \
  -path ./node_modules -prune -o \
  -path ./.venv -prune -o \
  -type f -print | wc -l | tr -d ' ')"
echo "掃描範圍：${FILE_COUNT} 個檔案"
if [[ "$FILE_COUNT" -eq 0 ]]; then
  echo "❌ 守門檢查失敗：一個檔案都沒掃到，這道關卡形同虛設。"
  echo "   怎麼修：確認在 repo 根目錄執行 bash scripts/validate-no-leaks.sh。"
  exit 1
fi

# ---- git 追蹤狀態（非 git repo 時退回檔案系統檢查） --------------------------
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git ls-files > /tmp/opay-tracked-files.txt
  TRACKED_MODE="git"
else
  : > /tmp/opay-tracked-files.txt
  TRACKED_MODE="fs"
fi
echo "追蹤狀態來源：${TRACKED_MODE}（git = git ls-files；fs = 尚未 git init，改掃檔案系統）"

python3 - "$TRACKED_MODE" <<'PY'
import os, re, sys

MODE = sys.argv[1]

# 官方技術文件公開的測試環境值。這些是任何人都查得到的公開值，允許出現。
# 新增例外前請先確認：它必須是「官方文件白紙黑字印出來的測試值」，不是「我們自己的測試值」。
OFFICIAL_TEST_VALUES = {
    "ejCk326UnaZWKisg",   # i100 B2C 測試 HashKey
    "q9jcZX8Ib9LM8wYk",   # i100 B2C 測試 HashIV
    "s0j9fhLtzYRARFQh",   # i200 B2B 測試 HashKey
    "5awAqXlKm4NlNdEs",   # i200 B2B 測試 HashIV
    "9XWzRmj7UJESChyn",   # i301 離線 測試 HashKey
    "sriQzbe1llJqk67P",   # i301 離線 測試 HashIV
}

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".ico",
              ".woff", ".woff2", ".ttf", ".docx", ".xlsx", ".pptx"}

# -----------------------------------------------------------------------------
# 樣式規則。key = 規則名稱，value = (正規表示式, 怎麼修)
# 每一條都是在比對「值長什麼樣子」。
# -----------------------------------------------------------------------------
RULES = [
    ("Telegram bot token",
     re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,45}\b"),
     "把 token 移到 .env 的 TELEGRAM_BOT_TOKEN，並立刻到 @BotFather 執行 /revoke 重簽一組。"),
    ("Discord bot token",
     re.compile(r"\b[MNO][A-Za-z\d_-]{23,25}\.[\w-]{6}\.[\w-]{27,40}\b|\bmfa\.[\w-]{84}\b"),
     "把 token 移到 .env 的 DISCORD_BOT_TOKEN，並到 Developer Portal → Bot → Reset Token。"),
    ("GitHub personal access token",
     re.compile(r"\bghp_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
     "立刻到 GitHub → Settings → Developer settings 撤銷該 token，再改用 Actions secrets。"),
    ("AWS access key id",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
     "立刻到 IAM 停用該金鑰，改用 OIDC 或 Secrets Manager，不要放進 repo。"),
    ("AWS secret access key",
     re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}\b"),
     "立刻到 IAM 停用該金鑰組，改用 OIDC 或 Secrets Manager。"),
    ("私鑰 PEM 標頭",
     re.compile(r"-{5}BEGIN [A-Z ]*PRIVATE KEY-{5}"),
     "私鑰絕對不能進 repo。撤銷該金鑰、重簽一把，並用 .gitignore 擋掉 *.key / *.pem。"),
]

# HashKey / HashIV：兩條互補的規則
#  (a) 賦值語境：變數名稱旁邊直接跟著 16 碼值（擋 HASHKEY=abc... 寫死）
HASH_ASSIGN = re.compile(
    r"(?i)(hash[_-]?(?:key|iv))\s*[=:]\s*['\"]?([A-Za-z0-9]{16})(?![A-Za-z0-9])")
#  (b) 值的樣式：程式碼／設定檔中被引號包住的 16 碼「大小寫混合且含數字」字串，
#      這是 AES-128 金鑰的典型長相；純識別字（例如 GetInvoiceWordSe）不會同時滿足三種字元類。
QUOTED_16 = re.compile(r"['\"]([A-Za-z0-9]{16})['\"]")
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".php", ".html", ".json",
            ".yml", ".yaml", ".sh", ".env", ".example", ".toml", ".ini"}

def looks_like_key(v: str) -> bool:
    return (re.search(r"[a-z]", v) and re.search(r"[A-Z]", v) and re.search(r"\d", v))

findings = []
scanned = 0
env_files = []

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
        path = os.path.join(root, fn).replace("\\", "/")
        rel = path[2:] if path.startswith("./") else path
        ext = os.path.splitext(fn)[1].lower()
        if ext in BINARY_EXT:
            continue
        # .env（非 .env.example）本身就是紅燈
        base = os.path.basename(rel)
        if base == ".env" or (base.startswith(".env.") and not base.endswith(".example")):
            env_files.append(rel)
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for ln, line in enumerate(lines, 1):
            for name, rx, fix in RULES:
                m = rx.search(line)
                if m:
                    findings.append((rel, ln, name, m.group(0)[:24] + "…", fix))
            for m in HASH_ASSIGN.finditer(line):
                val = m.group(2)
                if val not in OFFICIAL_TEST_VALUES:
                    findings.append((rel, ln, "疑似寫死的 HashKey/HashIV",
                                     f"{m.group(1)}=…{val[-4:]}",
                                     "金鑰只能從環境變數讀（os.environ / getenv），"
                                     "把值搬到 .env 並確認 .env 已被 .gitignore 擋掉；"
                                     "若這把是正式環境金鑰，請立刻到歐付寶廠商後台重新產生。"))
            if ext in CODE_EXT or base.startswith(".env"):
                for m in QUOTED_16.finditer(line):
                    val = m.group(1)
                    if val in OFFICIAL_TEST_VALUES:
                        continue
                    if looks_like_key(val):
                        findings.append((rel, ln, "疑似 AES-128 金鑰字面值（16 碼混合大小寫含數字）",
                                         f"…{val[-4:]}",
                                         "如果這是金鑰，搬到 .env；如果這是官方文件的公開測試值，"
                                         "請把它加進本腳本的 OFFICIAL_TEST_VALUES 並在註解寫明出處。"))

print(f"實際讀取：{scanned} 個文字檔")
if scanned == 0:
    print("❌ 守門檢查失敗：讀不到任何文字檔。")
    print("   怎麼修：確認在 repo 根目錄執行。")
    sys.exit(1)

# ---- .env 追蹤檢查 -----------------------------------------------------------
tracked = set()
try:
    tracked = {l.strip() for l in open("/tmp/opay-tracked-files.txt", encoding="utf-8") if l.strip()}
except OSError:
    pass

for rel in env_files:
    if MODE == "git" and rel in tracked:
        findings.append((rel, 0, ".env 已被 git 追蹤", rel,
                         "執行 git rm --cached "+rel+" 並確認 .gitignore 有 .env；"
                         "已 commit 過的話，裡面的金鑰一律視為外洩，必須重新產生。"))
    else:
        findings.append((rel, 0, "工作目錄存在 .env", rel,
                         "本 repo 是公開發布的 Skill，不應該有真實 .env。"
                         "請刪除或改名為 .env.example（且值必須清空）。"))

print("")
if findings:
    print(f"❌ 關卡 2 未通過，共 {len(findings)} 個疑似外洩：")
    for i, (f, ln, name, sample, fix) in enumerate(findings, 1):
        loc = f"{f}:{ln}" if ln else f
        print(f"  {i:>3}. [{name}] {loc}")
        print(f"       疑似值：{sample}")
        print(f"       怎麼修：{fix}")
    sys.exit(1)

print("✅ 關卡 2 通過：沒有掃到任何疑似金鑰、token、私鑰或被追蹤的 .env。")
PY
