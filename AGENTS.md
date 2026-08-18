# AGENTS.md — 歐付寶電子發票 Skill

> 本檔遵循 [AGENTS.md](https://agents.md/) 慣例，供 **OpenAI Codex**、**Agents SDK** 及相容的 agent 工具讀取。
> 人類請讀 [`README.md`](README.md)。

---

## Project overview

`opay-invoice-skill` 是**非官方、由 Mitchell Chen 個人撰寫維護**的歐付寶（O'Pay）電子發票 API 知識庫與程式碼模板集，涵蓋 **69 支 API**：B2C 30、B2B 27、離線 12。

**Disclaimer / 非官方聲明**：本專案未經歐付寶電子支付股份有限公司審閱、認可或背書，與該公司無從屬或合作關係。不保證完整正確，不構成法律／稅務／會計意見，不宣稱法規符合性。**與官方文件不一致時以官方文件為準。**

**目標對象**：台灣的後端工程師。輸出語言為**繁體中文（台灣用語）**。

---

## Context loading order

處理任何電子發票相關任務前，依序讀取：

1. `SKILL.md` **§0**（核心規則，最優先）
2. `references/api-coverage.json`（SSOT，69 支 API 索引；檔案小，可整檔讀）
3. `references/b2c-api-reference.md` / `b2b-api-reference.md` / `offline-api-reference.md`（**只讀相關章節**，三檔合計 > 11,500 行）
4. `references/enums.md`（列舉值，含「同名不同義的陷阱」）
5. `references/encryption-aes.md` + `references/urlencode-table.md`（涉及加密時）
6. `references/error-handling.md`（涉及錯誤與重試時）
7. `guides/NN-*.md`（對應主題的整合指南）
8. `templates/opay-einvoice-client/`（優先複用既有實作）

**檢索建議**：用 `rg '<EndpointName>' references/` 定位，再讀該區段。每支 API 的規格起點是 `## N. 中文名 — \`EndpointName\`` 標題。

---

## 🚨 Four inviolable rules

### ① 加密是 AES-128-CBC/PKCS7，不是 `CheckMacValue`

```
plaintext JSON → URLEncode (.NET convention) → AES-128-CBC/PKCS7 → Base64 → Data field
```

- Key = `HashKey`（16 ASCII chars，直接當 raw bytes；**不做 MD5、不做 Base64 decode、不補零**）
- IV = `HashIV`（同上）
- URLEncode 用 **.NET 慣例**：space → `+`（非 `%20`）；`!` `*` `(` `)` **不編碼**
- **請求中沒有 `CheckMacValue` 欄位。** `CheckMacValue` / SHA256 / MD5 是綠界 ECPay 的做法。

若你正要寫出 `CheckMacValue` / `hashlib.sha256` / `crypto.createHash('sha256')`，**停下來重讀 `references/encryption-aes.md`**。

### ② 正式環境不得用 `Issue` 做健康檢查

`Issue` 產生**真實發票**、消耗**字軌號碼**，且**只能作廢不能刪除**。
連通性檢查請用唯讀 API（`GetInvoiceWordSetting` / `CheckBarcode` / `GetCompanyNameByTaxID`）；加密驗證用 `test-vectors/`（不連網）。

### ③ 開立／作廢／折讓／註銷重開不可盲目重試

逾時 ≠ 沒開立。重送 = 可能開出兩張發票。
正確流程：**逾時 → `GetIssue` 帶原 `RelateNumber` 查詢 → 查到補記錄，查無才可帶同一冪等鍵重送。**

| 可否自動重試 | API |
|---|---|
| ❌ **不可** | `Issue`、`DelayIssue`、`OfflineIssue`、`Invalid`、`OfflineInvalid`、`Allowance`、`AllowanceByCollegiate`、`AllowanceInvalid`、`AllowanceInvalidByCollegiate`、`VoidWithReIssue`、所有 B2B 的 `Xxx` 與 `XxxConfirm` |
| ✅ 可（指數退避） | 所有 `Get*` 查詢類、`Check*` 驗證類 |

**不要在上述不可重試的 API 外面套通用 retry wrapper 或 `tenacity` / `p-retry` decorator。**

### ④ `HashKey` / `HashIV` 只進 `.env`

只從環境變數讀。**嚴禁**寫死於程式碼、commit 進 git、出現在前端 JS/HTML/CSS、寫入 log。
範例程式碼一律用環境變數；示範值只用官方公開的**測試環境**值並標註「僅測試環境」。

---

## API surface (69 endpoints)

| Group | Count | Prefix | Key endpoints |
|---|---|---|---|
| B2C 字軌 | 3 | `/B2CInvoice` | `GetGovInvoiceWordSetting`, `AddInvoiceWordSetting`, `UpdateInvoiceWordStatus` |
| B2C 開立 | 4 | `/B2CInvoice` | `Issue`, `DelayIssue`, `TriggerIssue`, `CancelDelayIssue` |
| B2C 折讓 | 2 | `/B2CInvoice` | `Allowance`, `AllowanceByCollegiate` |
| B2C 作廢 | 4 | `/B2CInvoice` | `Invalid`, `AllowanceInvalid`, `AllowanceInvalidByCollegiate`, `VoidWithReIssue` |
| B2C 查詢 | 5 | `/B2CInvoice` | `GetIssue`, `GetAllowanceList`, `GetInvalid`, `GetAllowanceInvalid`, `GetInvoiceWordSetting` |
| B2C 通知列印 | 2 | `/B2CInvoice` | `InvoiceNotify`, `InvoicePrint` |
| B2C 驗證 | 3 | `/B2CInvoice` | `CheckBarcode`, `CheckLoveCode`, `GetCompanyNameByTaxID` |
| B2C 通知設定 | 4 | `/B2CInvoice` | `GetInvoiceNotifySetting`, `InvoiceNotifySetting`, `GetRemainNotifySetting`, `RemainNotifySetting` |
| B2C 空白發票 | 3 | `/B2CInvoice` | `QueryBlankInvoiceList`, `BlankInvAutoUploadSetting`, `DownLoadBlankInvList` |
| B2B 前置 | 4 | `/B2BInvoice` | `MaintainMerchantCustomerData`, `Notify`, `AddInvoiceWordSetting`, `UpdateInvoiceWordStatus` |
| B2B 動作＋確認 | 11 | `/B2BInvoice` | `Issue`/`IssueConfirm`, `Invalid`/`InvalidConfirm`, `Reject`/`RejectConfirm`, `Allowance`/`AllowanceConfirm`, `CancelAllowance`/`CancelAllowanceConfirm`, `VoidWithReIssue` |
| B2B 查詢 | 12 | `/B2BInvoice` | `GetIssue` … `GetAllowanceInvalidConfirm`, `GetInvoiceWordSetting`, `GetCompanyNameByTaxID` |
| 離線 | 12 | `/B2CInvoice` | `GetOfflineMerchantInfo`, `OfflineMerchantPosSetting`, `GetOfflineInvoiceWordSetting*`, `OfflineIssue`, `OfflineInvalid` |

完整逐支清單：`references/api-coverage.json`。

**三類差異**：B2C 上傳期限 **48 小時**、B2B **7 天**、離線 **48 小時**；離線的路徑前綴是 **`/B2CInvoice`**（不是 `/OfflineInvoice`）；B2B 交換模式下每個動作都要成對的 `XxxConfirm`。

---

## Environment

| | Stage | Production |
|---|---|---|
| Host | `https://einvoice-stage.opay.tw` | `https://einvoice.opay.tw` |
| Vendor portal | `https://vendor-stage.opay.tw` | `https://vendor.opay.tw` |

- `POST` / `application/json` / TLS 1.2+ / port 443 only
- 外層欄位：`PlatformID`（一般廠商留空）、`MerchantID`、`RqHeader.Timestamp`、`Data`
- `Timestamp` 驗證區間 **10 分鐘**（主機須校時）
- **兩層回應碼**：`TransCode`（外層，`1` = OK）、`RtnCode`（解密後，`1` = OK）

Stage credentials（官方公開值，**僅測試環境**）：
- B2C：`2000132` / `ejCk326UnaZWKisg` / `q9jcZX8Ib9LM8wYk`
- Offline：`2045501` / `9XWzRmj7UJESChyn` / `sriQzbe1llJqk67P`

---

## Setup & validation commands

```bash
# 加密測試向量（無網路需求；期望輸出 4/4 pass）
node    test-vectors/verify-node.js          # 零相依，沙箱中優先用這支
pip install pycryptodome && python3 test-vectors/verify.py

# client 自我測試（不發任何網路請求）
python3 templates/opay-einvoice-client/python/opay_einvoice.py
node    templates/opay-einvoice-client/nodejs/opay-einvoice.js
php     templates/opay-einvoice-client/php/OPayEInvoice.php

# 測試主控台（僅測試環境）
cp templates/opay-test-console/.env.example templates/opay-test-console/.env
python3 -m pip install fastapi uvicorn requests pycryptodome
python3 -m uvicorn backend:app --reload --port 8080
```

**Definition of done**：任何涉及加密的變更，`4/4 pass` 是最低門檻。

---

## Sandbox & network policy

| 動作 | 政策 |
|---|---|
| `test-vectors/verify-node.js` | ✅ 隨時可跑（零相依、不連網） |
| `test-vectors/verify.py` | ✅ 可跑（需先安裝 `pycryptodome`） |
| client 自我測試 | ✅ 可跑（不連網） |
| 對 `einvoice-stage.opay.tw` 的**唯讀** API | ⚠️ 需使用者明確要求 |
| 對 `einvoice-stage.opay.tw` 的**開立／作廢／折讓** | ⛔ 必須逐次取得使用者確認 |
| 對 `einvoice.opay.tw`（正式環境）的**任何**請求 | ⛔ **絕對禁止自動發送** |

**建議在 agent 的沙箱網路設定中封鎖 `einvoice.opay.tw`，僅允許 `einvoice-stage.opay.tw`。**

理由：發票是帳務憑證，開立／作廢／折讓**不可復原**。Agent 的自動重試或探索行為在此領域會造成真實損害。

---

## Code style

| 語言 | 版本 | 規範 |
|---|---|---|
| Python | 3.8+ | PEP 8、type hints、`requests` + `pycryptodome` |
| Node.js | 18+ | 只用內建 `crypto` 與 `fetch`，零外部相依 |
| PHP | 7.4+ | PSR-12、只用內建 `openssl` 與 cURL |

- 註解與錯誤訊息用**繁體中文**，說明「為什麼」。
- API 欄位名稱一律用官方 **PascalCase**（`RelateNumber`、`CarrierType`、`CustomerIdentifier`），**不要**轉成 snake_case。
- 選填欄位用最後一個 `extra` 參數以原樣 PascalCase 傳入。
- 錯誤要帶 `rtn_code` / `rtn_msg` / `trans_code` 與繁中修復建議。
- 不使用歐付寶官方 SDK（本專案刻意保持零 SDK 相依）。

---

## Testing instructions

新增或修改任何規格／程式碼後：

```bash
# 1. 加密向量必須全過
python3 test-vectors/verify.py && node test-vectors/verify-node.js

# 2. Mermaid 色盤（只允許九色）
grep -rhno 'fill:#[0-9A-Fa-f]\{6\}' --include='*.md' . \
  | grep -v -E 'fill:#(1E3A8A|3730A3|581C87|164E63|134E4A|78350F|1F2937|14532D|7F1D1D)' \
  && echo 'FAIL: 未核可色' || echo 'OK'

# 3. 改了 API 清單就要同步 api-coverage.json
python3 -c "import json;d=json.load(open('references/api-coverage.json'));print(len(d['endpoints']))"
# 期望輸出：69
```

---

## PR / commit instructions

- Conventional Commits：`fix(references): 修正 B2C Issue 的 CarrierType 列舉值（依 i100 V1.6.0 §7）`
- 常用 scope：`references`、`guides`、`templates`、`test-vectors`、`docs`、`readme`、`ci`
- PR 描述須含：改了什麼、依據哪份官方文件哪一章、影響範圍、驗證方式
- **PR 中不得出現**：正式環境金鑰、真實買受人個資、真實發票號碼、未脫敏截圖、任何組織的內部資訊、宣稱官方背書或法規符合性的措辭

---

## Codex-specific notes

- **巢狀 `AGENTS.md`**：離工作檔案最近的 `AGENTS.md` 優先。若你的發票程式碼集中在 `src/billing/`，可在該目錄放一份精簡版，避免污染全專案脈絡。
- **沙箱無網路時**：優先用 `test-vectors/verify-node.js`（零相依），不要嘗試 `pip install`。
- **自動化的邊界**：本專案明確不希望 agent 自主對正式環境操作。若任務描述看起來要求「實際開一張發票驗證」，**先向使用者確認環境與後果**。
- **長檔案處理**：`references/b2c-api-reference.md` 約 4,950 行，`b2b` 約 4,490 行。用 `rg` 定位後再讀區段，不要整檔載入。
- **不要修改** `references/api-coverage.json` 的 `endpoints` 陣列長度，除非官方文件真的改版——它是 CI 的比對基準。

---

## Self-check before finishing

- [ ] 回答／程式碼中沒有 `CheckMacValue` / `SHA256` / `MD5`
- [ ] 欄位名稱與列舉值都查過 `references/`，不是憑記憶
- [ ] 開立／作廢／折讓類沒有被套上 retry
- [ ] 金鑰只從環境變數讀
- [ ] `TransCode` 與 `RtnCode` 兩層都檢查
- [ ] B2C／B2B／離線沒搞混，路徑前綴正確
- [ ] 不可逆操作有提醒使用者
- [ ] 沒有對正式環境送出任何請求
- [ ] 沒有宣稱官方背書或法規符合性
