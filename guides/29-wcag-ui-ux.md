# 29 · 商家前台無障礙規範（WCAG）— 發票相關 UI

發票 UI 的無障礙要求：色彩對比 ≥7:1、狀態三重編碼、鍵盤可操作、focus ring、觸控目標 ≥44px、表單 label、`aria-live`。含載具輸入框、統編輸入框、捐贈碼選擇、發票明細表格的具體寫法。

> **對應 API**：無（本文為 UI 規範）。驗證邏輯見 [`09-b2c-validation.md`](09-b2c-validation.md)，欄位互斥規則見 [`04-b2c-issue.md`](04-b2c-issue.md)。
> **前置條件**：已了解載具／捐贈／統編三選一的互斥規則。參考實作見 [`templates/opay-test-console/console.html`](../templates/opay-test-console/console.html)。

---

## 1. 為什麼發票 UI 特別需要無障礙

| 特性 | 影響 |
|---|---|
| **人人都要用** | 發票不是進階功能，是每一筆交易的必經步驟。使用者涵蓋所有年齡與能力 |
| **輸入格式嚴格** | 手機條碼 8 碼、統編 8 碼、捐贈碼 3–7 碼，錯一個字元就開立失敗 |
| **選擇不可逆** | 選了捐贈就不能對獎；KIOSK 只能列印一次 |
| **常在移動中使用** | 門市結帳、手機下單，環境光線與操作穩定度都不理想 |
| **錯誤成本高** | 結帳當下改要 3 秒；開立後才發現要一次人工客服 |

> 🔑 **無障礙在這裡不是「照顧少數人」，是「降低所有人的錯誤率」。** 對比夠高、標籤清楚、錯誤訊息明確的表單，對每個使用者都更不容易填錯。

---

## 2. 基礎規範

| 項目 | 要求 | 為什麼 |
|---|---|---|
| **色彩對比** | 文字與背景 **≥7:1**（WCAG AAA） | 門市與戶外環境光線差；長者對比敏感度下降 |
| **狀態三重編碼** | **顏色 + 圖示 + 文字**，缺一不可 | 約 8% 男性有色覺障礙；螢幕閱讀器讀不到顏色 |
| **鍵盤可操作** | 所有互動元素可用 Tab / Enter / Space 操作 | 有些使用者不用滑鼠；POS 常是純鍵盤操作 |
| **Focus ring** | 明顯可見（例如 `outline: 3px solid #FFFFFF`），**不可 `outline: none`** | 鍵盤使用者需要知道焦點在哪 |
| **觸控目標** | **≥44×44px**（建議 48px） | 手機結帳、手指精確度、手部顫抖 |
| **表單 label** | 每個輸入框都有 `<label for>`，不可只靠 placeholder | placeholder 會在輸入時消失；螢幕閱讀器支援不一 |
| **動態訊息** | 用 `aria-live="polite"` 播報 | 驗證結果是非同步出現的，不播報等於沒有 |

### 2.1 三重編碼的具體寫法

```html
<!-- ❌ 只靠顏色 -->
<span style="color:#DC2626">驗證失敗</span>

<!-- ✅ 顏色 + 圖示 + 文字 -->
<span class="status status--error">
  <span aria-hidden="true">✕</span>
  <span>驗證失敗：查無此手機條碼</span>
</span>
```

```css
.status--error   { color:#FFFFFF; background:#7F1D1D; }  /* 對比 ≥7:1 */
.status--success { color:#FFFFFF; background:#14532D; }
.status--warn    { color:#FFFFFF; background:#78350F; }
```

> **為什麼圖示要 `aria-hidden="true"`**：圖示是給視覺使用者的冗餘編碼。螢幕閱讀器已經會讀到後面的文字，讀出「叉」只是噪音。

---

## 3. 載具輸入框

### 3.1 結構

```html
<fieldset>
  <legend>發票開立方式</legend>

  <div class="radio-row">
    <input type="radio" id="inv-carrier" name="invoice_type" value="carrier">
    <label for="inv-carrier">存入手機條碼載具</label>
  </div>

  <div class="field" id="carrier-field">
    <label for="carrier-num">手機條碼</label>
    <input type="text" id="carrier-num" name="carrier_num"
           inputmode="text" autocapitalize="characters" maxlength="8"
           aria-describedby="carrier-hint carrier-status"
           pattern="^/[0-9A-Z+\-.]{7}$">
    <p id="carrier-hint" class="hint">
      共 8 碼，以斜線 / 開頭，其餘 7 碼為數字、大寫英文或 + - . 符號。
    </p>
    <p id="carrier-status" role="status" aria-live="polite"></p>
  </div>
</fieldset>
```

