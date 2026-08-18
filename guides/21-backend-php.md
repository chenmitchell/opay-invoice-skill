# 21 · Laravel 後端骨架

用 [`templates/opay-einvoice-client/php/`](../templates/opay-einvoice-client/php/) 接起 Laravel：設定、路由分層、錯誤轉譯，以及 PHP 專屬的 `urlencode` 陷阱。

> **對應 API**：不新增 API；本文說明如何把 client 的 69 支方法接進 Laravel。規格見 [`references/`](../references/)。
> **前置條件**：PHP 7.4+（client 使用內建 `openssl` 與 cURL，**無外部相依**）；已完成 [`02-preflight-checklist.md`](02-preflight-checklist.md)。

---

## 1. 專案結構

```
app/
├── Services/OPay/
│   ├── OPayEInvoice.php        # ← 直接複製自 templates/，不要改寫
│   ├── OPayClientFactory.php   # 由 config 建立 client
│   └── IssueService.php        # 冪等狀態機
├── Http/Controllers/OPay/
│   ├── InvoiceController.php   # 開立、作廢、註銷重開
│   ├── AllowanceController.php
│   ├── QueryController.php     # 查詢（可安全重試）
│   ├── ValidationController.php
│   └── CallbackController.php  # NotifyURL / ReturnURL
├── Models/InvoiceState.php
config/opay.php
database/migrations/xxxx_create_invoice_states_table.php
```

---

## 2. 設定

```php
// config/opay.php
$env = env('OPAY_ENV', 'stage');
return [
    'env'         => $env,
    'host'        => $env === 'production'
                        ? 'https://einvoice.opay.tw'
                        : 'https://einvoice-stage.opay.tw',
    'merchant_id' => env('OPAY_MERCHANT_ID'),
    'hash_key'    => env('OPAY_HASH_KEY'),
    'hash_iv'     => env('OPAY_HASH_IV'),
    'platform_id' => env('OPAY_PLATFORM_ID', ''),
    'timeout'     => (int) env('OPAY_TIMEOUT', 15),
    'word_remain_threshold' => (int) env('OPAY_WORD_REMAIN_THRESHOLD', 500),
];
```

```php
// AppServiceProvider::boot() —— 缺設定就讓應用啟動失敗
foreach (['merchant_id', 'hash_key', 'hash_iv'] as $key) {
    if (blank(config("opay.$key"))) {
        throw new \RuntimeException(
            "[啟動失敗] 缺少 opay.$key｜修復建議：於 .env 設定 OPAY_" . strtoupper($key) . "。"
        );
    }
}
foreach (['hash_key', 'hash_iv'] as $key) {
    if (strlen(config("opay.$key")) !== 16) {
        throw new \RuntimeException("[啟動失敗] opay.$key 必須是 16 bytes（AES-128）");
    }
}
```

> ⚠️ **Laravel 專屬**：跑過 `php artisan config:cache` 之後，`env()` 在**設定檔以外的地方會回 `null`**。所有金鑰一律透過 `config('opay.*')` 取用，不要在 Service 或 Controller 裡直接 `env('OPAY_HASH_KEY')`。
> **為什麼**：本機開發沒 cache 時一切正常，部署到正式環境跑了 `config:cache` 之後金鑰突然變成 `null`，錯誤訊息卻是「AES 解密失敗」——完全指不到真正原因。

---

## 3. 🚨 PHP 專屬陷阱：`urlencode()` 的 `%2A`

這是 PHP 串接歐付寶**最經典的一個坑**。

| 字元 | .NET 慣例（歐付寶要的） | PHP `urlencode()` | PHP `rawurlencode()` |
|---|---|---|---|
| 空格 | `+` | `+` ✅ | `%20` ❌ |
| `*` | **不編碼** | **`%2A`** ❌ | `%2A` ❌ |
| `!` | 不編碼 | `%21` ❌ | `%21` ❌ |
| `(` `)` | 不編碼 | `%28` `%29` ❌ | `%28` `%29` ❌ |
| `~` | `%7E` | `%7E` ✅ | `~` ❌ |

官方文件本身就提供了 `str_replace` 校正範例（見 [`urlencode-table.md` §4](../references/urlencode-table.md)），也就是說**這是官方已知且要求你自行處理的差異**。

```php
// templates/opay-einvoice-client/php/OPayEInvoice.php 已內建校正，大致如下
function opayUrlEncode(string $text): string {
    $encoded = urlencode($text);
    return str_replace(
        ['%2A', '%21', '%28', '%29', '%7e'],
        ['*',   '!',   '(',   ')',   '%7E'],
        $encoded
    );
}
```

> **為什麼這個 bug 會活很久**：`*` `!` `(` `)` 在一般商品名稱裡不常出現。你會在測試環境跑得好好的，直到某天有個商品叫「限量！特價(買一送一)」，那筆訂單的發票就開不出來，而且錯誤訊息只是籠統的參數錯誤。
>
> **驗證方法**：跑 client 內建的自我測試（`php OPayEInvoice.php`），它會用官方測試向量比對。**測試資料一定要包含 `!*()` 與空格。**

---

## 4. Client 工廠

```php
// app/Services/OPay/OPayClientFactory.php
class OPayClientFactory
{
    public static function make(): OPayEInvoiceClient
    {
        return new OPayEInvoiceClient(
            config('opay.merchant_id'),
            config('opay.hash_key'),
            config('opay.hash_iv'),
            config('opay.host'),
            config('opay.platform_id'),
            config('opay.timeout'),
        );
    }
}

// AppServiceProvider::register()
$this->app->singleton(OPayEInvoiceClient::class, fn () => OPayClientFactory::make());
```

---

## 5. 路由分層

