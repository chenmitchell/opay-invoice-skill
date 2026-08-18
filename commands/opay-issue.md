---
description: 互動式開立一張電子發票 —— 逐項收集必填欄位、先驗證再送出、預設走測試環境
---

# /opay-issue —— 開立發票

你要協助使用者開立一張電子發票。**這是會產生真實稅務資料的操作，流程要慢，不要急著送出。**

## 步驟 0：先確認環境

問清楚：**測試環境還是正式環境？**

- 測試環境 `https://einvoice-stage.opay.tw` —— 預設走這裡
- 正式環境 `https://einvoice.opay.tw` —— 使用者必須**明確說出口**才可以

不論哪一種，**開立後都無法刪除，只能作廢**。測試環境也會消耗字軌號碼。

## 步驟 1：確認要用哪一支

| 情境 | API | 文件 |
|---|---|---|
| 一般開立，立刻開票 | `Issue` | i100 §7 |
| 預約／延遲開立 | `DelayIssue` | i100 §7 |
| 觸發先前的延遲開立 | `TriggerIssue` | i100 §7 |
| 取消尚未觸發的延遲開立 | `CancelDelayIssue` | i100 §7 |
| 開給公司（需對方確認） | `B2BInvoice/Issue` → `IssueConfirm` | i200 §7、§8 |
| 門市斷網先取號後補傳 | `GetOfflineInvoiceWordSetting` → `OfflineIssue` | i301 §12、§13 |

規格逐欄位見 `references/b2c-api-reference.md`。

## 步驟 2：逐項收集必填欄位（一次列完，讓使用者一次補齊）

- `RelateNumber`：特店自訂編號，**必須唯一**。重複送會被擋，這也是最基本的冪等保護。
- `CustomerIdentifier`：統一編號（8 碼）。開給個人留空；填了就會走 B2B 規則。
- `CustomerName` / `CustomerEmail` / `CustomerPhone`：至少要有一種聯絡方式才通知得到。
- `Print`：是否列印（`0` 否／`1` 是）。填了統編通常要 `1`。
- `Donation` + `LoveCode`：捐贈與捐贈碼。捐贈與列印互斥。
- `CarrierType` + `CarrierNum`：載具類別與號碼。列舉值見 `references/enums.md`。
- `TaxType`：課稅別（`1` 應稅／`2` 零稅率／`3` 免稅／`9` 混合）。
- `SalesAmount`：發票總金額，**必須等於各明細計算後的總和**，對不上直接失敗。
- `Items[]`：每一筆要有 `ItemName`、`ItemCount`、`ItemWord`、`ItemPrice`、`ItemAmount`。
- `InvType`：字軌類別（`07` 一般稅額／`08` 特種稅額）。
- `vat`：`Items` 的價格是否含稅。這個欄位最常設錯，設錯會讓總額對不上。

## 步驟 3：送出前，**先做一次本地驗算並唸給使用者聽**

用純文字列出：

```
即將開立（環境：測試 / 正式）
  自訂編號：…
  買受人：…（統編：…／個人）
  課稅別：…
  明細：
    1. 品名 × 數量 @ 單價 = 小計
    …
  合計：…（與 SalesAmount 是否相符：✅ / ❌）
  載具：…／捐贈：…／列印：…
```

**金額對不上就停下來，不要送出。**

## 步驟 4：二次確認

明確問一句：「以上資料正確嗎？送出後只能作廢、無法刪除，且會消耗一組發票號碼。請回覆『確認開立』。」

正式環境要額外唸出：「這是**正式環境**，會產生真實的稅務憑證。」

## 步驟 5：送出並判讀結果

- `RtnCode = 1` 才是成功。其他值查 `references/error-handling.md`。
- 成功後記錄 `InvoiceNo` 與 `InvoiceDate`，並回報給使用者。
- **逾時或連線中斷不要重送。** 改用 `GetIssue` 帶 `RelateNumber` 查詢實際狀態
  （見 `guides/22-idempotency-and-retry.md`）。

## 你**不可以**做的事

- ❌ 不可以自己編造欄位值填進去湊數。缺什麼就問使用者。
- ❌ 不可以在使用者沒有明確確認之前送出。
- ❌ 不可以把開立 API 寫進任何排程、健康檢查或重試迴圈。