| 屬性 | 為什麼 |
|---|---|
| `maxlength="8"` | 硬性長度限制，防止多打 |
| `autocapitalize="characters"` | 手機條碼**只接受大寫英文**，自動轉大寫可省去一類錯誤 |
| `aria-describedby` | 把格式說明與驗證結果都關聯到輸入框，螢幕閱讀器會一起讀出 |
| `role="status"` + `aria-live="polite"` | 非同步的驗證結果會被播報，且不打斷使用者當下的操作 |
| **格式說明常駐顯示**，不是錯誤後才出現 | 事前提示比事後糾正有效得多 |

> ⚠️ **不要用 `<input type="tel">`**。手機條碼含英文與 `+ - .`，數字鍵盤打不出來。用 `type="text"` + `inputmode="text"`。
>
> ⚠️ **半形／全形**：官方明訂「英文、數字、符號**僅接受半形字元**」。手機輸入法很容易打出全形 `＋`。前端應該**自動正規化為半形**，而不是報錯給使用者。

### 3.2 驗證回饋的三個階段

| 階段 | 訊息範例 | 播報 |
|---|---|---|
| 輸入中 | （不播報，避免每打一個字就吵） | ❌ |
| 失焦、格式不符 | 「手機條碼須為 8 碼且以 / 開頭，目前為 6 碼」 | ✅ |
| 失焦、格式符合、API 驗證中 | 「驗證中…」 | ✅ |
| 驗證完成、不存在 | 「✕ 查無此手機條碼，請確認是否已向財政部申請」 | ✅ |
| 驗證完成、存在 | 「✓ 手機條碼驗證成功」 | ✅ |
| 財政部維護中 | 「ℹ️ 驗證系統維護中，您仍可完成結帳，或改選其他發票方式」 | ✅ |

> **為什麼「維護中」不能擋住結帳**：那是外部因素，擋住等於損失營收。詳見 [`09-b2c-validation.md`](09-b2c-validation.md) §3.1。訊息要讓使用者知道「這不是你的問題，而且你有其他選擇」。

---

## 4. 統編輸入框

```html
<div class="field">
  <label for="tax-id">統一編號</label>
  <input type="text" id="tax-id" name="customer_identifier"
         inputmode="numeric" maxlength="8" pattern="^[0-9]{8}$"
         aria-describedby="tax-id-hint tax-id-status">
  <p id="tax-id-hint" class="hint">8 碼數字。輸入後將自動帶出公司抬頭。</p>
  <p id="tax-id-status" role="status" aria-live="polite"></p>
</div>

<div class="field">
  <label for="company-name">公司抬頭</label>
  <input type="text" id="company-name" name="customer_name" readonly
         aria-describedby="company-name-hint">
  <p id="company-name-hint" class="hint">依統一編號自動帶入，如需修改請聯繫客服。</p>
</div>
```

| 設計 | 為什麼 |
|---|---|
| `inputmode="numeric"` | 手機會跳數字鍵盤，統編只有數字 |
| **驗證成功自動帶出公司抬頭** | 省去手打公司全名；且抬頭與財政部登記一致，不會出現「XX公司」vs「XX有限公司」的差異 |
| 抬頭欄位 `readonly` + 說明 | 避免使用者改成不一致的名稱；但要說明「為什麼不能改」 |
| **填了統編就要停用捐贈選項** | 有統編不能捐贈（官方規則）。停用時要說明原因，不能只是變灰 |

```html
<!-- 停用時一定要說明原因 -->
<div class="radio-row">
  <input type="radio" id="inv-donate" name="invoice_type" value="donate"
         disabled aria-describedby="donate-disabled-reason">
  <label for="inv-donate">捐贈發票</label>
  <p id="donate-disabled-reason" class="hint">
    已填寫統一編號，依規定不可捐贈。如需捐贈請先清除統一編號。
  </p>
</div>
```

> 🚫 **只把選項變灰而不說明，是最糟的做法。** 使用者會反覆點擊、以為網頁壞了。**停用一定要附帶「為什麼」與「怎麼解除」。**

---

## 5. 捐贈碼選擇

