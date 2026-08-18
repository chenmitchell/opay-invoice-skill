#!/usr/bin/env bash
# =============================================================================
# 關卡 6／內部連結檢查
#
# 這道關卡守的是最基本的可用性：文件互相引用的相對連結必須指得到真實檔案。
# 一份 AI Skill 的價值來自「AI 能沿著連結找到規格」，斷鏈等於斷了檢索路徑。
#
# 檢查項目：
#   1. 守門：確認掃到 > 0 個 markdown 檔、> 0 條內部連結
#   2. 所有 markdown 的相對連結（含圖片 ![](…)）目標檔案必須存在
#   3. 外部連結（http/https/mailto/tel）不檢查（由 validate-references.yml 每週非阻斷檢查）
#   4. 純錨點連結（#section）不檢查目標，只檢查檔案部分
#   5. 程式碼區塊（``` / ~~~）內的連結是「示範文字」，不列入檢查
#
# 用法：bash scripts/validate-links.sh
# 退出碼：0 = 全綠；1 = 有斷鏈
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 6／Markdown 內部相對連結檢查"
echo "──────────────────────────────────────────────────────────────"

python3 - <<'PY'
import os, re, sys, urllib.parse

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile(r"^\s*(```|~~~)")
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")

md_files = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
        if fn.lower().endswith(".md"):
            p = os.path.join(root, fn).replace("\\", "/")
            md_files.append(p[2:] if p.startswith("./") else p)
md_files.sort()

errors = []
internal = 0
external = 0

for path in md_files:
    base = os.path.dirname(path)
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except (UnicodeDecodeError, OSError):
        continue
    in_fence = False
    for ln, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in LINK.finditer(line):
            target = m.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if target.startswith(EXTERNAL):
                external += 1
                continue
            if target.startswith("#"):
                continue          # 同檔錨點，不檢查
            internal += 1
            file_part = urllib.parse.unquote(target.split("#", 1)[0])
            if not file_part:
                continue
            resolved = os.path.normpath(os.path.join(base, file_part))
            if not os.path.exists(resolved):
                errors.append(
                    f'{path}:{ln}｜連結目標不存在：{target}\n'
                    f'       解析後路徑：{resolved}\n'
                    f'       怎麼修：確認檔案是否被改名／搬移；'
                    f'相對路徑是以「{path} 所在目錄」為基準，'
                    f'從 guides/ 或 references/ 指向 docs/ 要寫成 ../docs/…。')

print(f"掃描範圍：{len(md_files)} 個 markdown 檔，"
      f"內部相對連結 {internal} 條、外部連結 {external} 條（外部不檢查）")

# ---- 守門檢查 ---------------------------------------------------------------
if not md_files:
    print("❌ 守門檢查失敗：一個 markdown 檔都沒掃到。")
    print("   怎麼修：確認在 repo 根目錄執行 bash scripts/validate-links.sh。")
    sys.exit(1)
if internal == 0:
    print("❌ 守門檢查失敗：掃不到任何內部相對連結。")
    print("   本 repo 的文件之間大量互相引用，完全掃不到代表比對規則壞掉了。")
    print("   怎麼修：檢查本腳本的 LINK 正規表示式。")
    sys.exit(1)

print("")
if errors:
    print(f"❌ 關卡 6 未通過，共 {len(errors)} 條斷鏈：")
    for i, msg in enumerate(errors, 1):
        print(f"  {i:>3}. {msg}")
    sys.exit(1)

print(f"✅ 關卡 6 通過：{internal} 條內部相對連結全數指向存在的檔案。")
PY
