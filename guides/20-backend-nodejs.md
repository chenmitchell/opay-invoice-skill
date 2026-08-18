# 20 · Express 後端骨架

用 [`templates/opay-einvoice-client/nodejs/`](../templates/opay-einvoice-client/nodejs/) 接起 Express：`.env` 設計、路由分層、錯誤轉譯。

> **對應 API**：不新增 API；本文說明如何把 client 的 69 支方法接進 Express 服務。規格見 [`references/`](../references/)。
> **前置條件**：Node.js 18+（client 使用內建 `crypto` 與 `fetch`，**無外部相依**）；已完成 [`02-preflight-checklist.md`](02-preflight-checklist.md)。

---

## 1. 專案結構

```
src/
├── server.js               # Express app、錯誤中介層
├── config.js               # 設定（缺少即 process.exit）
├── opayClient.js           # 建立並匯出單一 client 實例
├── routes/
│   ├── invoice.js          # 開立、作廢、註銷重開
│   ├── allowance.js        # 折讓
│   ├── query.js            # 查詢（可安全重試）
│   ├── validation.js       # CheckBarcode / CheckLoveCode / TaxID
│   └── callbacks.js        # NotifyURL / ReturnURL
├── services/
│   └── issueService.js     # 冪等狀態機
├── db/
│   └── invoiceState.js
└── opay-einvoice.js        # ← 直接複製自 templates/，不要改寫
```

> **為什麼 client 要原樣複製**：`templates/opay-einvoice-client/nodejs/opay-einvoice.js` 的加解密已用官方測試向量驗證（執行 `node opay-einvoice.js` 會跑自我測試）。改寫等於重新承擔加解密出錯的風險。

---

## 2. `.env` 與設定

```bash
OPAY_ENV=stage
OPAY_MERCHANT_ID=
OPAY_HASH_KEY=
OPAY_HASH_IV=
OPAY_PLATFORM_ID=
OPAY_TIMEOUT=15
OPAY_WORD_REMAIN_THRESHOLD=500
DATABASE_URL=postgres://user:pass@localhost/shop
```

```js
// config.js
const required = (key) => {
  const v = process.env[key];
  if (!v) {
    console.error(`[啟動失敗] 缺少環境變數 ${key}｜修復建議：複製 .env.example 為 .env 並填入廠商後台取得的值。`);
    process.exit(1);
  }
  return v;
};

const env = process.env.OPAY_ENV || 'stage';
const config = {
  env,
  host: env === 'production' ? 'https://einvoice.opay.tw' : 'https://einvoice-stage.opay.tw',
  merchantId: required('OPAY_MERCHANT_ID'),
  hashKey: required('OPAY_HASH_KEY'),
  hashIv: required('OPAY_HASH_IV'),
  platformId: process.env.OPAY_PLATFORM_ID || '',
  timeout: Number(process.env.OPAY_TIMEOUT || 15),
};

for (const [name, val] of [['OPAY_HASH_KEY', config.hashKey], ['OPAY_HASH_IV', config.hashIv]]) {
  if (Buffer.byteLength(val, 'utf8') !== 16) {
    console.error(`[啟動失敗] ${name} 必須是 16 bytes（AES-128）`);
    process.exit(1);
  }
}
module.exports = config;
```

| 規則 | 為什麼 |
|---|---|
| 缺金鑰**直接 `process.exit(1)`** | 有 fallback 的話會靜默用測試金鑰打正式環境 |
| `host` 由 `OPAY_ENV` 推導 | 避免「host 正式、金鑰測試」的組合 |
| 長度在啟動時檢查 | 早失敗好過在第一筆訂單時失敗 |

---

## 3. ⚠️ Node.js 專屬陷阱：`Date.now()` 是毫秒

```js
// ❌ 全部請求都會失敗
RqHeader: { Timestamp: Date.now() }

// ✅
RqHeader: { Timestamp: Math.floor(Date.now() / 1000) }
```

歐付寶的 `Timestamp` 是 **Unix 秒**。client 內部已經處理好，但如果你自己組 payload（例如寫測試或 debug 工具）就會踩到。

> **為什麼這個錯誤特別惱人**：毫秒的數值是秒的一千倍，換算成時間是幾萬年後，**每一支 API 都會失敗**，而錯誤訊息只是籠統的 `TransCode` 失敗。看起來像是金鑰錯誤。

---

## 4. ⚠️ URLEncode 校正

Node.js 的 `encodeURIComponent()` **不符合**歐付寶要求的 .NET 慣例：

| 字元 | .NET（歐付寶要的） | `encodeURIComponent` |
|---|---|---|
| 空格 | `+` | `%20` |
| `!` `*` `(` `)` | **不編碼** | `!` `*` `(` `)`（相同） |
| `~` | `%7E` | `~`（**不編碼，不符**） |
| 十六進位 | 大寫 | 大寫 |

client 已做校正。校正表與逐語言實作見 [`urlencode-table.md`](../references/urlencode-table.md)。

> **為什麼這個錯誤很難發現**：只有當資料**剛好含有**空格或 `~` 時才會失敗。用「測試商品」當品名永遠不會踩到，用「有機咖啡豆 200g」就會。**測試資料一定要包含空格與特殊符號。**

---

## 5. 路由分層

依「可否安全重試」分層：

