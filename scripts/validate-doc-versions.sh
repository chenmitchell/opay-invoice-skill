#!/usr/bin/env bash
# =============================================================================
# 關卡 7／官方文件版本一致性檢查
#
# 這道關卡守的是：三份官方技術文件的版本字串在全 repo 必須一致。
# 版本升級時最常見的錯誤是「只改了一處」——README 改了但 reference 沒改，
# 於是 AI 會同時看到兩個版本號，而使用者不知道該信哪一個。
#
# 期望值（本 Skill 對外承諾的基準版本）：
#   B2C  i100  V1.6.0（2026-01-06）
#   B2B  i200  V1.2.0（2025-09-10）
#   離線 i301  V1.3.0（2025-09-10）
#
# 檢查項目：
#   1. 守門：確認掃到 > 0 個檔案、> 0 個「文件名稱＋版本」配對
#   2. references/api-coverage.json 的 sources 版本／日期必須等於上述期望值
#   3. 全 repo 每一處「《…介接技術文件》…V1.x.y」的配對版本必須正確
#      （比對範圍限定在該書名號到下一個書名號之間，同一行提到多份文件也能各自比對）
#   4. 同一段若同時寫了日期（YYYY-MM-DD），日期也必須正確
#   5. 三份 reference 檔的開頭來源標註必須各自出現自己的版本
#   6. 每個版本字串至少要出現在 3 個不同檔案，避免「只改了一處」卻仍然全綠
#
# 版本沿革表（例如「V1.5.0 新增」「V1.4.0 調整」）不使用書名號，不會被誤判。
#
# 用法：bash scripts/validate-doc-versions.sh
# 退出碼：0 = 全綠；1 = 版本不一致
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 7／官方文件版本一致性檢查"
echo "──────────────────────────────────────────────────────────────"

python3 - <<'PY'
import json, os, re, sys

