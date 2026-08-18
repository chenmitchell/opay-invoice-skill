# vscode_copilot.md — 歐付寶電子發票 Skill（GitHub Copilot / VS Code）

> 本檔設計為複製到專案的 **`.github/copilot-instructions.md`**。
> 安裝步驟見 [`SETUP.md`](SETUP.md) §5。人類請讀 [`README.md`](README.md)。

```bash
mkdir -p .github && cp vscode_copilot.md .github/copilot-instructions.md
```

並在 `settings.json` 啟用：

```json
{ "github.copilot.chat.codeGeneration.useInstructionFiles": true }
```

---

## 專案脈絡

本專案整合**歐付寶（O'Pay）電子發票 API**，規格來源是 `opay-invoice-skill/`，涵蓋 **69 支 API**（B2C 30／B2B 27／離線 12）。

**非官方聲明**：該 Skill 由個人撰寫維護，未經歐付寶電子支付股份有限公司審閱或背書，不保證完整正確，不構成法律／稅務／會計意見，不宣稱法規符合性。**與官方文件不一致時以官方文件為準。**

產生的程式碼與說明一律使用**繁體中文（台灣用語）**註解：程式、專案、伺服器、快取、預設、支援、介面、登入。

---

## 查閱順序

產生任何發票相關程式碼前，依序參考：

1. `opay-invoice-skill/SKILL.md` §0
2. `opay-invoice-skill/references/api-coverage.json`（69 支索引）
3. `opay-invoice-skill/references/{b2c,b2b,offline}-api-reference.md`
4. `opay-invoice-skill/references/enums.md`
5. `opay-invoice-skill/references/encryption-aes.md`、`urlencode-table.md`
6. `opay-invoice-skill/references/error-handling.md`
7. `opay-invoice-skill/templates/opay-einvoice-client/`（**優先複用，不要重寫**）

---

## 🚨 四條不可違反的鐵律

### ① 加密是 AES-128-CBC/PKCS7，不是 `CheckMacValue`

```
明文 JSON → URLEncode(.NET 慣例) → AES-128-CBC/PKCS7 → Base64 → Data 欄位
```

- Key = `HashKey`、IV = `HashIV`，各 16 個 ASCII 字元**直接當 raw bytes**（不做 MD5、不做 Base64 decode、不補零）
- URLEncode 用 **.NET 慣例**：空格 → `+`（不是 `%20`）；`!` `*` `(` `)` **不編碼**
- **歐付寶電子發票的請求沒有 `CheckMacValue` 欄位。**

> ⚠️ **這是 Copilot 在本專案最高風險的錯誤。**
> 訓練資料中台灣金流的範例絕大多數是**綠界 ECPay** 的 `CheckMacValue` + SHA256 做法，inline 補全很容易把它補進來。
> **看到補全出現 `CheckMacValue`、`SHA256`、`hashlib.sha256`、`crypto.createHash('sha256')`、`md5`，一律按 Esc 拒絕。**

```python
# ❌ Copilot 常見的錯誤補全（這是綠界的做法）
check_mac_value = hashlib.sha256(query_string.encode()).hexdigest().upper()

# ✅ 正確
from Crypto.Cipher import AES
encoded = dotnet_urlencode(json.dumps(payload))
cipher  = AES.new(hash_key.encode(), AES.MODE_CBC, hash_iv.encode())
data    = base64.b64encode(cipher.encrypt(pad(encoded.encode(), 16))).decode()
```

### ② 正式環境不得用 `Issue` 做健康檢查

`Issue` 產生**真實發票**、消耗**字軌號碼**，**只能作廢不能刪除**。

- ❌ 不要產生把 `Issue` 放進 `/health`、`/readyz`、smoke test、cron ping 的程式碼。
- ✅ 連通性檢查用唯讀 API：`GetInvoiceWordSetting`、`CheckBarcode`、`GetCompanyNameByTaxID`。
- ✅ 加密驗證用 `test-vectors/`（不連網）。

### ③ 開立／作廢／折讓／註銷重開不可盲目重試

逾時 ≠ 沒開立。重送 = 可能開出兩張發票。

