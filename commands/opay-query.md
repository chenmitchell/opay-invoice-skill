---
description: 查詢發票、折讓、作廢明細與字軌狀態 —— 唯讀操作，正式環境也安全
---

# /opay-query —— 查詢

查詢類 API 全部是**唯讀**的，不會改變任何狀態，正式環境也可以放心呼叫。
這也是為什麼健康檢查只能用這一類（見 `guides/24-prod-monitoring.md`）。

## 先問：要查什麼？

| 想知道的事 | B2C API | B2B API | 文件 |
|---|---|---|---|
| 這張發票開成功了嗎、內容是什麼 | `GetIssue` | `GetIssue` / `GetIssueConfirm` | i100 §13、i200 §18–19 |
| 這張發票開過哪些折讓 | `GetAllowanceList` | `GetAllowance` / `GetAllowanceConfirm` | i100 §14、i200 §24–25 |
| 作廢紀錄 | `GetInvalid` | `GetInvalid` / `GetInvalidConfirm` | i100 §15、i200 §20–21 |
| 作廢折讓紀錄 | `GetAllowanceInvalid` | `GetAllowanceInvalid` / `GetAllowanceInvalidConfirm` | i100 §16、i200 §26–27 |
| 退回紀錄（B2B 專有） | —— | `GetReject` / `GetRejectConfirm` | i200 §22–23 |
| 字軌與剩餘號碼 | `GetInvoiceWordSetting` | `GetInvoiceWordSetting` | i100 §17、i200 §28 |
| 財政部配號結果 | `GetGovInvoiceWordSetting` | —— | i100 §4 |
| 空白未使用發票 | `QueryBlankInvoiceList` / `DownLoadBlankInvList` | —— | i100 §27、§29 |
| 統編對應的公司名稱 | `GetCompanyNameByTaxID` | `GetCompanyNameByTaxID` | i100 §22、i200 §29 |
| 手機條碼是否有效 | `CheckBarcode` | —— | i100 §20 |
| 捐贈碼是否有效 | `CheckLoveCode` | —— | i100 §21 |

**B2B 的「查詢」與「查詢確認」是兩支不同的 API。**
只查前者你只會看到「已開立」，看不到對方確認了沒有，這是 B2B 最常見的誤解。

## 查 `GetIssue` 的兩種查法

- 用 `RelateNumber`（你自己的訂單編號）—— **逾時後要確認開立結果就用這個**
- 用 `InvoiceNo` + `InvoiceDate` —— 已經知道發票號碼時用這個

## 輸出格式

查到之後用繁體中文表格整理，至少呈現：

```
發票號碼：      AA12345678
開立日期：      2026-08-18 14:32:05
自訂編號：      ORDER-20260818-001
買受人：        王小明（統編：無）
狀態：          已開立 / 已作廢 / 已折讓
總金額：        NT$ 1,050（含稅）
載具：          手機條碼 /ABC1234
明細：
  1. 咖啡豆 × 2 @ 500 = 1,000
```

若查無資料，先確認三件事再說「查不到」：
1. 環境對不對（測試查不到正式的發票，反之亦然）
2. 特店編號與金鑰是不是同一組
3. `InvoiceDate` 的日期格式與時區（歐付寶用台北時間）

## 錯誤判讀

`RtnCode != 1` 一律查 `references/error-handling.md`。
最常見的是 `TransCode` 就先失敗了 —— 那通常代表 HashKey / HashIV 或特店編號配錯，
不是資料有問題。
