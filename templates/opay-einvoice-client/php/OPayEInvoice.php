<?php
/**
 * OPayEInvoice.php — 歐付寶（O'Pay）電子發票 API PHP Client（模板）
 *
 * 用途
 *   以單一 class 封裝歐付寶電子發票 B2C / B2B / 離線共 69 支 API 的
 *   「外層組裝 → AES 加密 → 送出 → 雙層錯誤檢查 → 解密回傳」流程。
 *   僅使用 PHP 內建 openssl 與 cURL 擴充，不需要任何 Composer 套件。
 *
 * 對應規格（唯一事實來源）
 *   references/b2c-api-reference.md      B2C 30 支（i100 §4～§29）
 *   references/b2b-api-reference.md      B2B 27 支（i200 §3～§29）
 *   references/offline-api-reference.md  離線 12 支（i301 §5～§15）
 *
 * 加解密鐵律（順序不可顛倒）
 *   送出：明文 JSON ─URLEncode(.NET 慣例)→ AES-128-CBC/PKCS7 ─→ Base64 ─→ Data
 *   接收：Data ─Base64 解碼→ AES 解密 ─→ URLDecode ─→ 明文 JSON
 *
 * 金鑰管理
 *   正式環境 HashKey / HashIV 一律從環境變數讀取（getenv），嚴禁寫進原始碼或 commit 進 git。
 *   本檔內出現的金鑰全部是官方文件公開的「測試環境」值，僅供離線自我測試使用。
 *
 * 用法（最短版）
 *   require_once __DIR__ . '/OPayEInvoice.php';
 *   $client = new OPayEInvoiceClient('2000132', getenv('OPAY_HASH_KEY'), getenv('OPAY_HASH_IV'), OPayEInvoiceClient::STAGE_HOST);
 *   $result = $client->issue('ORDER-0001', '0', '0', '1', 100, [
 *       ['ItemName' => '測試商品', 'ItemCount' => 1, 'ItemWord' => '個', 'ItemPrice' => 100, 'ItemAmount' => 100],
 *   ], '07');
 *
 * 自我測試（不連網）
 *   php OPayEInvoice.php
 */

/**
 * 歐付寶電子發票 API 錯誤。
 * transCode / transMsg：外層傳輸層結果（TransCode 1 = 外層資料接收成功）
 * rtnCode / rtnMsg    ：解密後 Data 內的業務結果（RtnCode 1 = 業務成功）
 */
class OPayEInvoiceError extends Exception
{
    /** @var int|null */
    public $transCode;
    /** @var string|null */
    public $transMsg;
    /** @var int|null */
    public $rtnCode;
    /** @var string|null */
    public $rtnMsg;
    /** @var string|null */
    public $endpoint;
    /** @var mixed */
    public $raw;

    public function __construct(string $message, array $context = [])
    {
        parent::__construct($message);
        $this->transCode = $context['transCode'] ?? null;
        $this->transMsg = $context['transMsg'] ?? null;
        $this->rtnCode = $context['rtnCode'] ?? null;
        $this->rtnMsg = $context['rtnMsg'] ?? null;
        $this->endpoint = $context['endpoint'] ?? null;
        $this->raw = $context['raw'] ?? null;
    }
}

class OPayEInvoiceClient
{
    /** 測試環境 host（沙箱） */
    const STAGE_HOST = 'https://einvoice-stage.opay.tw';
    /** 正式環境 host */
    const PROD_HOST = 'https://einvoice.opay.tw';

    /** 官方文件公開的測試環境參數 —— 僅測試環境可用，正式環境請改用環境變數。 */
    const STAGE_B2C_MERCHANT_ID = '2000132';
    const STAGE_B2C_HASH_KEY = 'ejCk326UnaZWKisg';      // 僅測試環境
    const STAGE_B2C_HASH_IV = 'q9jcZX8Ib9LM8wYk';       // 僅測試環境
    const STAGE_OFFLINE_MERCHANT_ID = '2045501';
    const STAGE_OFFLINE_HASH_KEY = '9XWzRmj7UJESChyn';  // 僅測試環境
    const STAGE_OFFLINE_HASH_IV = 'sriQzbe1llJqk67P';   // 僅測試環境

    /** @var string */
    protected $merchantId;
    /** @var string */
    protected $hashKey;
    /** @var string */
    protected $hashIv;
    /** @var string */
    protected $host;
    /** @var string */
    protected $platformId;
    /** @var int */
    protected $timeout;

    /**
     * @param string $merchantId 特店編號（測試環境 B2C 2000132、離線 2045501）
     * @param string $hashKey    AES 金鑰，長度必須 16 bytes
     * @param string $hashIv     AES IV，長度必須 16 bytes
     * @param string $host       self::STAGE_HOST 或 self::PROD_HOST
     * @param string $platformId 平台商代號，一般廠商留空字串
     * @param int    $timeout    單次 HTTP 逾時秒數
     *
     * 時間戳提醒：外層 RqHeader.Timestamp 由本 class 以 time() 產生，歐付寶驗證區間為 10 分鐘，
     * 主機未校時（NTP）會直接被拒絕，部署前請確認系統時間已同步。
     */
    public function __construct(string $merchantId, string $hashKey, string $hashIv, string $host = self::STAGE_HOST, string $platformId = '', int $timeout = 15)
    {
        if ($merchantId === '') {
            throw new InvalidArgumentException('缺少 merchantId（特店編號）｜修復建議：測試環境 B2C 請填 2000132、離線請填 2045501，正式環境請至廠商後台查詢。');
        }
        if (strlen($hashKey) !== 16) {
            throw new InvalidArgumentException('hashKey 長度必須是 16 bytes（AES-128）｜修復建議：確認是否複製到多餘空白或換行，測試環境 B2C HashKey 為 16 碼。');
        }
        if (strlen($hashIv) !== 16) {
            throw new InvalidArgumentException('hashIv 長度必須是 16 bytes（AES-128）｜修復建議：確認是否複製到多餘空白或換行，測試環境 B2C HashIV 為 16 碼。');
        }
        $this->merchantId = $merchantId;
        $this->hashKey = $hashKey;
        $this->hashIv = $hashIv;
        $this->host = rtrim($host, '/');
        $this->platformId = $platformId;
        $this->timeout = $timeout;
    }

    /**
     * .NET 慣例的 URLEncode：空格→`+`、`!*()` 不編碼、`~`→%7E、十六進位大寫。
     * 對應 references/b2c-api-reference.md 附錄 2「URLEncode 轉換表」的「.NET編碼(opay)」欄。
     * PHP 的 urlencode() 會把 ! * ( ) 編碼掉，依官方注意事項用 str_replace 轉回來。
     */
    public static function urlencodeDotNet(string $text): string
    {
        $encoded = urlencode($text);
        return str_replace(['%21', '%2A', '%28', '%29'], ['!', '*', '(', ')'], $encoded);
    }

