# 13 · B2B 交易對象維護與發送通知

`MaintainMerchantCustomerData` 是 B2B 所有 API 的上游前提；`Notify` 負責通知交易相對人。

> **對應 API**：[`MaintainMerchantCustomerData`](../references/b2b-api-reference.md#1-交易對象維護--maintainmerchantcustomerdata)、[`Notify`](../references/b2b-api-reference.md#2-發送通知--notify)
> **前置條件**：已於財政部平台完成「授權歐付寶」（[`02-preflight-checklist.md`](02-preflight-checklist.md) §2.3）；已讀 [`12-b2b-overview.md`](12-b2b-overview.md) 了解存證／交換模式。

---

## 1. 為什麼交易對象維護是第一步

官方原文（i200 §3）：

> **串接本文件其他 API 前，必須先以本 API 設定交易對象（`type`）與開立形式（`ExchangeMode`）。**

也就是說，`ExchangeMode`（存證／交換）**不是全公司一個開關，而是「每一個交易對象各自的設定」**。你可以對 A 公司用存證、對 B 公司用交換。

> **為什麼這樣設計**：交換模式需要**對方也在財政部平台完成接收設定**。有些客戶做了、有些沒做。強制全公司一致會讓你被最慢的那個客戶卡住。

---

## 2. `MaintainMerchantCustomerData` 參數

```python
c.b2b_maintain_merchant_customer_data(
    action="Add",                 # Add 新增 / Update 編輯 / Delete 刪除
    identifier="12345675",        # 統一編號，8 碼數字，⚠️ 設定後不可變更
    customer_type="1",            # type：1 買方 / 2 賣方 / 3 買賣方（欄位名全小寫 type）
    company_name="範例科技股份有限公司",
    trading_slang="EXAMPLE-CO",   # 交易暗語，必填
    exchange_mode="0",            # 0 存證 / 1 交換
    email_address="ap@example.com;finance@example.com",   # 多組以半形分號區隔
    # 選填：CustomerNumber, PersonInCharge, Address, TelephoneNumber,
    #       FacsimileNumber, SalesName, ContactAddress
)
```

| 欄位 | 規則 | 為什麼要注意 |
|---|---|---|
| `Action` | `Add` / `Update` / `Delete`（**英文字串，首字大寫**） | 離線的 `ActionType` 是**數字 1/2/3**，共用同一個 enum 會送錯型態，見 [`enums.md` §10.8](../references/enums.md#108-️-actionb2b-字串vs-actiontype離線-數字) |
| `Identifier` | 8 碼數字、**註冊當下所使用的統一編號、設定後不可變更** | 🚨 打錯就只能刪掉重建 |
| `type` | **欄位名全小寫**；`1` 買方／`2` 賣方／`3` 買賣方 | 同一支 API 其他欄位都是大駝峰，只有這個小寫，很容易寫成 `Type` |
| `TradingSlang` | **必填** | — |
| `ExchangeMode` | `0` 存證／`1` 交換 | 決定後續所有流程 |
| `EmailAddress` | **必填**，可多組以半形分號區隔 | — |

### 2.1 🚨 `Identifier` 設定後不可變更

**打錯統編的處理方式**：只能 `Delete` 再 `Add`。而且如果這個交易對象**已經有發票紀錄**，刪除會影響什麼，官方文件沒有說明——**請先向歐付寶確認再操作**。

> **防呆做法**：在呼叫 `Add` 之前，先用 [`GetCompanyNameByTaxID`](../references/b2b-api-reference.md#27-統一編號驗證--getcompanynamebytaxid) 驗證統編並取得公司名稱，把回傳的公司名顯示給操作者確認：「你要新增的是『範例科技股份有限公司』，對嗎？」
>
> 統編檢核邏輯**自 2023-01-01 起由「可被 10 整除」改為「可被 5 整除」**；不符合會導致「開立發票、設定交易對象維護資料時失敗」。

---

## 3. `ExchangeMode` 選錯的後果

| 你選了 | 但實際需要 | 會發生什麼 |
|---|---|---|
| `0` 存證 | `1` 交換 | **永遠收不到對方開給你的進項發票**（「加值中心無法接收其他營業人開立給您的電子發票」），且沒有錯誤訊息 |
| `1` 交換 | `0` 存證 | 對方端一直有「待確認」的發票，可能造成對方作業困擾 |
| `1` 交換 | — | **但沒在財政部平台設定由歐付寶接收** → 一樣收不到 |

> **實務建議**：在交易對象建檔的 UI 上，把 `ExchangeMode` 的選項寫成完整句子而不是「存證／交換」兩個詞：
> - `0`：**只開發票給對方，不需要接收對方的發票**（存證）
> - `1`：**需要雙向交換，且已在財政部平台完成接收設定**（交換）
>
> *為什麼*：「存證」與「交換」這兩個詞對非財會背景的操作者沒有任何區別度，選錯的機率極高，而且錯了不會有錯誤訊息。

---

## 4. `Notify` 發送通知

```python
c.b2b_notify(
    invoice_date="2026-08-18",
    invoice_number="AB20000001",
    notify_mail="ap@example.com;finance@example.com",
    invoice_tag="1",       # ⚠️ B2B 是數字 1-10（B2C 是字母 I/II/A/AI/AW）
    notified="C",          # C 客戶 / M 特店 / A 皆發送
)
```

### 4.1 `InvoiceTag` 值域（交換／存證支援範圍不同）

| 值 | 意義 | 交換 | 存證 |
|:---:|---|:---:|:---:|
| `1` | 發票開立 | ✅ | ✅ |
| `2` | 發票作廢 | ✅ | ✅ |
| `3` | 發票退回 | ✅ | ✅ |
| `4` | 開立折讓 | ✅ | ✅ |
| `5` | **作廢折讓** | ✅ | ❌ |
| `6` | 開立發票確認 | ✅ | ❌ |
| `7` | 作廢發票確認 | ✅ | ❌ |
| `8` | 退回發票確認 | ✅ | ❌ |
| `9` | 折讓確認 | ✅ | ❌ |
| `10` | 作廢折讓確認 | ✅ | ❌ |

> ⚠️ **存證模式送 `5` 會收到「買/賣方錯誤」**。官方原文解釋：「存證模式下，根據財政部文件規定**只允許買方開立作廢折讓**，因此以賣方角度使用 5.作廢折讓通知，會收到買/賣方錯誤，**實際意義為無須再另行通知給作廢折讓開立方**。」
>
> **也就是說這個「錯誤」其實是預期行為。** 程式端要能識別這個情況，不要把它當成需要重試或告警的失敗，否則值班人員會被沒有意義的告警淹沒。

> 🚨 **B2C 的 `InvoiceTag` 是字母、B2B 是數字**，欄位名相同。見 [`enums.md` §10.4](../references/enums.md#104-️-invoicetag--b2c-字母-vs-b2b-數字)。

### 4.2 其他規則

| 規則 | 說明 |
|---|---|
| `NotifyMail` | 僅接受標準 Email 格式，可多組以**半形分號**區隔 |
| `AllowanceNo` | 長度**固定 16 碼** |
| 測試環境 | **不會主動發送任何通知**，需於廠商後台使用「補發通知」 |

---

## 5. 交易對象的資料同步

B2B 的交易對象資料在**兩個地方**：你的 CRM／ERP，以及歐付寶。這兩邊會不同步。

| 情況 | 建議做法 |
|---|---|
| 你的 ERP 新增客戶 | 同步呼叫 `Add`；失敗要進重試佇列（**但先查是否已存在**） |
| 客戶改公司名 | 呼叫 `Update`（統編不可改，公司名可以） |
| 客戶統編打錯 | `Delete` + `Add`，且先向歐付寶確認既有發票的影響 |
| 客戶終止合作 | 通常**不建議 `Delete`**，因為歷史發票查詢可能需要 |

> ⚠️ **`Add` 不是冪等的。** 重複 `Add` 同一個統編會怎樣，官方文件沒有明說。**重試前先查現況**，這是所有「建立類」API 的通則，見 [`error-handling.md` §3.1](../references/error-handling.md)。

---

### 常見錯誤

1. **跳過交易對象維護直接開發票。** 官方明寫「串接其他 API 前**必須**先設定」。開立會失敗。
2. **`type` 寫成 `Type`。** 官方欄位名是**全小寫** `type`，同一支 API 只有這個是小寫。
3. **`Identifier` 打錯。** **設定後不可變更**，只能刪除重建。務必先用統編驗證 API 確認公司名稱。
4. **把 B2B 的 `Action`（`Add`/`Update`/`Delete`）與離線的 `ActionType`（`1`/`2`/`3`）共用同一個 enum。** 型態完全不同，會在其中一邊送錯。
5. **存證模式送 `InvoiceTag=5` 然後把回應當成故障告警。** 那是**預期行為**，意思是「無須另行通知」。
6. **在測試環境驗「對方有沒有收到通知信」。** 測試環境不會主動發送任何通知。