```python
# ❌ 不要這樣補全
@retry(stop=stop_after_attempt(3))
def issue_invoice(...): ...

# ❌ 也不要這樣
for attempt in range(3):
    try: return client.issue(...)
    except TimeoutError: continue

# ✅ 正確：逾時後先查詢
try:
    return client.issue(relate_number, ...)
except TimeoutError:
    # 逾時不代表沒開立，先用原訂單編號查詢
    found = client.get_issue(relate_number=relate_number)
    if found:
        return found                      # 已開立，補記錄即可
    return client.issue(relate_number, ...)   # 查無才可帶同一冪等鍵重送
```

| 可否自動重試 | API |
|---|---|
| ❌ **不可** | `Issue`、`DelayIssue`、`OfflineIssue`、`Invalid`、`OfflineInvalid`、`Allowance`、`AllowanceByCollegiate`、`AllowanceInvalid`、`AllowanceInvalidByCollegiate`、`VoidWithReIssue`、所有 B2B 的 `Xxx` 與 `XxxConfirm` |
| ✅ 可（指數退避） | 所有 `Get*`、`Check*` |

### ④ `HashKey` / `HashIV` 只進 `.env`

```python
# ❌ 不要補全出這種
HASH_KEY = "ejCk326UnaZWKisg"

# ✅ 正確
HASH_KEY = os.environ["OPAY_HASH_KEY"]
```

嚴禁寫死、嚴禁 commit、**嚴禁出現在前端 JS/HTML/CSS**、嚴禁寫進 log。

---

## 69 支 API 導覽

| 分類 | 支數 | 前綴 | 代表 endpoint |
|---|---|---|---|
| B2C 字軌 | 3 | `/B2CInvoice` | `GetGovInvoiceWordSetting`、`AddInvoiceWordSetting`、`UpdateInvoiceWordStatus` |
| B2C 開立 | 4 | `/B2CInvoice` | `Issue`、`DelayIssue`、`TriggerIssue`、`CancelDelayIssue` |
| B2C 折讓 | 2 | `/B2CInvoice` | `Allowance`、`AllowanceByCollegiate` |
| B2C 作廢 | 4 | `/B2CInvoice` | `Invalid`、`AllowanceInvalid`、`AllowanceInvalidByCollegiate`、`VoidWithReIssue` |
| B2C 查詢 | 5 | `/B2CInvoice` | `GetIssue`、`GetAllowanceList`、`GetInvalid`、`GetAllowanceInvalid`、`GetInvoiceWordSetting` |
| B2C 通知列印 | 2 | `/B2CInvoice` | `InvoiceNotify`、`InvoicePrint` |
| B2C 驗證 | 3 | `/B2CInvoice` | `CheckBarcode`、`CheckLoveCode`、`GetCompanyNameByTaxID` |
| B2C 通知設定 | 4 | `/B2CInvoice` | `GetInvoiceNotifySetting`、`InvoiceNotifySetting`、`GetRemainNotifySetting`、`RemainNotifySetting` |
| B2C 空白發票 | 3 | `/B2CInvoice` | `QueryBlankInvoiceList`、`BlankInvAutoUploadSetting`、`DownLoadBlankInvList` |
| B2B 前置 | 4 | `/B2BInvoice` | `MaintainMerchantCustomerData`、`Notify`、`AddInvoiceWordSetting`、`UpdateInvoiceWordStatus` |
| B2B 動作＋確認 | 11 | `/B2BInvoice` | `Issue`/`IssueConfirm`、`Invalid`/`InvalidConfirm`、`Reject`/`RejectConfirm`、`Allowance`/`AllowanceConfirm`、`CancelAllowance`/`CancelAllowanceConfirm`、`VoidWithReIssue` |
| B2B 查詢 | 12 | `/B2BInvoice` | `GetIssue` … `GetAllowanceInvalidConfirm`、`GetInvoiceWordSetting`、`GetCompanyNameByTaxID` |
| 離線 | 12 | `/B2CInvoice` | `GetOfflineMerchantInfo`、`OfflineMerchantPosSetting`、`GetOfflineInvoiceWordSetting*`、`OfflineIssue`、`OfflineInvalid` |

**三類差異**：B2C 上傳期限 **48 小時**、B2B **7 天**、離線 **48 小時**；離線的路徑前綴是 **`/B2CInvoice`**；B2B 交換模式下每個動作都要成對的 `XxxConfirm`（漏了對方永遠停在「等待確認」）。

---

## 環境與共通參數

| | 測試 | 正式 |
|---|---|---|
| Host | `https://einvoice-stage.opay.tw` | `https://einvoice.opay.tw` |
| 後台 | `https://vendor-stage.opay.tw` | `https://vendor.opay.tw` |

