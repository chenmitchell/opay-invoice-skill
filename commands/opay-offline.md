---
description: 離線電子發票 —— 先取號、離線開立、48 小時內上傳；斷網門市的正確做法
---

# /opay-offline —— 離線發票取號與上傳

離線電子發票用在**開立當下可能連不上網**的場景：門市 POS、行動收銀、展場攤位。

核心觀念只有一句：**號碼要「事先」領好。** 斷網當下才想取號，已經來不及了。

## 流程（三段，順序不能顛倒）

```
【平時，有網路】        【現場，可能斷網】       【回線後，48 小時內】
取號並存進本機   ──▶   從本機取一個號開票  ──▶   上傳開立紀錄
```

1. **事先取號**：`GetOfflineInvoiceWordSetting`（區間，i301 §12）或
   `GetOfflineInvoiceWordSettingNumber`（依數量，含隨機碼與加密資料，i301 §12）或
   `GetOfflineInvoiceWordSettingWithAutoSplit`（自動配發，i301 §11）。
   把號碼安全地存在本機。
2. **離線開立**：從本機號碼池取一個，印出發票給客人。
   此時**還沒有**任何資料送到歐付寶。
3. **回線上傳**：`OfflineIssue`（i301 §13）。**上傳期限是開立後 48 小時內。**
   作廢則是 `OfflineInvalid`（i301 §14）。

## 12 支離線 API 一覽

| # | 用途 | API | 章節 |
|---|---|---|---|
| 1 | 查詢特店基本資料 | `GetOfflineMerchantInfo` | §5 |
| 2 | 查詢財政部配號結果 | `GetGovInvoiceWordSetting` | §6 |
| 3 | 管理發票機台 | `OfflineMerchantPosSetting` | §7 |
| 4 | 查詢發票機台 | `QueryOfflineMerchantPosSetting` | §8 |
| 5 | 字軌與配號設定 | `AddInvoiceWordSetting` | §9 |
| 6 | 設定字軌號碼狀態 | `UpdateInvoiceWordStatus` | §10 |
| 7 | 取得自動配發字軌號碼 | `GetOfflineInvoiceWordSettingWithAutoSplit` | §11 |
| 8 | 取得字軌號碼（區間） | `GetOfflineInvoiceWordSetting` | §12 |
| 9 | 取得字軌號碼（依數量） | `GetOfflineInvoiceWordSettingNumber` | §12 |
| 10 | 上傳開立發票 | `OfflineIssue` | §13 |
| 11 | 上傳作廢發票 | `OfflineInvalid` | §14 |
| 12 | 查詢字軌 | `GetInvoiceWordSetting` | §15 |

規格逐欄位見 `references/offline-api-reference.md`，教學見 `guides/18-offline-invoice.md`。
**注意：離線發票的路徑前綴仍然是 `/B2CInvoice`**，不是 `/OfflineInvoice`。

## 取號時要問清楚的事

- **一次要領多少張？** 抓「最長可能斷網時數 × 尖峰每小時開立量 × 安全係數 2」。
- **有幾台機器？** 每台機台要各自 `OfflineMerchantPosSetting` 註冊，
  號碼不能兩台共用同一池，否則會開出重號發票。
- **號碼存在哪？** 本機資料庫，**要有持久化**。存在記憶體裡的話機器一重開就全沒了，
  而那些號碼已經被系統認定配發出去，不會還你。

## 上傳時最容易踩的雷

1. **超過 48 小時**：逾期上傳會失敗，且是稅務違規。
   請把「未上傳筆數」做成監控指標，這是離線發票最重要的單一指標。
2. **`RqHeader.Timestamp` 時差**：驗證區間約 10 分鐘。
   門市機台的時鐘常年不準，**一定要開 NTP 校時**。
3. **重複上傳**：同一張重送會被擋。逾時不要盲目重試，先查再說。
4. **號碼與機台對不上**：用了 A 機台的號碼卻以 B 機台身分上傳。

## 輸出格式（上傳批次結果）

```
離線發票上傳批次結果

  本批筆數：      42
  成功：          40
  失敗：          2
  逾 48 小時：    0  ✅

  失敗明細：
    AA00000031  RtnCode 3000012  時間戳記逾時 → 檢查機台 NTP 校時
    AA00000037  RtnCode 3000009  號碼重複     → 先用 GetIssue 確認是否已上傳成功

  本機待上傳餘額：3 筆（最舊一筆已開立 6.2 小時）
```

## 你**不可以**做的事

- ❌ 不可以把離線號碼池只放在記憶體裡。
- ❌ 不可以讓多台機台共用同一個號碼池。
- ❌ 不可以用 `OfflineIssue` 做正式環境健康檢查 —— 那會產生真實發票，
  是稅務資料污染（見 `guides/24-prod-monitoring.md`）。
