# 26 · Discord Bot — 綁定、推播、選單、二次確認

[`templates/discord-bot/`](../templates/discord-bot/) 的使用方式。功能與 Telegram 版本一致，差別在指令前綴、Intent 設定與頻道權限模型。

> **對應 API**：bot 內部使用 [`GetIssue`](../references/b2c-api-reference.md#14-查詢發票明細--getissue)、[`GetInvoiceWordSetting`](../references/b2c-api-reference.md#18-查詢字軌--getinvoicewordsetting)、[`Invalid`](../references/b2c-api-reference.md#10-作廢發票--invalid)、[`Allowance`](../references/b2c-api-reference.md#8-開立折讓一般開立折讓紙本開立-allowance)
> **前置條件**：已在 Discord Developer Portal 建立應用程式與 bot；**已開啟 MESSAGE CONTENT INTENT**（見 §2）；已完成 [`02-preflight-checklist.md`](02-preflight-checklist.md)。

---

## 1. 與 Telegram 版本的差異

| 面向 | Telegram | Discord |
|---|---|---|
| 指令前綴 | `/`（固定） | `COMMAND_PREFIX`，**預設 `!`，可自訂** |
| 綁定對象 | 聊天室（chat） | **頻道**（channel） |
| 額外設定 | 無 | 🚨 **必須開啟 MESSAGE CONTENT INTENT** |
| 事件接收埠 | 8790 | 8791 |
| 訊息機制 | long polling | Gateway（discord.py） |

其餘（綁定驗證、事件推播、字軌檢查、二次確認、audit log）**設計完全一致**，可直接參考 [`25-telegram-bot.md`](25-telegram-bot.md)。

---

## 2. 🚨 必做：開啟 MESSAGE CONTENT INTENT

**Developer Portal → 你的應用程式 → Bot → Privileged Gateway Intents → 開啟「MESSAGE CONTENT INTENT」。**

> **不開會怎樣**：bot **收得到訊息事件，但讀不到訊息內容**，所有指令都不會有任何反應。
>
> **為什麼這個問題特別難查**：bot 正常上線、log 顯示已連線、沒有任何錯誤訊息，就是打指令沒反應。你會去懷疑前綴設錯、懷疑權限、懷疑程式碼——**唯獨不會想到是 Portal 上一個沒開的開關**。這是 Discord bot 開發最常見的第一個坑。

---

## 3. 設定

```bash
cd templates/discord-bot
cp .env.example .env
python3 -m pip install discord.py requests pycryptodome
python3 bot.py
```

| 變數 | 說明 | 注意 |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Developer Portal → Bot → Reset Token（通常 59 碼以上） | ⚠️ **不要誤填 Application ID 或 Public Key** |
| `ADMIN_TOKEN` | 綁定頻道用的密碼 | `openssl rand -hex 16`；勿在公開頻道貼出 |
| `COMMAND_PREFIX` | 指令前綴，預設 `!` | 與其他 bot 衝突時可改成 `opay!` |
| `NOTIFY_TOKEN` | `/notify` 的 `X-Notify-Token` | 留空只限本機測試 |
| `NOTIFY_PORT` | 事件接收埠（**只綁 `127.0.0.1`**） | 預設 8791 |
| `BOT_DB_PATH` / `AUDIT_LOG_PATH` | 本機狀態與稽核 log | 納入備份 |
| `WORD_REMAIN_THRESHOLD` / `WORD_CHECK_INTERVAL` | 字軌警戒與檢查間隔 | 見 [`24`](24-prod-monitoring.md) §3.2 |
| `LARGE_AMOUNT_WARN` | 大額提醒門檻 | 只警示不阻擋 |
| `CONFIRM_TTL_SECONDS` | 驗證碼有效秒數 | 預設 300 |

> ⚠️ **`COMMAND_PREFIX` 用 `!` 很容易與其他 bot 衝突。** 兩支 bot 同時回應 `!help` 會很吵，而且更糟的是**兩支 bot 都嘗試回應 `!invalid`**。在有多支 bot 的伺服器，改成 `opay!` 這類獨特前綴。

---

## 4. 指令選單

前綴以 `!` 為例：

| 指令 | 用途 | 危險？ |
|---|---|:---:|
| `!bind <ADMIN_TOKEN>` | 綁定本頻道 | — |
| `!unbind` | 解除綁定 | — |
| `!today` | 今日開立張數與金額 | — |
| `!invoice <發票號碼> [開立日期]` | 查發票明細 | — |
| `!words` | 查字軌剩餘數量 | — |
| `!invalid <發票號碼> <開立日期> <原因>` | **作廢發票** | 🚨 |
| `!allowance <發票號碼> <開立日期> <金額> <品名>` | **開立折讓** | 🚨 |
| `!confirm <驗證碼>` / `!cancel <驗證碼>` | 確認／取消危險操作 | — |
| `!help` | 說明 | — |

> ⚠️ `!today` 的資料來源是 bot **本機事件庫**，不是歐付寶（B2C 沒有依日期批次查詢的 API）。商店系統必須在開立後 POST 事件到 `/notify`。

---

## 5. 二次確認

與 Telegram 版本相同的三段流程：**查明細 → 產生 6 碼驗證碼 → `!confirm <code>` 執行**。

| 設計 | 實作要點 |
|---|---|
| 驗證碼**綁定發起者 + 頻道** | 「這組驗證碼不是你在這個頻道建立的」會被拒絕 |
| 有時效 | 逾時回「驗證碼已逾時，請重新發起指令取得新的驗證碼」 |
| 大額只加註警示 | 不阻擋 |
| 全程 audit log | 誰、何時、對哪張、原因、結果 |

> ⚠️ **Discord 專屬**：指令處理含 SQLite 與 HTTP 呼叫，**必須丟到執行緒執行**，否則會卡住 discord.py 的事件迴圈（bot 會變成「沒反應」）。模板已這樣處理。
>
> **為什麼這件事重要**：卡住事件迴圈的症狀是「bot 有時候不理人」，而且會隨負載變化，非常難重現。

---

## 6. 頻道權限模型

Discord 的權限比 Telegram 複雜，**綁定的是頻道，不是伺服器**。

| 風險 | 對策 |
|---|---|
| bot 被加進伺服器後，任何人在任何頻道下指令 | 未綁定的頻道**只能用 `!bind` 與 `!help`** |
| 綁定到 `#general` | 全伺服器成員都看得到**買受人個資** |
| 有人截圖分享 | 發票明細含 Email、手機、統編 |

**建議做法**：

1. 建立**私有頻道** `#invoice-ops`，只加值班與財務人員。
2. 用 Discord 的頻道權限限制「檢視頻道」。
3. 只綁定這個頻道。
4. **定期檢視成員名單**（離職、轉調）。

> **為什麼要特別強調**：Discord 伺服器通常成員很多、頻道很多、權限設定容易鬆散。發票明細是**個資**，見 [`27-legal-compliance.md`](27-legal-compliance.md) 的最小蒐集與存取控制原則。

---

## 7. 事件推播

與 Telegram 版本相同的事件格式：

```json
{"event": "issue_failed", "relate_number": "ORD20260818001", "error": "…"}
```

| 事件 | 意義 |
|---|---|
| `issue_success` / `issue_failed` | 開立結果 |
| `invalid` / `allowance` | 不可逆動作的紀錄 |
| `word_low` | 字軌低於警戒 |

```python
requests.post("http://127.0.0.1:8791/notify", json=payload,
              headers={"X-Notify-Token": os.environ["NOTIFY_TOKEN"]}, timeout=3)
```

⚠️ **推播失敗不可影響主流程**：短 timeout、包 try/except、失敗只寫 log。

---

## 8. 常駐化

```ini
# /etc/systemd/system/opay-invoice-discord.service
[Unit]
Description=OPay e-invoice Discord bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/opay-invoice-discord
EnvironmentFile=/opt/opay-invoice-discord/.env
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10
User=opaybot

[Install]
WantedBy=multi-user.target
```

> **同時跑 Telegram 與 Discord 兩支 bot 時**：`NOTIFY_PORT` 與 `BOT_DB_PATH` 必須不同（模板預設 8790 / 8791），且商店系統要**分別 POST 到兩個埠**。共用同一個 SQLite 檔會造成鎖競爭。

---

### 常見錯誤

1. **沒開 MESSAGE CONTENT INTENT。** bot 上線正常、沒有錯誤訊息、指令完全沒反應。這是第一個要檢查的地方。
2. **`DISCORD_BOT_TOKEN` 填成 Application ID 或 Public Key。** 三個值長得都像亂碼，很容易拿錯。
3. **綁定到 `#general`。** 全伺服器成員都能看到買受人個資。用私有頻道。
4. **`COMMAND_PREFIX` 用預設 `!` 且伺服器有其他 bot。** 指令會互相干擾。
5. **同時跑兩支 bot 卻共用 `NOTIFY_PORT` 或 `BOT_DB_PATH`。** 埠衝突或 SQLite 鎖競爭。
6. **在事件迴圈裡直接做 HTTP 呼叫。** bot 會變成「有時候不理人」，且難以重現。
7. **`/notify` 埠開到公網。** 只綁 `127.0.0.1`。