| 層 | 路由 | 中介層 |
|---|---|---|
| 唯讀 | `query.js`、`validation.js` | 自動重試 + 快取 |
| 🚫 財務動作 | `invoice.js`、`allowance.js` | 冪等鎖 + audit log |
| 回呼 | `callbacks.js` | 冪等 + 回 `1\|OK` |

```js
// routes/invoice.js
const router = require('express').Router();
router.post('/issue', async (req, res, next) => {
  try {
    res.json(await issueService.issueOnce(req.body));   // 冪等邏輯在 service
  } catch (err) { next(err); }
});
module.exports = router;
```

---

## 6. 冪等 service

```js
// services/issueService.js —— 以 Postgres 為例
async function issueOnce(payload) {
  const relate = toRelateNumber(payload.orderId);       // 穩定推導 + toUpperCase + 截 30

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const { rows } = await client.query(
      'SELECT status, result FROM invoice_state WHERE relate_number = $1 FOR UPDATE',
      [relate],
    );
    if (rows[0]?.status === 'SUCCEEDED') { await client.query('COMMIT'); return rows[0].result; }
    if (rows[0]?.status === 'IN_FLIGHT') { await client.query('COMMIT'); throw new Conflict('處理中'); }
    await client.query(
      `INSERT INTO invoice_state (relate_number, status) VALUES ($1, 'IN_FLIGHT')
       ON CONFLICT (relate_number) DO UPDATE SET status = 'IN_FLIGHT'`, [relate]);
    await client.query('COMMIT');                        // ← 送出「前」就 commit
  } finally { client.release(); }

  try {
    const result = await opay.issue(relate, payload.print, payload.donation,
                                    payload.taxType, payload.salesAmount,
                                    payload.items, payload.invType, payload.extra);
    await markSucceeded(relate, result);
    return result;
  } catch (err) {
    if (isUnknownOutcome(err)) throw new ServiceUnavailable('開立結果未知，系統將自動對帳');
    await markFailed(relate, err);
    throw err;
  }
}
```

**關鍵順序**：`IN_FLIGHT` 必須在發出 HTTP 請求**之前** commit。完整說明見 [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md)。

> ⚠️ **Node.js 的單執行緒不等於沒有併發問題。** 兩個 HTTP 請求可以同時進入 `issueOnce()` 並各自 `await`。冪等保護必須靠**資料庫的 `FOR UPDATE`**（或唯一索引），不能靠 JavaScript 的執行模型。

---

## 7. 錯誤中介層

```js
// server.js
app.use((err, req, res, next) => {
  if (err.name === 'OPayEInvoiceError') {
    // 🚫 不翻譯、不分類 RtnCode —— 官方沒有公開完整錯誤碼表
    console.error('opay_error', {
      endpoint: err.endpoint, transCode: err.transCode, transMsg: err.transMsg,
      rtnCode: err.rtnCode, rtnMsg: err.rtnMsg,
    });
    const reference = saveErrorForSupport(err);
    return res.status(400).json({ message: '發票處理失敗，請聯繫客服', reference });
  }
  res.status(500).json({ message: '系統錯誤' });
});
```

| 對外 | 對內 |
|---|---|
| 通用文案 + 參考碼 | `TransCode`/`TransMsg`/`RtnCode`/`RtnMsg` **原樣** |

> 🚫 不要建自己編的錯誤碼對照表。官方三份文件的附錄都只寫「請到廠商後台查詢」。詳見 [`error-handling.md` §0](../references/error-handling.md)。

---

## 8. 回呼路由

```js
// ⚠️ 歐付寶送的是表單編碼，不是 JSON
app.use('/opay', express.urlencoded({ extended: false }));

router.post('/notify', async (req, res) => {
  const { tsr, invoicenumber, invoicedate, inv_error } = req.body;
  if (invoicenumber) await markIssued(tsr, invoicenumber, invoicedate);
  else await markIssueFailed(tsr, inv_error);
  res.type('text/plain').send('1|OK');      // ⚠️ 必須正確回應，否則會被重送
});
```

> **最常見的失敗**：全域只掛了 `express.json()`，於是 `req.body` 是空物件。歐付寶送的是 `application/x-www-form-urlencoded`，**必須掛 `express.urlencoded()`**。

---

## 9. 排程任務

```
每 5 分鐘   → 對帳：逾時的 IN_FLIGHT 用 getIssue 收斂
每 1 小時   → 字軌餘量檢查，低於門檻推播
每日        → B2B：掃描「等待確認」與「被退回」
每期首日    → 下一期字軌檢查、上一期空白未使用發票處理
```

---

### 常見錯誤

1. **用 `Date.now()` 當 `Timestamp`。** 那是毫秒，會讓所有 API 失敗，且錯誤訊息看起來像金鑰問題。
2. **用 `encodeURIComponent()` 直接編碼。** 空格會變 `%20` 而不是 `+`，`~` 不會被編碼。只有資料含空格或 `~` 時才會失敗，很容易漏測。
3. **只掛 `express.json()`。** 回呼是表單編碼，`req.body` 會是空的。
4. **以為單執行緒就不會有併發。** 兩個請求可以同時 `await`。冪等要靠資料庫鎖。
5. **金鑰有預設值。** 缺少時應該 `process.exit(1)`。
6. **測試資料只用「測試商品」。** 不含空格與特殊符號，測不出 URLEncode 的問題。
