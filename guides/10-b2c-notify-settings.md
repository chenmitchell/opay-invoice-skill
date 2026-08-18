# 10 · B2C 通知開關設定 — 剩餘數量通知是保命機制

四支設定 API 怎麼用；重點放在「**字軌用完會直接開不出發票**」這件事上。

> **對應 API**：[`GetInvoiceNotifySetting`](../references/b2c-api-reference.md#24-取得發票通知開關--getinvoicenotifysetting)、[`InvoiceNotifySetting`](../references/b2c-api-reference.md#25-設定發票通知開關--invoicenotifysetting)、[`GetRemainNotifySetting`](../references/b2c-api-reference.md#26-取得剩餘數量通知開關--getremainnotifysetting)、[`RemainNotifySetting`](../references/b2c-api-reference.md#27-設定剩餘數量通知開關--remainnotifysetting)
> **前置條件**：可用金鑰。設定類 API 是**覆寫語意**，送出前務必先用 Get 讀出現況。

---

## 1. 四支 API 的關係

| API | 管什麼 | 語意 |
|---|---|---|
| `GetInvoiceNotifySetting` | 讀出**發票事件**通知設定 | 讀 |
| `InvoiceNotifySetting` | 設定發票事件通知（**含**剩餘數量欄位） | **覆寫** |
| `GetRemainNotifySetting` | 讀出**字軌剩餘數量**通知設定 | 讀 |
| `RemainNotifySetting` | 設定字軌剩餘數量通知 | **覆寫** |

> 🚨 **設定類是覆寫，不是 patch。** 你送出的內容會取代整組設定。**只想改一個開關卻整組重送、漏掉其他欄位**，會把別人設好的通知關掉。
>
> **正確流程**：`Get` 讀出現況 → 在記憶體中改動要改的那一項 → 整組送回。

```python
current = c.get_invoice_notify_setting()
# 改動：把「開立失敗」通知打開（SelfSetting 的 NotifyType=7）
self_setting = current["SelfSetting"]
for row in self_setting:
    if row["NotifyType"] == 7:
        row["NotifySwitch"] = 1
c.invoice_notify_setting(
    costomer_setting=current["CostomerSetting"],   # ← 官方欄位名就是拼成 Costomer
    self_setting=self_setting,
    inv_header_remain=current["InvHeaderRemain"],
    remain_word=current["RemainWord"],
    email_setting=current["EmailSetting"],
    notify_email=current["NotifyEmail"],
)
```

---

## 2. ⚠️ 官方欄位名拼作 `CostomerSetting`

不是 `CustomerSetting`。**這是官方文件的原始拼字，介接時必須照抄**，拼成正確英文反而會失敗。

> **為什麼要特別寫出來**：IDE 的拼字檢查、Copilot 的自動補全都會「幫你修正」成 `CustomerSetting`。這個錯誤會在 code review 時被當成「修好了」而合併進去。**在程式裡加一行註解說明這是官方拼字**，避免下一個人再改回來。

---

## 3. ⚠️ 同一個 request body 裡有兩套 `NotifyType` / `NotifySwitch`

| 區塊 | `NotifyType` 值域 | `NotifySwitch` 值域 |
|---|---|---|
| `CostomerSetting`（通知消費者） | `1` 開立／`2` 作廢／`3` 折讓／`4` 折讓作廢／`5` 註銷／`6` 中獎 | `0` 關閉／`1` 僅 Email／`2` 僅簡訊／`3` 優先 Email／`4` 優先簡訊／`5` 皆通知 |
| `SelfSetting`（通知自己） | `1`–`6` 同上，**另有** `7` 開立失敗／`8` 消費者索取紙本 | **只有 `0` 關閉／`1` 開啟** |

> 🚨 **同一支 API、同一個 request body、同一個欄位名，兩個區塊的值域完全不同。** 對消費者送 `NotifySwitch=3` 是「優先 Email」；對自己送 `3` 則超出定義。詳見 [`enums.md` §10.5](../references/enums.md#105-️-notifyswitch--notifytype--同一個-request-body-裡兩套)。
>
> **實務建議**：在程式裡用**兩個不同的型別／常數集合**（例如 `ConsumerNotifySwitch` 與 `SelfNotifySwitch`），不要共用一個 enum。共用會讓 IDE 幫你補出錯誤的值，而且編譯期不會報錯。

### 3.1 `SelfSetting` 的 `7` 與 `8` 是重點

| 值 | 意義 | 為什麼一定要開 |
|:---:|---|---|
| `7` | **開立失敗** | 🚨 這是你唯一會即時知道「有訂單開不出發票」的管道。不開就只能等會計月結才發現 |
| `8` | 消費者索取紙本 | 影響出貨流程（要附紙本發票） |

---

## 4. 🔑 剩餘數量通知是保命機制

**字軌用完 = 直接開不出發票。** 不是變慢、不是部分失敗，是**全部的開立都失敗**，而且無法即時補救——你必須向財政部申請配號、登記到歐付寶、等審核、再啟用（見 [`03-b2c-word-setting.md`](03-b2c-word-setting.md)）。

| 參數 | 說明 | 預設 |
|---|---|---|
| `InvHeaderRemain` | 剩餘多少數量時發提醒 | **`20`** |
| `RemainWord` | 單位：`1` = `%`／`2` = 張 | **`2`（張）** |
| `NotifyEmail` | 收件信箱，多組以**半形分號**分隔 | — |

```python
c.remain_notify_setting(
    inv_header_remain=500,       # 剩 500 張就提醒
    remain_word=2,               # 單位：張
    notify_email="ops@example.com;finance@example.com",
)
```

### 4.1 門檻怎麼訂

> 🚫 **預設值 `20` 張對大多數商家來說太低。** 從收到通知到新字軌可用，中間有申請、審核、啟用三段等待，可能是好幾天。20 張撐不到那時候。

**建議公式**：

```
門檻 = 尖峰時段單日開立張數 × 準備新字軌所需天數 × 安全係數(2)
```

| 商家規模 | 單日開立 | 建議門檻 |
|---|---:|---:|
| 小型 | 50 張 | 500 張 |
| 中型 | 500 張 | 3,000 張 |
| 大型 | 5,000 張 | 30,000 張 |

> **為什麼要乘安全係數**：通知是**寄 Email 給人**。人會請假、會漏信、會把它歸到促銷資料夾。門檻要抓到「就算第一封信沒人看到，第二道保險（排程監控）還來得及救」。

### 4.2 兩道保險

| 保險 | 機制 | 誰收到 |
|---|---|---|
| 第一道 | 歐付寶的 `RemainNotifySetting` Email 通知 | 財務／營運信箱 |
| **第二道** | 自己排程呼叫 `GetInvoiceWordSetting` 算剩餘，推播到工作群組 | 值班群組（Telegram / Discord） |

第二道的實作見 [`templates/telegram-bot/bot.py`](../templates/telegram-bot/bot.py) 的 `check_word_remaining()`，與 [`24-prod-monitoring.md`](24-prod-monitoring.md)。

> **為什麼需要兩道**：Email 是「推送到個人信箱」，群組推播是「推送到一群人」。前者的漏接率遠高於後者。而字軌用完的後果，值得兩道保險。
>
> ⚠️ 第二道只算「`UseStatus=2`（使用中）」的字軌。把未啟用或已停用的字軌算進剩餘量，會讓你以為還很多。

---

## 5. `RemainWord` 的單位陷阱

| `RemainWord` | `InvHeaderRemain=20` 的意思 |
|:---:|---|
| `1`（%） | 剩 **20%** 時提醒 |
| `2`（張，預設） | 剩 **20 張**時提醒 |

> **量大時差很多**：一段 10,000 張的字軌，`20%` 是 2,000 張（合理），`20 張`則是 0.2%（來不及）。**設定後一定要用 `GetRemainNotifySetting` 讀回來確認單位**，不要假設預設值是你要的。

---

## 6. 官方文件的已知瑕疵

介接時要有心理準備（原文照錄）：

| 瑕疵 | 影響 |
|---|---|
| `GetInvoiceNotifySetting` 的回傳 Data 範例標示「(待調整)」，且範例中 `CostomerSetting` 未含 `NotifyName`，與參數表不一致 | 程式端要容錯，欄位可能缺 |
| `GetRemainNotifySetting` / `RemainNotifySetting` 範例同樣標示「(待調整)」 | 同上 |
| `InvoiceNotifySetting` 的傳入表中 `CostomerSetting` 只有 `NotifyType`、`NotifySwitch`，沒有 Get 回傳的 `NotifyName` | **不要把 Get 的結果原封不動送回 Set**，要先過濾欄位 |

> **實務做法**：寫一個 `normalize_costomer_setting()`，只保留 `NotifyType` 與 `NotifySwitch` 兩個欄位再送出。直接把 Get 的結果丟回去可能因為多餘欄位被拒。

---

### 常見錯誤

1. **把 `CostomerSetting` 拼成 `CustomerSetting`。** 官方原始拼字就是 `Costomer`，「修正」它會導致失敗。在程式裡加註解防止下一個人改回來。
2. **設定類 API 當成 patch 用。** 它是**覆寫**。只送要改的欄位，會把其他設定清掉。務必先 Get 再整組送。
3. **`SelfSetting` 送 `NotifySwitch=3`。** 那是 `CostomerSetting` 的值域；`SelfSetting` 只有 `0`/`1`。
4. **不開 `SelfSetting` 的 `NotifyType=7`（開立失敗）。** 你會失去唯一即時得知「有訂單開不出發票」的管道。
5. **沿用 `InvHeaderRemain` 預設值 20 張。** 從通知到新字軌可用需要好幾天，20 張撐不到。
6. **只靠歐付寶的 Email 通知。** 信會被漏看。一定要有第二道排程監控 + 群組推播。
