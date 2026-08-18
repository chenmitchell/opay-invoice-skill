# opay-einvoice-client — 歐付寶電子發票核心 SDK 模板

三種語言、同一套設計，各自涵蓋歐付寶電子發票**全部 69 支 API**（B2C 30／B2B 27／離線 12），
不依賴任何歐付寶官方 SDK。

| 檔案 | 語言 | 相依 |
|---|---|---|
| `python/opay_einvoice.py` | Python 3.8+ | `requests`、`pycryptodome`（見 `python/requirements.txt`） |
| `nodejs/opay-einvoice.js` | Node.js 18+ | 無（內建 `crypto` + `fetch`） |
| `php/OPayEInvoice.php` | PHP 7.4+ | 無（內建 `openssl` + `cURL`） |

對應規格：`references/b2c-api-reference.md`、`references/b2b-api-reference.md`、`references/offline-api-reference.md`。

## 設計共通點

- **加解密鐵律**：明文 JSON →`URLEncode`（.NET 慣例：空格→`+`、`!*()` 不編碼）→ AES-128-CBC/PKCS7 → Base64；回來反向。
- **兩層錯誤都檢查**：外層 `TransCode`（1 = 傳輸接收成功）與解密後 `RtnCode`（1 = 業務成功），任一非 1 都丟出帶繁中修復建議的錯誤（可取 `rtn_code` / `rtn_msg` / `trans_code`）。
- **方法命名**：B2C 無前綴、B2B 加 `b2b` 前綴、離線加 `offline` 前綴（名稱本身已含 `Offline` 的不重複加）。
- **選填欄位**：一律用最後一個 `extra` 參數以官方 PascalCase 原樣傳入，例如 `CustomerEmail`、`CarrierType`。
- **金鑰**：正式環境 HashKey / HashIV 只從環境變數讀；檔內出現的金鑰全部是官方公開的**測試環境**值。
- **自我測試**：三支都可直接執行，用官方測試向量驗證加密結果，**不發任何網路請求**。

```bash
python3 python/opay_einvoice.py      # 期望輸出：結果：全部通過 ✅
node    nodejs/opay-einvoice.js
php     php/OPayEInvoice.php
```

## 5 行上手：開發票 / 查發票 / 作廢

### Python

```python
from opay_einvoice import OPayEInvoiceClient, STAGE_HOST
c = OPayEInvoiceClient("2000132", os.environ["OPAY_HASH_KEY"], os.environ["OPAY_HASH_IV"], STAGE_HOST)
issued = c.issue("ORDER-0001", "0", "0", "1", 100, [{"ItemName": "測試商品", "ItemCount": 1, "ItemWord": "個", "ItemPrice": 100, "ItemAmount": 100}], "07")
detail = c.get_issue(invoice_no=issued["InvoiceNo"], invoice_date=issued["InvoiceDate"][:10])
c.invalid(issued["InvoiceNo"], issued["InvoiceDate"][:10], "測試作廢")  # 不可復原
```

### Node.js

```js
const { OPayEInvoiceClient, STAGE_HOST } = require('./opay-einvoice');
const c = new OPayEInvoiceClient({ merchantId: '2000132', hashKey: process.env.OPAY_HASH_KEY, hashIv: process.env.OPAY_HASH_IV, host: STAGE_HOST });
const issued = await c.issue('ORDER-0001', '0', '0', '1', 100, [{ ItemName: '測試商品', ItemCount: 1, ItemWord: '個', ItemPrice: 100, ItemAmount: 100 }], '07');
const detail = await c.getIssue({ invoiceNo: issued.InvoiceNo, invoiceDate: issued.InvoiceDate.slice(0, 10) });
await c.invalid(issued.InvoiceNo, issued.InvoiceDate.slice(0, 10), '測試作廢'); // 不可復原
```

### PHP

```php
require_once __DIR__ . '/OPayEInvoice.php';
$c = new OPayEInvoiceClient('2000132', getenv('OPAY_HASH_KEY'), getenv('OPAY_HASH_IV'), OPayEInvoiceClient::STAGE_HOST);
$issued = $c->issue('ORDER-0001', '0', '0', '1', 100, [['ItemName' => '測試商品', 'ItemCount' => 1, 'ItemWord' => '個', 'ItemPrice' => 100, 'ItemAmount' => 100]], '07');
$detail = $c->getIssue(null, $issued['InvoiceNo'], substr($issued['InvoiceDate'], 0, 10));
$c->invalid($issued['InvoiceNo'], substr($issued['InvoiceDate'], 0, 10), '測試作廢'); // 不可復原
```

## 常見錯誤與修復方向

| 症狀 | 最可能原因 | 修復 |
|---|---|---|
| `TransCode != 1` | 主機時間偏移超過 10 分鐘、MerchantID 與金鑰非同一組 | 校時（NTP）、確認金鑰來源 |
| `AES 解密失敗` | HashKey / HashIV 錯或測試正式混用 | 逐字比對 16 碼、確認沒有多餘空白 |
| 加密結果與官方向量不同 | URLEncode 未用 .NET 慣例 | 空格必須是 `+`、`!*()` 不可編碼 |
| `RtnCode` 非 1 且提到字軌 | 字軌未設定或號碼用罄 | 先呼叫 `get_invoice_word_setting` 查剩餘 |
| 開立 API 逾時 | 網路或對方延遲 | **不要直接重送**，先用 `get_issue` 以 `RelateNumber` 查是否已開立 |

> ⚠️ 作廢（`invalid`）、折讓（`allowance`）、註銷重開（`void_with_re_issue`）都是**不可復原**的動作，
> 請在應用層加上二次確認與 audit log。