EXPECTED = {
    "i100": {"label": "B2C",  "version": "V1.6.0", "date": "2026-01-06",
             "title_key": "B2C介接技術文件",
             "ref": "references/b2c-api-reference.md"},
    "i200": {"label": "B2B",  "version": "V1.2.0", "date": "2025-09-10",
             "title_key": "B2B介接技術文件",
             "ref": "references/b2b-api-reference.md"},
    "i301": {"label": "離線", "version": "V1.3.0", "date": "2025-09-10",
             "title_key": "離線電子發票介接技術文件",
             "ref": "references/offline-api-reference.md"},
}

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
SCAN_EXT = {".md", ".txt", ".json", ".py", ".js", ".php", ".yml", ".yaml", ".cff"}
VER = re.compile(r"V\d+\.\d+\.\d+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

errors = []

# ---- 檢查 2：SSOT 自己的版本 --------------------------------------------------
ssot_path = "references/api-coverage.json"
if not os.path.isfile(ssot_path):
    print(f"❌ 守門檢查失敗：找不到 {ssot_path}。")
    sys.exit(1)
ssot = json.load(open(ssot_path, encoding="utf-8"))
for s in ssot["sources"]:
    exp = EXPECTED.get(s["id"])
    if not exp:
        errors.append(f'{ssot_path}｜出現未知的來源文件 id「{s["id"]}」'
                      f'｜怎麼修：新增文件時請同步更新本腳本的 EXPECTED。')
        continue
    if s.get("doc_version") != exp["version"]:
        errors.append(f'{ssot_path}｜{exp["label"]}（{s["id"]}）doc_version 是 '
                      f'{s.get("doc_version")}，期望 {exp["version"]}'
                      f'｜怎麼修：版本升級要「同一次 commit 改完所有地方」，'
                      f'先改 SSOT，再跑本腳本把其餘不一致的地方一次抓出來。')
    if s.get("doc_date") != exp["date"]:
        errors.append(f'{ssot_path}｜{exp["label"]}（{s["id"]}）doc_date 是 '
                      f'{s.get("doc_date")}，期望 {exp["date"]}'
                      f'｜怎麼修：日期與版本必須成對更新。')

# ---- 掃描全 repo ------------------------------------------------------------
files = []
for root, dirs, fs in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in fs:
        if os.path.splitext(fn)[1].lower() in SCAN_EXT:
            p = os.path.join(root, fn).replace("\\", "/")
            files.append(p[2:] if p.startswith("./") else p)
files.sort()

pairs = 0                       # 找到幾組「文件名稱 + 版本」配對
seen_files = {k: set() for k in EXPECTED}   # 每個版本出現在哪些檔案

for path in files:
    if path.startswith("scripts/"):
        continue                # 腳本自己就是期望值的定義處，不列入比對
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except (UnicodeDecodeError, OSError):
        continue
    for ln, line in enumerate(lines, 1):
        if "介接技術文件" not in line:
            continue
        # 以書名號「《」切段，讓同一行提到多份文件時能各自比對
        for seg in line.split("《")[1:]:
            seg = seg.split("《")[0]
            hit = None
            for key, exp in EXPECTED.items():
                if exp["title_key"] in seg:
                    hit = (key, exp)
                    break
            if not hit:
                continue
            key, exp = hit
            vm = VER.search(seg)
            if not vm:
                continue        # 只提到文件名稱、沒寫版本，不強制
            pairs += 1
            seen_files[key].add(path)
            if vm.group(0) != exp["version"]:
                errors.append(
                    f'{path}:{ln}｜{exp["label"]}文件標為 {vm.group(0)}，'
                    f'期望 {exp["version"]}\n'
                    f'       原文：{line.strip()[:110]}\n'
                    f'       怎麼修：把這一處改成 {exp["version"]}；'
                    f'若確實是官方升版，請先改 {ssot_path} 與本腳本的 EXPECTED，'
                    f'再一次改完全 repo。')
            dm = DATE.search(seg)
            if dm and dm.group(0) != exp["date"]:
                errors.append(
                    f'{path}:{ln}｜{exp["label"]}文件日期標為 {dm.group(0)}，'
                    f'期望 {exp["date"]}\n'
                    f'       原文：{line.strip()[:110]}\n'
                    f'       怎麼修：版本與日期必須成對，改完記得同步 {ssot_path}。')

print(f"掃描範圍：{len(files)} 個檔案，找到 {pairs} 組「官方文件名稱 + 版本」配對")

# ---- 守門檢查 ---------------------------------------------------------------
if not files:
    print("❌ 守門檢查失敗：一個檔案都沒掃到。")
    print("   怎麼修：確認在 repo 根目錄執行 bash scripts/validate-doc-versions.sh。")
    sys.exit(1)
if pairs == 0:
    print("❌ 守門檢查失敗：掃不到任何「《…介接技術文件》…V1.x.y」配對。")
    print("   本 repo 的 references／README／CHANGELOG 依設計一定會標註來源文件版本，")
    print("   完全掃不到代表比對規則壞掉了（例如書名號被改成引號）。")
    print("   怎麼修：手動 grep -rn '介接技術文件' . 確認，再檢查本腳本的切段邏輯。")
    sys.exit(1)

# ---- 檢查 5：三份 reference 開頭必須標自己的版本 ------------------------------
for key, exp in EXPECTED.items():
    p = exp["ref"]
    if not os.path.isfile(p):
        errors.append(f'找不到 {p}｜怎麼修：三份 reference 缺一不可。')
        continue
    head = "\n".join(open(p, encoding="utf-8").read().split("\n")[:10])
    if exp["version"] not in head:
        errors.append(
            f'{p}｜檔案開頭 10 行內找不到版本字串 {exp["version"]}'
            f'｜怎麼修：在檔案開頭的「> **來源**：」那一行標明 '
            f'{exp["version"]}（{exp["date"]}），讀者與 AI 才知道這份規格對應哪一版。')

# ---- 檢查 6：避免「只改了一處」 ----------------------------------------------
MIN_FILES = 3
for key, exp in EXPECTED.items():
    n = len(seen_files[key])
    if n < MIN_FILES:
        errors.append(
            f'{exp["label"]}（{exp["version"]}）只在 {n} 個檔案中標註（門檻 {MIN_FILES}）：'
            f'{sorted(seen_files[key]) or "無"}\n'
            f'       怎麼修：這個門檻的用意是抓「版本升級只改了一處」。'
            f'請確認 references／README／CHANGELOG 三處都有同步標註。')

print("")
print("版本標註分布：")
for key, exp in EXPECTED.items():
    print(f"  · {exp['label']:<3} {exp['version']}（{exp['date']}）"
          f"｜出現在 {len(seen_files[key])} 個檔案")

print("")
if errors:
    print(f"❌ 關卡 7 未通過，共 {len(errors)} 個問題：")
    for i, msg in enumerate(errors, 1):
        print(f"  {i:>3}. {msg}")
    sys.exit(1)

print("✅ 關卡 7 通過：三份官方文件的版本與日期在全 repo 一致。")
PY
