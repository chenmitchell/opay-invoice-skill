---
description: 字軌管理與餘量檢查 —— 號碼用完就開不出發票，這是最容易在週末尖峰爆掉的地方
---

# /opay-words —— 字軌管理與餘量檢查

**發票號碼用完，就是開不出發票。** 沒有備援、沒有降級、沒有「先開了再補」。
這是電子發票串接裡最典型的「可預期的災難」：它一定會發生在你沒注意的那個期別交界。

## 先解釋名詞（使用者常常聽不懂「字軌」）

- **字軌**：發票號碼前兩碼英文字母，例如 `AA`。由財政部按期別配發給營業人。
- **期別**：電子發票以**兩個月**為一期（1-2 月、3-4 月、…、11-12 月）。
  每一期的字軌與號碼區間都是獨立的，**跨期不能用**。
- **配號**：財政部核配給你的號碼區間，例如 `AA00000000` ～ `AA00000049`。
- **字軌狀態**：`暫停使用` / `使用中` / `停用`。只有「使用中」的字軌開得出發票。

## 這一組會用到的 API

| 想做的事 | B2C API | 文件 |
|---|---|---|
| 查財政部配了哪些號給我 | `GetGovInvoiceWordSetting` | i100 §4 |
| 把配到的號碼設定進歐付寶 | `AddInvoiceWordSetting` | i100 §5 |
| 啟用／停用某一組字軌 | `UpdateInvoiceWordStatus` | i100 §6 |
| 查目前字軌設定與剩餘數量 | `GetInvoiceWordSetting` | i100 §17 |
| 查空白未使用發票 | `QueryBlankInvoiceList` | i100 §27 |
| 設定空白發票是否自動上傳 | `BlankInvAutoUploadSetting` | i100 §28 |
| 下載空白發票清單 | `DownLoadBlankInvList` | i100 §29 |

B2B 對應 `B2BInvoice/AddInvoiceWordSetting`（i200 §5）、`UpdateInvoiceWordStatus`（§6）、
`GetInvoiceWordSetting`（§28）。
離線發票另有 `GetOfflineInvoiceWordSetting`（i301 §12）與
`GetOfflineInvoiceWordSettingWithAutoSplit`（§11）。

## 標準流程

1. **查配號**：`GetGovInvoiceWordSetting`，帶年度與期別。
2. **設定字軌**：`AddInvoiceWordSetting`，把區間寫進歐付寶。
3. **啟用**：`UpdateInvoiceWordStatus` 設為「使用中」。
   **這一步最常被忘記** —— 設定完但沒啟用，開立時會直接失敗。
4. **驗證**：`GetInvoiceWordSetting` 確認狀態是「使用中」且剩餘數量正確。

## 餘量檢查：輸出格式

```
字軌餘量檢查（2026 年 7-8 月期）

  字軌   區間                        已用    剩餘    狀態      評估
  AA     AA00000000–AA00000049       38      12      使用中    🟥 低於警戒值
  AB     AB00000000–AB00000099       0       100     暫停使用  🟨 尚未啟用

  合計剩餘：112 張
  近 7 日平均開立：18 張／日
  預估可撐：      約 6.2 天
  下一期別開始：  2026-09-01（距今 14 天）

  ⚠️ 預估用罄日早於下一期別開始日 —— 需要立刻處理。
```

**警戒值怎麼抓**：至少要蓋住「尖峰時段兩天的開立量」。
不要設固定張數，要跟著實際用量每季校準。

## 期別交界：這不是「可能會壞」，是「一定會壞」

在每一期的最後兩週，主動提醒使用者：

1. 下一期的配號拿到了嗎？（`GetGovInvoiceWordSetting`）
2. 設定進歐付寶了嗎？（`AddInvoiceWordSetting`）
3. 啟用了嗎？（`UpdateInvoiceWordStatus`）
4. 舊字軌的空白發票處理了嗎？（`QueryBlankInvoiceList`）

## 監控建議

`GetInvoiceWordSetting` 是**唯讀**的，也是正式環境健康檢查的首選：
它不需要任何既有資料當參數，只要年度就查得到，永遠有得查。
詳見 `guides/24-prod-monitoring.md`。

`templates/telegram-bot/` 與 `templates/discord-bot/` 都內建餘量告警，
設定 `WORD_REMAIN_THRESHOLD` 即可。
