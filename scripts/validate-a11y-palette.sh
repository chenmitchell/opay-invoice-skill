#!/usr/bin/env bash
# =============================================================================
# 關卡 5／圖表無障礙與配色檢查
#
# 這道關卡守的承諾是：「所有圖表配色只能用九色核可色盤，且必附純文字重述」。
# 看不到圖的人（螢幕閱讀器使用者、色覺障礙者、純文字模式的 AI）也必須讀得懂。
#
# 檢查項目（掃全 repo 的 markdown，逐個 mermaid 區塊）：
#   1. 守門：確認掃到 > 0 個 mermaid 區塊
#   2. 每個 fill: 顏色必須落在九色核可色盤內
#   3. 區塊「前」必須有 🧭 純文字重述
#   4. 區塊「後」必須有 ♿ 配色註記
#   5. stateDiagram 不支援節點 fill:，豁免 fill 檢查，但仍須有 🧭 與 ♿
#   6. 非 stateDiagram 的區塊若一個 fill: 都沒有 → 紅燈（代表沒套配色）
#
# 用法：bash scripts/validate-a11y-palette.sh
# 退出碼：0 = 全綠；1 = 有配色或重述缺漏
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 5／Mermaid 圖表無障礙與九色核可色盤檢查"
echo "──────────────────────────────────────────────────────────────"

python3 - <<'PY'
import os, re, sys

# 九色核可色盤。全部對白字達 WCAG AAA（對比 ≥ 7:1），且對三種常見色覺障礙可辨。
# 要新增顏色必須先更新 docs/accessibility.md 並附對比度數據，不能只改這裡。
PALETTE = {
    "#1E3A8A": "深藍",
    "#3730A3": "靛藍",
    "#581C87": "深紫",
    "#164E63": "深青",
    "#134E4A": "深藍綠",
    "#78350F": "深棕",
    "#1F2937": "深灰",
    "#14532D": "深綠",
    "#7F1D1D": "深紅",
}

FENCE = re.compile(r"^(\s*)(```|~~~)\s*mermaid\s*$", re.I)
FENCE_END = re.compile(r"^\s*(```|~~~)\s*$")
FILL = re.compile(r"fill\s*:\s*(#[0-9A-Fa-f]{3,8})")
LOOKBACK = 8   # 🧭 允許出現在區塊前幾行內
LOOKAHEAD = 8  # ♿ 允許出現在區塊後幾行內

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}

md_files = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fn in files:
        if fn.lower().endswith(".md"):
            md_files.append(os.path.join(root, fn).replace("\\", "/").lstrip("./"))
md_files.sort()

errors = []
blocks = 0
fills_total = 0

for path in md_files:
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except (UnicodeDecodeError, OSError):
        continue
    i = 0
    while i < len(lines):
        if not FENCE.match(lines[i]):
            i += 1
            continue
        start = i
        j = i + 1
        while j < len(lines) and not FENCE_END.match(lines[j]):
            j += 1
        blocks += 1
        body = "\n".join(lines[start + 1:j])
        loc = f"{path}:{start + 1}"

        is_state = "stateDiagram" in body
        fills = FILL.findall(body)
        fills_total += len(fills)

        for c in fills:
            if c.upper() not in PALETTE:
                errors.append(
                    f'{loc}｜fill:{c} 不在九色核可色盤內\n'
                    f'       怎麼修：改用下列其中一色 —— '
                    + "、".join(f"{k}（{v}）" for k, v in PALETTE.items())
                    + "；若真的需要新色，請先在 docs/accessibility.md 補上對比度與色覺障礙驗證數據。")

        if not fills and not is_state:
            errors.append(
                f'{loc}｜這個 mermaid 區塊沒有任何 fill: 樣式\n'
                f'       怎麼修：用 style／classDef 為每個節點套上九色核可色盤，'
                f'預設配色的對比度不足，色覺障礙者無法區分。'
                f'（stateDiagram 不支援節點 fill:，才可以豁免。）')

        has_compass = any("🧭" in lines[k] for k in range(max(0, start - LOOKBACK), start))
        has_a11y = any("♿" in lines[k] for k in range(j + 1, min(len(lines), j + 1 + LOOKAHEAD)))

        if not has_compass:
            errors.append(
                f'{loc}｜區塊前 {LOOKBACK} 行內找不到 🧭 純文字重述\n'
                f'       怎麼修：在圖前加一行 '
                f'「> 🧭 **純文字重述（螢幕閱讀器友善）**：……」，'
                f'用完整句子把節點與流向講一遍，不要寫「如上圖」。')
        if not has_a11y:
            errors.append(
                f'{loc}｜區塊後 {LOOKAHEAD} 行內找不到 ♿ 配色註記\n'
                f'       怎麼修：在圖後加一行 '
                f'「> ♿ 配色遵循 [`docs/accessibility.md`](…)：WCAG AAA 對比 ≥7:1、'
                f'色盲安全色盤、圖示＋文字雙編碼。」')
        i = j + 1

print(f"掃描範圍：{len(md_files)} 個 markdown 檔，"
      f"共 {blocks} 個 mermaid 區塊、{fills_total} 個 fill: 宣告")

# ---- 守門檢查 ---------------------------------------------------------------
if not md_files:
    print("❌ 守門檢查失敗：一個 markdown 檔都沒掃到。")
    print("   怎麼修：確認在 repo 根目錄執行 bash scripts/validate-a11y-palette.sh。")
    sys.exit(1)
if blocks == 0:
    print("❌ 守門檢查失敗：整個 repo 掃不到任何 mermaid 區塊。")
    print("   本 repo 的 guides/ 依設計有大量流程圖，完全掃不到代表比對規則壞掉了")
    print("   （例如 code fence 寫法改了）。怎麼修：手動 grep -rn '```mermaid' . 確認，")
    print("   再檢查本腳本的 FENCE 規則。")
    sys.exit(1)

print("")
if errors:
    print(f"❌ 關卡 5 未通過，共 {len(errors)} 個問題：")
    for i, msg in enumerate(errors, 1):
        print(f"  {i:>3}. {msg}")
    sys.exit(1)

print(f"✅ 關卡 5 通過：{blocks} 個 mermaid 區塊全數使用九色核可色盤，"
      f"且每個都有 🧭 純文字重述與 ♿ 配色註記。")
PY
