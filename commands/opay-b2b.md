---
description: B2B 營業人間電子發票 —— 每個動作都是兩段式（發起 + 確認），只做一半等於沒做
---

# /opay-b2b —— B2B 開立與確認流程

B2B 與 B2C 最根本的差別，一句話：

> **B2C 是「開出去就結束」，B2B 是「開出去只完成一半，要對方確認才算數」。**

沒搞懂這件事的人，會做完 `Issue` 就以為結束了，然後發票永遠停在「待確認」。

## 成對規則：所有動作都是兩段式

| 動作 | 第一段（發起） | 第二段（確認） | 章節 |
|---|---|---|---|
| 開立 | `Issue` | `IssueConfirm` | §7、§8 |
| 作廢 | `Invalid` | `InvalidConfirm` | §9、§10 |
| 退回（買方發起） | `Reject` | `RejectConfirm` | §11、§12 |
| 折讓 | `Allowance` | `AllowanceConfirm` | §13、§14 |
| 作廢折讓 | `CancelAllowance` | `CancelAllowanceConfirm` | §15、§16 |

**查詢也是成對的**：`GetIssue`（§18）查開立，`GetIssueConfirm`（§19）查確認狀態。
只查前者你看不到對方確認了沒有。作廢、退回、折讓、作廢折讓的查詢同理（§20–§27）。

## B2B 專有的 27 支 API

除了上面的成對動作與查詢，還有：

| 用途 | API | 章節 |
|---|---|---|
| 交易對象維護（建檔買方公司） | `MaintainMerchantCustomerData` | §3 |
| 發送通知 | `Notify` | §4 |
| 字軌與配號設定 | `AddInvoiceWordSetting` | §5 |
| 設定字軌號碼狀態 | `UpdateInvoiceWordStatus` | §6 |
| 註銷重開 | `VoidWithReIssue` | §17 |
| 查詢字軌 | `GetInvoiceWordSetting` | §28 |
| 統一編號驗證 | `GetCompanyNameByTaxID` | §29 |

規格見 `references/b2b-api-reference.md`，教學見 `guides/12-b2b-overview.md` 起。
路徑前綴是 **`/B2BInvoice`**。

## 標準開立流程

1. **確認買方統編有效**：`GetCompanyNameByTaxID`。
   統編錯了整張發票就作廢重開，先驗證比較便宜。
2. **買方建檔**：`MaintainMerchantCustomerData`（第一次交易時）。
3. **開立**：`Issue`。此時狀態是「已開立、待確認」。
4. **確認**：`IssueConfirm`。**這一步做完才算完成。**
5. **驗證**：`GetIssueConfirm` 確認狀態。

## 誰負責確認？先問清楚

`IssueConfirm` 由誰呼叫，取決於雙方協議：

- 常見情況：**賣方（你）自行確認**，因為買方沒有系統介接。
- 也有情況：**買方系統自行確認**，你只要開立就好。

**這件事一定要問使用者，不要替他決定。**
如果他不知道，請他去問對方的資訊窗口，或先看歐付寶後台的設定。

## 狀態機（純文字）

```
   [未開立]
      │ Issue
      ▼
   [已開立・待確認] ──── IssueConfirm ────▶ [已確認・完成]
      │                                          │
      │ Reject（買方退回）                        │ Invalid（賣方作廢）
      ▼                                          ▼
   [待退回確認] ── RejectConfirm ──▶ [已退回]  [待作廢確認] ── InvalidConfirm ──▶ [已作廢]
                                                 │
                                                 │ Allowance（折讓）
                                                 ▼
                                          [待折讓確認] ── AllowanceConfirm ──▶ [已折讓]
```

## 輸出格式（狀態檢查）

```
B2B 發票狀態

  發票號碼：    BB12345678
  買方：        某某股份有限公司（統編 12345678）
  開立：        ✅ 2026-08-18 14:32（Issue）
  確認：        ❌ 尚未確認（IssueConfirm）  ⚠️ 已等待 3 天
  金額：        NT$ 52,500

  下一步：呼叫 IssueConfirm，或聯繫買方請他們在系統中確認。
```

## 你**不可以**做的事

- ❌ 不可以只做 `Issue` 就跟使用者說「開好了」。
- ❌ 不可以把 B2C 的欄位規則直接套用到 B2B。兩份文件的欄位不完全相同。
- ❌ 不可以用 B2C 的字軌開 B2B 發票。字軌類別（`InvType`）不同。
- ❌ 不可以在使用者沒確認前執行作廢、退回、折讓（見 `/opay-void`、`/opay-allowance`）。
