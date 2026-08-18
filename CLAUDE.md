# CLAUDE.md — 歐付寶電子發票 Skill（Claude Code / Cowork）

> 這個檔案是給 **Claude Code** 與 **Claude Cowork** 讀的專案指令。
> 人類請讀 [`README.md`](README.md)。

---

## 0. 這是什麼

`opay-invoice-skill` 是一份**非官方、由 Mitchell Chen 個人撰寫維護**的歐付寶（O'Pay）電子發票 API 知識庫與程式碼模板集，涵蓋 **69 支 API**（B2C 30／B2B 27／離線 12）。

**非官方聲明**：本 Skill 未經歐付寶電子支付股份有限公司審閱、認可或背書，與該公司無任何從屬或合作關係。內容不保證完整正確，不構成法律、稅務或會計意見，不宣稱任何法規符合性。**若與官方文件不一致，一律以官方文件為準。**

**回答使用者時，若涉及正確性風險，請主動提醒這一點。**

---

## 1. 載入順序（處理任何發票需求前照做）

```
① SKILL.md §0            ← 核心規則，最優先
② references/api-coverage.json  ← 69 支 API 索引，先定位再深讀
③ references/{b2c|b2b|offline}-api-reference.md  ← 只讀相關那一段
④ references/enums.md    ← 列舉值不要憑記憶寫
⑤ references/encryption-aes.md + urlencode-table.md  ← 涉及加密時
⑥ references/error-handling.md  ← 涉及錯誤與重試時
⑦ guides/NN-*.md         ← 對應主題的整合指南
⑧ templates/opay-einvoice-client/  ← 有現成實作就不要重寫
```

**檢索策略**（善用你的工具）：

- 用 `Grep` 搜 endpoint 名稱（例如 `AllowanceByCollegiate`）比全文讀檔快得多——三份 reference 加起來超過 11,500 行。
- 用 `Read` 搭配 `offset`／`limit` 只讀相關章節，不要整檔載入。
- `api-coverage.json` 很小，**可以整檔讀**，用它決定要看哪一份、哪一章。
- 每個 `## N. 中文名 — \`EndpointName\`` 標題就是該 API 的規格起點。

---

## 2. 四條不可違反的鐵律

### ① 加密是 AES-128-CBC/PKCS7，不是 `CheckMacValue`

```
明文 JSON → URLEncode（.NET 慣例）→ AES-128-CBC/PKCS7 → Base64 → 放進 Data 欄位
```

- Key = `HashKey`（16 個 ASCII 字元，直接當 raw bytes，**不做 MD5、不做 Base64 decode、不補零**）
- IV = `HashIV`（同上）
- URLEncode 用 **.NET 慣例**：空格 → `+`（不是 `%20`），`!` `*` `(` `)` **不編碼**
- **歐付寶電子發票的請求裡沒有 `CheckMacValue` 這個欄位。** `CheckMacValue` / SHA256 / MD5 是綠界 ECPay 的做法，套過來永遠驗不過。

> 若你發現自己正要寫出 `CheckMacValue`、`SHA256`、`hashlib.sha256`，**停下來重新讀 `references/encryption-aes.md`**。

### ② 正式環境不得用 `Issue` 做健康檢查

`Issue` 會**產生真實發票**、**消耗字軌號碼**，而且**只能作廢、不能刪除**。

- 要驗證連通性，用唯讀 API：`GetInvoiceWordSetting`、`CheckBarcode`、`GetCompanyNameByTaxID`。
- 要驗證加密實作，用 `test-vectors/verify.py`（**完全不連網**）。
- 測試環境（`einvoice-stage.opay.tw`）同樣會產生真實紀錄，也不要當 ping 用。

### ③ 開立／作廢／折讓／註銷重開不可盲目重試

逾時 ≠ 沒開立。直接重送 = 可能開出兩張發票。

正確流程：**逾時 → 用 `GetIssue` 帶原 `RelateNumber` 查詢 → 查到就補記錄，查不到才可帶同一冪等鍵重送。**

- ❌ 不可自動重試：`Issue`、`DelayIssue`、`OfflineIssue`、`Invalid`、`OfflineInvalid`、`Allowance`、`AllowanceByCollegiate`、`AllowanceInvalid`、`VoidWithReIssue`，以及所有 B2B 的 `Xxx` 與 `XxxConfirm`
- ✅ 可指數退避重試：所有 `Get*` 查詢類、`Check*` 驗證類

**產生程式碼時，絕不要在這些 API 外面套通用的 retry decorator。**

### ④ HashKey／HashIV 只進 `.env`

- 只從環境變數讀（`os.environ` / `process.env` / `getenv`）。
- **嚴禁**寫死在程式碼、**嚴禁** commit、**嚴禁**出現在前端 JS/HTML/CSS、**嚴禁**寫進 log。
- 產生範例程式碼時一律用環境變數；需要示範值時只用官方公開的**測試環境**值，並標註「僅測試環境」。

