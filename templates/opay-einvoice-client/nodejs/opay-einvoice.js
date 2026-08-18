/**
 * opay-einvoice.js — 歐付寶（O'Pay）電子發票 API Node.js Client（模板）
 *
 * 用途
 *   以單一 class 封裝歐付寶電子發票 B2C / B2B / 離線共 69 支 API 的
 *   「外層組裝 → AES 加密 → 送出 → 雙層錯誤檢查 → 解密回傳」流程。
 *   僅使用 Node 內建 `crypto` 與 `fetch`（Node 18+），不需要任何第三方套件。
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
 *   正式環境 HashKey / HashIV 一律從環境變數讀取，嚴禁寫進原始碼或 commit 進 git。
 *   本檔內出現的金鑰全部是官方文件公開的「測試環境」值，僅供離線自我測試使用。
 *
 * 用法（最短版）
 *   const { OPayEInvoiceClient } = require('./opay-einvoice');
 *   const client = new OPayEInvoiceClient({
 *     merchantId: '2000132',
 *     hashKey: process.env.OPAY_HASH_KEY,
 *     hashIv: process.env.OPAY_HASH_IV,
 *     host: 'https://einvoice-stage.opay.tw',
 *   });
 *   const result = await client.issue('ORDER-0001', '0', '0', '1', 100,
 *     [{ ItemName: '測試商品', ItemCount: 1, ItemWord: '個', ItemPrice: 100, ItemAmount: 100 }], '07');
 *
 * 自我測試（不連網）
 *   node opay-einvoice.js
 */

'use strict';

const crypto = require('crypto');

/** 測試環境 host（沙箱） */
const STAGE_HOST = 'https://einvoice-stage.opay.tw';
/** 正式環境 host */
const PROD_HOST = 'https://einvoice.opay.tw';

/** 官方文件公開的測試環境參數 —— 僅測試環境可用，正式環境請改用環境變數。 */
const STAGE_B2C_MERCHANT_ID = '2000132';
const STAGE_B2C_HASH_KEY = 'ejCk326UnaZWKisg'; // 僅測試環境
const STAGE_B2C_HASH_IV = 'q9jcZX8Ib9LM8wYk'; // 僅測試環境
const STAGE_OFFLINE_MERCHANT_ID = '2045501';
const STAGE_OFFLINE_HASH_KEY = '9XWzRmj7UJESChyn'; // 僅測試環境
const STAGE_OFFLINE_HASH_IV = 'sriQzbe1llJqk67P'; // 僅測試環境

/**
 * 歐付寶電子發票 API 錯誤。
 * transCode / transMsg：外層傳輸層結果（TransCode 1 = 外層資料接收成功）
 * rtnCode / rtnMsg    ：解密後 Data 內的業務結果（RtnCode 1 = 業務成功）
 */
class OPayEInvoiceError extends Error {
  constructor(message, { transCode = null, transMsg = null, rtnCode = null, rtnMsg = null, endpoint = null, raw = null } = {}) {
    super(message);
    this.name = 'OPayEInvoiceError';
    this.transCode = transCode;
    this.transMsg = transMsg;
    this.rtnCode = rtnCode;
    this.rtnMsg = rtnMsg;
    this.endpoint = endpoint;
    this.raw = raw;
  }
}

/**
 * .NET 慣例的 URLEncode：空格→`+`、`!*()` 不編碼、`'`→%27、`~`→%7E、十六進位大寫。
 * 對應 references/b2c-api-reference.md 附錄 2「URLEncode 轉換表」的「.NET編碼(opay)」欄。
 * @param {string} text
 * @returns {string}
 */