- `POST` / `application/json` / TLS 1.2+ / 僅 443 port
- 外層欄位：`PlatformID`（一般廠商留空）、`MerchantID`、`RqHeader.Timestamp`、`Data`
- `Timestamp` 驗證區間 **10 分鐘**
- **兩層回應碼都要檢查**：

```python
# ❌ 只檢查一層是常見 bug
if resp["TransCode"] == 1:
    return "成功"          # 錯：發票可能根本沒開出來

# ✅ 兩層都檢查
if resp["TransCode"] != 1:
    raise OPayTransportError(resp.get("TransMsg"))   # 外層：校時、金鑰配對
inner = decrypt(resp["Data"])
if inner["RtnCode"] != 1:
    raise OPayBusinessError(inner["RtnCode"], inner["RtnMsg"])  # 內層：業務
```

測試環境公開值（**僅測試環境**）：B2C `2000132` / `ejCk326UnaZWKisg` / `q9jcZX8Ib9LM8wYk`；離線 `2045501` / `9XWzRmj7UJESChyn` / `sriQzbe1llJqk67P`。

---

## 程式風格

| 語言 | 版本 | 規範 |
|---|---|---|
| Python | 3.8+ | PEP 8、type hints、`requests` + `pycryptodome` |
| Node.js | 18+ | 只用內建 `crypto` 與 `fetch` |
| PHP | 7.4+ | PSR-12、只用內建 `openssl` 與 cURL |

- API 欄位名稱一律用官方 **PascalCase**（`RelateNumber`、`CarrierType`、`CustomerIdentifier`），**不要**轉 snake_case。
- 列舉值查 `references/enums.md`，**不要憑補全**。
- 錯誤訊息帶繁中修復建議，不要只丟 `Exception: failed`。
- **不使用歐付寶官方 SDK**（本專案刻意零 SDK 相依）。

---

## Copilot 特有注意事項

### inline 補全 vs Copilot Chat

- **inline 補全不會完整讀取本檔**，它主要靠當前檔案與鄰近檔案的上下文。
  → **複雜邏輯（加密、重試、錯誤處理）請用 Copilot Chat，不要靠 inline 補全。**
- 讓 inline 補全變準的技巧：**把 `templates/opay-einvoice-client/python/opay_einvoice.py` 開在旁邊的分頁**。Copilot 會參考已開啟的檔案，補出來的欄位名稱會準很多。

### Copilot Chat 用法

明確引用檔案，命中率最高：

```
#file:opay-invoice-skill/references/b2c-api-reference.md
#file:opay-invoice-skill/references/enums.md
幫我實作 B2C Issue，買受人使用手機條碼載具，語言 TypeScript。
```

其他有用的指令：

```
@workspace 這個專案怎麼處理歐付寶發票開立的逾時？
/explain 這段加密程式碼為什麼驗不過？
/fix 這段有沒有把不可重試的 API 套上 retry？
```

### 高風險補全的檢查清單

Copilot 產生任何發票相關程式碼後，**逐項確認**：

- [ ] 有沒有 `CheckMacValue` / `SHA256` / `MD5` / `hashlib` / `createHash`？→ 有就刪掉重來
- [ ] URLEncode 是 .NET 慣例嗎（空格 → `+`）？→ 用 `urllib.parse.quote_plus` 之後還要修正 `!*()`
- [ ] 金鑰是 `os.environ` 讀的，還是被補成字串常數？
- [ ] 有沒有 `@retry` / `for attempt in range(...)` 包住開立類 API？
- [ ] `TransCode` 與 `RtnCode` 兩層都檢查了嗎？
- [ ] 欄位名稱是官方 PascalCase 嗎？
- [ ] B2C／B2B／離線的路徑前綴對嗎？
- [ ] 有沒有把 `Issue` 補進 health check？

### 安全

- Copilot 的補全**不會**知道哪些是敏感資料。**不要**在程式碼註解裡寫真實金鑰、真實發票號碼、買受人 Email。
- 測試資料一律用：`AA00000000`（發票號碼）、`00000000`（統編）、`user@example.com`、`0900000000`、`ORDER-0001`。
- 若不慎把正式金鑰寫進檔案並 commit，**立即到廠商後台輪換**。詳見 [`SECURITY.md`](SECURITY.md)。
