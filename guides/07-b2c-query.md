# 07 · B2C 查詢類五支 API — 查詢是冪等的，可安全重試

五支查詢 API 的用途對照、查詢鍵怎麼選，以及為什麼「用讀取來消解寫入的不確定性」是電子發票唯一安全的收斂方式。

> **對應 API**：[`GetIssue`](../references/b2c-api-reference.md#14-查詢發票明細--getissue)、[`GetAllowanceList`](../references/b2c-api-reference.md#15-查詢折讓明細--getallowancelist)、[`GetInvalid`](../references/b2c-api-reference.md#16-查詢作廢發票明細--getinvalid)、[`GetAllowanceInvalid`](../references/b2c-api-reference.md#17-查詢作廢折讓明細--getallowanceinvalid)、[`GetInvoiceWordSetting`](../references/b2c-api-reference.md#18-查詢字軌--getinvoicewordsetting)
> **前置條件**：已有可用金鑰與已完成 [`02-preflight-checklist.md`](02-preflight-checklist.md)。查詢類 API **不需要**字軌啟用。

---

## 1. 查什麼用哪支

| 我想知道 | 用哪支 | 查詢鍵 |
|---|---|---|
| 這張發票開出來了嗎、內容是什麼 | `GetIssue` | `RelateNumber`／或 `InvoiceNo`+`InvoiceDate` |
| 這張發票有哪些折讓單 | `GetAllowanceList` | `AllowanceNo`／或 `InvoiceNo`+日期 |
| 這張發票作廢了嗎 | `GetInvalid` | `RelateNumber`+`InvoiceNo`+`InvoiceDate` |
| 這張折讓作廢了嗎 | `GetAllowanceInvalid` | `InvoiceNo`+`AllowanceNo` |
| 字軌還剩幾張、狀態如何 | `GetInvoiceWordSetting` | `InvoiceYear`+`InvoiceCategory` |

---

## 2. 🔑 核心觀念：查詢是冪等的，可安全重試

| 類別 | 可否重試 | 理由 |
|---|:---:|---|
| 查詢類（本文五支） | ✅ | 不改變任何狀態，查一百次結果都一樣 |
| 驗證類（`CheckBarcode` 等） | ✅ | 同上，見 [`09-b2c-validation.md`](09-b2c-validation.md) |
| 財務動作（`Issue` / `Invalid` / `Allowance`） | 🚫 | 見 [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md) |

**這個性質的真正價值不在「查詢很方便」，而在於：**

> 🔑 **當寫入操作的結果未知時（timeout、5xx、connection reset），唯一安全的收斂方式是「先查再決定」，而不是「盲目重送」。**

```
開立 timeout
  → 狀態標記 IN_FLIGHT，🚫 不可重送
  → 用 GetIssue 以 RelateNumber 查
     ├─ 查得到 → 標記 SUCCEEDED，記下 InvoiceNo（其實已經成功了）
     └─ 查不到 → 才可以用「同一個」RelateNumber 重送
```

**為什麼不能盲目重送**：最惡毒的失敗是「請求其實成功了，但回應在網路上遺失」。你的程式看到失敗，歐付寶那邊已經開好發票。這時重送 **100% 會重複開立**。

**重試查詢的參數建議**：指數退避（1s / 2s / 4s / 8s）+ jitter，上限 4–5 次。⚠️ **每次重試都要重新產生 `Timestamp`**，因為驗證區間只有 10 分鐘，沿用第一次的會在後面幾次全部失敗。

---

## 3. `GetIssue` — 最常用的一支

兩種查詢方式**擇一**：

| 情境 | 傳什麼 | 適用 |
|---|---|---|
| 情境一 | `RelateNumber` | **冪等對帳的標準做法**（你一定知道自己的訂單編號） |
| 情境二 | `InvoiceNo` + `InvoiceDate` | 客服拿著發票號碼來查 |

```python
detail = c.get_issue(relate_number="ORD20260818001")
# 或
detail = c.get_issue(invoice_no="AA12345678", invoice_date="2026-08-18")
```

### 3.1 回傳欄位的陷阱

| 欄位 | 陷阱 |
|---|---|
| `IIS_Identifier` | 回 `0000000000` **代表沒有統編**，不是統編是零 |
| `IIS_Tax_Amount` | **沒有統編時回 `0`**——不是免稅，是「稅金含在發票金額內，不拆算」 |
| `IIS_Carrier_Type` | 回傳只有 `1`/`2`/`3`，**送出時卻有 `1`–`8`**。見 [`enums.md` §10.9](../references/enums.md#109-️-carriertype送出-18vs-iis_carrier_type回傳-13) |
| `IIS_Carrier_Num` | `CarrierType=4~8` 時回的是**顯碼**，不會回隱碼（資安考量） |
| `IIS_Award_Flag` | **空值 ≠ `0`**。空值 = 不可對獎（如捐贈）、`0` = 對過獎沒中、`X` = 有統編之發票 |
| `IIS_Award_Type` | **數值大小 ≠ 獎金大小**（`8` 特別獎一千萬 > `7` 特獎二百萬 > `1` 頭獎二十萬）。不要拿數值排序 |
| `IIS_Turnkey_Status` | `C` 成功／`E` 失敗／`G` 待財政部回覆／`P` 上傳財政部中 |
| `QRCode_Left` / `QRCode_Right` | 僅 POS 廠商專用，且**須先在歐付寶設定密碼種子**才會壓碼回傳 |
| QR Code 內容 | 「為避免過於複雜無法辨識，**QR Code 僅顯示前 2 個品項**」 |

> **為什麼 `IIS_Award_Flag` 的空值特別危險**：`if not flag:` 會把「不可對獎」與「未中獎」混成同一類。捐贈的發票本來就不對獎，被歸類成「未中獎」看起來沒差，但當你要統計「有多少發票尚未對獎」時就會完全錯。

---

## 4. `GetAllowanceList` — 三種查詢方式

| `SearchType` | 必填 | `Date` 是什麼 |
|:---:|---|---|
| `0` | `AllowanceNo`（其他值無效） | — |
| `1` | `InvoiceNo`（其他值無效） | 發票**開立**日期 |
| `2` | `InvoiceNo`（其他值無效） | 發票**折讓**日期 |

`Date` 格式：`yyyy-MM-dd` 或 `yyyy/MM/dd`。

> ⚠️ **`1` 和 `2` 都是「發票號碼 + 日期」，差別只在日期的語意。** 用錯回的是「查無資料」而不是「參數錯誤」，是最難 debug 的一種失敗。
>
> ⚠️ **查詢結果不包含「消費者尚未同意之線上折讓單」**（原文）。已申請未同意的折讓**確實佔用可折讓額度**，但這支查不到。要掌握待處理的申請，只能靠自己的本地狀態表，見 [`05-b2c-allowance.md`](05-b2c-allowance.md) §7。

---

## 5. `GetInvalid` / `GetAllowanceInvalid`

```python
inv = c.get_invalid(relate_number="ORD20260818001",
                    invoice_no="AA12345678", invoice_date="2026-08-18")
alw = c.get_allowance_invalid(invoice_no="AA12345678",
                              allowance_no="1909181313013546")
```

| 注意 | 說明 |
|---|---|
| `II_Buyer_Identifier` / `AI_Buyer_Identifier` = `0000000000` | 代表**沒有統編** |
| 上傳狀態當天是 `0` | **正常**。作廢資料是**隔日**才上傳財政部 |
| `GetInvalid` 回傳外層出現 `EncData` | 原文範例有、參數表沒有；程式端要能容錯 |

> **為什麼要強調「當天是 `0` 正常」**：很多人在作廢後立刻查，看到 `Upload_Status=0` 以為失敗，於是再作廢一次或開工單。**這是設計上的非同步，不是錯誤。**

---

## 6. `GetInvoiceWordSetting` — 字軌餘量的資料來源

```python
words = c.get_invoice_word_setting(invoice_year="115", invoice_category=1)
```

| 傳入 | 規則 |
|---|---|
| `InvoiceYear` | 民國年 3 碼；**僅可查去年、當年、明年** |
| `InvoiceCategory` | B2C **固定 `1`**，原文：「否則**會查無資料**」（B2B `2`、離線 `4`） |
| `InvoiceTerm` / `UseStatus` | 可帶 `0`（全部）作為查詢條件 |
| `InvType` / `InvoiceHeader` | 選填，用來縮小範圍 |

| 回傳 | 說明 |
|---|---|
| `InvoiceStart` / `InvoiceEnd` | 字軌區間 |
| `InvoiceNo` | **目前已使用號碼** |
| `UseStatus` | `1`–`6`（**回傳不會有 `0`**） |
| `TrackID` | 設定字軌狀態要用的鍵 |

剩餘張數：`int(InvoiceEnd) - int(InvoiceNo)`。監控做法見 [`24-prod-monitoring.md`](24-prod-monitoring.md)。

> ⚠️ 官方範例的 `InvoiceInfo` 在參數表標示為 Array、範例卻寫成物件。**程式端要能同時吃 list 與 dict**：

```python
infos = result.get("InvoiceInfo") or []
if isinstance(infos, dict):
    infos = [infos]
```

---

## 7. 查詢在整體架構中的三個角色

| 角色 | 做法 | 頻率 |
|---|---|---|
| **對帳收斂** | `IN_FLIGHT` 超時後用 `GetIssue` 查 `RelateNumber` | 事件驅動 |
| **健康探測** | 正式環境用 `GetInvoiceWordSetting` 當唯讀 ping | 定期（如每 5 分鐘） |
| **日結核對** | 比對本地成功筆數 vs 歐付寶查詢結果 | 每日 |

> 🚨 **正式環境的健康檢查絕不可以用 `Issue`。** 它會產生真實發票，是**稅務資料污染**。詳見 [`24-prod-monitoring.md`](24-prod-monitoring.md)。

---

### 常見錯誤

1. **timeout 後直接重送開立。** 應該先用 `GetIssue` 以 `RelateNumber` 查。這是本 Skill 最重要的一條規則。
2. **把 `IIS_Identifier=0000000000` 當成統編。** 它代表「沒有統編」。用它去比對客戶資料會全部對不上。
3. **`GetAllowanceList` 的 `SearchType` 1/2 用錯。** 回「查無資料」而不是參數錯誤，會讓人往完全錯誤的方向查。
4. **`InvoiceCategory` 沒填 `1`。** 官方明寫「否則會查無資料」，你會以為字軌不見了。
5. **用 `IIS_Award_Type` 的數值大小排序獎金。** `8` 是一千萬、`1` 是二十萬，排出來會完全相反。
6. **重試時沿用第一次的 `Timestamp`。** 10 分鐘驗證區間，後面幾次會全部失敗，看起來像「歐付寶壞掉了」。
