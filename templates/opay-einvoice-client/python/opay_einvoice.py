#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opay_einvoice.py — 歐付寶（O'Pay）電子發票 API Python Client（模板）

用途
    以單一 class 封裝歐付寶電子發票 B2C / B2B / 離線共 69 支 API 的
    「外層組裝 → AES 加密 → 送出 → 雙層錯誤檢查 → 解密回傳」流程。
    只依賴 requests 與 pycryptodome，不依賴任何歐付寶官方 SDK。

對應規格（唯一事實來源）
    references/b2c-api-reference.md      B2C 30 支（i100 §4～§29）
    references/b2b-api-reference.md      B2B 27 支（i200 §3～§29）
    references/offline-api-reference.md  離線 12 支（i301 §5～§15）

加解密鐵律（順序不可顛倒）
    送出：明文 JSON ─URLEncode(.NET 慣例)→ AES-128-CBC/PKCS7 ─→ Base64 ─→ Data
    接收：Data ─Base64 解碼→ AES 解密 ─→ URLDecode ─→ 明文 JSON

金鑰管理
    正式環境 HashKey / HashIV 一律從環境變數讀取，嚴禁寫進原始碼或 commit 進 git。
    本檔內出現的金鑰全部是官方文件公開的「測試環境」值，僅供離線自我測試使用。

用法（最短版）
    from opay_einvoice import OPayEInvoiceClient
    client = OPayEInvoiceClient(merchant_id="2000132",
                                hash_key=os.environ["OPAY_HASH_KEY"],
                                hash_iv=os.environ["OPAY_HASH_IV"],
                                host="https://einvoice-stage.opay.tw")
    result = client.issue(relate_number="ORDER-0001", print_mark="0", donation="0",
                          tax_type="1", sales_amount=100,
                          items=[{"ItemName": "測試商品", "ItemCount": 1,
                                  "ItemWord": "個", "ItemPrice": 100, "ItemAmount": 100}])

自我測試（不連網）
    python3 opay_einvoice.py
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# --- 環境常數 ---------------------------------------------------------------

#: 測試環境 host（沙箱，不會產生真實稅務資料以外的法律效力，但會留下測試發票紀錄）
STAGE_HOST = "https://einvoice-stage.opay.tw"
#: 正式環境 host
PROD_HOST = "https://einvoice.opay.tw"

#: 官方文件公開的測試環境參數 —— 僅測試環境可用，正式環境請改用環境變數。
STAGE_B2C_MERCHANT_ID = "2000132"
STAGE_B2C_HASH_KEY = "ejCk326UnaZWKisg"      # 僅測試環境
STAGE_B2C_HASH_IV = "q9jcZX8Ib9LM8wYk"       # 僅測試環境
STAGE_OFFLINE_MERCHANT_ID = "2045501"
STAGE_OFFLINE_HASH_KEY = "9XWzRmj7UJESChyn"  # 僅測試環境
STAGE_OFFLINE_HASH_IV = "sriQzbe1llJqk67P"   # 僅測試環境

#: URLEncode 後「不編碼」的字元（.NET 慣例：`!*()` 保持原樣，空格轉成 `+`）
_DOTNET_SAFE_CHARS = "!*()"