```php
// routes/api.php
Route::prefix('opay')->group(function () {
    // 唯讀：可安全重試
    Route::get('query/{invoiceNo}', [QueryController::class, 'show']);
    Route::post('validate/barcode', [ValidationController::class, 'barcode']);

    // 🚫 財務動作：冪等鎖 + audit log
    Route::post('invoice/issue',   [InvoiceController::class, 'issue']);
    Route::post('invoice/invalid', [InvoiceController::class, 'invalid'])
         ->middleware('opay.confirm');     // 二次確認中介層

    // 回呼：不可掛 CSRF
    Route::post('notify',   [CallbackController::class, 'notify']);
    Route::post('allowance-callback', [CallbackController::class, 'allowance']);
});
```

> ⚠️ **回呼路由必須排除 CSRF 驗證。** 放在 `routes/api.php` 或於 `VerifyCsrfToken::$except` 加入路徑。放在 `routes/web.php` 且沒排除的話，歐付寶的回呼會收到 419，而你在 log 裡只看到「TokenMismatch」，很難聯想到是歐付寶打進來的。

---

## 6. 冪等 service

```php
// app/Services/OPay/IssueService.php
public function issueOnce(array $payload): array
{
    $relate = $this->toRelateNumber($payload['order_id']);   // 穩定推導 + strtoupper + 截 30

    DB::transaction(function () use ($relate) {
        $row = InvoiceState::where('relate_number', $relate)->lockForUpdate()->first();
        if ($row && $row->status === 'SUCCEEDED') {
            throw new AlreadyIssued($row->result);           // 已開過，直接回
        }
        if ($row && $row->status === 'IN_FLIGHT') {
            throw new InFlight();                            // 處理中，不重送
        }
        InvoiceState::updateOrCreate(
            ['relate_number' => $relate],
            ['status' => 'IN_FLIGHT'],
        );
    });                                                      // ← 送出「前」就 commit

    try {
        $result = $this->client->issue(
            $relate, $payload['print'], $payload['donation'], $payload['tax_type'],
            $payload['sales_amount'], $payload['items'], $payload['inv_type'],
            $payload['extra'] ?? []
        );
    } catch (OPayEInvoiceError $e) {
        if ($this->isUnknownOutcome($e)) {
            throw new ResultUnknown();     // 保持 IN_FLIGHT，交給對帳排程
        }
        $this->markFailed($relate, $e);
        throw $e;
    }

    $this->markSucceeded($relate, $result);
    return $result;
}
```

**關鍵順序**：`IN_FLIGHT` 必須在發出 HTTP 請求**之前** commit。完整說明見 [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md)。

> ⚠️ **`lockForUpdate()` 只在交易內有效**，而且 SQLite 不支援。開發環境用 SQLite、正式用 MySQL 時，冪等保護在開發環境是**假的**。加一個唯一索引（`relate_number` unique）當第二道保險。

---

## 7. 錯誤轉譯

```php
// app/Exceptions/Handler.php
public function render($request, Throwable $e)
{
    if ($e instanceof OPayEInvoiceError) {
        // 🚫 不翻譯、不分類 RtnCode —— 官方沒有公開完整錯誤碼表
        Log::error('opay_error', [
            'endpoint' => $e->endpoint, 'trans_code' => $e->transCode,
            'trans_msg' => $e->transMsg, 'rtn_code' => $e->rtnCode, 'rtn_msg' => $e->rtnMsg,
        ]);
        $reference = $this->saveErrorForSupport($e);
        return response()->json([
            'message' => '發票處理失敗，請聯繫客服',
            'reference' => $reference,
        ], 400);
    }
    return parent::render($request, $e);
}
```

詳見 [`error-handling.md` §0](../references/error-handling.md)。

---

## 8. 回呼 Controller

```php
public function notify(Request $request)
{
    // 歐付寶送的是 application/x-www-form-urlencoded；Laravel 的 $request->input() 可直接取
    $tsr = $request->input('tsr');
    if ($request->filled('invoicenumber')) {
        $this->markIssued($tsr, $request->input('invoicenumber'), $request->input('invoicedate'));
    } else {
        $this->markIssueFailed($tsr, $request->input('inv_error'));
    }
    return response('1|OK')->header('Content-Type', 'text/plain');  // ⚠️ 必須正確回應
}
```

---

## 9. 排程

```php
// app/Console/Kernel.php
$schedule->command('opay:reconcile')->everyFiveMinutes();   // IN_FLIGHT 收斂
$schedule->command('opay:check-words')->hourly();           // 字軌餘量
$schedule->command('opay:b2b-pending')->dailyAt('09:00');   // B2B 等待確認 / 被退回
$schedule->command('opay:term-check')->monthlyOn(1, '08:00'); // 期別字軌與空白發票
```

---

### 常見錯誤

1. **用 PHP 內建 `urlencode()` 不做校正。** `*` 會變 `%2A`，只有商品名含 `!*()` 時才失敗，很容易漏測。
2. **在 Service 裡用 `env()` 取金鑰。** `config:cache` 之後會回 `null`，錯誤訊息是「AES 解密失敗」，完全指不到原因。
3. **回呼路由沒排除 CSRF。** 歐付寶會收到 419，log 裡只有 TokenMismatch。
4. **開發用 SQLite、正式用 MySQL。** `lockForUpdate()` 在 SQLite 無效，冪等保護在開發環境是假的。加唯一索引當第二道保險。
5. **`rawurlencode()` 當成替代方案。** 空格會變 `%20` 而不是 `+`，一樣不符合。
6. **改寫 client 的加解密邏輯。** 那份已用官方測試向量驗證過，跑 `php OPayEInvoice.php` 可確認。
