#!/usr/bin/env bash
# =============================================================================
# 關卡 1／API 覆蓋率檢查（本 repo 最重要的一道關卡）
#
# 這道關卡守的承諾是：「69 支 API 一支都不能漏」。
# 唯一權威（SSOT）是 references/api-coverage.json，其他所有檔案都必須跟它對齊。
#
# 檢查項目：
#   1. 守門：SSOT 檔存在且解析得出 > 0 筆 endpoint（掃不到東西就直接紅燈）
#   2. 每一筆的 ref 檔存在，且檔中出現該 endpoint 名稱
#   3. 每一筆的 guide 檔存在，且檔中出現該 endpoint 名稱
#   4. 三支 client（python / nodejs / php）都各有對應的 post("<path>") 呼叫
#   5. 反向檢查：三份 reference 的 `## ` 標題中出現的 endpoint 名稱，
#      若不在 SSOT 清單中即紅燈（防止「加了 API 卻沒登記進 SSOT」）
#   6. 統計：B2C 30/30、B2B 27/27、離線 12/12、合計 69/69
#
# 用法：bash scripts/validate-api-coverage.sh
# 退出碼：0 = 全綠；1 = 有缺漏或不一致
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SSOT="references/api-coverage.json"

echo "──────────────────────────────────────────────────────────────"
echo "關卡 1／API 覆蓋率檢查（SSOT：${SSOT}）"
echo "──────────────────────────────────────────────────────────────"

# ---- 守門檢查：先確認我真的掃得到東西 -------------------------------------
# 一個掃不到任何檔案的守門腳本會永遠是綠的，而且沒有人會發現，那比沒有這道關卡更糟。
if [[ ! -f "$SSOT" ]]; then
  echo "❌ 找不到 SSOT 檔：${SSOT}"
  echo "   怎麼修：這支腳本沒有它就沒有任何判斷依據。請確認在 repo 根目錄執行，"
  echo "           或從 git 還原 ${SSOT}。"
  exit 1
fi

python3 - "$SSOT" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print(f"❌ SSOT JSON 解析失敗：{exc}")
    print("   怎麼修：用 python3 -m json.tool references/api-coverage.json 找出壞掉的那一行。")
    sys.exit(1)
n = len(d.get("endpoints", []))
if n == 0:
    print("❌ 守門檢查失敗：SSOT 解析出 0 筆 endpoint。")
    print("   怎麼修：檢查 references/api-coverage.json 的 endpoints 陣列是不是空的或被改名了。")
    sys.exit(1)
sys.exit(0)
PY

python3 - <<'PY'
# -----------------------------------------------------------------------------
# 主檢查邏輯。所有失敗訊息都要指出「哪一支 API／哪一個檔案／怎麼修」。
# -----------------------------------------------------------------------------
import json, os, re, sys

SSOT = "references/api-coverage.json"
CLIENTS = {
    "python": "templates/opay-einvoice-client/python/opay_einvoice.py",
    "nodejs": "templates/opay-einvoice-client/nodejs/opay-einvoice.js",
    "php":    "templates/opay-einvoice-client/php/OPayEInvoice.php",
}
REF_FILES = [
    "references/b2c-api-reference.md",
    "references/b2b-api-reference.md",
    "references/offline-api-reference.md",
]
SRC_LABEL = {"i100": "B2C", "i200": "B2B", "i301": "離線"}

doc = json.load(open(SSOT, encoding="utf-8"))
endpoints = doc["endpoints"]
expected = {s["id"]: s["endpoints"] for s in doc["sources"]}

errors = []      # 每一筆 = 一行紅字
warned = 0

# ---- 守門統計：印出我掃到多少東西 -------------------------------------------
ref_files_found = [p for p in REF_FILES if os.path.isfile(p)]
client_files_found = {k: p for k, p in CLIENTS.items() if os.path.isfile(p)}
guide_files = sorted({e["guide"] for e in endpoints})
guide_files_found = [p for p in guide_files if os.path.isfile(p)]

print(f"掃描範圍：SSOT {len(endpoints)} 筆 endpoint、"
      f"reference {len(ref_files_found)}/{len(REF_FILES)} 檔、"
      f"guide {len(guide_files_found)}/{len(guide_files)} 檔、"
      f"client {len(client_files_found)}/{len(CLIENTS)} 支")

if len(endpoints) == 0 or not ref_files_found or not client_files_found or not guide_files_found:
    print("❌ 守門檢查失敗：掃描範圍中有一類完全掃不到檔案，這道關卡形同虛設。")
    print("   怎麼修：確認在 repo 根目錄執行，且 references/ templates/ guides/ 都在。")
    sys.exit(1)

# ---- 讀檔（一次讀完，後面重複比對） ------------------------------------------
def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()

cache = {}
def text_of(path):
    if path not in cache:
        cache[path] = read(path) if os.path.isfile(path) else None
    return cache[path]

