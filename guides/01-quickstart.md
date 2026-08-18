# 01 · Quickstart — 從一句話到第一張測試發票（目標 30 分鐘）

用最少的指令，從「我要串歐付寶電子發票」走到「測試環境跑出一張真的發票號碼」。

> **對應 API**：[`CheckBarcode`](../references/b2c-api-reference.md#21-手機條碼驗證--checkbarcode)（唯讀熱身）、[`GetInvoiceWordSetting`](../references/b2c-api-reference.md#18-查詢字軌--getinvoicewordsetting)（確認字軌）、[`Issue`](../references/b2c-api-reference.md#4-開立發票一般開立發票--issue)（開立）、[`GetIssue`](../references/b2c-api-reference.md#14-查詢發票明細--getissue)（驗收）
> **前置條件**：本機有 Python 3.8+（或 Node 18+／PHP 7.4+）、可連外網 443 port、主機時間已校時。**測試環境金鑰是官方公開值，不需要先申請帳號**。

---

## 0. 時間預算

| 階段 | 預計 | 卡住的話看 |
|---|---:|---|
| ① 安裝與設定 | 5 分 | 本文 §1 |
| ② 六步自我驗證（不連外網） | 5 分 | [`23-test-console.md`](23-test-console.md) |
| ③ 唯讀 API 打通 | 5 分 | [`09-b2c-validation.md`](09-b2c-validation.md) |
| ④ 確認字軌可用 | 5 分 | [`03-b2c-word-setting.md`](03-b2c-word-setting.md) |
| ⑤ 開出第一張發票 | 5 分 | [`04-b2c-issue.md`](04-b2c-issue.md) |
| ⑥ 查回來驗收 | 5 分 | [`07-b2c-query.md`](07-b2c-query.md) |

> **為什麼要分六段而不是直接開發票**：`Issue` 失敗的原因至少有四層（網路／加解密／字軌／欄位）。一次到位失敗時，你不知道是哪一層。分段的目的是**讓失敗有座標**。

---

## 1. 三行啟動

```bash
cd templates/opay-test-console
cp .env.example .env && python3 -m pip install fastapi uvicorn requests pycryptodome
set -a && . ./.env && set +a && python3 -m uvicorn backend:app --reload --port 8080
```

開 `http://127.0.0.1:8080`。`.env.example` 內已填好官方公開的**測試環境**值（`OPAY_MERCHANT_ID=2000132`），不用改任何東西就能跑前兩關。

> **為什麼先用主控台而不是直接寫程式**：主控台的第①關完全不連外網，它比對的是官方測試向量。如果你的機器連這關都過不了，寫再多業務邏輯都是白費。

---

## 2. 六步自我驗證（第①關，不連外網）

按下「執行六步自我驗證」，六格全綠再往下。

| 步 | 驗什麼 | 紅燈代表 |
|---:|---|---|
| ① | AES 加密結果 vs 官方測試向量 | 模式／padding／順序錯了，見 [`encryption-aes.md`](../references/encryption-aes.md) |
| ② | .NET URLEncode 校正 | 空格沒轉 `+`、`!*()` 被編掉，見 [`urlencode-table.md`](../references/urlencode-table.md) |
| ③ | 外層 payload 四欄位 | `PlatformID` / `MerchantID` / `RqHeader` / `Data` 結構錯 |
| ④ | 本機時差 | **主機沒校時**，10 分鐘驗證區間會炸掉全部 API |
| ⑤ | 加解密往返 | 解密順序顛倒（必須先 AES 解密再 URLDecode） |
| ⑥ | 錯誤處理路徑 | 壞密文沒被攔成可讀錯誤，會變成 HTTP 500 |

逐步的失敗解讀見 [`23-test-console.md`](23-test-console.md)。

---

## 3. 唯讀 API 打通（第②關）

主控台第②關會實際打測試環境的四支**唯讀**API：`CheckBarcode`、`CheckLoveCode`、`GetCompanyNameByTaxID`、`GetInvoiceWordSetting`。

用程式碼做同一件事（Python）：

```python
import os
from opay_einvoice import OPayEInvoiceClient, STAGE_HOST   # templates/opay-einvoice-client/python/

c = OPayEInvoiceClient(
    merchant_id=os.environ["OPAY_MERCHANT_ID"],
    hash_key=os.environ["OPAY_HASH_KEY"],
    hash_iv=os.environ["OPAY_HASH_IV"],
    host=STAGE_HOST,
)
print(c.check_barcode("/ABC+123"))   # 注意：RtnCode=1 只代表「呼叫成功」，還要看 IsExist
```

> ⚠️ **這裡最常見的誤判**：`RtnCode=1` 之後**還要再看 `IsExist` 是 `Y` 還是 `N`**（i100 §20 原文：「若回應代碼 `RtnCode` 為 1(成功)時，請再判斷此欄位值」）。把 `RtnCode=1` 當成「條碼存在」，會讓假載具一路帶到開立階段才爆炸。

打不通就對照 [`error-handling.md` §2.1](../references/error-handling.md)：多半是防火牆沒用 FQDN 放行、或 TLS 低於 1.2。

---

## 4. 確認字軌可用（第③關之前）

```python
words = c.get_invoice_word_setting(invoice_year="115", invoice_category=1)  # 民國年；B2C 固定 1
```

| 回傳 `UseStatus` | 意義 | 能不能開發票 |
|:---:|---|---|
| `1` | 未啟用 | ❌ 要先 `UpdateInvoiceWordStatus` 設成 `2` |
| `2` | **使用中** | ✅ |
| `3` | 已停用 | ❌ **且不可逆** |
| `4` | 暫停中 | ❌ |
| `5` | 待審核 | ❌ 等審核 |
| `6` | 審核不通過 | ❌ 要重新處理 |

> **為什麼要先查**：新增字軌後預設是「已審核通過但**未啟用**」（i100 §5 注意事項）。很多人第一次 `Issue` 失敗，就是卡在這一格。查一次只要一秒，比翻參數表快得多。
>
> 剩餘張數的粗估算法：`InvoiceEnd - InvoiceNo`（`InvoiceNo` 是「目前已使用號碼」）。這也是 [`templates/telegram-bot/bot.py`](../templates/telegram-bot/bot.py) 的 `check_word_remaining()` 用的算法。

`InvoiceCategory` 必須是 `1`（B2C），否則官方原文明寫「會查無資料」。B2B 是 `2`、離線是 `4`。

---

## 5. 開出第一張測試發票（第③關）

主控台第③關預設**關閉**，要在 `.env` 設 `OPAY_ALLOW_ISSUE_DEMO=true`，前端還要再勾一次確認框。

> **為什麼要兩道鎖**：`Issue` 會消耗一個**真實的財政部配號**，而且**只能作廢、不能刪除**。就算在測試環境，號碼也是有限資源。

程式碼版本：

```python
issued = c.issue(
    relate_number="QUICKSTART-0001",   # 特店自訂編號，唯一、大小寫視為相同、勿用特殊符號
    print_mark="0",                    # 不列印
    donation="0",                      # 不捐贈
    tax_type="1",                      # 應稅
    sales_amount=100,                  # 含稅總額，整數、不可為 0
    items=[{"ItemName": "測試商品", "ItemCount": 1, "ItemWord": "個",
            "ItemPrice": 100, "ItemAmount": 100}],
    inv_type="07",                     # 一般稅額；字串，前導 0 不能掉
)
print(issued["InvoiceNo"], issued["InvoiceDate"])
```

**三選一互斥規則**（超過一項就會失敗，完整規則見 [`04-b2c-issue.md`](04-b2c-issue.md)）：

| 你要的 | `CustomerIdentifier` | `CarrierType` | `Donation` | `Print` |
|---|---|---|---|---|
| 純載具 | 空 | `1`/`2`/`3`… | `0` | `0` |
| 捐贈 | 空 | 可空 | `1` + `LoveCode` | 必須 `0` |
| 統編（B2C 帶統編） | 8 碼 | 依 `Print` 連動 | 必須 `0` | 見 04 |

---

## 6. 查回來驗收（第④關）

```python
detail = c.get_issue(relate_number="QUICKSTART-0001")
```

查得到、`IIS_Invoice_No` 有值 → **恭喜，第一張測試發票完成**。

> **為什麼一定要查一次**：這一步同時驗證了兩件事 —— (1) 發票真的存在，(2) 你的 `RelateNumber` 真的可以當查詢鍵。第 (2) 點是後面所有冪等機制的基礎，見 [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md)。

---

## 7. 接下來做什麼

| 下一步 | 為什麼現在就要做 |
|---|---|
| [`02-preflight-checklist.md`](02-preflight-checklist.md) | 正式環境的前置作業有審核與等待期，越早開始越好 |
| [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md) | 上線前沒有冪等機制 = 遲早重複開票 |
| [`10-b2c-notify-settings.md`](10-b2c-notify-settings.md) | 設定字軌剩餘通知，避免某天早上突然開不出發票 |
| [`24-prod-monitoring.md`](24-prod-monitoring.md) | 正式環境的健康檢查**絕不可以**用 `Issue` |

---

### 常見錯誤

1. **跳過六步自我驗證直接打 API。** 加解密錯誤在 API 端的回應是籠統的參數錯誤，你會以為是欄位填錯，花好幾小時翻參數表。**離線驗證五分鐘，可省下半天。**
2. **主機沒校時。** 症狀是「有時成功有時失敗」，最難查。`Timestamp` 驗證區間只有 10 分鐘。跑 `timedatectl` / `chronyc tracking` 確認 NTP 有在同步。
3. **`InvType` 送成數字 `7`。** 型態是 `String(2)`，必須是 `"07"`。用整數存 DB 再序列化回 JSON 就會掉前導零。
4. **把 `RelateNumber` 加上隨機碼「避免撞號」。** 這樣做等於自廢冪等：重試時產生新的編號 → 開出第二張發票。`RelateNumber` 必須由訂單 ID **穩定推導**。
5. **在測試環境填真實 Email。** 官方明寫「測試環境請勿帶入真實電子信箱，避免個資外洩」，而且測試環境本來就不發信、只驗規則。
6. **以為測試發票可以刪掉。** 不行。只能作廢，而且會消耗字軌號碼。示範用的訂單編號請加明顯前綴（例如 `QUICKSTART-`），方便日後辨識。