```html
<fieldset>
  <legend>捐贈對象</legend>

  <div class="radio-row">
    <input type="radio" id="love-168001" name="love_code" value="168001">
    <label for="love-168001">OMG 關懷社會愛心基金會（168001）</label>
  </div>

  <div class="radio-row">
    <input type="radio" id="love-custom" name="love_code" value="custom">
    <label for="love-custom">輸入其他捐贈碼</label>
  </div>

  <div class="field">
    <label for="love-code-input">捐贈碼</label>
    <input type="text" id="love-code-input" inputmode="numeric"
           minlength="3" maxlength="7" pattern="^[0-9]{3,7}$"
           aria-describedby="love-hint love-status">
    <p id="love-hint" class="hint">3 至 7 碼數字，開頭可以是 0。</p>
    <p id="love-status" role="status" aria-live="polite"></p>
  </div>

  <p class="notice" role="note">
    <span aria-hidden="true">⚠️</span>
    選擇捐贈後，此張發票<strong>無法對獎、無法索取紙本</strong>，且送出後不可更改。
  </p>
</fieldset>
```

| 規則 | 為什麼 |
|---|---|
| **不可預設勾選捐贈** | 消費者可能在不知情下放棄中獎權利，且不可逆。見 [`27-legal-compliance.md`](27-legal-compliance.md) §4 |
| 後果說明**放在選項旁邊**，不是頁尾小字 | 告知要在決策當下發生才有意義 |
| 提示「開頭可以是 0」 | 捐贈碼首位可以為零，使用者可能以為自己打錯了 |
| **前端不可把捐贈碼轉成數字** | `0123` 會變 `123`，捐給錯的機構。**一律當字串處理** |

---

## 6. 發票明細表格

```html
<table>
  <caption>發票明細（共 3 筆）</caption>
  <thead>
    <tr>
      <th scope="col">發票號碼</th>
      <th scope="col">開立日期</th>
      <th scope="col" class="num">金額</th>
      <th scope="col">狀態</th>
      <th scope="col">操作</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">AA12345678</th>
      <td>2026-08-18</td>
      <td class="num">1,050</td>
      <td>
        <span class="status status--success">
          <span aria-hidden="true">✓</span> 已開立
        </span>
      </td>
      <td>
        <button type="button" aria-label="作廢發票 AA12345678">作廢</button>
      </td>
    </tr>
  </tbody>
</table>
```

| 規則 | 為什麼 |
|---|---|
| `<caption>` 說明表格內容與筆數 | 螢幕閱讀器使用者需要先知道這是什麼表、有多大 |
| `<th scope="col">` / `<th scope="row">` | 讓螢幕閱讀器能把每個儲存格與欄列標題關聯起來 |
| 發票號碼當 `<th scope="row">` | 它是這一列的識別，不是普通資料 |
| **按鈕的 `aria-label` 要含發票號碼** | 否則螢幕閱讀器只會讀到一堆「作廢、作廢、作廢」，不知道是哪一張 |
| 金額右對齊、用等寬數字（`font-variant-numeric: tabular-nums`） | 便於視覺比對 |
| **狀態用三重編碼** | 「已開立／已作廢／已折讓」不能只靠顏色區分 |

### 6.1 狀態對照

| 狀態 | 圖示 | 底色 | 文字 |
|---|:---:|---|---|
| 已開立 | ✓ | `#14532D` | 已開立 |
| 已作廢 | ✕ | `#7F1D1D` | 已作廢 |
| 已折讓 | ↩ | `#78350F` | 已折讓 |
| 處理中 | ⋯ | `#1F2937` | 處理中 |
| **結果未知** | ⚠ | `#78350F` | 結果確認中 |

> **為什麼要有「結果未知」這個狀態**：`IN_FLIGHT`（見 [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md)）不是「成功」也不是「失敗」。UI 上把它顯示成失敗，會讓客服去重開；顯示成成功，會讓人以為結束了。**它需要自己的狀態與自己的說明文字**：「系統正在與歐付寶確認結果，請勿重複操作。」

---

## 7. 不可逆操作的 UI

作廢、折讓、註銷重開都不可逆。