    /** 對應的反向解碼（`+` 會還原成空格）。 */
    public static function urldecodeDotNet(string $text): string
    {
        return urldecode($text);
    }

    /** 產生外層 RqHeader.Timestamp（Unix 秒）。驗證區間 10 分鐘，主機務必校時。 */
    public static function timestamp(): int
    {
        return time();
    }

    /**
     * 明文陣列 → JSON → URLEncode → AES-128-CBC/PKCS7 → Base64。
     * @param array $data
     */
    public function encrypt(array $data): string
    {
        $json = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($json === false) {
            throw new OPayEInvoiceError('傳入資料無法轉成 JSON｜修復建議：檢查是否含非 UTF-8 字元或無法序列化的物件。');
        }
        $encoded = self::urlencodeDotNet($json);
        // openssl_encrypt 的 CBC 模式預設即為 PKCS7 padding。
        $cipher = openssl_encrypt($encoded, 'AES-128-CBC', $this->hashKey, OPENSSL_RAW_DATA, $this->hashIv);
        if ($cipher === false) {
            throw new OPayEInvoiceError('AES 加密失敗｜修復建議：確認 PHP 已載入 openssl 擴充（php -m | grep openssl），且 HashKey / HashIV 長度為 16 bytes。');
        }
        return base64_encode($cipher);
    }

    /**
     * Base64 → AES 解密 → URLDecode → 陣列。失敗時丟出繁中錯誤。
     * @return array
     */
    public function decrypt(string $cipherText): array
    {
        $raw = base64_decode($cipherText, true);
        if ($raw === false) {
            throw new OPayEInvoiceError('回傳 Data 不是合法的 Base64｜修復建議：確認伺服器回應未被 proxy 改寫，並確認取用的是回應 JSON 的 Data 欄位。');
        }
        if ($raw === '' || strlen($raw) % 16 !== 0) {
            throw new OPayEInvoiceError('回傳 Data 解碼後長度不是 16 的倍數，無法進行 AES 解密｜修復建議：密文可能被截斷，請檢查是否有中間層改寫回應內容。');
        }
        $decoded = openssl_decrypt($raw, 'AES-128-CBC', $this->hashKey, OPENSSL_RAW_DATA, $this->hashIv);
        if ($decoded === false) {
            throw new OPayEInvoiceError('AES 解密失敗｜修復建議：HashKey / HashIV 幾乎都是這個錯的來源，請確認 (1) 用的是同一組特店的金鑰 (2) 測試與正式金鑰沒有混用 (3) 沒有多餘空白。');
        }
        $result = json_decode(self::urldecodeDotNet($decoded), true);
        if (!is_array($result)) {
            throw new OPayEInvoiceError('解密後的內容不是合法 JSON｜修復建議：確認 URLDecode 有做（解密結果應為 %7B%22… 形式），順序為先 AES 解密再 URLDecode。');
        }
        return $result;
    }

    /**
     * 組出外層固定結構（不送出），方便單元測試與除錯。
     * @return array
     */
    public function buildPayload(array $data): array
    {
        return [
            'PlatformID' => $this->platformId,
            'MerchantID' => $this->merchantId,
            'RqHeader' => ['Timestamp' => self::timestamp()],
            'Data' => $this->encrypt($data),
        ];
    }

    /**
     * 送出一支 API，回傳「解密後的 Data」。
     * 兩層檢查缺一不可：外層 TransCode !== 1 → 傳輸失敗；解密後 RtnCode !== 1 → 業務失敗。
     * @return array
     */
    public function post(string $path, array $data): array
    {
        $url = $this->host . $path;
        $payload = json_encode($this->buildPayload($data), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => $this->timeout,
            CURLOPT_SSL_VERIFYPEER => true,
            CURLOPT_SSL_VERIFYHOST => 2,
        ]);
        $body = curl_exec($ch);
        $errno = curl_errno($ch);
        $error = curl_error($ch);
        $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($errno === CURLE_OPERATION_TIMEOUTED) {
            throw new OPayEInvoiceError(
                "呼叫 {$path} 逾時（{$this->timeout} 秒）｜修復建議：開立類 API 逾時不代表沒開成功，請改用 GetIssue 以 RelateNumber 查詢後再決定是否重送，避免重複開立。",
                ['endpoint' => $path]
            );
        }
        if ($errno !== 0) {
            throw new OPayEInvoiceError(
                "連線 {$url} 失敗：{$error}｜修復建議：(1) 確認防火牆以 FQDN 放行 einvoice.opay.tw / einvoice-stage.opay.tw（官方 IP 不固定）(2) 僅支援 TLS 1.2 以上、443 port。",
                ['endpoint' => $path]
            );
        }
        if ($status !== 200) {
            throw new OPayEInvoiceError(
                "呼叫 {$path} 得到 HTTP {$status}｜修復建議：確認 URL 路徑大小寫正確、Content-Type 為 application/json；回應內容：" . substr((string) $body, 0, 200),
                ['endpoint' => $path, 'raw' => $body]
            );
        }

        $decodedBody = json_decode((string) $body, true);
        if (!is_array($decodedBody)) {
            throw new OPayEInvoiceError(
                "呼叫 {$path} 的回應不是 JSON｜修復建議：多半是打到錯的網域或被中間層攔截，回應前 200 字：" . substr((string) $body, 0, 200),
                ['endpoint' => $path, 'raw' => $body]
            );
        }

        $transCode = $decodedBody['TransCode'] ?? null;
        $transMsg = $decodedBody['TransMsg'] ?? '';
        if ((int) $transCode !== 1) {
            throw new OPayEInvoiceError(
                "外層傳輸失敗（TransCode={$transCode}）：{$transMsg}｜修復建議：TransCode 非 1 代表 MerchantID / RqHeader.Timestamp / Data 三者之一有問題，請優先檢查主機時間是否在 10 分鐘驗證區間內、MerchantID 是否與金鑰同一組。",
                ['transCode' => $transCode, 'transMsg' => $transMsg, 'endpoint' => $path, 'raw' => $decodedBody]
            );
        }
        if (empty($decodedBody['Data'])) {
            throw new OPayEInvoiceError(
                "外層 TransCode=1 但沒有 Data 欄位｜修復建議：請將原始回應保留並回報歐付寶客服。原始回應：" . substr((string) $body, 0, 200),
                ['transCode' => $transCode, 'endpoint' => $path, 'raw' => $decodedBody]
            );
        }