class OPayEInvoiceError(Exception):
    """歐付寶電子發票 API 錯誤。

    屬性
        trans_code / trans_msg：外層傳輸層結果（TransCode 1 = 外層資料接收成功）
        rtn_code / rtn_msg    ：解密後 Data 內的業務結果（RtnCode 1 = 業務成功）
        endpoint / raw        ：出錯的 API 路徑與原始回應，方便寫進 log
    """

    def __init__(
        self,
        message: str,
        *,
        trans_code: Optional[int] = None,
        trans_msg: Optional[str] = None,
        rtn_code: Optional[int] = None,
        rtn_msg: Optional[str] = None,
        endpoint: Optional[str] = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.trans_code = trans_code
        self.trans_msg = trans_msg
        self.rtn_code = rtn_code
        self.rtn_msg = rtn_msg
        self.endpoint = endpoint
        self.raw = raw


class OPayEInvoiceClient:
    """歐付寶電子發票 API Client。

    參數
        merchant_id：特店編號（測試環境 B2C 為 2000132、離線為 2045501）
        hash_key   ：AES 金鑰，長度必須是 16 bytes
        hash_iv    ：AES IV，長度必須是 16 bytes
        host       ：`STAGE_HOST` 或 `PROD_HOST`（結尾斜線會自動去除）
        platform_id：平台商代號，一般廠商留空字串
        timeout    ：單次 HTTP 逾時秒數

    時間戳提醒
        外層 `RqHeader.Timestamp` 由本 class 以 `int(time.time())` 產生，
        歐付寶的驗證區間為 **10 分鐘**；主機時間若未校時（NTP）會直接被拒絕，
        部署前請確認 `timedatectl` / `chronyc tracking` 顯示已同步。
    """

    def __init__(
        self,
        merchant_id: str,
        hash_key: str,
        hash_iv: str,
        host: str = STAGE_HOST,
        platform_id: str = "",
        timeout: int = 15,
    ) -> None:
        if not merchant_id:
            raise ValueError("缺少 merchant_id（特店編號）｜修復建議：測試環境 B2C 請填 2000132、離線請填 2045501，正式環境請至廠商後台查詢。")
        if len(hash_key.encode("utf-8")) != 16:
            raise ValueError("hash_key 長度必須是 16 bytes（AES-128）｜修復建議：確認是否複製到多餘空白或換行，測試環境 B2C HashKey 為 16 碼。")
        if len(hash_iv.encode("utf-8")) != 16:
            raise ValueError("hash_iv 長度必須是 16 bytes（AES-128）｜修復建議：確認是否複製到多餘空白或換行，測試環境 B2C HashIV 為 16 碼。")
        self.merchant_id = merchant_id
        self.hash_key = hash_key.encode("utf-8")
        self.hash_iv = hash_iv.encode("utf-8")
        self.host = host.rstrip("/")
        self.platform_id = platform_id
        self.timeout = timeout
        self.session = requests.Session()

    # --- 編碼與加解密 ------------------------------------------------------

    @staticmethod
    def urlencode_dotnet(text: str) -> str:
        """.NET 慣例的 URLEncode：空格→`+`、`!*()` 不編碼、`~` 需編碼成 %7E、十六進位大寫。

        對應 references/b2c-api-reference.md 附錄 2「URLEncode 轉換表」的「.NET編碼(opay)」欄。
        """
        encoded = urllib.parse.quote_plus(text, safe=_DOTNET_SAFE_CHARS)
        # Python 3.7 起 quote_plus 不會編碼 `~`，但官方轉換表要求 `~` → %7e，故手動補上。
        return encoded.replace("~", "%7E")

    @staticmethod
    def urldecode_dotnet(text: str) -> str:
        """對應的反向解碼（`+` 會還原成空格）。"""
        return urllib.parse.unquote_plus(text)

    def _encrypt(self, data: Dict[str, Any]) -> str:
        """明文 dict → JSON → URLEncode → AES-128-CBC/PKCS7 → Base64。"""
        plain = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        encoded = self.urlencode_dotnet(plain)
        cipher = AES.new(self.hash_key, AES.MODE_CBC, self.hash_iv)
        return base64.b64encode(cipher.encrypt(pad(encoded.encode("utf-8"), AES.block_size))).decode("ascii")

    def _decrypt(self, cipher_text: str) -> Dict[str, Any]:
        """Base64 → AES 解密 → URLDecode → JSON dict。失敗時丟出繁中錯誤。"""
        try:
            raw = base64.b64decode(cipher_text)
        except Exception as exc:  # noqa: BLE001
            raise OPayEInvoiceError(
                f"回傳 Data 不是合法的 Base64：{exc}｜修復建議：確認伺服器回應未被 proxy 改寫，並確認取用的是回應 JSON 的 Data 欄位。"
            ) from exc
        if not raw or len(raw) % AES.block_size != 0:
            raise OPayEInvoiceError(
                "回傳 Data 解碼後長度不是 16 的倍數，無法進行 AES 解密｜修復建議：密文可能被截斷，請檢查是否有中間層改寫回應內容。"
            )
        try:
            cipher = AES.new(self.hash_key, AES.MODE_CBC, self.hash_iv)
            decoded = unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise OPayEInvoiceError(
                f"AES 解密失敗：{exc}｜修復建議：HashKey / HashIV 幾乎都是這個錯的來源，請確認 (1) 用的是同一組特店的金鑰 (2) 測試與正式金鑰沒有混用 (3) 沒有多餘空白。"
            ) from exc
        try:
            return json.loads(self.urldecode_dotnet(decoded))
        except json.JSONDecodeError as exc:
            raise OPayEInvoiceError(
                f"解密後的內容不是合法 JSON：{exc}｜修復建議：確認 URLDecode 有做（解密結果應為 %7B%22… 形式），順序為先 AES 解密再 URLDecode。"
            ) from exc

    @staticmethod
    def timestamp() -> int:
        """產生外層 `RqHeader.Timestamp`（Unix 秒）。驗證區間 10 分鐘，主機務必校時。"""
        return int(time.time())

    # --- 傳輸 --------------------------------------------------------------

    def build_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """組出外層固定結構（不送出），方便單元測試與除錯。"""
        return {
            "PlatformID": self.platform_id,
            "MerchantID": self.merchant_id,
            "RqHeader": {"Timestamp": self.timestamp()},
            "Data": self._encrypt(data),
        }

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """送出一支 API，回傳「解密後的 Data」dict。

        兩層檢查缺一不可：
            1. 外層 `TransCode` != 1 → 外層資料（MerchantID / RqHeader / Data）沒被接受
            2. 解密後 `RtnCode` != 1 → 業務邏輯失敗（欄位錯誤、字軌用完、發票不存在…）
        """
        url = f"{self.host}{path}"
        payload = self.build_payload(data)
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        except requests.Timeout as exc:
            raise OPayEInvoiceError(
                f"呼叫 {path} 逾時（{self.timeout} 秒）｜修復建議：開立類 API 逾時不代表沒開成功，請改用 GetIssue 以 RelateNumber 查詢後再決定是否重送，避免重複開立。",
                endpoint=path,
            ) from exc
        except requests.RequestException as exc:
            raise OPayEInvoiceError(
                f"連線 {url} 失敗：{exc}｜修復建議：(1) 確認防火牆以 FQDN 放行 einvoice.opay.tw / einvoice-stage.opay.tw（官方 IP 不固定）(2) 僅支援 TLS 1.2 以上、443 port。",
                endpoint=path,
            ) from exc

        if response.status_code != 200:
            raise OPayEInvoiceError(
                f"呼叫 {path} 得到 HTTP {response.status_code}｜修復建議：確認 URL 路徑大小寫正確、Content-Type 為 application/json；回應內容：{response.text[:200]}",
                endpoint=path,
                raw=response.text,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise OPayEInvoiceError(
                f"呼叫 {path} 的回應不是 JSON｜修復建議：多半是打到錯的網域或被中間層攔截，回應前 200 字：{response.text[:200]}",
                endpoint=path,
                raw=response.text,
            ) from exc

        trans_code = body.get("TransCode")
        trans_msg = body.get("TransMsg", "")
        if trans_code != 1:
            raise OPayEInvoiceError(
                f"外層傳輸失敗（TransCode={trans_code}）：{trans_msg}｜修復建議：TransCode 非 1 代表 MerchantID / RqHeader.Timestamp / Data 三者之一有問題，"
                "請優先檢查主機時間是否在 10 分鐘驗證區間內、MerchantID 是否與金鑰同一組。",
                trans_code=trans_code,
                trans_msg=trans_msg,
                endpoint=path,
                raw=body,
            )

        cipher_text = body.get("Data")
        if not cipher_text:
            raise OPayEInvoiceError(
                f"外層 TransCode=1 但沒有 Data 欄位｜修復建議：請將原始回應保留並回報歐付寶客服。原始回應：{body}",
                trans_code=trans_code,
                endpoint=path,
                raw=body,
            )
        result = self._decrypt(cipher_text)

        rtn_code = result.get("RtnCode")
        rtn_msg = result.get("RtnMsg", "")
        if rtn_code != 1:
            raise OPayEInvoiceError(
                f"業務處理失敗（RtnCode={rtn_code}）：{rtn_msg}｜修復建議：對照 references 各檔「錯誤代碼」附錄；"
                "常見原因為必填欄位缺漏、字軌尚未設定或已用罄、發票號碼不存在、金額與明細加總不符。",
                trans_code=trans_code,
                trans_msg=trans_msg,
                rtn_code=rtn_code,
                rtn_msg=rtn_msg,
                endpoint=path,
                raw=result,
            )
        return result

    # =======================================================================
    # 以下為 69 支 API 方法（B2C 30 / B2B 27 / 離線 12）
    # 命名規則：B2C 無前綴、B2B 加 `b2b_`、離線加 `offline_`，避免同名 endpoint 撞名。
    # 每個方法只做「組 dict → _post → 回傳解密後 Data」；選填欄位一律用 **extra
    # 以官方 PascalCase 欄位名原樣傳入，例如 client.issue(..., CustomerEmail="a@b.c")。
    # =======================================================================

    def get_gov_invoice_word_setting(
        self,
        invoice_year: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢財政部配號結果｜i100 §4｜POST /B2CInvoice/GetGovInvoiceWordSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetGovInvoiceWordSetting", data)

    def add_invoice_word_setting(
        self,
        invoice_term: int,
        invoice_year: str,
        inv_type: str,
        invoice_category: str,
        invoice_header: str,
        invoice_start: str,
        invoice_end: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """字軌與配號設定｜i100 §5｜POST /B2CInvoice/AddInvoiceWordSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceTerm": invoice_term,
            "InvoiceYear": invoice_year,
            "InvType": inv_type,
            "InvoiceCategory": invoice_category,
            "InvoiceHeader": invoice_header,
            "InvoiceStart": invoice_start,
            "InvoiceEnd": invoice_end,
        }
        data.update(extra)
        return self._post("/B2CInvoice/AddInvoiceWordSetting", data)

    def update_invoice_word_status(
        self,
        track_id: str,
        invoice_status: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """設定字軌號碼狀態｜i100 §6｜POST /B2CInvoice/UpdateInvoiceWordStatus"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "TrackID": track_id,
            "InvoiceStatus": invoice_status,
        }
        data.update(extra)
        return self._post("/B2CInvoice/UpdateInvoiceWordStatus", data)

    def issue(
        self,
        relate_number: str,
        print_mark: str,
        donation: str,
        tax_type: str,
        sales_amount: int,
        items: List[Dict[str, Any]],
        inv_type: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立發票（一般開立發票）｜i100 §7｜POST /B2CInvoice/Issue"""
        # 選填（**extra，PascalCase）：CustomerID、CustomerIdentifier、CustomerName、CustomerAddr、
        #     CustomerPhone、CustomerEmail、ClearanceMark、LoveCode、CarrierType、CarrierNum、
        #     CarrierNum2、ZeroTaxRateReason、SpecialTaxType、InvoiceRemark、vat
        # 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、
        #     Items[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "RelateNumber": relate_number,
            "Print": print_mark,
            "Donation": donation,
            "TaxType": tax_type,
            "SalesAmount": sales_amount,
            "Items": items,
            "InvType": inv_type,
        }
        data.update(extra)
        return self._post("/B2CInvoice/Issue", data)

    def delay_issue(
        self,
        relate_number: str,
        print_mark: str,
        donation: str,
        tax_type: str,
        sales_amount: int,
        items: List[Dict[str, Any]],
        inv_type: str,
        delay_flag: str,
        delay_day: int,
        tsr: str,
        pay_type: str,
        pay_act: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立發票（延遲開立發票／預約開立發票）｜i100 §7｜POST /B2CInvoice/DelayIssue"""
        # 選填（**extra，PascalCase）：CustomerID、CustomerIdentifier、CustomerName、CustomerAddr、
        #     CustomerPhone、CustomerEmail、ClearanceMark、LoveCode、CarrierType、CarrierNum、
        #     CarrierNum2、ZeroTaxRateReason、SpecialTaxType、InvoiceRemark、NotifyURL、vat
        # 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、
        #     Items[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "RelateNumber": relate_number,
            "Print": print_mark,
            "Donation": donation,
            "TaxType": tax_type,
            "SalesAmount": sales_amount,
            "Items": items,
            "InvType": inv_type,
            "DelayFlag": delay_flag,
            "DelayDay": delay_day,
            "Tsr": tsr,
            "PayType": pay_type,
            "PayAct": pay_act,
        }
        data.update(extra)
        return self._post("/B2CInvoice/DelayIssue", data)

    def trigger_issue(
        self,
        tsr: str,
        pay_type: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """觸發開立發票｜i100 §7｜POST /B2CInvoice/TriggerIssue"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "Tsr": tsr,
            "PayType": pay_type,
        }
        data.update(extra)
        return self._post("/B2CInvoice/TriggerIssue", data)

    def cancel_delay_issue(
        self,
        tsr: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取消延遲開立發票｜i100 §7｜POST /B2CInvoice/CancelDelayIssue"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "Tsr": tsr,
        }
        data.update(extra)
        return self._post("/B2CInvoice/CancelDelayIssue", data)

    def allowance(
        self,
        invoice_no: str,
        invoice_date: str,
        allowance_notify: str,
        allowance_amount: int,
        items: List[Dict[str, Any]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立折讓－一般開立折讓（紙本開立）｜i100 §8｜POST /B2CInvoice/Allowance"""
        # 選填（**extra，PascalCase）：CustomerName、NotifyMail、NotifyPhone
        # 巢狀必填欄位：Items[].ItemSeq、Items[].ItemName、Items[].ItemCount、Items[].ItemWord、
        #     Items[].ItemPrice、Items[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
            "AllowanceNotify": allowance_notify,
            "AllowanceAmount": allowance_amount,
            "Items": items,
        }
        data.update(extra)
        return self._post("/B2CInvoice/Allowance", data)

    def allowance_by_collegiate(
        self,
        invoice_no: str,
        invoice_date: str,
        allowance_notify: str,
        notify_mail: str,
        allowance_amount: int,
        items: List[Dict[str, Any]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立折讓－線上開立折讓（通知開立）｜i100 §8｜POST /B2CInvoice/AllowanceByCollegiate"""
        # 選填（**extra，PascalCase）：CustomerName、ReturnURL
        # 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、
        #     Items[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
            "AllowanceNotify": allowance_notify,
            "NotifyMail": notify_mail,
            "AllowanceAmount": allowance_amount,
            "Items": items,
        }
        data.update(extra)
        return self._post("/B2CInvoice/AllowanceByCollegiate", data)

    def invalid(
        self,
        invoice_no: str,
        invoice_date: str,
        reason: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """作廢發票｜i100 §9｜POST /B2CInvoice/Invalid"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
            "Reason": reason,
        }
        data.update(extra)
        return self._post("/B2CInvoice/Invalid", data)

    def allowance_invalid(
        self,
        invoice_no: str,
        allowance_no: str,
        reason: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """作廢折讓｜i100 §10｜POST /B2CInvoice/AllowanceInvalid"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "AllowanceNo": allowance_no,
            "Reason": reason,
        }
        data.update(extra)
        return self._post("/B2CInvoice/AllowanceInvalid", data)

    def allowance_invalid_by_collegiate(
        self,
        invoice_no: str,
        allowance_no: str,
        reason: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取消線上折讓｜i100 §11｜POST /B2CInvoice/AllowanceInvalidByCollegiate"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "AllowanceNo": allowance_no,
            "Reason": reason,
        }
        data.update(extra)
        return self._post("/B2CInvoice/AllowanceInvalidByCollegiate", data)

    def void_with_re_issue(
        self,
        void_model: Dict[str, Any],
        issue_model: Dict[str, Any],
        **extra: Any,
    ) -> Dict[str, Any]:
        """註銷重開｜i100 §12｜POST /B2CInvoice/VoidWithReIssue"""
        # 巢狀必填欄位：VoidModel.InvoiceNo、VoidModel.VoidReason、IssueModel.RelateNumber、
        #     IssueModel.InvoiceDate、IssueModel.Print、IssueModel.Donation、IssueModel.TaxType、
        #     IssueModel.SalesAmount、IssueModel.Items[].ItemName、IssueModel.Items[].ItemCount、
        #     IssueModel.Items[].ItemWord、IssueModel.Items[].ItemPrice、
        #     IssueModel.Items[].ItemAmount、IssueModel.InvType
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "VoidModel": void_model,
            "IssueModel": issue_model,
        }
        data.update(extra)
        return self._post("/B2CInvoice/VoidWithReIssue", data)

    def get_issue(
        self,
        relate_number: Optional[str] = None,
        invoice_no: Optional[str] = None,
        invoice_date: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢發票明細｜i100 §13｜POST /B2CInvoice/GetIssue"""
        # 兩種查詢情境擇一：情境一 relate_number；情境二 invoice_no + invoice_date（yyyy-MM-dd）。
        data: Dict[str, Any] = {"MerchantID": self.merchant_id}
        if relate_number:
            data["RelateNumber"] = relate_number
        elif invoice_no and invoice_date:
            data["InvoiceNo"] = invoice_no
            data["InvoiceDate"] = invoice_date
        else:
            raise ValueError(
                "查詢發票明細需擇一情境｜修復建議：情境一請傳 relate_number（特店自訂編號）；"
                "情境二請同時傳 invoice_no 與 invoice_date（格式 yyyy-MM-dd 或 yyyy/MM/dd）。"
            )
        data.update(extra)
        return self._post("/B2CInvoice/GetIssue", data)

    def get_allowance_list(
        self,
        search_type: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢折讓明細｜i100 §14｜POST /B2CInvoice/GetAllowanceList"""
        # 選填（**extra，PascalCase）：AllowanceNo、InvoiceNo、Date
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "SearchType": search_type,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetAllowanceList", data)

    def get_invalid(
        self,
        relate_number: str,
        invoice_no: str,
        invoice_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢作廢發票明細｜i100 §15｜POST /B2CInvoice/GetInvalid"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "RelateNumber": relate_number,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetInvalid", data)

    def get_allowance_invalid(
        self,
        invoice_no: str,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢作廢折讓明細｜i100 §16｜POST /B2CInvoice/GetAllowanceInvalid"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetAllowanceInvalid", data)

    def get_invoice_word_setting(
        self,
        invoice_year: str,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢字軌｜i100 §17｜POST /B2CInvoice/GetInvoiceWordSetting"""
        # 選填（**extra，PascalCase）：InvoiceTerm、UseStatus、InvType、InvoiceHeader
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetInvoiceWordSetting", data)

    def invoice_notify(
        self,
        invoice_no: str,
        notify: str,
        invoice_tag: str,
        notified: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """發送發票通知｜i100 §18｜POST /B2CInvoice/InvoiceNotify"""
        # 選填（**extra，PascalCase）：AllowanceNo、Phone、NotifyMail
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "Notify": notify,
            "InvoiceTag": invoice_tag,
            "Notified": notified,
        }
        data.update(extra)
        return self._post("/B2CInvoice/InvoiceNotify", data)

    def invoice_print(
        self,
        invoice_no: str,
        invoice_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """發票列印｜i100 §19｜POST /B2CInvoice/InvoicePrint"""
        # 選填（**extra，PascalCase）：PrintStyle
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
        }
        data.update(extra)
        return self._post("/B2CInvoice/InvoicePrint", data)

    def check_barcode(
        self,
        bar_code: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """手機條碼驗證｜i100 §20｜POST /B2CInvoice/CheckBarcode"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "BarCode": bar_code,
        }
        data.update(extra)
        return self._post("/B2CInvoice/CheckBarcode", data)

    def check_love_code(
        self,
        love_code: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """捐贈碼驗證｜i100 §21｜POST /B2CInvoice/CheckLoveCode"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "LoveCode": love_code,
        }
        data.update(extra)
        return self._post("/B2CInvoice/CheckLoveCode", data)

    def get_company_name_by_tax_id(
        self,
        unified_business_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """統一編號驗證｜i100 §22｜POST /B2CInvoice/GetCompanyNameByTaxID"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "UnifiedBusinessNo": unified_business_no,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetCompanyNameByTaxID", data)

    def get_invoice_notify_setting(
        self,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取得發票通知開關｜i100 §23｜POST /B2CInvoice/GetInvoiceNotifySetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetInvoiceNotifySetting", data)

    def invoice_notify_setting(
        self,
        costomer_setting: List[Dict[str, Any]],
        self_setting: List[Dict[str, Any]],
        inv_header_remain: int,
        remain_word: int,
        email_setting: str,
        notify_email: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """設定發票通知開關｜i100 §24｜POST /B2CInvoice/InvoiceNotifySetting"""
        # 巢狀必填欄位：CostomerSetting[].NotifyType、CostomerSetting[].NotifySwitch、
        #     SelfSetting[].NotifyType、SelfSetting[].NotifySwitch
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "CostomerSetting": costomer_setting,
            "SelfSetting": self_setting,
            "InvHeaderRemain": inv_header_remain,
            "RemainWord": remain_word,
            "EmailSetting": email_setting,
            "NotifyEmail": notify_email,
        }
        data.update(extra)
        return self._post("/B2CInvoice/InvoiceNotifySetting", data)

    def get_remain_notify_setting(
        self,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取得剩餘數量通知開關｜i100 §25｜POST /B2CInvoice/GetRemainNotifySetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetRemainNotifySetting", data)

    def remain_notify_setting(
        self,
        inv_header_remain: int,
        remain_word: int,
        notify_email: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """設定剩餘數量通知開關｜i100 §26｜POST /B2CInvoice/RemainNotifySetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvHeaderRemain": inv_header_remain,
            "RemainWord": remain_word,
            "NotifyEmail": notify_email,
        }
        data.update(extra)
        return self._post("/B2CInvoice/RemainNotifySetting", data)

    def query_blank_invoice_list(
        self,
        invoice_year: str,
        invoice_term: int,
        page_no: int,
        page_size: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢空白未使用發票｜i100 §27｜POST /B2CInvoice/QueryBlankInvoiceList"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceTerm": invoice_term,
            "PageNo": page_no,
            "PageSize": page_size,
        }
        data.update(extra)
        return self._post("/B2CInvoice/QueryBlankInvoiceList", data)

    def blank_inv_auto_upload_setting(
        self,
        setting_list: List[Dict[str, Any]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """設定空白發票是否自動上傳｜i100 §28｜POST /B2CInvoice/BlankInvAutoUploadSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "SettingList": setting_list,
        }
        data.update(extra)
        return self._post("/B2CInvoice/BlankInvAutoUploadSetting", data)

    def down_load_blank_inv_list(
        self,
        blank_list: List[Dict[str, Any]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """下載空白發票清單｜i100 §29｜POST /B2CInvoice/DownLoadBlankInvList"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "BlankList": blank_list,
        }
        data.update(extra)
        return self._post("/B2CInvoice/DownLoadBlankInvList", data)

    def b2b_maintain_merchant_customer_data(
        self,
        action: str,
        identifier: str,
        customer_type: str,
        company_name: str,
        trading_slang: str,
        exchange_mode: str,
        email_address: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """交易對象維護｜i200 §3｜POST /B2BInvoice/MaintainMerchantCustomerData"""
        # 選填（**extra，PascalCase）：CustomerNumber、PersonInCharge、Address、TelephoneNumber、
        #     FacsimileNumber、SalesName、ContactAddress
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "Action": action,
            "Identifier": identifier,
            "type": customer_type,
            "CompanyName": company_name,
            "TradingSlang": trading_slang,
            "ExchangeMode": exchange_mode,
            "EmailAddress": email_address,
        }
        data.update(extra)
        return self._post("/B2BInvoice/MaintainMerchantCustomerData", data)

    def b2b_notify(
        self,
        invoice_date: str,
        invoice_number: str,
        notify_mail: str,
        invoice_tag: str,
        notified: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """發送通知｜i200 §4｜POST /B2BInvoice/Notify"""
        # 選填（**extra，PascalCase）：AllowanceNo
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceDate": invoice_date,
            "InvoiceNumber": invoice_number,
            "NotifyMail": notify_mail,
            "InvoiceTag": invoice_tag,
            "Notified": notified,
        }
        data.update(extra)
        return self._post("/B2BInvoice/Notify", data)

    def b2b_add_invoice_word_setting(
        self,
        invoice_term: int,
        invoice_year: str,
        inv_type: str,
        invoice_category: str,
        invoice_header: str,
        invoice_start: str,
        invoice_end: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """字軌與配號設定｜i200 §5｜POST /B2BInvoice/AddInvoiceWordSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceTerm": invoice_term,
            "InvoiceYear": invoice_year,
            "InvType": inv_type,
            "InvoiceCategory": invoice_category,
            "InvoiceHeader": invoice_header,
            "InvoiceStart": invoice_start,
            "InvoiceEnd": invoice_end,
        }
        data.update(extra)
        return self._post("/B2BInvoice/AddInvoiceWordSetting", data)

    def b2b_update_invoice_word_status(
        self,
        track_id: str,
        invoice_status: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """設定字軌號碼狀態｜i200 §6｜POST /B2BInvoice/UpdateInvoiceWordStatus"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "TrackID": track_id,
            "InvoiceStatus": invoice_status,
        }
        data.update(extra)
        return self._post("/B2BInvoice/UpdateInvoiceWordStatus", data)

    def b2b_issue(
        self,
        relate_number: str,
        customer_identifier: str,
        inv_type: str,
        tax_type: str,
        items: List[Dict[str, Any]],
        sales_amount: int,
        tax_amount: int,
        total_amount: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立發票｜i200 §7｜POST /B2BInvoice/Issue"""
        # 選填（**extra，PascalCase）：InvoiceTime、CustomerEmail、CustomerAddress、
        #     CustomerTelephoneNumber、ClearanceMark、ZeroTaxRateReason、TaxRate、SpecialTaxType、
        #     InvoiceRemark
        # 巢狀必填欄位：Items[].ItemSeq、Items[].ItemName、Items[].ItemCount、Items[].ItemPrice、
        #     Items[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "RelateNumber": relate_number,
            "CustomerIdentifier": customer_identifier,
            "InvType": inv_type,
            "TaxType": tax_type,
            "Items": items,
            "SalesAmount": sales_amount,
            "TaxAmount": tax_amount,
            "TotalAmount": total_amount,
        }
        data.update(extra)
        return self._post("/B2BInvoice/Issue", data)

    def b2b_issue_confirm(
        self,
        invoice_number: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立發票確認｜i200 §8｜POST /B2BInvoice/IssueConfirm"""
        # 選填（**extra，PascalCase）：InvoiceDate、Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNumber": invoice_number,
        }
        data.update(extra)
        return self._post("/B2BInvoice/IssueConfirm", data)

    def b2b_invalid(
        self,
        invoice_number: str,
        invoice_date: str,
        reason: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """作廢發票｜i200 §9｜POST /B2BInvoice/Invalid"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNumber": invoice_number,
            "InvoiceDate": invoice_date,
            "Reason": reason,
        }
        data.update(extra)
        return self._post("/B2BInvoice/Invalid", data)

    def b2b_invalid_confirm(
        self,
        invoice_number: str,
        invoice_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """作廢發票確認｜i200 §10｜POST /B2BInvoice/InvalidConfirm"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNumber": invoice_number,
            "InvoiceDate": invoice_date,
        }
        data.update(extra)
        return self._post("/B2BInvoice/InvalidConfirm", data)

    def b2b_reject(
        self,
        invoice_number: str,
        invoice_date: str,
        reason: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """退回發票｜i200 §11｜POST /B2BInvoice/Reject"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNumber": invoice_number,
            "InvoiceDate": invoice_date,
            "Reason": reason,
        }
        data.update(extra)
        return self._post("/B2BInvoice/Reject", data)

    def b2b_reject_confirm(
        self,
        invoice_number: str,
        invoice_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """退回發票確認｜i200 §12｜POST /B2BInvoice/RejectConfirm"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNumber": invoice_number,
            "InvoiceDate": invoice_date,
        }
        data.update(extra)
        return self._post("/B2BInvoice/RejectConfirm", data)

    def b2b_allowance(
        self,
        tax_amount: int,
        total_amount: int,
        details: List[Dict[str, Any]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """開立折讓發票｜i200 §13｜POST /B2BInvoice/Allowance"""
        # 選填（**extra，PascalCase）：AllowanceDate、CustomerEmail、CustomerAddress
        # 巢狀必填欄位：Details[].OriginalInvoiceNumber、Details[].OriginalInvoiceDate、
        #     Details[].OriginalSequenceNumber、Details[].ItemName、Details[].ItemCount、
        #     Details[].ItemPrice、Details[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "TaxAmount": tax_amount,
            "TotalAmount": total_amount,
            "Details": details,
        }
        data.update(extra)
        return self._post("/B2BInvoice/Allowance", data)

    def b2b_allowance_confirm(
        self,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """折讓發票確認｜i200 §14｜POST /B2BInvoice/AllowanceConfirm"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/AllowanceConfirm", data)

    def b2b_cancel_allowance(
        self,
        allowance_no: str,
        reason: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """作廢折讓發票｜i200 §15｜POST /B2BInvoice/CancelAllowance"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
            "Reason": reason,
        }
        data.update(extra)
        return self._post("/B2BInvoice/CancelAllowance", data)

    def b2b_cancel_allowance_confirm(
        self,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """作廢折讓發票確認｜i200 §16｜POST /B2BInvoice/CancelAllowanceConfirm"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/CancelAllowanceConfirm", data)

    def b2b_void_with_re_issue(
        self,
        void_model: Dict[str, Any],
        issue_model: Dict[str, Any],
        **extra: Any,
    ) -> Dict[str, Any]:
        """註銷重開｜i200 §17｜POST /B2BInvoice/VoidWithReIssue"""
        # 巢狀必填欄位：VoidModel.InvoiceNumber、VoidModel.VoidReason、IssueModel.RelateNumber、
        #     IssueModel.InvoiceTime、IssueModel.CustomerIdentifier、IssueModel.InvType、
        #     IssueModel.TaxType、IssueModel.Items[].ItemSeq、IssueModel.Items[].ItemName、
        #     IssueModel.Items[].ItemCount、IssueModel.Items[].ItemPrice、
        #     IssueModel.Items[].ItemAmount、IssueModel.SalesAmount、IssueModel.TaxAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "VoidModel": void_model,
            "IssueModel": issue_model,
        }
        data.update(extra)
        return self._post("/B2BInvoice/VoidWithReIssue", data)

    def b2b_get_issue(
        self,
        invoice_category: int,
        invoice_number: str,
        invoice_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢發票｜i200 §18｜POST /B2BInvoice/GetIssue"""
        # 選填（**extra，PascalCase）：RelateNumber
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceCategory": invoice_category,
            "InvoiceNumber": invoice_number,
            "InvoiceDate": invoice_date,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetIssue", data)

    def b2b_get_issue_confirm(
        self,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢發票確認｜i200 §19｜POST /B2BInvoice/GetIssueConfirm"""
        # 選填（**extra，PascalCase）：InvoiceNumber、InvoiceDate、RelateNumber、Seller_Identifier、
        #     Buyer_Identifier、InvoiceDateBegin、InvoiceDateEnd、InvoiceNumberBegin、
        #     InvoiceNumberEnd、Issue_Status、Invalid_Status、ExchangeMode、ExchangeStatus、
        #     Upload_Status
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetIssueConfirm", data)

    def b2b_get_invalid(
        self,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢作廢發票｜i200 §20｜POST /B2BInvoice/GetInvalid"""
        # 選填（**extra，PascalCase）：InvoiceNumber、InvoiceDate、RelateNumber
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetInvalid", data)

    def b2b_get_invalid_confirm(
        self,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢作廢發票確認｜i200 §21｜POST /B2BInvoice/GetInvalidConfirm"""
        # 選填（**extra，PascalCase）：InvoiceNumber、InvoiceDate、RelateNumber
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetInvalidConfirm", data)

    def b2b_get_reject(
        self,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢退回發票｜i200 §22｜POST /B2BInvoice/GetReject"""
        # 選填（**extra，PascalCase）：InvoiceNumber、InvoiceDate、RelateNumber
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetReject", data)

    def b2b_get_reject_confirm(
        self,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢退回發票確認｜i200 §23｜POST /B2BInvoice/GetRejectConfirm"""
        # 選填（**extra，PascalCase）：InvoiceNumber、InvoiceDate、RelateNumber
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetRejectConfirm", data)

    def b2b_get_allowance(
        self,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢折讓發票｜i200 §24｜POST /B2BInvoice/GetAllowance"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetAllowance", data)

    def b2b_get_allowance_confirm(
        self,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢折讓發票確認｜i200 §25｜POST /B2BInvoice/GetAllowanceConfirm"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetAllowanceConfirm", data)

    def b2b_get_allowance_invalid(
        self,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢作廢折讓發票｜i200 §26｜POST /B2BInvoice/GetAllowanceInvalid"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetAllowanceInvalid", data)

    def b2b_get_allowance_invalid_confirm(
        self,
        allowance_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢作廢折讓發票確認｜i200 §27｜POST /B2BInvoice/GetAllowanceInvalidConfirm"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "AllowanceNo": allowance_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetAllowanceInvalidConfirm", data)

    def b2b_get_invoice_word_setting(
        self,
        invoice_year: str,
        invoice_term: int,
        use_status: int,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢字軌｜i200 §28｜POST /B2BInvoice/GetInvoiceWordSetting"""
        # 選填（**extra，PascalCase）：InvType、InvoiceHeader
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceTerm": invoice_term,
            "UseStatus": use_status,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetInvoiceWordSetting", data)

    def b2b_get_company_name_by_tax_id(
        self,
        unified_business_no: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """統一編號驗證｜i200 §29｜POST /B2BInvoice/GetCompanyNameByTaxID"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "UnifiedBusinessNo": unified_business_no,
        }
        data.update(extra)
        return self._post("/B2BInvoice/GetCompanyNameByTaxID", data)

    def get_offline_merchant_info(
        self,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢特店基本資料｜i301 §5｜POST /B2CInvoice/GetOfflineMerchantInfo"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetOfflineMerchantInfo", data)

    def offline_get_gov_invoice_word_setting(
        self,
        invoice_year: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢財政部配號結果｜i301 §6｜POST /B2CInvoice/GetGovInvoiceWordSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetGovInvoiceWordSetting", data)

    def offline_merchant_pos_setting(
        self,
        action_type: int,
        machine_id: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """管理發票機台｜i301 §7｜POST /B2CInvoice/OfflineMerchantPosSetting"""
        # 選填（**extra，PascalCase）：Remark
        data: Dict[str, Any] = {
            # 原文本 API 的 Data 未列 MerchantID，故不帶；若歐付寶要求可用 extra 補上。
            "ActionType": action_type,
            "MachineID": machine_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/OfflineMerchantPosSetting", data)

    def query_offline_merchant_pos_setting(
        self,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢發票機台｜i301 §8｜POST /B2CInvoice/QueryOfflineMerchantPosSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/QueryOfflineMerchantPosSetting", data)

    def offline_add_invoice_word_setting(
        self,
        invoice_term: int,
        invoice_year: str,
        inv_type: str,
        invoice_category: str,
        invoice_header: str,
        invoice_start: str,
        invoice_end: str,
        machine_id: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """字軌與配號設定｜i301 §9｜POST /B2CInvoice/AddInvoiceWordSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceTerm": invoice_term,
            "InvoiceYear": invoice_year,
            "InvType": inv_type,
            "InvoiceCategory": invoice_category,
            "InvoiceHeader": invoice_header,
            "InvoiceStart": invoice_start,
            "InvoiceEnd": invoice_end,
            "MachineID": machine_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/AddInvoiceWordSetting", data)

    def offline_update_invoice_word_status(
        self,
        track_id: str,
        invoice_status: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """設定字軌號碼狀態｜i301 §10｜POST /B2CInvoice/UpdateInvoiceWordStatus"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "TrackID": track_id,
            "InvoiceStatus": invoice_status,
        }
        data.update(extra)
        return self._post("/B2CInvoice/UpdateInvoiceWordStatus", data)

    def get_offline_invoice_word_setting_with_auto_split(
        self,
        invoice_year: str,
        invoice_term: int,
        machine_id: str,
        inv_type: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取得自動配發發票字軌號碼｜i301 §11｜POST /B2CInvoice/GetOfflineInvoiceWordSettingWithAutoSplit"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceTerm": invoice_term,
            "MachineID": machine_id,
            "InvType": inv_type,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetOfflineInvoiceWordSettingWithAutoSplit", data)

    def get_offline_invoice_word_setting(
        self,
        invoice_year: str,
        invoice_term: int,
        invoice_status: int,
        machine_id: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取得發票字軌號碼（區間）｜i301 §12｜POST /B2CInvoice/GetOfflineInvoiceWordSetting"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceTerm": invoice_term,
            "InvoiceStatus": invoice_status,
            "MachineID": machine_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetOfflineInvoiceWordSetting", data)

    def get_offline_invoice_word_setting_number(
        self,
        invoice_year: str,
        invoice_term: int,
        invoice_status: int,
        machine_id: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """取得發票字軌號碼（依數量／含隨機碼、加密資料）｜i301 §12｜POST /B2CInvoice/GetOfflineInvoiceWordSettingNumber"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceTerm": invoice_term,
            "InvoiceStatus": invoice_status,
            "MachineID": machine_id,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetOfflineInvoiceWordSettingNumber", data)

    def offline_issue(
        self,
        machine_id: str,
        invoice_no: str,
        invoice_date: str,
        relate_number: str,
        tax_type: str,
        sales_amount: int,
        inv_type: str,
        random_number: str,
        items: List[Dict[str, Any]],
        print_mark: str,
        donation: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """上傳開立發票｜i301 §13｜POST /B2CInvoice/OfflineIssue"""
        # 選填（**extra，PascalCase）：ZeroTaxRateReason、CustomerIdentifier、CustomerID、CustomerAddr、
        #     CustomerPhone、CustomerEmail、ClearanceMark、SpecialTaxType、vat、InvoiceRemark、
        #     CustomerName、LoveCode、CarrierType、CarrierNum、CarrierNum2
        # 巢狀必填欄位：Items[].ItemName、Items[].ItemCount、Items[].ItemWord、Items[].ItemPrice、
        #     Items[].ItemAmount
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "MachineID": machine_id,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
            "RelateNumber": relate_number,
            "TaxType": tax_type,
            "SalesAmount": sales_amount,
            "InvType": inv_type,
            "RandomNumber": random_number,
            "Items": items,
            "Print": print_mark,
            "Donation": donation,
        }
        data.update(extra)
        return self._post("/B2CInvoice/OfflineIssue", data)

    def offline_invalid(
        self,
        invoice_no: str,
        invoice_date: str,
        reason: str,
        cancel_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """上傳作廢發票｜i301 §14｜POST /B2CInvoice/OfflineInvalid"""
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceNo": invoice_no,
            "InvoiceDate": invoice_date,
            "Reason": reason,
            "CancelDate": cancel_date,
        }
        data.update(extra)
        return self._post("/B2CInvoice/OfflineInvalid", data)

    def offline_get_invoice_word_setting(
        self,
        invoice_year: str,
        invoice_term: int,
        use_status: int,
        invoice_category: int,
        **extra: Any,
    ) -> Dict[str, Any]:
        """查詢字軌｜i301 §15｜POST /B2CInvoice/GetInvoiceWordSetting"""
        # 選填（**extra，PascalCase）：InvType、InvoiceHeader
        data: Dict[str, Any] = {
            "MerchantID": self.merchant_id,
            "InvoiceYear": invoice_year,
            "InvoiceTerm": invoice_term,
            "UseStatus": use_status,
            "InvoiceCategory": invoice_category,
        }
        data.update(extra)
        return self._post("/B2CInvoice/GetInvoiceWordSetting", data)


# ---------------------------------------------------------------------------
# 自我測試：只驗證加解密正確性，不會發出任何網路請求。
#   執行：python3 opay_einvoice.py
# ---------------------------------------------------------------------------

#: 官方文件附錄 3 的加密範例（測試向量）
_OFFICIAL_VECTOR = {
    "key": STAGE_B2C_HASH_KEY,
    "iv": STAGE_B2C_HASH_IV,
    "plain": {"Name": "Test", "ID": "A123456789"},
    "urlencoded": "%7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D",
    "cipher": "uvI4yrErM37XNQkXGAgRgJAgHn2t72jahaMZzYhWL1HmvH4WV18VJDP2i9pTbC+tby5nxVExLLFyAkbjbS2Dvg==",
}


def _self_test() -> int:
    client = OPayEInvoiceClient(
        merchant_id=STAGE_B2C_MERCHANT_ID,
        hash_key=_OFFICIAL_VECTOR["key"],
        hash_iv=_OFFICIAL_VECTOR["iv"],
        host=STAGE_HOST,
    )
    failures = 0

    def check(title: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        print(("[PASS] " if ok else "[FAIL] ") + title + (("｜" + detail) if detail else ""))
        if not ok:
            failures += 1

    plain_json = json.dumps(_OFFICIAL_VECTOR["plain"], ensure_ascii=False, separators=(",", ":"))
    encoded = client.urlencode_dotnet(plain_json)
    check("URLEncode（.NET 慣例）與官方範例相同", encoded == _OFFICIAL_VECTOR["urlencoded"], f"實得 {encoded}")

    cipher = client._encrypt(_OFFICIAL_VECTOR["plain"])
    check("AES-128-CBC/PKCS7 加密結果與官方測試向量相同", cipher == _OFFICIAL_VECTOR["cipher"], f"實得 {cipher}")

    restored = client._decrypt(_OFFICIAL_VECTOR["cipher"])
    check("解密官方密文可還原明文", restored == _OFFICIAL_VECTOR["plain"], f"實得 {restored}")

    sample = {"MerchantID": "2000132", "Note": "空格 與 !*()~ 符號 測試"}
    check("加解密往返一致（含空格與特殊符號）", client._decrypt(client._encrypt(sample)) == sample)

    payload = client.build_payload({"MerchantID": "2000132"})
    check(
        "外層 payload 欄位齊全（PlatformID / MerchantID / RqHeader.Timestamp / Data）",
        set(payload) == {"PlatformID", "MerchantID", "RqHeader", "Data"}
        and isinstance(payload["RqHeader"]["Timestamp"], int),
    )

    try:
        client._decrypt("這不是合法密文")
        check("壞密文會丟出 OPayEInvoiceError", False, "沒有丟出例外")
    except OPayEInvoiceError as exc:
        check("壞密文會丟出繁中 OPayEInvoiceError", "修復建議" in str(exc), str(exc)[:40])

    method_count = sum(
        1
        for name in dir(OPayEInvoiceClient)
        if not name.startswith("_")
        and callable(getattr(OPayEInvoiceClient, name))
        and name not in {"urlencode_dotnet", "urldecode_dotnet", "timestamp", "build_payload"}
    )
    check(f"API 方法數量為 69（B2C 30／B2B 27／離線 12），實得 {method_count}", method_count == 69)

    print("-" * 60)
    print("結果：全部通過 ✅" if failures == 0 else f"結果：{failures} 項失敗 ❌（請先修好加解密再串接 API）")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