---

## 3. 69 支 API 分類導覽

| 分類 | 支數 | 前綴 | 主題 | 主要 endpoint |
|---|---|---|---|---|
| **B2C 字軌** | 3 | `/B2CInvoice` | 配號、設定、狀態 | `GetGovInvoiceWordSetting`、`AddInvoiceWordSetting`、`UpdateInvoiceWordStatus` |
| **B2C 開立** | 4 | `/B2CInvoice` | 一般／延遲／觸發／取消 | `Issue`、`DelayIssue`、`TriggerIssue`、`CancelDelayIssue` |
| **B2C 折讓** | 2 | `/B2CInvoice` | 紙本／線上 | `Allowance`、`AllowanceByCollegiate` |
| **B2C 作廢** | 4 | `/B2CInvoice` | 作廢、作廢折讓、註銷重開 | `Invalid`、`AllowanceInvalid`、`AllowanceInvalidByCollegiate`、`VoidWithReIssue` |
| **B2C 查詢** | 5 | `/B2CInvoice` | 發票、折讓、作廢、字軌 | `GetIssue`、`GetAllowanceList`、`GetInvalid`、`GetAllowanceInvalid`、`GetInvoiceWordSetting` |
| **B2C 通知列印** | 2 | `/B2CInvoice` | 通知、列印 | `InvoiceNotify`、`InvoicePrint` |
| **B2C 驗證** | 3 | `/B2CInvoice` | 條碼、愛心碼、統編 | `CheckBarcode`、`CheckLoveCode`、`GetCompanyNameByTaxID` |
| **B2C 通知設定** | 4 | `/B2CInvoice` | 通知開關、餘量通知 | `GetInvoiceNotifySetting`、`InvoiceNotifySetting`、`GetRemainNotifySetting`、`RemainNotifySetting` |
| **B2C 空白發票** | 3 | `/B2CInvoice` | 查詢、自動上傳、下載 | `QueryBlankInvoiceList`、`BlankInvAutoUploadSetting`、`DownLoadBlankInvList` |
| **B2B 前置** | 4 | `/B2BInvoice` | 交易對象、通知、字軌 | `MaintainMerchantCustomerData`、`Notify`、`AddInvoiceWordSetting`、`UpdateInvoiceWordStatus` |
| **B2B 動作＋確認** | 11 | `/B2BInvoice` | 每個動作都成對 | `Issue`/`IssueConfirm`、`Invalid`/`InvalidConfirm`、`Reject`/`RejectConfirm`、`Allowance`/`AllowanceConfirm`、`CancelAllowance`/`CancelAllowanceConfirm`、`VoidWithReIssue` |
| **B2B 查詢** | 12 | `/B2BInvoice` | 每種動作都有查詢與查詢確認 | `GetIssue`…`GetAllowanceInvalidConfirm`、`GetInvoiceWordSetting`、`GetCompanyNameByTaxID` |
| **離線** | 12 | `/B2CInvoice` | 特店、機台、取號、上傳 | `GetOfflineMerchantInfo`、`OfflineMerchantPosSetting`、`GetOfflineInvoiceWordSetting*`、`OfflineIssue`、`OfflineInvalid` |

**完整逐支清單見 `references/api-coverage.json`（SSOT）與 `README.md` 的「API 覆蓋總表」。**

### 三類的關鍵差異（回答前先確認使用者要哪一類）

| | B2C | B2B | 離線 |
|---|---|---|---|
| 買受人 | 消費者（載具／捐贈） | 雙方皆營業人（必帶統編） | 同 B2C |
| 上傳期限 | **48 小時** | **7 天** | **48 小時** |
| 路徑前綴 | `/B2CInvoice` | `/B2BInvoice` | **`/B2CInvoice`**（不是 `/OfflineInvoice`） |
| 特殊機制 | — | 交換模式的 `XxxConfirm` 成對 | 事先取號、離線開立、事後上傳 |

---

## 4. 環境與共通參數

| 項目 | 測試 | 正式 |
|---|---|---|
| Host | `https://einvoice-stage.opay.tw` | `https://einvoice.opay.tw` |
| 廠商後台 | `https://vendor-stage.opay.tw` | `https://vendor.opay.tw` |

- HTTP `POST`、`application/json`、TLS 1.2+、僅 443 port
- 外層欄位：`PlatformID`（一般廠商留空）、`MerchantID`、`RqHeader.Timestamp`、`Data`
- `Timestamp`：Unix timestamp，**驗證區間 10 分鐘**
- **兩層回應碼都要檢查**：`TransCode`（外層，`1` = 接收成功）與 `RtnCode`（解密後，`1` = 業務成功）