        $result = $this->decrypt($decodedBody['Data']);
        $rtnCode = $result['RtnCode'] ?? null;
        $rtnMsg = $result['RtnMsg'] ?? '';
        if ((int) $rtnCode !== 1) {
            throw new OPayEInvoiceError(
                "業務處理失敗（RtnCode={$rtnCode}）：{$rtnMsg}｜修復建議：對照 references 各檔「錯誤代碼」附錄；常見原因為必填欄位缺漏、字軌尚未設定或已用罄、發票號碼不存在、金額與明細加總不符。",
                ['transCode' => $transCode, 'transMsg' => $transMsg, 'rtnCode' => $rtnCode, 'rtnMsg' => $rtnMsg, 'endpoint' => $path, 'raw' => $result]
            );
        }
        return $result;
    }

    // =========================================================================
    // 以下為 69 支 API 方法（B2C 30 / B2B 27 / 離線 12）
    // 命名規則：B2C 無前綴、B2B 加 `b2b` 前綴、離線加 `offline` 前綴，避免同名 endpoint 撞名。
    // 每個方法只做「組陣列 → post → 回傳解密後 Data」；選填欄位一律用最後一個 $extra 參數
    // 以官方 PascalCase 欄位名原樣傳入，例如 $client->issue(..., ['CustomerEmail' => 'a@b.c'])。
    // =========================================================================

    /**
     * 查詢財政部配號結果｜i100 §4｜POST /B2CInvoice/GetGovInvoiceWordSetting
     * @return array 解密後的 Data
     */
    public function getGovInvoiceWordSetting(string $invoiceYear, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
        ];
        return $this->post('/B2CInvoice/GetGovInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 字軌與配號設定｜i100 §5｜POST /B2CInvoice/AddInvoiceWordSetting
     * @return array 解密後的 Data
     */
    public function addInvoiceWordSetting(int $invoiceTerm, string $invoiceYear, string $invType, string $invoiceCategory, string $invoiceHeader, string $invoiceStart, string $invoiceEnd, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceTerm' => $invoiceTerm,
            'InvoiceYear' => $invoiceYear,
            'InvType' => $invType,
            'InvoiceCategory' => $invoiceCategory,
            'InvoiceHeader' => $invoiceHeader,
            'InvoiceStart' => $invoiceStart,
            'InvoiceEnd' => $invoiceEnd,
        ];
        return $this->post('/B2CInvoice/AddInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 設定字軌號碼狀態｜i100 §6｜POST /B2CInvoice/UpdateInvoiceWordStatus
     * @return array 解密後的 Data
     */
    public function updateInvoiceWordStatus(string $trackId, int $invoiceStatus, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'TrackID' => $trackId,
            'InvoiceStatus' => $invoiceStatus,
        ];
        return $this->post('/B2CInvoice/UpdateInvoiceWordStatus', array_merge($data, $extra));
    }

    /**
     * 開立發票（一般開立發票）｜i100 §7｜POST /B2CInvoice/Issue
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：CustomerID、CustomerIdentifier、CustomerName、CustomerAddr、CustomerPhone、CustomerEmail、ClearanceMark、LoveCode、CarrierType、CarrierNum、CarrierNum2、ZeroTaxRateReason、SpecialTaxType、InvoiceRemark、vat
     * 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
     * @return array 解密後的 Data
     */
    public function issue(string $relateNumber, string $printMark, string $donation, string $taxType, int $salesAmount, array $items, string $invType, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'RelateNumber' => $relateNumber,
            'Print' => $printMark,
            'Donation' => $donation,
            'TaxType' => $taxType,
            'SalesAmount' => $salesAmount,
            'Items' => $items,
            'InvType' => $invType,
        ];
        return $this->post('/B2CInvoice/Issue', array_merge($data, $extra));
    }

    /**
     * 開立發票（延遲開立發票／預約開立發票）｜i100 §7｜POST /B2CInvoice/DelayIssue
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：CustomerID、CustomerIdentifier、CustomerName、CustomerAddr、CustomerPhone、CustomerEmail、ClearanceMark、LoveCode、CarrierType、CarrierNum、CarrierNum2、ZeroTaxRateReason、SpecialTaxType、InvoiceRemark、NotifyURL、vat
     * 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
     * @return array 解密後的 Data
     */
    public function delayIssue(string $relateNumber, string $printMark, string $donation, string $taxType, int $salesAmount, array $items, string $invType, string $delayFlag, int $delayDay, string $tsr, string $payType, string $payAct, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'RelateNumber' => $relateNumber,
            'Print' => $printMark,
            'Donation' => $donation,
            'TaxType' => $taxType,
            'SalesAmount' => $salesAmount,
            'Items' => $items,
            'InvType' => $invType,
            'DelayFlag' => $delayFlag,
            'DelayDay' => $delayDay,
            'Tsr' => $tsr,
            'PayType' => $payType,
            'PayAct' => $payAct,
        ];
        return $this->post('/B2CInvoice/DelayIssue', array_merge($data, $extra));
    }

    /**
     * 觸發開立發票｜i100 §7｜POST /B2CInvoice/TriggerIssue
     * @return array 解密後的 Data
     */
    public function triggerIssue(string $tsr, string $payType, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'Tsr' => $tsr,
            'PayType' => $payType,
        ];
        return $this->post('/B2CInvoice/TriggerIssue', array_merge($data, $extra));
    }

    /**
     * 取消延遲開立發票｜i100 §7｜POST /B2CInvoice/CancelDelayIssue
     * @return array 解密後的 Data
     */
    public function cancelDelayIssue(string $tsr, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'Tsr' => $tsr,
        ];
        return $this->post('/B2CInvoice/CancelDelayIssue', array_merge($data, $extra));
    }

    /**
     * 開立折讓－一般開立折讓（紙本開立）｜i100 §8｜POST /B2CInvoice/Allowance
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：CustomerName、NotifyMail、NotifyPhone
     * 巢狀必填欄位：Items[].ItemSeq、Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
     * @return array 解密後的 Data
     */
    public function allowance(string $invoiceNo, string $invoiceDate, string $allowanceNotify, int $allowanceAmount, array $items, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
            'AllowanceNotify' => $allowanceNotify,
            'AllowanceAmount' => $allowanceAmount,
            'Items' => $items,
        ];
        return $this->post('/B2CInvoice/Allowance', array_merge($data, $extra));
    }

    /**
     * 開立折讓－線上開立折讓（通知開立）｜i100 §8｜POST /B2CInvoice/AllowanceByCollegiate
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：CustomerName、ReturnURL
     * 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
     * @return array 解密後的 Data
     */
    public function allowanceByCollegiate(string $invoiceNo, string $invoiceDate, string $allowanceNotify, string $notifyMail, int $allowanceAmount, array $items, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
            'AllowanceNotify' => $allowanceNotify,
            'NotifyMail' => $notifyMail,
            'AllowanceAmount' => $allowanceAmount,
            'Items' => $items,
        ];
        return $this->post('/B2CInvoice/AllowanceByCollegiate', array_merge($data, $extra));
    }

    /**
     * 作廢發票｜i100 §9｜POST /B2CInvoice/Invalid
     * @return array 解密後的 Data
     */
    public function invalid(string $invoiceNo, string $invoiceDate, string $reason, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
            'Reason' => $reason,
        ];
        return $this->post('/B2CInvoice/Invalid', array_merge($data, $extra));
    }

    /**
     * 作廢折讓｜i100 §10｜POST /B2CInvoice/AllowanceInvalid
     * @return array 解密後的 Data
     */
    public function allowanceInvalid(string $invoiceNo, string $allowanceNo, string $reason, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'AllowanceNo' => $allowanceNo,
            'Reason' => $reason,
        ];
        return $this->post('/B2CInvoice/AllowanceInvalid', array_merge($data, $extra));
    }

    /**
     * 取消線上折讓｜i100 §11｜POST /B2CInvoice/AllowanceInvalidByCollegiate
     * @return array 解密後的 Data
     */
    public function allowanceInvalidByCollegiate(string $invoiceNo, string $allowanceNo, string $reason, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'AllowanceNo' => $allowanceNo,
            'Reason' => $reason,
        ];
        return $this->post('/B2CInvoice/AllowanceInvalidByCollegiate', array_merge($data, $extra));
    }

    /**
     * 註銷重開｜i100 §12｜POST /B2CInvoice/VoidWithReIssue
     * 巢狀必填欄位：VoidModel.InvoiceNo、VoidModel.VoidReason、IssueModel.RelateNumber、IssueModel.InvoiceDate、IssueModel.Print、IssueModel.Donation、IssueModel.TaxType、IssueModel.SalesAmount、IssueModel.Items[].ItemName、IssueModel.Items[].ItemCount、IssueModel.Items[].ItemWord、IssueModel.Items[].ItemPrice、IssueModel.Items[].ItemAmount、IssueModel.InvType
     * @return array 解密後的 Data
     */
    public function voidWithReIssue(array $voidModel, array $issueModel, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'VoidModel' => $voidModel,
            'IssueModel' => $issueModel,
        ];
        return $this->post('/B2CInvoice/VoidWithReIssue', array_merge($data, $extra));
    }

    /**
     * 查詢發票明細｜i100 §13｜POST /B2CInvoice/GetIssue
     * 兩種查詢情境擇一：情境一 $relateNumber；情境二 $invoiceNo + $invoiceDate（yyyy-MM-dd）。
     * @return array 解密後的 Data
     */
    public function getIssue(?string $relateNumber = null, ?string $invoiceNo = null, ?string $invoiceDate = null, array $extra = []): array
    {
        $data = ['MerchantID' => $this->merchantId];
        if ($relateNumber !== null && $relateNumber !== '') {
            $data['RelateNumber'] = $relateNumber;
        } elseif ($invoiceNo && $invoiceDate) {
            $data['InvoiceNo'] = $invoiceNo;
            $data['InvoiceDate'] = $invoiceDate;
        } else {
            throw new OPayEInvoiceError('查詢發票明細需擇一情境｜修復建議：情境一請傳 $relateNumber（特店自訂編號）；情境二請同時傳 $invoiceNo 與 $invoiceDate（格式 yyyy-MM-dd 或 yyyy/MM/dd）。');
        }
        return $this->post('/B2CInvoice/GetIssue', array_merge($data, $extra));
    }

    /**
     * 查詢折讓明細｜i100 §14｜POST /B2CInvoice/GetAllowanceList
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：AllowanceNo、InvoiceNo、Date
     * @return array 解密後的 Data
     */
    public function getAllowanceList(string $searchType, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'SearchType' => $searchType,
        ];
        return $this->post('/B2CInvoice/GetAllowanceList', array_merge($data, $extra));
    }

    /**
     * 查詢作廢發票明細｜i100 §15｜POST /B2CInvoice/GetInvalid
     * @return array 解密後的 Data
     */
    public function getInvalid(string $relateNumber, string $invoiceNo, string $invoiceDate, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'RelateNumber' => $relateNumber,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
        ];
        return $this->post('/B2CInvoice/GetInvalid', array_merge($data, $extra));
    }

    /**
     * 查詢作廢折讓明細｜i100 §16｜POST /B2CInvoice/GetAllowanceInvalid
     * @return array 解密後的 Data
     */
    public function getAllowanceInvalid(string $invoiceNo, string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2CInvoice/GetAllowanceInvalid', array_merge($data, $extra));
    }

    /**
     * 查詢字軌｜i100 §17｜POST /B2CInvoice/GetInvoiceWordSetting
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceTerm、UseStatus、InvType、InvoiceHeader
     * @return array 解密後的 Data
     */
    public function getInvoiceWordSetting(string $invoiceYear, int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2CInvoice/GetInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 發送發票通知｜i100 §18｜POST /B2CInvoice/InvoiceNotify
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：AllowanceNo、Phone、NotifyMail
     * @return array 解密後的 Data
     */
    public function invoiceNotify(string $invoiceNo, string $notify, string $invoiceTag, string $notified, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'Notify' => $notify,
            'InvoiceTag' => $invoiceTag,
            'Notified' => $notified,
        ];
        return $this->post('/B2CInvoice/InvoiceNotify', array_merge($data, $extra));
    }

    /**
     * 發票列印｜i100 §19｜POST /B2CInvoice/InvoicePrint
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：PrintStyle
     * @return array 解密後的 Data
     */
    public function invoicePrint(string $invoiceNo, string $invoiceDate, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
        ];
        return $this->post('/B2CInvoice/InvoicePrint', array_merge($data, $extra));
    }

    /**
     * 手機條碼驗證｜i100 §20｜POST /B2CInvoice/CheckBarcode
     * @return array 解密後的 Data
     */
    public function checkBarcode(string $barCode, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'BarCode' => $barCode,
        ];
        return $this->post('/B2CInvoice/CheckBarcode', array_merge($data, $extra));
    }

    /**
     * 捐贈碼驗證｜i100 §21｜POST /B2CInvoice/CheckLoveCode
     * @return array 解密後的 Data
     */
    public function checkLoveCode(string $loveCode, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'LoveCode' => $loveCode,
        ];
        return $this->post('/B2CInvoice/CheckLoveCode', array_merge($data, $extra));
    }

    /**
     * 統一編號驗證｜i100 §22｜POST /B2CInvoice/GetCompanyNameByTaxID
     * @return array 解密後的 Data
     */
    public function getCompanyNameByTaxId(string $unifiedBusinessNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'UnifiedBusinessNo' => $unifiedBusinessNo,
        ];
        return $this->post('/B2CInvoice/GetCompanyNameByTaxID', array_merge($data, $extra));
    }

    /**
     * 取得發票通知開關｜i100 §23｜POST /B2CInvoice/GetInvoiceNotifySetting
     * @return array 解密後的 Data
     */
    public function getInvoiceNotifySetting(array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
        ];
        return $this->post('/B2CInvoice/GetInvoiceNotifySetting', array_merge($data, $extra));
    }

    /**
     * 設定發票通知開關｜i100 §24｜POST /B2CInvoice/InvoiceNotifySetting
     * 巢狀必填欄位：CostomerSetting[].NotifyType、CostomerSetting[].NotifySwitch、SelfSetting[].NotifyType、SelfSetting[].NotifySwitch
     * @return array 解密後的 Data
     */
    public function invoiceNotifySetting(array $costomerSetting, array $selfSetting, int $invHeaderRemain, int $remainWord, string $emailSetting, string $notifyEmail, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'CostomerSetting' => $costomerSetting,
            'SelfSetting' => $selfSetting,
            'InvHeaderRemain' => $invHeaderRemain,
            'RemainWord' => $remainWord,
            'EmailSetting' => $emailSetting,
            'NotifyEmail' => $notifyEmail,
        ];
        return $this->post('/B2CInvoice/InvoiceNotifySetting', array_merge($data, $extra));
    }

    /**
     * 取得剩餘數量通知開關｜i100 §25｜POST /B2CInvoice/GetRemainNotifySetting
     * @return array 解密後的 Data
     */
    public function getRemainNotifySetting(array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
        ];
        return $this->post('/B2CInvoice/GetRemainNotifySetting', array_merge($data, $extra));
    }

    /**
     * 設定剩餘數量通知開關｜i100 §26｜POST /B2CInvoice/RemainNotifySetting
     * @return array 解密後的 Data
     */
    public function remainNotifySetting(int $invHeaderRemain, int $remainWord, string $notifyEmail, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvHeaderRemain' => $invHeaderRemain,
            'RemainWord' => $remainWord,
            'NotifyEmail' => $notifyEmail,
        ];
        return $this->post('/B2CInvoice/RemainNotifySetting', array_merge($data, $extra));
    }

    /**
     * 查詢空白未使用發票｜i100 §27｜POST /B2CInvoice/QueryBlankInvoiceList
     * @return array 解密後的 Data
     */
    public function queryBlankInvoiceList(string $invoiceYear, int $invoiceTerm, int $pageNo, int $pageSize, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceTerm' => $invoiceTerm,
            'PageNo' => $pageNo,
            'PageSize' => $pageSize,
        ];
        return $this->post('/B2CInvoice/QueryBlankInvoiceList', array_merge($data, $extra));
    }

    /**
     * 設定空白發票是否自動上傳｜i100 §28｜POST /B2CInvoice/BlankInvAutoUploadSetting
     * @return array 解密後的 Data
     */
    public function blankInvAutoUploadSetting(array $settingList, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'SettingList' => $settingList,
        ];
        return $this->post('/B2CInvoice/BlankInvAutoUploadSetting', array_merge($data, $extra));
    }

    /**
     * 下載空白發票清單｜i100 §29｜POST /B2CInvoice/DownLoadBlankInvList
     * @return array 解密後的 Data
     */
    public function downLoadBlankInvList(array $blankList, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'BlankList' => $blankList,
        ];
        return $this->post('/B2CInvoice/DownLoadBlankInvList', array_merge($data, $extra));
    }

    /**
     * 交易對象維護｜i200 §3｜POST /B2BInvoice/MaintainMerchantCustomerData
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：CustomerNumber、PersonInCharge、Address、TelephoneNumber、FacsimileNumber、SalesName、ContactAddress
     * @return array 解密後的 Data
     */
    public function b2bMaintainMerchantCustomerData(string $action, string $identifier, string $customerType, string $companyName, string $tradingSlang, string $exchangeMode, string $emailAddress, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'Action' => $action,
            'Identifier' => $identifier,
            'type' => $customerType,
            'CompanyName' => $companyName,
            'TradingSlang' => $tradingSlang,
            'ExchangeMode' => $exchangeMode,
            'EmailAddress' => $emailAddress,
        ];
        return $this->post('/B2BInvoice/MaintainMerchantCustomerData', array_merge($data, $extra));
    }

    /**
     * 發送通知｜i200 §4｜POST /B2BInvoice/Notify
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：AllowanceNo
     * @return array 解密後的 Data
     */
    public function b2bNotify(string $invoiceDate, string $invoiceNumber, string $notifyMail, string $invoiceTag, string $notified, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceDate' => $invoiceDate,
            'InvoiceNumber' => $invoiceNumber,
            'NotifyMail' => $notifyMail,
            'InvoiceTag' => $invoiceTag,
            'Notified' => $notified,
        ];
        return $this->post('/B2BInvoice/Notify', array_merge($data, $extra));
    }

    /**
     * 字軌與配號設定｜i200 §5｜POST /B2BInvoice/AddInvoiceWordSetting
     * @return array 解密後的 Data
     */
    public function b2bAddInvoiceWordSetting(int $invoiceTerm, string $invoiceYear, string $invType, string $invoiceCategory, string $invoiceHeader, string $invoiceStart, string $invoiceEnd, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceTerm' => $invoiceTerm,
            'InvoiceYear' => $invoiceYear,
            'InvType' => $invType,
            'InvoiceCategory' => $invoiceCategory,
            'InvoiceHeader' => $invoiceHeader,
            'InvoiceStart' => $invoiceStart,
            'InvoiceEnd' => $invoiceEnd,
        ];
        return $this->post('/B2BInvoice/AddInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 設定字軌號碼狀態｜i200 §6｜POST /B2BInvoice/UpdateInvoiceWordStatus
     * @return array 解密後的 Data
     */
    public function b2bUpdateInvoiceWordStatus(string $trackId, int $invoiceStatus, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'TrackID' => $trackId,
            'InvoiceStatus' => $invoiceStatus,
        ];
        return $this->post('/B2BInvoice/UpdateInvoiceWordStatus', array_merge($data, $extra));
    }

    /**
     * 開立發票｜i200 §7｜POST /B2BInvoice/Issue
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceTime、CustomerEmail、CustomerAddress、CustomerTelephoneNumber、ClearanceMark、ZeroTaxRateReason、TaxRate、SpecialTaxType、InvoiceRemark
     * 巢狀必填欄位：Items[].ItemSeq、Items[].ItemName、Items[].ItemCount、Items[].ItemPrice、Items[].ItemAmount
     * @return array 解密後的 Data
     */
    public function b2bIssue(string $relateNumber, string $customerIdentifier, string $invType, string $taxType, array $items, int $salesAmount, int $taxAmount, int $totalAmount, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'RelateNumber' => $relateNumber,
            'CustomerIdentifier' => $customerIdentifier,
            'InvType' => $invType,
            'TaxType' => $taxType,
            'Items' => $items,
            'SalesAmount' => $salesAmount,
            'TaxAmount' => $taxAmount,
            'TotalAmount' => $totalAmount,
        ];
        return $this->post('/B2BInvoice/Issue', array_merge($data, $extra));
    }

    /**
     * 開立發票確認｜i200 §8｜POST /B2BInvoice/IssueConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceDate、Remark
     * @return array 解密後的 Data
     */
    public function b2bIssueConfirm(string $invoiceNumber, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNumber' => $invoiceNumber,
        ];
        return $this->post('/B2BInvoice/IssueConfirm', array_merge($data, $extra));
    }

    /**
     * 作廢發票｜i200 §9｜POST /B2BInvoice/Invalid
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bInvalid(string $invoiceNumber, string $invoiceDate, string $reason, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNumber' => $invoiceNumber,
            'InvoiceDate' => $invoiceDate,
            'Reason' => $reason,
        ];
        return $this->post('/B2BInvoice/Invalid', array_merge($data, $extra));
    }

    /**
     * 作廢發票確認｜i200 §10｜POST /B2BInvoice/InvalidConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bInvalidConfirm(string $invoiceNumber, string $invoiceDate, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNumber' => $invoiceNumber,
            'InvoiceDate' => $invoiceDate,
        ];
        return $this->post('/B2BInvoice/InvalidConfirm', array_merge($data, $extra));
    }

    /**
     * 退回發票｜i200 §11｜POST /B2BInvoice/Reject
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bReject(string $invoiceNumber, string $invoiceDate, string $reason, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNumber' => $invoiceNumber,
            'InvoiceDate' => $invoiceDate,
            'Reason' => $reason,
        ];
        return $this->post('/B2BInvoice/Reject', array_merge($data, $extra));
    }

    /**
     * 退回發票確認｜i200 §12｜POST /B2BInvoice/RejectConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bRejectConfirm(string $invoiceNumber, string $invoiceDate, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNumber' => $invoiceNumber,
            'InvoiceDate' => $invoiceDate,
        ];
        return $this->post('/B2BInvoice/RejectConfirm', array_merge($data, $extra));
    }

    /**
     * 開立折讓發票｜i200 §13｜POST /B2BInvoice/Allowance
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：AllowanceDate、CustomerEmail、CustomerAddress
     * 巢狀必填欄位：Details[].OriginalInvoiceNumber、Details[].OriginalInvoiceDate、Details[].OriginalSequenceNumber、Details[].ItemName、Details[].ItemCount、Details[].ItemPrice、Details[].ItemAmount
     * @return array 解密後的 Data
     */
    public function b2bAllowance(int $taxAmount, int $totalAmount, array $details, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'TaxAmount' => $taxAmount,
            'TotalAmount' => $totalAmount,
            'Details' => $details,
        ];
        return $this->post('/B2BInvoice/Allowance', array_merge($data, $extra));
    }

    /**
     * 折讓發票確認｜i200 §14｜POST /B2BInvoice/AllowanceConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bAllowanceConfirm(string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2BInvoice/AllowanceConfirm', array_merge($data, $extra));
    }

    /**
     * 作廢折讓發票｜i200 §15｜POST /B2BInvoice/CancelAllowance
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bCancelAllowance(string $allowanceNo, string $reason, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
            'Reason' => $reason,
        ];
        return $this->post('/B2BInvoice/CancelAllowance', array_merge($data, $extra));
    }

    /**
     * 作廢折讓發票確認｜i200 §16｜POST /B2BInvoice/CancelAllowanceConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function b2bCancelAllowanceConfirm(string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2BInvoice/CancelAllowanceConfirm', array_merge($data, $extra));
    }

    /**
     * 註銷重開｜i200 §17｜POST /B2BInvoice/VoidWithReIssue
     * 巢狀必填欄位：VoidModel.InvoiceNumber、VoidModel.VoidReason、IssueModel.RelateNumber、IssueModel.InvoiceTime、IssueModel.CustomerIdentifier、IssueModel.InvType、IssueModel.TaxType、IssueModel.Items[].ItemSeq、IssueModel.Items[].ItemName、IssueModel.Items[].ItemCount、IssueModel.Items[].ItemPrice、IssueModel.Items[].ItemAmount、IssueModel.SalesAmount、IssueModel.TaxAmount
     * @return array 解密後的 Data
     */
    public function b2bVoidWithReIssue(array $voidModel, array $issueModel, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'VoidModel' => $voidModel,
            'IssueModel' => $issueModel,
        ];
        return $this->post('/B2BInvoice/VoidWithReIssue', array_merge($data, $extra));
    }

    /**
     * 查詢發票｜i200 §18｜POST /B2BInvoice/GetIssue
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：RelateNumber
     * @return array 解密後的 Data
     */
    public function b2bGetIssue(int $invoiceCategory, string $invoiceNumber, string $invoiceDate, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceCategory' => $invoiceCategory,
            'InvoiceNumber' => $invoiceNumber,
            'InvoiceDate' => $invoiceDate,
        ];
        return $this->post('/B2BInvoice/GetIssue', array_merge($data, $extra));
    }

    /**
     * 查詢發票確認｜i200 §19｜POST /B2BInvoice/GetIssueConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber、Seller_Identifier、Buyer_Identifier、InvoiceDateBegin、InvoiceDateEnd、InvoiceNumberBegin、InvoiceNumberEnd、Issue_Status、Invalid_Status、ExchangeMode、ExchangeStatus、Upload_Status
     * @return array 解密後的 Data
     */
    public function b2bGetIssueConfirm(int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2BInvoice/GetIssueConfirm', array_merge($data, $extra));
    }

    /**
     * 查詢作廢發票｜i200 §20｜POST /B2BInvoice/GetInvalid
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
     * @return array 解密後的 Data
     */
    public function b2bGetInvalid(int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2BInvoice/GetInvalid', array_merge($data, $extra));
    }

    /**
     * 查詢作廢發票確認｜i200 §21｜POST /B2BInvoice/GetInvalidConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
     * @return array 解密後的 Data
     */
    public function b2bGetInvalidConfirm(int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2BInvoice/GetInvalidConfirm', array_merge($data, $extra));
    }

    /**
     * 查詢退回發票｜i200 §22｜POST /B2BInvoice/GetReject
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
     * @return array 解密後的 Data
     */
    public function b2bGetReject(int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2BInvoice/GetReject', array_merge($data, $extra));
    }

    /**
     * 查詢退回發票確認｜i200 §23｜POST /B2BInvoice/GetRejectConfirm
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
     * @return array 解密後的 Data
     */
    public function b2bGetRejectConfirm(int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2BInvoice/GetRejectConfirm', array_merge($data, $extra));
    }

    /**
     * 查詢折讓發票｜i200 §24｜POST /B2BInvoice/GetAllowance
     * @return array 解密後的 Data
     */
    public function b2bGetAllowance(string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2BInvoice/GetAllowance', array_merge($data, $extra));
    }

    /**
     * 查詢折讓發票確認｜i200 §25｜POST /B2BInvoice/GetAllowanceConfirm
     * @return array 解密後的 Data
     */
    public function b2bGetAllowanceConfirm(string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2BInvoice/GetAllowanceConfirm', array_merge($data, $extra));
    }

    /**
     * 查詢作廢折讓發票｜i200 §26｜POST /B2BInvoice/GetAllowanceInvalid
     * @return array 解密後的 Data
     */
    public function b2bGetAllowanceInvalid(string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2BInvoice/GetAllowanceInvalid', array_merge($data, $extra));
    }

    /**
     * 查詢作廢折讓發票確認｜i200 §27｜POST /B2BInvoice/GetAllowanceInvalidConfirm
     * @return array 解密後的 Data
     */
    public function b2bGetAllowanceInvalidConfirm(string $allowanceNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'AllowanceNo' => $allowanceNo,
        ];
        return $this->post('/B2BInvoice/GetAllowanceInvalidConfirm', array_merge($data, $extra));
    }

    /**
     * 查詢字軌｜i200 §28｜POST /B2BInvoice/GetInvoiceWordSetting
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvType、InvoiceHeader
     * @return array 解密後的 Data
     */
    public function b2bGetInvoiceWordSetting(string $invoiceYear, int $invoiceTerm, int $useStatus, int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceTerm' => $invoiceTerm,
            'UseStatus' => $useStatus,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2BInvoice/GetInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 統一編號驗證｜i200 §29｜POST /B2BInvoice/GetCompanyNameByTaxID
     * @return array 解密後的 Data
     */
    public function b2bGetCompanyNameByTaxId(string $unifiedBusinessNo, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'UnifiedBusinessNo' => $unifiedBusinessNo,
        ];
        return $this->post('/B2BInvoice/GetCompanyNameByTaxID', array_merge($data, $extra));
    }

    /**
     * 查詢特店基本資料｜i301 §5｜POST /B2CInvoice/GetOfflineMerchantInfo
     * @return array 解密後的 Data
     */
    public function getOfflineMerchantInfo(array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
        ];
        return $this->post('/B2CInvoice/GetOfflineMerchantInfo', array_merge($data, $extra));
    }

    /**
     * 查詢財政部配號結果｜i301 §6｜POST /B2CInvoice/GetGovInvoiceWordSetting
     * @return array 解密後的 Data
     */
    public function offlineGetGovInvoiceWordSetting(string $invoiceYear, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
        ];
        return $this->post('/B2CInvoice/GetGovInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 管理發票機台｜i301 §7｜POST /B2CInvoice/OfflineMerchantPosSetting
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：Remark
     * @return array 解密後的 Data
     */
    public function offlineMerchantPosSetting(int $actionType, string $machineId, array $extra = []): array
    {
        $data = [
            // 原文本 API 的 Data 未列 MerchantID，故不帶；若歐付寶要求可用 $extra 補上。
            'ActionType' => $actionType,
            'MachineID' => $machineId,
        ];
        return $this->post('/B2CInvoice/OfflineMerchantPosSetting', array_merge($data, $extra));
    }

    /**
     * 查詢發票機台｜i301 §8｜POST /B2CInvoice/QueryOfflineMerchantPosSetting
     * @return array 解密後的 Data
     */
    public function queryOfflineMerchantPosSetting(array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
        ];
        return $this->post('/B2CInvoice/QueryOfflineMerchantPosSetting', array_merge($data, $extra));
    }

    /**
     * 字軌與配號設定｜i301 §9｜POST /B2CInvoice/AddInvoiceWordSetting
     * @return array 解密後的 Data
     */
    public function offlineAddInvoiceWordSetting(int $invoiceTerm, string $invoiceYear, string $invType, string $invoiceCategory, string $invoiceHeader, string $invoiceStart, string $invoiceEnd, string $machineId, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceTerm' => $invoiceTerm,
            'InvoiceYear' => $invoiceYear,
            'InvType' => $invType,
            'InvoiceCategory' => $invoiceCategory,
            'InvoiceHeader' => $invoiceHeader,
            'InvoiceStart' => $invoiceStart,
            'InvoiceEnd' => $invoiceEnd,
            'MachineID' => $machineId,
        ];
        return $this->post('/B2CInvoice/AddInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 設定字軌號碼狀態｜i301 §10｜POST /B2CInvoice/UpdateInvoiceWordStatus
     * @return array 解密後的 Data
     */
    public function offlineUpdateInvoiceWordStatus(string $trackId, int $invoiceStatus, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'TrackID' => $trackId,
            'InvoiceStatus' => $invoiceStatus,
        ];
        return $this->post('/B2CInvoice/UpdateInvoiceWordStatus', array_merge($data, $extra));
    }

    /**
     * 取得自動配發發票字軌號碼｜i301 §11｜POST /B2CInvoice/GetOfflineInvoiceWordSettingWithAutoSplit
     * @return array 解密後的 Data
     */
    public function getOfflineInvoiceWordSettingWithAutoSplit(string $invoiceYear, int $invoiceTerm, string $machineId, string $invType, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceTerm' => $invoiceTerm,
            'MachineID' => $machineId,
            'InvType' => $invType,
        ];
        return $this->post('/B2CInvoice/GetOfflineInvoiceWordSettingWithAutoSplit', array_merge($data, $extra));
    }

    /**
     * 取得發票字軌號碼（區間）｜i301 §12｜POST /B2CInvoice/GetOfflineInvoiceWordSetting
     * @return array 解密後的 Data
     */
    public function getOfflineInvoiceWordSetting(string $invoiceYear, int $invoiceTerm, int $invoiceStatus, string $machineId, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceTerm' => $invoiceTerm,
            'InvoiceStatus' => $invoiceStatus,
            'MachineID' => $machineId,
        ];
        return $this->post('/B2CInvoice/GetOfflineInvoiceWordSetting', array_merge($data, $extra));
    }

    /**
     * 取得發票字軌號碼（依數量／含隨機碼、加密資料）｜i301 §12｜POST /B2CInvoice/GetOfflineInvoiceWordSettingNumber
     * @return array 解密後的 Data
     */
    public function getOfflineInvoiceWordSettingNumber(string $invoiceYear, int $invoiceTerm, int $invoiceStatus, string $machineId, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceTerm' => $invoiceTerm,
            'InvoiceStatus' => $invoiceStatus,
            'MachineID' => $machineId,
        ];
        return $this->post('/B2CInvoice/GetOfflineInvoiceWordSettingNumber', array_merge($data, $extra));
    }

    /**
     * 上傳開立發票｜i301 §13｜POST /B2CInvoice/OfflineIssue
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：ZeroTaxRateReason、CustomerIdentifier、CustomerID、CustomerAddr、CustomerPhone、CustomerEmail、ClearanceMark、SpecialTaxType、vat、InvoiceRemark、CustomerName、LoveCode、CarrierType、CarrierNum、CarrierNum2
     * 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
     * @return array 解密後的 Data
     */
    public function offlineIssue(string $machineId, string $invoiceNo, string $invoiceDate, string $relateNumber, string $taxType, int $salesAmount, string $invType, string $randomNumber, array $items, string $printMark, string $donation, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'MachineID' => $machineId,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
            'RelateNumber' => $relateNumber,
            'TaxType' => $taxType,
            'SalesAmount' => $salesAmount,
            'InvType' => $invType,
            'RandomNumber' => $randomNumber,
            'Items' => $items,
            'Print' => $printMark,
            'Donation' => $donation,
        ];
        return $this->post('/B2CInvoice/OfflineIssue', array_merge($data, $extra));
    }

    /**
     * 上傳作廢發票｜i301 §14｜POST /B2CInvoice/OfflineInvalid
     * @return array 解密後的 Data
     */
    public function offlineInvalid(string $invoiceNo, string $invoiceDate, string $reason, string $cancelDate, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceNo' => $invoiceNo,
            'InvoiceDate' => $invoiceDate,
            'Reason' => $reason,
            'CancelDate' => $cancelDate,
        ];
        return $this->post('/B2CInvoice/OfflineInvalid', array_merge($data, $extra));
    }

    /**
     * 查詢字軌｜i301 §15｜POST /B2CInvoice/GetInvoiceWordSetting
     * 選填欄位以 $extra 傳入（PascalCase 原樣）：InvType、InvoiceHeader
     * @return array 解密後的 Data
     */
    public function offlineGetInvoiceWordSetting(string $invoiceYear, int $invoiceTerm, int $useStatus, int $invoiceCategory, array $extra = []): array
    {
        $data = [
            'MerchantID' => $this->merchantId,
            'InvoiceYear' => $invoiceYear,
            'InvoiceTerm' => $invoiceTerm,
            'UseStatus' => $useStatus,
            'InvoiceCategory' => $invoiceCategory,
        ];
        return $this->post('/B2CInvoice/GetInvoiceWordSetting', array_merge($data, $extra));
    }
}