function urlencodeDotNet(text) {
  return encodeURIComponent(text)
    .replace(/%20/g, '+')
    .replace(/'/g, '%27')
    .replace(/~/g, '%7E');
}

/**
 * 對應的反向解碼（`+` 會還原成空格）。
 * @param {string} text
 * @returns {string}
 */
function urldecodeDotNet(text) {
  return decodeURIComponent(text.replace(/\+/g, '%20'));
}

class OPayEInvoiceClient {
  /**
   * @param {Object} options
   * @param {string} options.merchantId 特店編號（測試環境 B2C 2000132、離線 2045501）
   * @param {string} options.hashKey AES 金鑰，長度必須 16 bytes
   * @param {string} options.hashIv AES IV，長度必須 16 bytes
   * @param {string} [options.host] STAGE_HOST 或 PROD_HOST
   * @param {string} [options.platformId] 平台商代號，一般廠商留空字串
   * @param {number} [options.timeout] 單次 HTTP 逾時秒數
   *
   * 時間戳提醒：外層 RqHeader.Timestamp 由本 class 產生，歐付寶驗證區間為 10 分鐘，
   * 主機未校時（NTP）會直接被拒絕，部署前請確認系統時間已同步。
   */
  constructor({ merchantId, hashKey, hashIv, host = STAGE_HOST, platformId = '', timeout = 15 } = {}) {
    if (!merchantId) {
      throw new Error('缺少 merchantId（特店編號）｜修復建議：測試環境 B2C 請填 2000132、離線請填 2045501，正式環境請至廠商後台查詢。');
    }
    if (Buffer.byteLength(hashKey || '', 'utf8') !== 16) {
      throw new Error('hashKey 長度必須是 16 bytes（AES-128）｜修復建議：確認是否複製到多餘空白或換行，測試環境 B2C HashKey 為 16 碼。');
    }
    if (Buffer.byteLength(hashIv || '', 'utf8') !== 16) {
      throw new Error('hashIv 長度必須是 16 bytes（AES-128）｜修復建議：確認是否複製到多餘空白或換行，測試環境 B2C HashIV 為 16 碼。');
    }
    this.merchantId = merchantId;
    this.hashKey = Buffer.from(hashKey, 'utf8');
    this.hashIv = Buffer.from(hashIv, 'utf8');
    this.host = host.replace(/\/+$/, '');
    this.platformId = platformId;
    this.timeout = timeout;
  }

  /** 產生外層 RqHeader.Timestamp（Unix 秒）。驗證區間 10 分鐘，主機務必校時。 */
  static timestamp() {
    return Math.floor(Date.now() / 1000);
  }

  /**
   * 明文物件 → JSON → URLEncode → AES-128-CBC/PKCS7 → Base64。
   * @param {Object} data
   * @returns {string}
   */
  _encrypt(data) {
    const encoded = urlencodeDotNet(JSON.stringify(data));
    const cipher = crypto.createCipheriv('aes-128-cbc', this.hashKey, this.hashIv);
    cipher.setAutoPadding(true); // Node 的 aes-128-cbc 預設即為 PKCS7 padding
    return Buffer.concat([cipher.update(encoded, 'utf8'), cipher.final()]).toString('base64');
  }

  /**
   * Base64 → AES 解密 → URLDecode → 物件。失敗時丟出繁中錯誤。
   * @param {string} cipherText
   * @returns {Object}
   */
  _decrypt(cipherText) {
    let raw;
    try {
      raw = Buffer.from(String(cipherText), 'base64');
    } catch (err) {
      throw new OPayEInvoiceError(`回傳 Data 不是合法的 Base64：${err.message}｜修復建議：確認伺服器回應未被 proxy 改寫，並確認取用的是回應 JSON 的 Data 欄位。`);
    }
    if (raw.length === 0 || raw.length % 16 !== 0) {
      throw new OPayEInvoiceError('回傳 Data 解碼後長度不是 16 的倍數，無法進行 AES 解密｜修復建議：密文可能被截斷，請檢查是否有中間層改寫回應內容。');
    }
    let decoded;
    try {
      const decipher = crypto.createDecipheriv('aes-128-cbc', this.hashKey, this.hashIv);
      decoded = Buffer.concat([decipher.update(raw), decipher.final()]).toString('utf8');
    } catch (err) {
      throw new OPayEInvoiceError(`AES 解密失敗：${err.message}｜修復建議：HashKey / HashIV 幾乎都是這個錯的來源，請確認 (1) 用的是同一組特店的金鑰 (2) 測試與正式金鑰沒有混用 (3) 沒有多餘空白。`);
    }
    try {
      return JSON.parse(urldecodeDotNet(decoded));
    } catch (err) {
      throw new OPayEInvoiceError(`解密後的內容不是合法 JSON：${err.message}｜修復建議：確認 URLDecode 有做（解密結果應為 %7B%22… 形式），順序為先 AES 解密再 URLDecode。`);
    }
  }

  /**
   * 組出外層固定結構（不送出），方便單元測試與除錯。
   * @param {Object} data
   * @returns {Object}
   */
  buildPayload(data) {
    return {
      PlatformID: this.platformId,
      MerchantID: this.merchantId,
      RqHeader: { Timestamp: OPayEInvoiceClient.timestamp() },
      Data: this._encrypt(data),
    };
  }

  /**
   * 送出一支 API，回傳「解密後的 Data」。
   * 兩層檢查缺一不可：外層 TransCode !== 1 → 傳輸失敗；解密後 RtnCode !== 1 → 業務失敗。
   * @param {string} path
   * @param {Object} data
   * @returns {Promise<Object>}
   */
  async _post(path, data) {
    const url = `${this.host}${path}`;
    const payload = this.buildPayload(data);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout * 1000);
    let response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
    } catch (err) {
      if (err.name === 'AbortError') {
        throw new OPayEInvoiceError(
          `呼叫 ${path} 逾時（${this.timeout} 秒）｜修復建議：開立類 API 逾時不代表沒開成功，請改用 GetIssue 以 RelateNumber 查詢後再決定是否重送，避免重複開立。`,
          { endpoint: path }
        );
      }
      throw new OPayEInvoiceError(
        `連線 ${url} 失敗：${err.message}｜修復建議：(1) 確認防火牆以 FQDN 放行 einvoice.opay.tw / einvoice-stage.opay.tw（官方 IP 不固定）(2) 僅支援 TLS 1.2 以上、443 port。`,
        { endpoint: path }
      );
    } finally {
      clearTimeout(timer);
    }

    const text = await response.text();
    if (!response.ok) {
      throw new OPayEInvoiceError(
        `呼叫 ${path} 得到 HTTP ${response.status}｜修復建議：確認 URL 路徑大小寫正確、Content-Type 為 application/json；回應內容：${text.slice(0, 200)}`,
        { endpoint: path, raw: text }
      );
    }
    let body;
    try {
      body = JSON.parse(text);
    } catch (err) {
      throw new OPayEInvoiceError(
        `呼叫 ${path} 的回應不是 JSON｜修復建議：多半是打到錯的網域或被中間層攔截，回應前 200 字：${text.slice(0, 200)}`,
        { endpoint: path, raw: text }
      );
    }

    if (body.TransCode !== 1) {
      throw new OPayEInvoiceError(
        `外層傳輸失敗（TransCode=${body.TransCode}）：${body.TransMsg || ''}｜修復建議：TransCode 非 1 代表 MerchantID / RqHeader.Timestamp / Data 三者之一有問題，請優先檢查主機時間是否在 10 分鐘驗證區間內、MerchantID 是否與金鑰同一組。`,
        { transCode: body.TransCode, transMsg: body.TransMsg, endpoint: path, raw: body }
      );
    }
    if (!body.Data) {
      throw new OPayEInvoiceError(
        `外層 TransCode=1 但沒有 Data 欄位｜修復建議：請將原始回應保留並回報歐付寶客服。原始回應：${text.slice(0, 200)}`,
        { transCode: body.TransCode, endpoint: path, raw: body }
      );
    }

    const result = this._decrypt(body.Data);
    if (result.RtnCode !== 1) {
      throw new OPayEInvoiceError(
        `業務處理失敗（RtnCode=${result.RtnCode}）：${result.RtnMsg || ''}｜修復建議：對照 references 各檔「錯誤代碼」附錄；常見原因為必填欄位缺漏、字軌尚未設定或已用罄、發票號碼不存在、金額與明細加總不符。`,
        { transCode: body.TransCode, transMsg: body.TransMsg, rtnCode: result.RtnCode, rtnMsg: result.RtnMsg, endpoint: path, raw: result }
      );
    }
    return result;
  }

  // =========================================================================
  // 以下為 69 支 API 方法（B2C 30 / B2B 27 / 離線 12）
  // 命名規則：B2C 無前綴、B2B 加 `b2b` 前綴、離線加 `offline` 前綴，避免同名 endpoint 撞名。
  // 每個方法只做「組物件 → _post → 回傳解密後 Data」；選填欄位一律用最後一個 extra 參數
  // 以官方 PascalCase 欄位名原樣傳入，例如 client.issue(..., { CustomerEmail: 'a@b.c' })。
  // =========================================================================

  /**
   * 查詢財政部配號結果｜i100 §4｜POST /B2CInvoice/GetGovInvoiceWordSetting
   * @param {string} invoiceYear 發票年度
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getGovInvoiceWordSetting(invoiceYear, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      ...extra,
    };
    return this._post('/B2CInvoice/GetGovInvoiceWordSetting', data);
  }

  /**
   * 字軌與配號設定｜i100 §5｜POST /B2CInvoice/AddInvoiceWordSetting
   * @param {number} invoiceTerm 發票期別
   * @param {string} invoiceYear 發票年度
   * @param {string} invType 字軌類別
   * @param {string} invoiceCategory 發票種類
   * @param {string} invoiceHeader 發票字軌
   * @param {string} invoiceStart 起始發票編號
   * @param {string} invoiceEnd 結束發票編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async addInvoiceWordSetting(invoiceTerm, invoiceYear, invType, invoiceCategory, invoiceHeader, invoiceStart, invoiceEnd, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceTerm: invoiceTerm,
      InvoiceYear: invoiceYear,
      InvType: invType,
      InvoiceCategory: invoiceCategory,
      InvoiceHeader: invoiceHeader,
      InvoiceStart: invoiceStart,
      InvoiceEnd: invoiceEnd,
      ...extra,
    };
    return this._post('/B2CInvoice/AddInvoiceWordSetting', data);
  }

  /**
   * 設定字軌號碼狀態｜i100 §6｜POST /B2CInvoice/UpdateInvoiceWordStatus
   * @param {string} trackId 字軌號碼ID
   * @param {number} invoiceStatus 發票字軌狀態
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async updateInvoiceWordStatus(trackId, invoiceStatus, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      TrackID: trackId,
      InvoiceStatus: invoiceStatus,
      ...extra,
    };
    return this._post('/B2CInvoice/UpdateInvoiceWordStatus', data);
  }

  /**
   * 開立發票（一般開立發票）｜i100 §7｜POST /B2CInvoice/Issue
   * @param {string} relateNumber 特店自訂編號
   * @param {string} printMark 列印註記
   * @param {string} donation 捐贈註記
   * @param {string} taxType 課稅類別
   * @param {number} salesAmount 發票總金額(含稅)
   * @param {Array<Object>} items 商品
   * @param {string} invType 字軌類別
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：CustomerID、CustomerIdentifier、CustomerName、CustomerAddr、CustomerPhone、CustomerEmail、ClearanceMark、LoveCode、CarrierType、CarrierNum、CarrierNum2、ZeroTaxRateReason、SpecialTaxType、InvoiceRemark、vat
   * @remarks 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async issue(relateNumber, printMark, donation, taxType, salesAmount, items, invType, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      RelateNumber: relateNumber,
      Print: printMark,
      Donation: donation,
      TaxType: taxType,
      SalesAmount: salesAmount,
      Items: items,
      InvType: invType,
      ...extra,
    };
    return this._post('/B2CInvoice/Issue', data);
  }

  /**
   * 開立發票（延遲開立發票／預約開立發票）｜i100 §7｜POST /B2CInvoice/DelayIssue
   * @param {string} relateNumber 特店自訂編號
   * @param {string} printMark 列印註記
   * @param {string} donation 捐贈註記
   * @param {string} taxType 課稅類別
   * @param {number} salesAmount 發票總金額(含稅)
   * @param {Array<Object>} items 商品
   * @param {string} invType 字軌類別
   * @param {string} delayFlag 延遲註記
   * @param {number} delayDay 延遲天數
   * @param {string} tsr 交易單號
   * @param {string} payType 交易類別
   * @param {string} payAct 交易類別名稱
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：CustomerID、CustomerIdentifier、CustomerName、CustomerAddr、CustomerPhone、CustomerEmail、ClearanceMark、LoveCode、CarrierType、CarrierNum、CarrierNum2、ZeroTaxRateReason、SpecialTaxType、InvoiceRemark、NotifyURL、vat
   * @remarks 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async delayIssue(relateNumber, printMark, donation, taxType, salesAmount, items, invType, delayFlag, delayDay, tsr, payType, payAct, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      RelateNumber: relateNumber,
      Print: printMark,
      Donation: donation,
      TaxType: taxType,
      SalesAmount: salesAmount,
      Items: items,
      InvType: invType,
      DelayFlag: delayFlag,
      DelayDay: delayDay,
      Tsr: tsr,
      PayType: payType,
      PayAct: payAct,
      ...extra,
    };
    return this._post('/B2CInvoice/DelayIssue', data);
  }

  /**
   * 觸發開立發票｜i100 §7｜POST /B2CInvoice/TriggerIssue
   * @param {string} tsr 交易單號
   * @param {string} payType 交易類別
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async triggerIssue(tsr, payType, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      Tsr: tsr,
      PayType: payType,
      ...extra,
    };
    return this._post('/B2CInvoice/TriggerIssue', data);
  }

  /**
   * 取消延遲開立發票｜i100 §7｜POST /B2CInvoice/CancelDelayIssue
   * @param {string} tsr 交易單號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async cancelDelayIssue(tsr, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      Tsr: tsr,
      ...extra,
    };
    return this._post('/B2CInvoice/CancelDelayIssue', data);
  }

  /**
   * 開立折讓－一般開立折讓（紙本開立）｜i100 §8｜POST /B2CInvoice/Allowance
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} allowanceNotify 通知類別
   * @param {number} allowanceAmount 折讓單總金額(含稅)
   * @param {Array<Object>} items 商品
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：CustomerName、NotifyMail、NotifyPhone
   * @remarks 巢狀必填欄位：Items[].ItemSeq、Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async allowance(invoiceNo, invoiceDate, allowanceNotify, allowanceAmount, items, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      AllowanceNotify: allowanceNotify,
      AllowanceAmount: allowanceAmount,
      Items: items,
      ...extra,
    };
    return this._post('/B2CInvoice/Allowance', data);
  }

  /**
   * 開立折讓－線上開立折讓（通知開立）｜i100 §8｜POST /B2CInvoice/AllowanceByCollegiate
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} allowanceNotify 通知類別
   * @param {string} notifyMail 通知電子信箱
   * @param {number} allowanceAmount 折讓單總金額(含稅)
   * @param {Array<Object>} items 商品
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：CustomerName、ReturnURL
   * @remarks 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async allowanceByCollegiate(invoiceNo, invoiceDate, allowanceNotify, notifyMail, allowanceAmount, items, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      AllowanceNotify: allowanceNotify,
      NotifyMail: notifyMail,
      AllowanceAmount: allowanceAmount,
      Items: items,
      ...extra,
    };
    return this._post('/B2CInvoice/AllowanceByCollegiate', data);
  }

  /**
   * 作廢發票｜i100 §9｜POST /B2CInvoice/Invalid
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} reason 作廢原因
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async invalid(invoiceNo, invoiceDate, reason, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      Reason: reason,
      ...extra,
    };
    return this._post('/B2CInvoice/Invalid', data);
  }

  /**
   * 作廢折讓｜i100 §10｜POST /B2CInvoice/AllowanceInvalid
   * @param {string} invoiceNo 發票號碼
   * @param {string} allowanceNo 折讓編號
   * @param {string} reason 作廢原因
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async allowanceInvalid(invoiceNo, allowanceNo, reason, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      AllowanceNo: allowanceNo,
      Reason: reason,
      ...extra,
    };
    return this._post('/B2CInvoice/AllowanceInvalid', data);
  }

  /**
   * 取消線上折讓｜i100 §11｜POST /B2CInvoice/AllowanceInvalidByCollegiate
   * @param {string} invoiceNo 發票號碼
   * @param {string} allowanceNo 折讓編號
   * @param {string} reason 取消原因
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async allowanceInvalidByCollegiate(invoiceNo, allowanceNo, reason, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      AllowanceNo: allowanceNo,
      Reason: reason,
      ...extra,
    };
    return this._post('/B2CInvoice/AllowanceInvalidByCollegiate', data);
  }

  /**
   * 註銷重開｜i100 §12｜POST /B2CInvoice/VoidWithReIssue
   * @param {Object} voidModel 註銷資料
   * @param {Object} issueModel 開立資料
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @remarks 巢狀必填欄位：VoidModel.InvoiceNo、VoidModel.VoidReason、IssueModel.RelateNumber、IssueModel.InvoiceDate、IssueModel.Print、IssueModel.Donation、IssueModel.TaxType、IssueModel.SalesAmount、IssueModel.Items[].ItemName、IssueModel.Items[].ItemCount、IssueModel.Items[].ItemWord、IssueModel.Items[].ItemPrice、IssueModel.Items[].ItemAmount、IssueModel.InvType
   * @returns {Promise<Object>} 解密後的 Data
   */
  async voidWithReIssue(voidModel, issueModel, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      VoidModel: voidModel,
      IssueModel: issueModel,
      ...extra,
    };
    return this._post('/B2CInvoice/VoidWithReIssue', data);
  }

  /**
   * 查詢發票明細｜i100 §13｜POST /B2CInvoice/GetIssue
   * 兩種查詢情境擇一：情境一 relateNumber；情境二 invoiceNo + invoiceDate（yyyy-MM-dd）。
   * @param {Object} [options]
   * @param {string} [options.relateNumber] 特店自訂編號
   * @param {string} [options.invoiceNo] 發票號碼
   * @param {string} [options.invoiceDate] 發票開立日期
   * @param {Object} [options.extra] 其他欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getIssue({ relateNumber, invoiceNo, invoiceDate, extra = {} } = {}) {
    const data = { MerchantID: this.merchantId };
    if (relateNumber) {
      data.RelateNumber = relateNumber;
    } else if (invoiceNo && invoiceDate) {
      data.InvoiceNo = invoiceNo;
      data.InvoiceDate = invoiceDate;
    } else {
      throw new OPayEInvoiceError(
        '查詢發票明細需擇一情境｜修復建議：情境一請傳 relateNumber（特店自訂編號）；情境二請同時傳 invoiceNo 與 invoiceDate（格式 yyyy-MM-dd 或 yyyy/MM/dd）。'
      );
    }
    Object.assign(data, extra);
    return this._post('/B2CInvoice/GetIssue', data);
  }

  /**
   * 查詢折讓明細｜i100 §14｜POST /B2CInvoice/GetAllowanceList
   * @param {string} searchType 查詢方式
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：AllowanceNo、InvoiceNo、Date
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getAllowanceList(searchType, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      SearchType: searchType,
      ...extra,
    };
    return this._post('/B2CInvoice/GetAllowanceList', data);
  }

  /**
   * 查詢作廢發票明細｜i100 §15｜POST /B2CInvoice/GetInvalid
   * @param {string} relateNumber 特店自訂編號
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getInvalid(relateNumber, invoiceNo, invoiceDate, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      RelateNumber: relateNumber,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      ...extra,
    };
    return this._post('/B2CInvoice/GetInvalid', data);
  }

  /**
   * 查詢作廢折讓明細｜i100 §16｜POST /B2CInvoice/GetAllowanceInvalid
   * @param {string} invoiceNo 發票號碼
   * @param {string} allowanceNo 折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getAllowanceInvalid(invoiceNo, allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2CInvoice/GetAllowanceInvalid', data);
  }

  /**
   * 查詢字軌｜i100 §17｜POST /B2CInvoice/GetInvoiceWordSetting
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceCategory 發票類別
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceTerm、UseStatus、InvType、InvoiceHeader
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getInvoiceWordSetting(invoiceYear, invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2CInvoice/GetInvoiceWordSetting', data);
  }

  /**
   * 發送發票通知｜i100 §18｜POST /B2CInvoice/InvoiceNotify
   * @param {string} invoiceNo 發票號碼
   * @param {string} notify 發送方式
   * @param {string} invoiceTag 發送內容類型
   * @param {string} notified 發送對象
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：AllowanceNo、Phone、NotifyMail
   * @returns {Promise<Object>} 解密後的 Data
   */
  async invoiceNotify(invoiceNo, notify, invoiceTag, notified, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      Notify: notify,
      InvoiceTag: invoiceTag,
      Notified: notified,
      ...extra,
    };
    return this._post('/B2CInvoice/InvoiceNotify', data);
  }

  /**
   * 發票列印｜i100 §19｜POST /B2CInvoice/InvoicePrint
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：PrintStyle
   * @returns {Promise<Object>} 解密後的 Data
   */
  async invoicePrint(invoiceNo, invoiceDate, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      ...extra,
    };
    return this._post('/B2CInvoice/InvoicePrint', data);
  }

  /**
   * 手機條碼驗證｜i100 §20｜POST /B2CInvoice/CheckBarcode
   * @param {string} barCode 手機條碼
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async checkBarcode(barCode, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      BarCode: barCode,
      ...extra,
    };
    return this._post('/B2CInvoice/CheckBarcode', data);
  }

  /**
   * 捐贈碼驗證｜i100 §21｜POST /B2CInvoice/CheckLoveCode
   * @param {string} loveCode 受贈單位之捐贈碼
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async checkLoveCode(loveCode, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      LoveCode: loveCode,
      ...extra,
    };
    return this._post('/B2CInvoice/CheckLoveCode', data);
  }

  /**
   * 統一編號驗證｜i100 §22｜POST /B2CInvoice/GetCompanyNameByTaxID
   * @param {string} unifiedBusinessNo 統一編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getCompanyNameByTaxId(unifiedBusinessNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      UnifiedBusinessNo: unifiedBusinessNo,
      ...extra,
    };
    return this._post('/B2CInvoice/GetCompanyNameByTaxID', data);
  }

  /**
   * 取得發票通知開關｜i100 §23｜POST /B2CInvoice/GetInvoiceNotifySetting
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getInvoiceNotifySetting(extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      ...extra,
    };
    return this._post('/B2CInvoice/GetInvoiceNotifySetting', data);
  }

  /**
   * 設定發票通知開關｜i100 §24｜POST /B2CInvoice/InvoiceNotifySetting
   * @param {Array<Object>} costomerSetting 發送通知給消費者
   * @param {Array<Object>} selfSetting 發送通知給自己
   * @param {number} invHeaderRemain 發票字軌剩餘多少數量要發提醒
   * @param {number} remainWord [InvHeaderRemain] 數量的單位
   * @param {string} emailSetting 發送通知給自己 Email
   * @param {string} notifyEmail 發送字軌配號剩餘量提醒通知 Email
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @remarks 巢狀必填欄位：CostomerSetting[].NotifyType、CostomerSetting[].NotifySwitch、SelfSetting[].NotifyType、SelfSetting[].NotifySwitch
   * @returns {Promise<Object>} 解密後的 Data
   */
  async invoiceNotifySetting(costomerSetting, selfSetting, invHeaderRemain, remainWord, emailSetting, notifyEmail, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      CostomerSetting: costomerSetting,
      SelfSetting: selfSetting,
      InvHeaderRemain: invHeaderRemain,
      RemainWord: remainWord,
      EmailSetting: emailSetting,
      NotifyEmail: notifyEmail,
      ...extra,
    };
    return this._post('/B2CInvoice/InvoiceNotifySetting', data);
  }

  /**
   * 取得剩餘數量通知開關｜i100 §25｜POST /B2CInvoice/GetRemainNotifySetting
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getRemainNotifySetting(extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      ...extra,
    };
    return this._post('/B2CInvoice/GetRemainNotifySetting', data);
  }

  /**
   * 設定剩餘數量通知開關｜i100 §26｜POST /B2CInvoice/RemainNotifySetting
   * @param {number} invHeaderRemain 發票字軌剩餘多少數量要發提醒
   * @param {number} remainWord [InvHeaderRemain] 數量的單位
   * @param {string} notifyEmail 發送字軌配號剩餘量提醒通知 Email
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async remainNotifySetting(invHeaderRemain, remainWord, notifyEmail, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvHeaderRemain: invHeaderRemain,
      RemainWord: remainWord,
      NotifyEmail: notifyEmail,
      ...extra,
    };
    return this._post('/B2CInvoice/RemainNotifySetting', data);
  }

  /**
   * 查詢空白未使用發票｜i100 §27｜POST /B2CInvoice/QueryBlankInvoiceList
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceTerm 發票期別
   * @param {number} pageNo 當前頁碼
   * @param {number} pageSize 分頁筆數
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async queryBlankInvoiceList(invoiceYear, invoiceTerm, pageNo, pageSize, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceTerm: invoiceTerm,
      PageNo: pageNo,
      PageSize: pageSize,
      ...extra,
    };
    return this._post('/B2CInvoice/QueryBlankInvoiceList', data);
  }

  /**
   * 設定空白發票是否自動上傳｜i100 §28｜POST /B2CInvoice/BlankInvAutoUploadSetting
   * @param {Array<Object>} settingList 設定清單
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async blankInvAutoUploadSetting(settingList, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      SettingList: settingList,
      ...extra,
    };
    return this._post('/B2CInvoice/BlankInvAutoUploadSetting', data);
  }

  /**
   * 下載空白發票清單｜i100 §29｜POST /B2CInvoice/DownLoadBlankInvList
   * @param {Array<Object>} blankList 字軌空白發票識別碼(流水號)
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async downLoadBlankInvList(blankList, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      BlankList: blankList,
      ...extra,
    };
    return this._post('/B2CInvoice/DownLoadBlankInvList', data);
  }

  /**
   * 交易對象維護｜i200 §3｜POST /B2BInvoice/MaintainMerchantCustomerData
   * @param {string} action 動作
   * @param {string} identifier 統一編號
   * @param {string} customerType 交易對象
   * @param {string} companyName 公司名稱
   * @param {string} tradingSlang 交易暗語
   * @param {string} exchangeMode 開立形式
   * @param {string} emailAddress 公司信箱
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：CustomerNumber、PersonInCharge、Address、TelephoneNumber、FacsimileNumber、SalesName、ContactAddress
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bMaintainMerchantCustomerData(action, identifier, customerType, companyName, tradingSlang, exchangeMode, emailAddress, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      Action: action,
      Identifier: identifier,
      type: customerType,
      CompanyName: companyName,
      TradingSlang: tradingSlang,
      ExchangeMode: exchangeMode,
      EmailAddress: emailAddress,
      ...extra,
    };
    return this._post('/B2BInvoice/MaintainMerchantCustomerData', data);
  }

  /**
   * 發送通知｜i200 §4｜POST /B2BInvoice/Notify
   * @param {string} invoiceDate 發票開立日期
   * @param {string} invoiceNumber 發票號碼
   * @param {string} notifyMail 發送電子郵件
   * @param {string} invoiceTag 發送內容類型
   * @param {string} notified 發送對象
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：AllowanceNo
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bNotify(invoiceDate, invoiceNumber, notifyMail, invoiceTag, notified, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceDate: invoiceDate,
      InvoiceNumber: invoiceNumber,
      NotifyMail: notifyMail,
      InvoiceTag: invoiceTag,
      Notified: notified,
      ...extra,
    };
    return this._post('/B2BInvoice/Notify', data);
  }

  /**
   * 字軌與配號設定｜i200 §5｜POST /B2BInvoice/AddInvoiceWordSetting
   * @param {number} invoiceTerm 發票期別
   * @param {string} invoiceYear 發票年度
   * @param {string} invType 字軌類別
   * @param {string} invoiceCategory 發票種類
   * @param {string} invoiceHeader 發票字軌
   * @param {string} invoiceStart 起始發票編號
   * @param {string} invoiceEnd 結束發票編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bAddInvoiceWordSetting(invoiceTerm, invoiceYear, invType, invoiceCategory, invoiceHeader, invoiceStart, invoiceEnd, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceTerm: invoiceTerm,
      InvoiceYear: invoiceYear,
      InvType: invType,
      InvoiceCategory: invoiceCategory,
      InvoiceHeader: invoiceHeader,
      InvoiceStart: invoiceStart,
      InvoiceEnd: invoiceEnd,
      ...extra,
    };
    return this._post('/B2BInvoice/AddInvoiceWordSetting', data);
  }

  /**
   * 設定字軌號碼狀態｜i200 §6｜POST /B2BInvoice/UpdateInvoiceWordStatus
   * @param {string} trackId 字軌號碼ID
   * @param {number} invoiceStatus 發票字軌狀態
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bUpdateInvoiceWordStatus(trackId, invoiceStatus, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      TrackID: trackId,
      InvoiceStatus: invoiceStatus,
      ...extra,
    };
    return this._post('/B2BInvoice/UpdateInvoiceWordStatus', data);
  }

  /**
   * 開立發票｜i200 §7｜POST /B2BInvoice/Issue
   * @param {string} relateNumber 廠商自訂編號
   * @param {string} customerIdentifier 買方統編
   * @param {string} invType 字軌類別
   * @param {string} taxType 課稅別
   * @param {Array<Object>} items 傳入資料
   * @param {number} salesAmount 銷售額合計
   * @param {number} taxAmount 稅額合計
   * @param {number} totalAmount 發票金額
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceTime、CustomerEmail、CustomerAddress、CustomerTelephoneNumber、ClearanceMark、ZeroTaxRateReason、TaxRate、SpecialTaxType、InvoiceRemark
   * @remarks 巢狀必填欄位：Items[].ItemSeq、Items[].ItemName、Items[].ItemCount、Items[].ItemPrice、Items[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bIssue(relateNumber, customerIdentifier, invType, taxType, items, salesAmount, taxAmount, totalAmount, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      RelateNumber: relateNumber,
      CustomerIdentifier: customerIdentifier,
      InvType: invType,
      TaxType: taxType,
      Items: items,
      SalesAmount: salesAmount,
      TaxAmount: taxAmount,
      TotalAmount: totalAmount,
      ...extra,
    };
    return this._post('/B2BInvoice/Issue', data);
  }

  /**
   * 開立發票確認｜i200 §8｜POST /B2BInvoice/IssueConfirm
   * @param {string} invoiceNumber 發票號碼
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceDate、Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bIssueConfirm(invoiceNumber, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNumber: invoiceNumber,
      ...extra,
    };
    return this._post('/B2BInvoice/IssueConfirm', data);
  }

  /**
   * 作廢發票｜i200 §9｜POST /B2BInvoice/Invalid
   * @param {string} invoiceNumber 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} reason 作廢原因
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bInvalid(invoiceNumber, invoiceDate, reason, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNumber: invoiceNumber,
      InvoiceDate: invoiceDate,
      Reason: reason,
      ...extra,
    };
    return this._post('/B2BInvoice/Invalid', data);
  }

  /**
   * 作廢發票確認｜i200 §10｜POST /B2BInvoice/InvalidConfirm
   * @param {string} invoiceNumber 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bInvalidConfirm(invoiceNumber, invoiceDate, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNumber: invoiceNumber,
      InvoiceDate: invoiceDate,
      ...extra,
    };
    return this._post('/B2BInvoice/InvalidConfirm', data);
  }

  /**
   * 退回發票｜i200 §11｜POST /B2BInvoice/Reject
   * @param {string} invoiceNumber 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} reason 退回原因
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bReject(invoiceNumber, invoiceDate, reason, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNumber: invoiceNumber,
      InvoiceDate: invoiceDate,
      Reason: reason,
      ...extra,
    };
    return this._post('/B2BInvoice/Reject', data);
  }

  /**
   * 退回發票確認｜i200 §12｜POST /B2BInvoice/RejectConfirm
   * @param {string} invoiceNumber 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bRejectConfirm(invoiceNumber, invoiceDate, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNumber: invoiceNumber,
      InvoiceDate: invoiceDate,
      ...extra,
    };
    return this._post('/B2BInvoice/RejectConfirm', data);
  }

  /**
   * 開立折讓發票｜i200 §13｜POST /B2BInvoice/Allowance
   * @param {number} taxAmount 營業稅額
   * @param {number} totalAmount 折讓金額總計(未稅)
   * @param {Array<Object>} details 傳入資料
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：AllowanceDate、CustomerEmail、CustomerAddress
   * @remarks 巢狀必填欄位：Details[].OriginalInvoiceNumber、Details[].OriginalInvoiceDate、Details[].OriginalSequenceNumber、Details[].ItemName、Details[].ItemCount、Details[].ItemPrice、Details[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bAllowance(taxAmount, totalAmount, details, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      TaxAmount: taxAmount,
      TotalAmount: totalAmount,
      Details: details,
      ...extra,
    };
    return this._post('/B2BInvoice/Allowance', data);
  }

  /**
   * 折讓發票確認｜i200 §14｜POST /B2BInvoice/AllowanceConfirm
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bAllowanceConfirm(allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2BInvoice/AllowanceConfirm', data);
  }

  /**
   * 作廢折讓發票｜i200 §15｜POST /B2BInvoice/CancelAllowance
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {string} reason 折讓作廢原因
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bCancelAllowance(allowanceNo, reason, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      Reason: reason,
      ...extra,
    };
    return this._post('/B2BInvoice/CancelAllowance', data);
  }

  /**
   * 作廢折讓發票確認｜i200 §16｜POST /B2BInvoice/CancelAllowanceConfirm
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bCancelAllowanceConfirm(allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2BInvoice/CancelAllowanceConfirm', data);
  }

  /**
   * 註銷重開｜i200 §17｜POST /B2BInvoice/VoidWithReIssue
   * @param {Object} voidModel 註銷資料
   * @param {Object} issueModel 開立資料
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @remarks 巢狀必填欄位：VoidModel.InvoiceNumber、VoidModel.VoidReason、IssueModel.RelateNumber、IssueModel.InvoiceTime、IssueModel.CustomerIdentifier、IssueModel.InvType、IssueModel.TaxType、IssueModel.Items[].ItemSeq、IssueModel.Items[].ItemName、IssueModel.Items[].ItemCount、IssueModel.Items[].ItemPrice、IssueModel.Items[].ItemAmount、IssueModel.SalesAmount、IssueModel.TaxAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bVoidWithReIssue(voidModel, issueModel, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      VoidModel: voidModel,
      IssueModel: issueModel,
      ...extra,
    };
    return this._post('/B2BInvoice/VoidWithReIssue', data);
  }

  /**
   * 查詢發票｜i200 §18｜POST /B2BInvoice/GetIssue
   * @param {number} invoiceCategory B2B發票種類
   * @param {string} invoiceNumber 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：RelateNumber
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetIssue(invoiceCategory, invoiceNumber, invoiceDate, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceCategory: invoiceCategory,
      InvoiceNumber: invoiceNumber,
      InvoiceDate: invoiceDate,
      ...extra,
    };
    return this._post('/B2BInvoice/GetIssue', data);
  }

  /**
   * 查詢發票確認｜i200 §19｜POST /B2BInvoice/GetIssueConfirm
   * @param {number} invoiceCategory B2B發票種類
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber、Seller_Identifier、Buyer_Identifier、InvoiceDateBegin、InvoiceDateEnd、InvoiceNumberBegin、InvoiceNumberEnd、Issue_Status、Invalid_Status、ExchangeMode、ExchangeStatus、Upload_Status
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetIssueConfirm(invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2BInvoice/GetIssueConfirm', data);
  }

  /**
   * 查詢作廢發票｜i200 §20｜POST /B2BInvoice/GetInvalid
   * @param {number} invoiceCategory B2B發票種類
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetInvalid(invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2BInvoice/GetInvalid', data);
  }

  /**
   * 查詢作廢發票確認｜i200 §21｜POST /B2BInvoice/GetInvalidConfirm
   * @param {number} invoiceCategory B2B發票種類
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetInvalidConfirm(invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2BInvoice/GetInvalidConfirm', data);
  }

  /**
   * 查詢退回發票｜i200 §22｜POST /B2BInvoice/GetReject
   * @param {number} invoiceCategory B2B發票種類
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetReject(invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2BInvoice/GetReject', data);
  }

  /**
   * 查詢退回發票確認｜i200 §23｜POST /B2BInvoice/GetRejectConfirm
   * @param {number} invoiceCategory B2B發票種類
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvoiceNumber、InvoiceDate、RelateNumber
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetRejectConfirm(invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2BInvoice/GetRejectConfirm', data);
  }

  /**
   * 查詢折讓發票｜i200 §24｜POST /B2BInvoice/GetAllowance
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetAllowance(allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2BInvoice/GetAllowance', data);
  }

  /**
   * 查詢折讓發票確認｜i200 §25｜POST /B2BInvoice/GetAllowanceConfirm
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetAllowanceConfirm(allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2BInvoice/GetAllowanceConfirm', data);
  }

  /**
   * 查詢作廢折讓發票｜i200 §26｜POST /B2BInvoice/GetAllowanceInvalid
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetAllowanceInvalid(allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2BInvoice/GetAllowanceInvalid', data);
  }

  /**
   * 查詢作廢折讓發票確認｜i200 §27｜POST /B2BInvoice/GetAllowanceInvalidConfirm
   * @param {string} allowanceNo 歐付寶折讓編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetAllowanceInvalidConfirm(allowanceNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      AllowanceNo: allowanceNo,
      ...extra,
    };
    return this._post('/B2BInvoice/GetAllowanceInvalidConfirm', data);
  }

  /**
   * 查詢字軌｜i200 §28｜POST /B2BInvoice/GetInvoiceWordSetting
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceTerm 發票期別
   * @param {number} useStatus 字軌使用狀態
   * @param {number} invoiceCategory 發票類別
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvType、InvoiceHeader
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetInvoiceWordSetting(invoiceYear, invoiceTerm, useStatus, invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceTerm: invoiceTerm,
      UseStatus: useStatus,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2BInvoice/GetInvoiceWordSetting', data);
  }

  /**
   * 統一編號驗證｜i200 §29｜POST /B2BInvoice/GetCompanyNameByTaxID
   * @param {string} unifiedBusinessNo 統一編號
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async b2bGetCompanyNameByTaxId(unifiedBusinessNo, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      UnifiedBusinessNo: unifiedBusinessNo,
      ...extra,
    };
    return this._post('/B2BInvoice/GetCompanyNameByTaxID', data);
  }

  /**
   * 查詢特店基本資料｜i301 §5｜POST /B2CInvoice/GetOfflineMerchantInfo
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getOfflineMerchantInfo(extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      ...extra,
    };
    return this._post('/B2CInvoice/GetOfflineMerchantInfo', data);
  }

  /**
   * 查詢財政部配號結果｜i301 §6｜POST /B2CInvoice/GetGovInvoiceWordSetting
   * @param {string} invoiceYear 發票年度
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineGetGovInvoiceWordSetting(invoiceYear, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      ...extra,
    };
    return this._post('/B2CInvoice/GetGovInvoiceWordSetting', data);
  }

  /**
   * 管理發票機台｜i301 §7｜POST /B2CInvoice/OfflineMerchantPosSetting
   * @param {number} actionType 管理功能類別
   * @param {string} machineId 發票機台ID
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：Remark
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineMerchantPosSetting(actionType, machineId, extra = {}) {
    const data = {
      // 原文本 API 的 Data 未列 MerchantID，故不帶；若歐付寶要求可用 extra 補上。
      ActionType: actionType,
      MachineID: machineId,
      ...extra,
    };
    return this._post('/B2CInvoice/OfflineMerchantPosSetting', data);
  }

  /**
   * 查詢發票機台｜i301 §8｜POST /B2CInvoice/QueryOfflineMerchantPosSetting
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async queryOfflineMerchantPosSetting(extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      ...extra,
    };
    return this._post('/B2CInvoice/QueryOfflineMerchantPosSetting', data);
  }

  /**
   * 字軌與配號設定｜i301 §9｜POST /B2CInvoice/AddInvoiceWordSetting
   * @param {number} invoiceTerm 發票期別
   * @param {string} invoiceYear 發票年度
   * @param {string} invType 字軌類別
   * @param {string} invoiceCategory 發票種類
   * @param {string} invoiceHeader 發票字軌
   * @param {string} invoiceStart 起始發票編號
   * @param {string} invoiceEnd 結束發票編號
   * @param {string} machineId 發票機台ID
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineAddInvoiceWordSetting(invoiceTerm, invoiceYear, invType, invoiceCategory, invoiceHeader, invoiceStart, invoiceEnd, machineId, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceTerm: invoiceTerm,
      InvoiceYear: invoiceYear,
      InvType: invType,
      InvoiceCategory: invoiceCategory,
      InvoiceHeader: invoiceHeader,
      InvoiceStart: invoiceStart,
      InvoiceEnd: invoiceEnd,
      MachineID: machineId,
      ...extra,
    };
    return this._post('/B2CInvoice/AddInvoiceWordSetting', data);
  }

  /**
   * 設定字軌號碼狀態｜i301 §10｜POST /B2CInvoice/UpdateInvoiceWordStatus
   * @param {string} trackId 字軌號碼ID
   * @param {number} invoiceStatus 發票字軌狀態
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineUpdateInvoiceWordStatus(trackId, invoiceStatus, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      TrackID: trackId,
      InvoiceStatus: invoiceStatus,
      ...extra,
    };
    return this._post('/B2CInvoice/UpdateInvoiceWordStatus', data);
  }

  /**
   * 取得自動配發發票字軌號碼｜i301 §11｜POST /B2CInvoice/GetOfflineInvoiceWordSettingWithAutoSplit
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceTerm 發票期別
   * @param {string} machineId 發票機台ID
   * @param {string} invType 字軌類別
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getOfflineInvoiceWordSettingWithAutoSplit(invoiceYear, invoiceTerm, machineId, invType, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceTerm: invoiceTerm,
      MachineID: machineId,
      InvType: invType,
      ...extra,
    };
    return this._post('/B2CInvoice/GetOfflineInvoiceWordSettingWithAutoSplit', data);
  }

  /**
   * 取得發票字軌號碼（區間）｜i301 §12｜POST /B2CInvoice/GetOfflineInvoiceWordSetting
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceTerm 發票期別
   * @param {number} invoiceStatus 發票字軌狀態
   * @param {string} machineId 發票機台ID
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getOfflineInvoiceWordSetting(invoiceYear, invoiceTerm, invoiceStatus, machineId, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceTerm: invoiceTerm,
      InvoiceStatus: invoiceStatus,
      MachineID: machineId,
      ...extra,
    };
    return this._post('/B2CInvoice/GetOfflineInvoiceWordSetting', data);
  }

  /**
   * 取得發票字軌號碼（依數量／含隨機碼、加密資料）｜i301 §12｜POST /B2CInvoice/GetOfflineInvoiceWordSettingNumber
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceTerm 發票期別
   * @param {number} invoiceStatus 發票字軌狀態
   * @param {string} machineId 發票機台ID
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async getOfflineInvoiceWordSettingNumber(invoiceYear, invoiceTerm, invoiceStatus, machineId, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceTerm: invoiceTerm,
      InvoiceStatus: invoiceStatus,
      MachineID: machineId,
      ...extra,
    };
    return this._post('/B2CInvoice/GetOfflineInvoiceWordSettingNumber', data);
  }

  /**
   * 上傳開立發票｜i301 §13｜POST /B2CInvoice/OfflineIssue
   * @param {string} machineId 發票機台ID
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} relateNumber 特店自訂編號
   * @param {string} taxType 課稅類別
   * @param {number} salesAmount 發票總金額(含稅)
   * @param {string} invType 字軌類別
   * @param {string} randomNumber 隨機碼
   * @param {Array<Object>} items 商品
   * @param {string} printMark 列印註記
   * @param {string} donation 捐贈註記
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：ZeroTaxRateReason、CustomerIdentifier、CustomerID、CustomerAddr、CustomerPhone、CustomerEmail、ClearanceMark、SpecialTaxType、vat、InvoiceRemark、CustomerName、LoveCode、CarrierType、CarrierNum、CarrierNum2
   * @remarks 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、Items[].ItemAmount
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineIssue(machineId, invoiceNo, invoiceDate, relateNumber, taxType, salesAmount, invType, randomNumber, items, printMark, donation, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      MachineID: machineId,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      RelateNumber: relateNumber,
      TaxType: taxType,
      SalesAmount: salesAmount,
      InvType: invType,
      RandomNumber: randomNumber,
      Items: items,
      Print: printMark,
      Donation: donation,
      ...extra,
    };
    return this._post('/B2CInvoice/OfflineIssue', data);
  }

  /**
   * 上傳作廢發票｜i301 §14｜POST /B2CInvoice/OfflineInvalid
   * @param {string} invoiceNo 發票號碼
   * @param {string} invoiceDate 發票開立日期
   * @param {string} reason 作廢原因
   * @param {string} cancelDate 發票作廢時間
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineInvalid(invoiceNo, invoiceDate, reason, cancelDate, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceNo: invoiceNo,
      InvoiceDate: invoiceDate,
      Reason: reason,
      CancelDate: cancelDate,
      ...extra,
    };
    return this._post('/B2CInvoice/OfflineInvalid', data);
  }

  /**
   * 查詢字軌｜i301 §15｜POST /B2CInvoice/GetInvoiceWordSetting
   * @param {string} invoiceYear 發票年度
   * @param {number} invoiceTerm 發票期別
   * @param {number} useStatus 字軌使用狀態
   * @param {number} invoiceCategory 發票類別
   * @param {Object} [extra] 選填欄位（PascalCase 原樣）：InvType、InvoiceHeader
   * @returns {Promise<Object>} 解密後的 Data
   */
  async offlineGetInvoiceWordSetting(invoiceYear, invoiceTerm, useStatus, invoiceCategory, extra = {}) {
    const data = {
      MerchantID: this.merchantId,
      InvoiceYear: invoiceYear,
      InvoiceTerm: invoiceTerm,
      UseStatus: useStatus,
      InvoiceCategory: invoiceCategory,
      ...extra,
    };
    return this._post('/B2CInvoice/GetInvoiceWordSetting', data);
  }
}