**測試環境公開值（僅測試環境）**：
- B2C：`MerchantID` `2000132`、`HashKey` `ejCk326UnaZWKisg`、`HashIV` `q9jcZX8Ib9LM8wYk`
- 離線：`MerchantID` `2045501`、`HashKey` `9XWzRmj7UJESChyn`、`HashIV` `sriQzbe1llJqk67P`

---

## 5. Claude 特有注意事項

### 工具使用

- **優先 `Grep` 再 `Read`**：三份 reference 超過 11,500 行，全讀會吃掉大量 context。先 `Grep` 找到行號，再 `Read` 該段落。
- **`api-coverage.json` 可整檔讀**（很小），用它當索引。
- **不要用 `WebFetch` 抓歐付寶官網**當作規格來源——本 repo 的 reference 就是規格來源，官網頁面可能是行銷內容。

### 執行指令時

```bash
# ✅ 這些安全，不連外網
python3 test-vectors/verify.py
node    test-vectors/verify-node.js
python3 templates/opay-einvoice-client/python/opay_einvoice.py
```

- ⛔ **絕不要主動對 `einvoice.opay.tw`（正式）送出任何請求。**
- ⛔ **不要主動送出 `Issue`／`Invalid`／`Allowance`／`VoidWithReIssue`**，即使是測試環境——這些會產生無法刪除的紀錄。要跑之前**先問使用者**。
- 對測試環境的唯讀 API（`CheckBarcode` 等）可以在使用者要求時執行。

### 產生程式碼時

1. **先看 `templates/opay-einvoice-client/`**——69 支都有現成實作，通常改參數就好，不要重寫。
2. 欄位名稱一律用官方 **PascalCase**（`RelateNumber`、`CarrierType`、`CustomerIdentifier`），不要自作主張轉 snake_case。
3. 列舉值**去 `references/enums.md` 查**，特別注意「同名不同義的陷阱」章節。
4. 錯誤處理要**兩層都檢查**，錯誤訊息要帶繁中修復建議。
5. 金額欄位注意含稅／未稅與四捨五入，這是最常見的對帳差異來源。

### 回答風格

- **繁體中文（台灣用語）**：程式、專案、伺服器、快取、預設、支援、介面、登入。
- 引用規格時**標明檔案與章節**，讓使用者能自己驗證。
- 不確定就說不確定，**不要編造欄位名稱或錯誤碼**。官方沒公開完整錯誤碼表，這一點要誠實說。
- 涉及不可逆操作（作廢／折讓／註銷重開）時，**主動提醒不可復原**並建議加二次確認與稽核 log。
- 使用者若問「這樣合不合法／合不合規」，說明本 Skill 不提供法律或稅務意見，建議諮詢會計師或稅務專業人員。

### 畫圖時

若要產生 Mermaid 圖，遵循 [`docs/accessibility.md`](docs/accessibility.md)：

- 固定 init 標頭（`curve:'step'`、`fontSize:'16px'`、`htmlLabels:true`、`useMaxWidth:true`）
- `fill:` 只能用這九色：`#1E3A8A` `#3730A3` `#581C87` `#164E63` `#134E4A` `#78350F` `#1F2937` `#14532D`（成功）`#7F1D1D`（失敗），一律 `stroke:#FFFFFF,stroke-width:3px,color:#FFFFFF`
- 節點標籤「圖示 ＋ 中文 ＋ 英文」
- 圖前加 `> 🧭 **純文字重述（螢幕閱讀器友善）**：…`，圖後加 `> ♿ 配色遵循 …`

### 安全

- 使用者若貼上疑似**正式環境金鑰**或**真實買受人個資**，**立刻提醒**他不該這麼做，並建議輪換金鑰（廠商後台）。
- 產出的範例一律用脫敏值：`AA00000000`（發票號碼）、`00000000`（統編）、`user@example.com`、`0900000000`、`ORDER-0001`。
- 詳見 [`SECURITY.md`](SECURITY.md)。

---

## 6. 自我檢查（回答送出前）

- [ ] 有沒有出現 `CheckMacValue` / `SHA256` / `MD5`？→ 有的話一定錯了
- [ ] 欄位名稱是從 reference 查來的，還是憑印象寫的？
- [ ] 列舉值查過 `enums.md` 了嗎？
- [ ] 開立／作廢／折讓類有沒有被套上 retry？→ 有的話拿掉
- [ ] 金鑰是從環境變數讀的嗎？
- [ ] `TransCode` 與 `RtnCode` 兩層都檢查了嗎？
- [ ] B2C／B2B／離線有沒有搞混？路徑前綴對嗎？
- [ ] 不可逆操作有沒有提醒使用者？
- [ ] 有沒有不小心宣稱官方背書或法規符合性？