# ---- 檢查 2／3：ref 與 guide 是否收錄該 endpoint ------------------------------
for e in endpoints:
    ep = e["path"].rsplit("/", 1)[-1]         # endpoint 名稱，例如 Issue
    tag = f'{SRC_LABEL[e["src"]]} §{e["ch"]} {e["name"]}（{e["path"]}）'

    ref_text = text_of(e["ref"])
    if ref_text is None:
        errors.append(f'{tag}｜ref 檔不存在：{e["ref"]}'
                      f'｜怎麼修：建立該檔，或修正 {SSOT} 中這一筆的 ref 欄位。')
    elif not re.search(r'^##\s.*`%s`' % re.escape(ep), ref_text, re.M) and ep not in ref_text:
        errors.append(f'{tag}｜ref 檔 {e["ref"]} 中找不到 endpoint 名稱「{ep}」'
                      f'｜怎麼修：在該檔補上「## N. 中文名 — `{ep}`」整節規格。')

    guide_text = text_of(e["guide"])
    if guide_text is None:
        errors.append(f'{tag}｜guide 檔不存在：{e["guide"]}'
                      f'｜怎麼修：建立該教學檔，或修正 {SSOT} 中這一筆的 guide 欄位。')
    elif ep not in guide_text:
        errors.append(f'{tag}｜guide 檔 {e["guide"]} 中找不到 endpoint 名稱「{ep}」'
                      f'｜怎麼修：在該指南中實際講到這支 API（至少出現一次 `{ep}`）。')

# ---- 檢查 4：三支 client 都要有對應方法 --------------------------------------
# 三種語言的呼叫寫法：self._post("/x")、this._post('/x')、$this->post('/x')
for name, path in CLIENTS.items():
    t = text_of(path)
    if t is None:
        errors.append(f'client 檔不存在：{path}'
                      f'｜怎麼修：三支 client 是本 Skill 的可執行證明，缺一不可。')
        continue
    for e in endpoints:
        pat = r"""post\(\s*['"]%s['"]""" % re.escape(e["path"])
        if not re.search(pat, t):
            errors.append(
                f'{SRC_LABEL[e["src"]]} {e["name"]}（{e["path"]}）｜'
                f'{name} client 缺對應方法（{path} 中找不到 post("{e["path"]}")）'
                f'｜怎麼修：在該 client 補一個方法，最後一行 return 呼叫 post("{e["path"]}", ...)。')

# ---- 檢查 5：反向檢查（reference 有、SSOT 沒有 → 紅燈） -----------------------
ssot_names = {e["path"].rsplit("/", 1)[-1] for e in endpoints}
heading_re = re.compile(r'^##\s+\d+\.\s.*?`([A-Za-z][A-Za-z0-9_]*)`')
reverse_seen = 0
for path in REF_FILES:
    t = text_of(path)
    if t is None:
        errors.append(f'reference 檔不存在：{path}｜怎麼修：三份 reference 缺一不可。')
        continue
    for ln, line in enumerate(t.split("\n"), 1):
        m = heading_re.match(line)
        if not m:
            continue
        reverse_seen += 1
        ep = m.group(1)
        if ep not in ssot_names:
            errors.append(
                f'反向檢查：{path}:{ln} 出現未登記的 endpoint「{ep}」'
                f'｜怎麼修：把這支 API 補進 {SSOT} 的 endpoints 陣列（含 src/ch/name/path/ref/guide），'
                f'否則它永遠不會被覆蓋率檢查守到。')

if reverse_seen == 0:
    errors.append('反向檢查守門失敗：三份 reference 中掃不到任何「## N. 中文名 — `Endpoint`」標題。'
                  '｜怎麼修：標題格式若改過，請同步更新本腳本的 heading_re，否則這項檢查等於沒跑。')
else:
    print(f"反向檢查：從 reference 標題掃到 {reverse_seen} 個 endpoint 名稱")

# ---- 統計 -------------------------------------------------------------------
print("")
print("覆蓋率統計：")
total_ok = 0
for src in ("i100", "i200", "i301"):
    got = sum(1 for e in endpoints if e["src"] == src)
    want = expected[src]
    mark = "✅" if got == want else "❌"
    print(f"  {mark} {SRC_LABEL[src]:<3} {got}/{want}")
    total_ok += got
    if got != want:
        errors.append(f'{SRC_LABEL[src]} 數量不符：SSOT endpoints 有 {got} 筆，'
                      f'但 sources 宣告應為 {want} 筆'
                      f'｜怎麼修：兩邊對齊，並確認官方文件章節數沒有變動。')
grand = sum(expected.values())
mark = "✅" if total_ok == grand else "❌"
print(f"  {mark} 合計 {total_ok}/{grand}")
if grand != 69:
    errors.append(f'合計應為 69 支，但 SSOT sources 宣告為 {grand} 支'
                  f'｜怎麼修：69 是本 Skill 對外承諾的數字，改動前請先更新 README 與 SKILL.md。')

# ---- 結果 -------------------------------------------------------------------
print("")
if errors:
    print(f"❌ 關卡 1 未通過，共 {len(errors)} 個問題：")
    for i, msg in enumerate(errors, 1):
        print(f"  {i:>3}. {msg}")
    sys.exit(1)

print(f"✅ 關卡 1 通過：{len(endpoints)} 支 API 全數在 reference、guide、三支 client 中有對應，且無未登記的 API。")
PY
