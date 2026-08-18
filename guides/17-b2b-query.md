# 17 · B2B 查詢類 API — 查什麼用哪支

B2B 有 12 支查詢／驗證 API，命名高度相似（`GetXxx` 與 `GetXxxConfirm` 成對）。本文提供對照表與決策表。

> **對應 API**：[`GetIssue`](../references/b2b-api-reference.md#16-查詢發票--getissue)、[`GetIssueConfirm`](../references/b2b-api-reference.md#17-查詢發票確認--getissueconfirm)、[`GetInvalid`](../references/b2b-api-reference.md#18-查詢作廢發票--getinvalid)、[`GetInvalidConfirm`](../references/b2b-api-reference.md#19-查詢作廢發票確認--getinvalidconfirm)、[`GetReject`](../references/b2b-api-reference.md#20-查詢退回發票--getreject)、[`GetRejectConfirm`](../references/b2b-api-reference.md#21-查詢退回發票確認--getrejectconfirm)、[`GetAllowance`](../references/b2b-api-reference.md#22-查詢折讓發票--getallowance)、[`GetAllowanceConfirm`](../references/b2b-api-reference.md#23-查詢折讓發票確認--getallowanceconfirm)、[`GetAllowanceInvalid`](../references/b2b-api-reference.md#24-查詢作廢折讓發票--getallowanceinvalid)、[`GetAllowanceInvalidConfirm`](../references/b2b-api-reference.md#25-查詢作廢折讓發票確認--getallowanceinvalidconfirm)、[`GetInvoiceWordSetting`](../references/b2b-api-reference.md#26-查詢字軌--getinvoicewordsetting)、[`GetCompanyNameByTaxID`](../references/b2b-api-reference.md#27-統一編號驗證--getcompanynamebytaxid)
> **前置條件**：可用金鑰；已於財政部平台完成授權歐付寶。查詢類**不需要**字軌啟用。

---

## 1. 決策表：查什麼用哪支

| 我想知道 | 用哪支 | 查詢鍵 |
|---|---|---|
| 這張發票的內容是什麼 | `GetIssue` | `InvoiceNumber`+`InvoiceDate`／或 `RelateNumber` |
| **對方確認了嗎** | `GetIssueConfirm` | 同上（互為條件必填） |
| 這張發票作廢了嗎 | `GetInvalid` | 同上 |
| 作廢被對方確認了嗎 | `GetInvalidConfirm` | 同上 |
| 這張發票被退回了嗎 | `GetReject` | 同上 |
| 退回被確認了嗎 | `GetRejectConfirm` | 同上 |
| 這筆折讓的內容 | `GetAllowance` | **`AllowanceNo`（16 碼）** |
| 折讓被確認了嗎 | `GetAllowanceConfirm` | `AllowanceNo` |
| 折讓作廢了嗎 | `GetAllowanceInvalid` | `AllowanceNo` |
| 作廢折讓被確認了嗎 | `GetAllowanceInvalidConfirm` | `AllowanceNo` |
| 字軌狀態與剩餘 | `GetInvoiceWordSetting` | `InvoiceYear`+`InvoiceCategory=2` |
| 統編對應的公司名 | `GetCompanyNameByTaxID` | `UnifiedBusinessNo`（8 碼數字） |

> 🔑 **記憶法**：**發票類**（開立／作廢／退回）用「發票號碼 + 日期」或「自訂編號」；**折讓類**（折讓／作廢折讓）一律用 **`AllowanceNo` 16 碼**。

---

## 2. `GetXxx` vs `GetXxxConfirm` 的差別

| 面向 | `GetXxx` | `GetXxxConfirm` |
|---|---|---|
| 查什麼 | 這個**動作**本身的資料 | 這個動作的**確認**狀態 |
| 什麼時候用 | 想知道發票內容、金額、明細 | 想知道**交換完成了沒**（`ExchangeStatus`） |
| 交換模式下 | `ExchangeStatus=0` 代表等待確認 | 確認記錄存在代表已完成 |

> **實務上你多半需要 `GetXxxConfirm`**。因為 B2B 最大的風險是「動作做了但沒完成交換」（見 [`14-b2b-issue.md`](14-b2b-issue.md)），而那件事只有確認查詢看得出來。

---

## 3. 查詢鍵的互為條件必填

多數 `GetXxx` / `GetXxxConfirm` 的規則（i200 §17–§21 原文）：

| 規則 | 說明 |
|---|---|
| `InvoiceNumber` 與 `RelateNumber` **互為條件必填** | `RelateNumber` 為空時 `InvoiceNumber` 需有值；反之亦然 |
| `InvoiceNumber` 有值時，`InvoiceDate` **必填** | 只帶號碼不帶日期會失敗 |

```python
# 用自訂編號查（推薦：對帳時你一定知道自己的訂單編號）
c.b2b_get_issue_confirm(invoice_category=0, RelateNumber="B2B20260818001")

# 用發票號碼查（客服拿著發票來問時）
c.b2b_get_issue_confirm(invoice_category=0,
                        InvoiceNumber="AB20000001", InvoiceDate="2026-08-18")
```

---

## 4. 🚨 `InvoiceCategory` 在查詢類是「銷項／進項」

| 值 | 意義 |
|:---:|---|
| `0` | **銷項發票**（你開給交易相對人的） |
| `1` | **進項發票**（交易相對人開給你的） |

**這與字軌章節的 `InvoiceCategory=2`（B2B 體系）是完全不同的定義**，見 [`enums.md` §10.3](../references/enums.md#103-️-invoicecategory--同一份-i200-文件內就兩套)。

> **查不到資料時的第一個懷疑對象就是這個欄位填反了。** 而且它回的是「查無資料」而不是「參數錯誤」。

### 4.1 `InvoiceCategory` 決定哪些欄位是空的

官方對每一支查詢 API 都有對應規則，整理如下：

| API | 條件 | 哪些欄位是空 |
|---|---|---|
| `GetIssue` | `InvoiceCategory=0`（銷項） | `Seller_Identifier`、`Seller_Name`、`Seller_Address`、`Seller_TelephoneNumber`、`Seller_EmailAddress`、`Seller_FacsimileNumber` 皆為空值 |
| `GetIssue` | `InvoiceCategory=1`（進項） | `Upload_Status` 為空值、`Upload_Date` 為 null |
| `GetIssueConfirm` / `GetInvalidConfirm` / `GetRejectConfirm` / `GetAllowanceConfirm` | `InvoiceCategory=0` | `Upload_Status` 為空值、`Upload_Date` 為 null |
| `GetInvalid` / `GetReject` / `GetAllowanceInvalidConfirm` | `InvoiceCategory=1` | `Upload_Status` 為空值、`Upload_Date` 為 null |
| `GetAllowanceInvalid` | `InvoiceCategory=0` | `Upload_Status`、`Upload_Date` **此二參數不顯示**（用語與其他章節的「為空值」不同） |

> **為什麼要列這張表**：這些空值**不是錯誤**。程式如果對 `Upload_Status` 做 `int()` 轉型或 falsy 判斷，會在特定查詢方向下爆炸或誤判。**每一支查詢的回傳處理都要能吃空值。**
>
> ⚠️ 三支折讓類查詢（`GetAllowance` / `GetAllowanceConfirm` / `GetAllowanceInvalid` / `GetAllowanceInvalidConfirm`）的**傳入 Data 並無 `InvoiceCategory` 參數**，但回傳欄位說明卻以它的值決定是否為空。原文未說明此值如何判定，**介接前請向歐付寶確認**。

---

## 5. 🚨 欄位命名不一致

| API | 買方統編欄位 | 賣方統編欄位 |
|---|---|---|
| 多數查詢 | `Buyer_Identifier` | `Seller_Identifier` |
| **`GetInvalid`** | **`BuyerId`** | **`SellerId`** |
| **`GetAllowanceInvalid`** | **`BuyerId`** | **`SellerId`** |

> **請勿混用。** 寫一個統一的正規化函式，把兩種命名都對應到你自己的欄位名：

```python
def buyer_tax_id(row: dict) -> str | None:
    return row.get("Buyer_Identifier") or row.get("BuyerId")
```

其他命名陷阱：

| 概念 | 送出時叫 | B2B 查詢回傳時叫 |
|---|---|---|
| 字軌類別 | `InvType` | `InvoiceType`（§18 標 String(1)、§24 標 String(2)，文件自身不一致，**當 2 碼字串處理**） |
| 通關方式 | `ClearanceMark` | `CustomsClearanceMark` |

---

## 6. 狀態欄位判讀

| 欄位 | 值 | 判讀重點 |
|---|---|---|
| `ExchangeStatus` | 空值／`0`／`1` | **空值 = 未設定 ≠ `0`**；存證模式下 `1` 直接是終態，沒有 `0` |
| `Upload_Status` | `0`／`1`／**`2`** | 🚨 **`2` 是上傳失敗（終態）**，不是處理中。B2C 只有 `0`/`1` |
| `Issue_Status` | `1` 發票開立／`0` **發票退回** | B2C 的 `0` 是「註銷」，語意不同 |
| `Invalid_Status` | `0` 未作廢／`1` 已作廢 | — |

> 🚨 **把 `Upload_Status=2` 當成「處理中」會造成無限輪詢。** 輪詢邏輯必須把 `2` 當終態失敗並告警。見 [`enums.md` §10.6](../references/enums.md#106-️-上傳狀態家族--b2c-兩值b2b-三值)。

---

## 7. `GetInvoiceWordSetting`（B2B）

```python
c.b2b_get_invoice_word_setting(invoice_year="115", invoice_term=0,
                               use_status=0, invoice_category=2)
```

| 規則 | 說明 |
|---|---|
| `InvoiceCategory` | **固定 `2`**（B2B） |
| `InvoiceYear` | 民國年 3 碼；僅可查去年、當年、明年 |
| `InvoiceTerm` / `UseStatus` | 傳入可用 `0`（全部）；**回傳只有 `1`–`6`，沒有 `0`** |

字軌餘量監控與 B2C 相同，見 [`03-b2c-word-setting.md`](03-b2c-word-setting.md) §6 與 [`24-prod-monitoring.md`](24-prod-monitoring.md)。

---

## 8. `GetCompanyNameByTaxID`（B2B）

與 B2C 版本行為一致：`UnifiedBusinessNo` 僅限數字、長度 8，回傳公司名稱。

**B2B 的用途更關鍵**：交易對象維護的 `Identifier` **設定後不可變更**，建檔前一定要先驗。見 [`13-b2b-customer-notify.md`](13-b2b-customer-notify.md) §2.1。

---

## 9. 查詢是冪等的，可安全重試

與 B2C 相同：查詢類與驗證類 API 不改變狀態，可用指數退避重試（⚠️ **每次重新產生 `Timestamp`**）。

**B2B 特別需要查詢的三個場景**：

| 場景 | 用哪支 | 頻率 |
|---|---|---|
| 「等待確認」逾時掃描 | `GetIssueConfirm` | 每日 |
| 「被對方退回」偵測 | `GetReject` | 每日 |
| 上傳失敗（`Upload_Status=2`）偵測 | 各 `GetXxx` | 每日 |

> **為什麼這三個都要排程**：它們全部是**對方或系統發起**的狀態變化，你不會收到任何呼叫或通知。不主動查就不會知道。

---

### 常見錯誤

1. **`InvoiceCategory` 銷項／進項填反。** 回「查無資料」而不是參數錯誤，是最難 debug 的一種。
2. **把查詢用的 `InvoiceCategory`（`0`/`1`）與字軌用的（`2`）當成同一個。** 同一份文件內同名不同義。
3. **`Upload_Status=2` 當成處理中。** 那是**上傳失敗**的終態，會造成無限輪詢。
4. **`GetInvalid` / `GetAllowanceInvalid` 用 `Buyer_Identifier` 取值。** 這兩支的欄位名是 `BuyerId` / `SellerId`。
5. **只帶 `InvoiceNumber` 不帶 `InvoiceDate`。** 官方明訂 `InvoiceNumber` 有值時 `InvoiceDate` 必填。
6. **不排程掃描「等待確認」與「被退回」。** 這些狀態變化你不會收到通知，不查就不知道。