// ---------------------------------------------------------------------------
// 自我測試：只驗證加解密正確性，不會發出任何網路請求。
//   執行：php OPayEInvoice.php
// ---------------------------------------------------------------------------
if (PHP_SAPI === 'cli' && isset($argv[0]) && realpath($argv[0]) === realpath(__FILE__)) {
    /** 官方文件附錄 3 的加密範例（測試向量） */
    $vector = [
        'plain' => ['Name' => 'Test', 'ID' => 'A123456789'],
        'urlencoded' => '%7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D',
        'cipher' => 'uvI4yrErM37XNQkXGAgRgJAgHn2t72jahaMZzYhWL1HmvH4WV18VJDP2i9pTbC+tby5nxVExLLFyAkbjbS2Dvg==',
    ];
    $client = new OPayEInvoiceClient(
        OPayEInvoiceClient::STAGE_B2C_MERCHANT_ID,
        OPayEInvoiceClient::STAGE_B2C_HASH_KEY,
        OPayEInvoiceClient::STAGE_B2C_HASH_IV,
        OPayEInvoiceClient::STAGE_HOST
    );
    $failures = 0;
    $check = function (string $title, bool $ok, string $detail = '') use (&$failures) {
        echo ($ok ? '[PASS] ' : '[FAIL] ') . $title . ($detail !== '' ? "｜{$detail}" : '') . PHP_EOL;
        if (!$ok) {
            $failures++;
        }
    };

    $json = json_encode($vector['plain'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    $encoded = OPayEInvoiceClient::urlencodeDotNet($json);
    $check('URLEncode（.NET 慣例）與官方範例相同', $encoded === $vector['urlencoded'], "實得 {$encoded}");

    $cipher = $client->encrypt($vector['plain']);
    $check('AES-128-CBC/PKCS7 加密結果與官方測試向量相同', $cipher === $vector['cipher'], "實得 {$cipher}");

    $restored = $client->decrypt($vector['cipher']);
    $check('解密官方密文可還原明文', $restored === $vector['plain'], '實得 ' . json_encode($restored, JSON_UNESCAPED_UNICODE));

    $sample = ['MerchantID' => '2000132', 'Note' => '空格 與 !*()~ 符號 測試'];
    $check('加解密往返一致（含空格與特殊符號）', $client->decrypt($client->encrypt($sample)) === $sample);

    $payload = $client->buildPayload(['MerchantID' => '2000132']);
    $check(
        '外層 payload 欄位齊全（PlatformID / MerchantID / RqHeader.Timestamp / Data）',
        array_keys($payload) === ['PlatformID', 'MerchantID', 'RqHeader', 'Data'] && is_int($payload['RqHeader']['Timestamp'])
    );

    try {
        $client->decrypt('這不是合法密文');
        $check('壞密文會丟出 OPayEInvoiceError', false, '沒有丟出例外');
    } catch (OPayEInvoiceError $e) {
        $check('壞密文會丟出繁中 OPayEInvoiceError', strpos($e->getMessage(), '修復建議') !== false, mb_substr($e->getMessage(), 0, 30));
    }

    $internal = ['__construct', 'urlencodeDotNet', 'urldecodeDotNet', 'timestamp', 'encrypt', 'decrypt', 'buildPayload', 'post'];
    $methods = array_diff(get_class_methods('OPayEInvoiceClient'), $internal);
    $count = count($methods);
    $check("API 方法數量為 69（B2C 30／B2B 27／離線 12），實得 {$count}", $count === 69);

    echo str_repeat('-', 60) . PHP_EOL;
    echo($failures === 0 ? "結果：全部通過 ✅" : "結果：{$failures} 項失敗 ❌（請先修好加解密再串接 API）");
    echo PHP_EOL;
    exit($failures === 0 ? 0 : 1);
}