module.exports = {
  OPayEInvoiceClient,
  OPayEInvoiceError,
  urlencodeDotNet,
  urldecodeDotNet,
  STAGE_HOST,
  PROD_HOST,
  STAGE_B2C_MERCHANT_ID,
  STAGE_B2C_HASH_KEY,
  STAGE_B2C_HASH_IV,
  STAGE_OFFLINE_MERCHANT_ID,
  STAGE_OFFLINE_HASH_KEY,
  STAGE_OFFLINE_HASH_IV,
};

// ---------------------------------------------------------------------------
// 自我測試：只驗證加解密正確性，不會發出任何網路請求。
//   執行：node opay-einvoice.js
// ---------------------------------------------------------------------------

/** 官方文件附錄 3 的加密範例（測試向量） */
const OFFICIAL_VECTOR = {
  key: STAGE_B2C_HASH_KEY,
  iv: STAGE_B2C_HASH_IV,
  plain: { Name: 'Test', ID: 'A123456789' },
  urlencoded: '%7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D',
  cipher: 'uvI4yrErM37XNQkXGAgRgJAgHn2t72jahaMZzYhWL1HmvH4WV18VJDP2i9pTbC+tby5nxVExLLFyAkbjbS2Dvg==',
};

function selfTest() {
  const client = new OPayEInvoiceClient({
    merchantId: STAGE_B2C_MERCHANT_ID,
    hashKey: OFFICIAL_VECTOR.key,
    hashIv: OFFICIAL_VECTOR.iv,
    host: STAGE_HOST,
  });
  let failures = 0;
  const check = (title, ok, detail = '') => {
    console.log(`${ok ? '[PASS] ' : '[FAIL] '}${title}${detail ? `｜${detail}` : ''}`);
    if (!ok) failures += 1;
  };

  const encoded = urlencodeDotNet(JSON.stringify(OFFICIAL_VECTOR.plain));
  check('URLEncode（.NET 慣例）與官方範例相同', encoded === OFFICIAL_VECTOR.urlencoded, `實得 ${encoded}`);

  const cipher = client._encrypt(OFFICIAL_VECTOR.plain);
  check('AES-128-CBC/PKCS7 加密結果與官方測試向量相同', cipher === OFFICIAL_VECTOR.cipher, `實得 ${cipher}`);

  const restored = client._decrypt(OFFICIAL_VECTOR.cipher);
  check('解密官方密文可還原明文', JSON.stringify(restored) === JSON.stringify(OFFICIAL_VECTOR.plain), `實得 ${JSON.stringify(restored)}`);

  const sample = { MerchantID: '2000132', Note: '空格 與 !*()~ 符號 測試' };
  check('加解密往返一致（含空格與特殊符號）', JSON.stringify(client._decrypt(client._encrypt(sample))) === JSON.stringify(sample));

  const payload = client.buildPayload({ MerchantID: '2000132' });
  check(
    '外層 payload 欄位齊全（PlatformID / MerchantID / RqHeader.Timestamp / Data）',
    ['PlatformID', 'MerchantID', 'RqHeader', 'Data'].every((k) => k in payload) && Number.isInteger(payload.RqHeader.Timestamp)
  );

  try {
    client._decrypt('這不是合法密文');
    check('壞密文會丟出 OPayEInvoiceError', false, '沒有丟出例外');
  } catch (err) {
    check('壞密文會丟出繁中 OPayEInvoiceError', err instanceof OPayEInvoiceError && err.message.includes('修復建議'), err.message.slice(0, 40));
  }

  const internal = new Set(['constructor', 'buildPayload']);
  const methodCount = Object.getOwnPropertyNames(OPayEInvoiceClient.prototype).filter(
    (name) => !name.startsWith('_') && !internal.has(name) && typeof OPayEInvoiceClient.prototype[name] === 'function'
  ).length;
  check(`API 方法數量為 69（B2C 30／B2B 27／離線 12），實得 ${methodCount}`, methodCount === 69);

  console.log('-'.repeat(60));
  console.log(failures === 0 ? '結果：全部通過 ✅' : `結果：${failures} 項失敗 ❌（請先修好加解密再串接 API）`);
  return failures === 0 ? 0 : 1;
}

if (require.main === module) {
  process.exit(selfTest());
}