```html
<div role="alertdialog" aria-labelledby="void-title" aria-describedby="void-desc">
  <h2 id="void-title">確認作廢發票 AA12345678？</h2>
  <p id="void-desc">
    <strong>此操作不可復原。</strong>發票號碼將報廢且無法再次使用。
    金額 1,050 元，開立日期 2026-08-18。
  </p>
  <label for="void-reason">作廢原因</label>
  <select id="void-reason" required>
    <option value="">請選擇</option>
    <option value="duplicate">重複開立</option>
    <option value="wrong_taxid">買受人統編錯誤</option>
    <option value="order_void">訂單取消未成立</option>
  </select>
  <button type="button">取消</button>
  <button type="button" class="danger">確認作廢</button>
</div>
```

| 規則 | 為什麼 |
|---|---|
| `role="alertdialog"` | 螢幕閱讀器會提高播報層級 |
| **顯示發票的關鍵資訊**（號碼、金額、日期） | 讓人確認自己選對了那一張 |
| 「不可復原」用 `<strong>` 而不只是紅字 | 顏色不是唯一編碼 |
| 原因用**下拉選單**而非自由輸入 | 便於事後統計分群，見 [`06-b2c-invalid-void.md`](06-b2c-invalid-void.md) §9 |
| **危險按鈕不要放在預設焦點** | 避免 Enter 直接觸發 |
| 焦點要 trap 在對話框內，Esc 可關閉 | 標準對話框無障礙行為 |

> ⚠️ **不要用「反紅按鈕 + 大字」當作唯一的危險提示。** 對色覺障礙者與螢幕閱讀器使用者，那個紅色不存在。**文字本身必須說明後果。**

---

## 8. 自我檢查清單

```
對比與色彩
[ ] 所有文字對比 >= 7:1
[ ] 沒有任何資訊「只靠顏色」傳達
[ ] 每個狀態都有 顏色 + 圖示 + 文字

鍵盤
[ ] 所有互動元素可用 Tab 到達，順序合理
[ ] Focus ring 明顯可見，沒有 outline: none
[ ] 對話框有 focus trap，Esc 可關閉
[ ] 危險按鈕不是預設焦點

觸控
[ ] 所有可點擊目標 >= 44x44px（建議 48px）
[ ] 相鄰目標之間有足夠間距

表單
[ ] 每個 input 都有對應的 <label for>
[ ] 格式說明常駐顯示，不是錯誤後才出現
[ ] 用 aria-describedby 關聯說明與錯誤訊息
[ ] 停用的選項有說明「為什麼」與「怎麼解除」
[ ] 手機條碼用 type="text"，統編與捐贈碼用 inputmode="numeric"
[ ] 全形字元自動正規化為半形，而不是報錯

動態訊息
[ ] 驗證結果用 aria-live="polite" 播報
[ ] 輸入過程中不播報（避免打字時被打斷）
[ ] 「處理中」與「結果未知」有各自的狀態與說明

表格
[ ] 有 <caption>，含筆數
[ ] 有 scope="col" / scope="row"
[ ] 每列的操作按鈕 aria-label 含發票號碼

發票專屬
[ ] 捐贈選項未預設勾選
[ ] 捐贈的後果（不可對獎、不可索取紙本）寫在選項旁
[ ] 填了統編時捐贈選項停用並說明原因
[ ] 捐贈碼在前端全程以字串處理（不轉數字）
[ ] 財政部維護中時不阻擋結帳，提供替代方案
[ ] 不可逆操作有二次確認，且顯示發票關鍵資訊
```

參考實作：[`templates/opay-test-console/console.html`](../templates/opay-test-console/console.html)（深色底白字 ≥9:1、狀態三重編碼、全鍵盤可操作、白色 focus ring、觸控目標 ≥48px、每個輸入框都有 `<label>`、`aria-live="polite"`）。

---

### 常見錯誤

1. **只用紅色表示錯誤。** 色覺障礙者與螢幕閱讀器使用者看不到。必須加圖示與文字。
2. **用 placeholder 取代 label。** 輸入後就消失，而且螢幕閱讀器支援不一致。
3. **`outline: none` 移除 focus ring。** 鍵盤使用者完全不知道焦點在哪。
4. **手機條碼用 `type="tel"`。** 數字鍵盤打不出英文與 `+ - .`。
5. **停用選項只變灰不說明。** 使用者會反覆點擊，以為網頁壞了。
6. **捐贈碼在前端轉成數字。** `0123` 變 `123`，捐給錯的機構。
7. **表格的操作按鈕沒有 `aria-label`。** 螢幕閱讀器只會讀到一連串「作廢、作廢、作廢」。
8. **把 `IN_FLIGHT`（結果未知）顯示成失敗。** 客服會去重開，造成重複開立。
