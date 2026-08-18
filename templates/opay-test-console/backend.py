#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend.py — 歐付寶電子發票「測試環境全鏈路儀表板」後端（FastAPI）

用途
    在真正串接前，先用六步自我驗證確認「加解密、外層組裝、時間、錯誤處理」都正確，
    再用唯讀 API 打一次歐付寶測試環境，最後（可選）開一張測試發票驗證全鏈路。

對應規格
    references/b2c-api-reference.md（唯讀 API：CheckBarcode / CheckLoveCode /
    GetCompanyNameByTaxID / GetInvoiceWordSetting；開立 API：Issue）
    加解密規格見同檔附錄 2、附錄 3。

相依
    fastapi、uvicorn、requests、pycryptodome
    另需 templates/opay-einvoice-client/python/opay_einvoice.py（本檔會自動加入 sys.path）

啟動
    cp .env.example .env  # 填入測試環境參數
    python3 -m pip install fastapi uvicorn requests pycryptodome
    python3 -m uvicorn backend:app --reload --port 8080
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent
# 讓本檔可直接引用同 repo 的 client 模板，不必先安裝成套件。
CLIENT_DIR = BASE_DIR.parent / "opay-einvoice-client" / "python"
if CLIENT_DIR.exists():
    sys.path.insert(0, str(CLIENT_DIR))

try:
    import requests
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel
except ImportError as exc:  # 缺套件時給人看得懂的中文訊息
    raise SystemExit(
        f"缺少必要套件（{exc.name}）｜修復建議：請執行 "
        "`python3 -m pip install fastapi uvicorn requests pycryptodome` 後再啟動。"
    ) from exc

try:
    from opay_einvoice import (  # type: ignore
        PROD_HOST,
        STAGE_B2C_HASH_IV,
        STAGE_B2C_HASH_KEY,
        STAGE_B2C_MERCHANT_ID,
        STAGE_HOST,
        OPayEInvoiceClient,
        OPayEInvoiceError,
    )
except ImportError as exc:
    raise SystemExit(
        "找不到 opay_einvoice.py｜修復建議：請確認 templates/opay-einvoice-client/python/opay_einvoice.py 存在，"
        f"或把該檔複製到本目錄後再啟動。原始錯誤：{exc}"
    ) from exc


# --- 設定（全部從環境變數讀，測試環境公開值僅作為預設） ---------------------

def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


#: 預設值皆為官方文件公開的「測試環境」參數，正式環境請務必用環境變數覆蓋。
MERCHANT_ID = _env("OPAY_MERCHANT_ID", STAGE_B2C_MERCHANT_ID)
HASH_KEY = _env("OPAY_HASH_KEY", STAGE_B2C_HASH_KEY)      # 僅測試環境
HASH_IV = _env("OPAY_HASH_IV", STAGE_B2C_HASH_IV)         # 僅測試環境
HOST = _env("OPAY_HOST", STAGE_HOST)
PLATFORM_ID = _env("OPAY_PLATFORM_ID", "")
ALLOW_ISSUE_DEMO = _env("OPAY_ALLOW_ISSUE_DEMO", "false").lower() in {"1", "true", "yes", "on"}

#: 官方文件附錄 3 的加密測試向量
OFFICIAL_VECTOR = {
    "key": STAGE_B2C_HASH_KEY,
    "iv": STAGE_B2C_HASH_IV,
    "plain": {"Name": "Test", "ID": "A123456789"},
    "urlencoded": "%7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D",
    "cipher": "uvI4yrErM37XNQkXGAgRgJAgHn2t72jahaMZzYhWL1HmvH4WV18VJDP2i9pTbC+tby5nxVExLLFyAkbjbS2Dvg==",
}

app = FastAPI(title="歐付寶電子發票測試主控台", version="1.0.0")


def get_client() -> OPayEInvoiceClient:
    """建立 client；金鑰長度不對時回 400 而不是 500。"""
    try:
        return OPayEInvoiceClient(
            merchant_id=MERCHANT_ID,
            hash_key=HASH_KEY,
            hash_iv=HASH_IV,
            host=HOST,
            platform_id=PLATFORM_ID,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _step(step_id: int, title: str, status: str, message: str, fix: str = "", detail: Any = None) -> Dict[str, Any]:
    """status：pass（通過）／warn（可繼續但要注意）／fail（必須修好）"""
    return {"id": step_id, "title": title, "status": status, "message": message, "fix": fix, "detail": detail}


# --- 首頁 -------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    """回傳單檔前端 console.html。"""
    page = BASE_DIR / "console.html"
    if not page.exists():
        raise HTTPException(status_code=500, detail="找不到 console.html｜修復建議：請確認 console.html 與 backend.py 放在同一個資料夾。")
    return FileResponse(page, media_type="text/html; charset=utf-8")


@app.get("/api/config")
def config() -> Dict[str, Any]:
    """讓前端顯示目前連的是哪個環境（不回傳任何金鑰內容）。"""
    return {
        "merchant_id": MERCHANT_ID,
        "host": HOST,
        "is_production": HOST.rstrip("/") == PROD_HOST,
        "platform_id": PLATFORM_ID,
        "hash_key_length": len(HASH_KEY),
        "hash_iv_length": len(HASH_IV),
        "allow_issue_demo": ALLOW_ISSUE_DEMO,
    }


# --- 六步自我驗證（完全不打外部網路） ---------------------------------------

@app.post("/api/selftest")
def selftest() -> Dict[str, Any]:
    """六步離線自我驗證：加密向量、URLEncode、外層組裝、時間、往返、錯誤處理。"""
    steps = []

    # 建 client 時若金鑰長度不對，直接回一則可讀的失敗，不讓它變成 500。
    try:
        client = OPayEInvoiceClient(MERCHANT_ID, HASH_KEY, HASH_IV, HOST, PLATFORM_ID)
    except ValueError as exc:
        for i, title in enumerate(
            ["AES 加密向量比對", "URLEncode .NET 校正", "外層 payload 組裝", "Timestamp 時差檢查", "加解密往返", "錯誤處理路徑"],
            start=1,
        ):
            steps.append(_step(i, title, "fail", str(exc), "請修正 .env 的 OPAY_HASH_KEY / OPAY_HASH_IV 後重新啟動。"))
        return {"ok": False, "steps": steps}

    # ① AES 加密向量比對（用官方公開測試金鑰，與目前設定的金鑰無關）
    vector_client = OPayEInvoiceClient(
        STAGE_B2C_MERCHANT_ID, OFFICIAL_VECTOR["key"], OFFICIAL_VECTOR["iv"], STAGE_HOST
    )
    cipher = vector_client._encrypt(OFFICIAL_VECTOR["plain"])
    if cipher == OFFICIAL_VECTOR["cipher"]:
        steps.append(_step(1, "AES 加密向量比對", "pass", "與官方測試向量完全一致（AES-128-CBC / PKCS7 / Base64）。",
                           detail={"expected": OFFICIAL_VECTOR["cipher"], "actual": cipher}))
    else:
        steps.append(_step(1, "AES 加密向量比對", "fail", "加密結果與官方測試向量不同。",
                           "檢查三件事：(1) 模式必須是 AES-128-CBC (2) Padding 必須是 PKCS7 (3) 必須先 URLEncode 再加密，順序不可顛倒。",
                           {"expected": OFFICIAL_VECTOR["cipher"], "actual": cipher}))

    # ② URLEncode .NET 校正比對
    cases = [
        ('{"Name":"Test","ID":"A123456789"}', OFFICIAL_VECTOR["urlencoded"]),
        ("a b", "a+b"),
        ("!*()", "!*()"),
        ("~", "%7E"),
        ("中文", "%E4%B8%AD%E6%96%87"),
    ]
    bad = [(src, exp, OPayEInvoiceClient.urlencode_dotnet(src)) for src, exp in cases
           if OPayEInvoiceClient.urlencode_dotnet(src) != exp]
    if not bad:
        steps.append(_step(2, "URLEncode .NET 校正", "pass", "空格轉 `+`、`!*()` 不編碼、`~` 轉 %7E，皆符合官方轉換表。",
                           detail={"cases": [{"輸入": s, "輸出": e} for s, e in cases]}))
    else:
        steps.append(_step(2, "URLEncode .NET 校正", "fail", f"有 {len(bad)} 個字元的編碼結果不符合官方轉換表。",
                           "多數語言的 urlencode 會把 `!*()` 編碼掉，請用字元替換轉回；空格必須是 `+` 不是 %20。",
                           {"mismatch": [{"輸入": s, "期望": e, "實得": a} for s, e, a in bad]}))

    # ③ 外層 payload 組裝格式檢查
    payload = client.build_payload({"MerchantID": MERCHANT_ID})
    problems = []
    if set(payload) != {"PlatformID", "MerchantID", "RqHeader", "Data"}:
        problems.append("外層欄位應為 PlatformID / MerchantID / RqHeader / Data 四項")
    if not isinstance(payload.get("RqHeader", {}).get("Timestamp"), int):
        problems.append("RqHeader.Timestamp 必須是整數 Unix timestamp")
    if not isinstance(payload.get("Data"), str) or not payload["Data"]:
        problems.append("Data 必須是加密後的 Base64 字串")
    masked = dict(payload, Data=(payload["Data"][:24] + "…（已截斷）"))
    if not problems:
        steps.append(_step(3, "外層 payload 組裝", "pass", "外層四欄位齊全、Timestamp 為整數、Data 為 Base64 字串。", detail=masked))
    else:
        steps.append(_step(3, "外層 payload 組裝", "fail", "；".join(problems),
                           "外層結構固定為 {\"PlatformID\":\"\",\"MerchantID\":\"…\",\"RqHeader\":{\"Timestamp\":…},\"Data\":\"…\"}。",
                           masked))

    # ④ Timestamp 時差檢查（本機時間 vs UTC）
    local_epoch = int(time.time())
    utc_epoch = int(datetime.now(timezone.utc).timestamp())
    drift = abs(local_epoch - utc_epoch)
    tz_name = datetime.now().astimezone().tzname() or "未知時區"
    detail = {
        "本機 epoch": local_epoch,
        "UTC epoch": utc_epoch,
        "差值（秒）": drift,
        "時區": tz_name,
        "說明": "本檢查只能驗證程式取得的時間戳一致；主機整體時鐘偏移請用 NTP（timedatectl / chronyc tracking）確認。",
    }
    if drift <= 60:
        steps.append(_step(4, "Timestamp 時差檢查", "pass",
                           f"本機時間與 UTC 差 {drift} 秒，在歐付寶 10 分鐘驗證區間內。", detail=detail))
    else:
        steps.append(_step(4, "Timestamp 時差檢查", "warn",
                           f"本機時間與 UTC 差 {drift} 秒（超過 60 秒）。",
                           "請立即校時：Linux `sudo timedatectl set-ntp true` 或 `sudo chronyc makestep`；"
                           "時差超過 10 分鐘會導致所有 API 直接回 TransCode 失敗。", detail))

    # ⑤ 解密往返（encrypt → decrypt 還原）
    sample = {"MerchantID": MERCHANT_ID, "Note": "往返測試 空格 !*()~ 中文"}
    try:
        restored = client._decrypt(client._encrypt(sample))
        if restored == sample:
            steps.append(_step(5, "加解密往返", "pass", "加密後再解密可完整還原（含空格、特殊符號與中文）。", detail=restored))
        else:
            steps.append(_step(5, "加解密往返", "fail", "還原結果與原始資料不同。",
                               "檢查解密順序是否為「先 AES 解密再 URLDecode」，以及 URLDecode 是否有把 `+` 還原成空格。",
                               {"原始": sample, "還原": restored}))
    except OPayEInvoiceError as exc:
        steps.append(_step(5, "加解密往返", "fail", str(exc), "請先修正第 ① ② 步的問題再重跑。"))

    # ⑥ 錯誤處理路徑（餵壞密文，必須丟出繁中錯誤而不是 500）
    try:
        client._decrypt("這不是合法密文")
        steps.append(_step(6, "錯誤處理路徑", "fail", "餵入壞密文竟然沒有丟出錯誤。",
                           "請確認 _decrypt 有針對 Base64、區塊長度、AES、JSON 四種失敗各自丟出 OPayEInvoiceError。"))
    except OPayEInvoiceError as exc:
        has_fix = "修復建議" in str(exc)
        steps.append(_step(6, "錯誤處理路徑", "pass" if has_fix else "warn",
                           f"已正確攔截並丟出 OPayEInvoiceError：{exc}",
                           "" if has_fix else "錯誤訊息建議補上「修復建議」，讓值班同事不必翻文件。"))
    except Exception as exc:  # noqa: BLE001
        steps.append(_step(6, "錯誤處理路徑", "fail", f"丟出的是未包裝的例外：{type(exc).__name__}: {exc}",
                           "請把解密失敗包成 OPayEInvoiceError，避免直接變成 HTTP 500。"))

    return {"ok": all(s["status"] != "fail" for s in steps), "steps": steps}


# --- 真的打測試環境（唯讀 API） ---------------------------------------------

class LiveRequest(BaseModel):
    """唯讀 API 的參數；未填者使用官方文件的測試值。"""

    barcode: Optional[str] = None            # 手機條碼，例如 /ABC+123
    love_code: Optional[str] = None          # 捐贈碼，例如 168001
    tax_id: Optional[str] = None             # 統一編號，例如 53538851
    invoice_year: Optional[str] = None       # 民國年，例如 115
    invoice_category: Optional[int] = None   # 1=一般（B2C）、2=特種


LIVE_ACTIONS = {
    "CheckBarcode": "手機條碼驗證（i100 §20）",
    "CheckLoveCode": "捐贈碼驗證（i100 §21）",
    "GetCompanyNameByTaxID": "統一編號驗證（i100 §22）",
    "GetInvoiceWordSetting": "查詢字軌（i100 §17）",
}


def _live_call(client: OPayEInvoiceClient, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """送出唯讀 API，同時回傳「原始外層回應」與「解密後 Data」，失敗也不丟例外。"""
    url = f"{client.host}{path}"
    payload = client.build_payload(data)
    try:
        response = requests.post(url, json=payload, timeout=client.timeout,
                                 headers={"Content-Type": "application/json"})
    except requests.Timeout:
        return {"ok": False, "error": f"呼叫 {path} 逾時（{client.timeout} 秒）｜修復建議：確認對外網路可通、防火牆以 FQDN 放行 einvoice-stage.opay.tw。"}
    except requests.RequestException as exc:
        return {"ok": False, "error": f"連線 {url} 失敗：{exc}｜修復建議：僅支援 TLS 1.2 以上與 443 port，且官方 IP 不固定，請用 FQDN 設定防火牆。"}

    raw_text = response.text
    try:
        raw_body = response.json()
    except ValueError:
        return {"ok": False, "error": f"回應不是 JSON（HTTP {response.status_code}）｜修復建議：確認打到的網域與路徑正確。",
                "request": dict(payload, Data=payload["Data"][:24] + "…（已截斷）"), "raw_text": raw_text[:500]}

    result: Dict[str, Any] = {
        "ok": False,
        "http_status": response.status_code,
        "request": dict(payload, Data=payload["Data"][:24] + "…（已截斷）"),
        "raw_response": raw_body,
        "trans_code": raw_body.get("TransCode"),
        "trans_msg": raw_body.get("TransMsg"),
    }
    if raw_body.get("TransCode") != 1:
        result["error"] = (f"外層傳輸失敗（TransCode={raw_body.get('TransCode')}）：{raw_body.get('TransMsg', '')}"
                           "｜修復建議：優先檢查主機時間是否在 10 分鐘驗證區間內、MerchantID 是否與金鑰同一組。")
        return result
    try:
        decrypted = client._decrypt(raw_body.get("Data", ""))
    except OPayEInvoiceError as exc:
        result["error"] = str(exc)
        return result
    result["decrypted"] = decrypted
    result["rtn_code"] = decrypted.get("RtnCode")
    result["rtn_msg"] = decrypted.get("RtnMsg")
    result["ok"] = decrypted.get("RtnCode") == 1
    if not result["ok"]:
        result["error"] = (f"業務處理失敗（RtnCode={decrypted.get('RtnCode')}）：{decrypted.get('RtnMsg', '')}"
                           "｜修復建議：對照 references/b2c-api-reference.md 附錄 1 錯誤代碼；查詢類多半是參數格式或資料不存在。")
    return result


@app.post("/api/live/{action}")
def live(action: str, body: LiveRequest) -> Dict[str, Any]:
    """真的呼叫測試環境的**唯讀** API（不會產生任何發票資料）。"""
    if action not in LIVE_ACTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"不支援的動作「{action}」｜修復建議：唯讀動作僅限 {'、'.join(LIVE_ACTIONS)}。",
        )
    client = get_client()
    if action == "CheckBarcode":
        data = {"MerchantID": client.merchant_id, "BarCode": body.barcode or "/ABC+123"}
    elif action == "CheckLoveCode":
        data = {"MerchantID": client.merchant_id, "LoveCode": body.love_code or "168001"}
    elif action == "GetCompanyNameByTaxID":
        data = {"MerchantID": client.merchant_id, "UnifiedBusinessNo": body.tax_id or "53538851"}
    else:  # GetInvoiceWordSetting
        default_year = str(datetime.now().year - 1911)
        data = {
            "MerchantID": client.merchant_id,
            "InvoiceYear": body.invoice_year or default_year,
            "InvoiceCategory": body.invoice_category if body.invoice_category is not None else 1,
        }
    outcome = _live_call(client, f"/B2CInvoice/{action}", data)
    outcome["action"] = action
    outcome["action_label"] = LIVE_ACTIONS[action]
    outcome["sent_data"] = data
    return outcome


# --- 開一張測試發票（會產生真實紀錄） ---------------------------------------

class IssueDemoRequest(BaseModel):
    """開立測試發票的參數。

    ⚠️ 這支 API 會在**測試環境產生一張真實的發票紀錄**，並消耗一個字軌號碼，
    無法「刪除」，只能作廢。因此必須明確帶 confirm=true 才會執行。
    """

    confirm: bool = False
    relate_number: Optional[str] = None
    sales_amount: int = 100
    item_name: str = "測試商品"
    customer_email: Optional[str] = None


@app.post("/api/issue-demo")
def issue_demo(body: IssueDemoRequest) -> JSONResponse:
    """開立一張測試發票（⚠️ 會在測試環境留下真實發票紀錄，且會消耗字軌號碼）。"""
    if not ALLOW_ISSUE_DEMO:
        raise HTTPException(
            status_code=403,
            detail="開立示範已停用｜修復建議：這會產生真實發票紀錄，確定要開再於 .env 設定 OPAY_ALLOW_ISSUE_DEMO=true 並重新啟動。",
        )
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="尚未確認｜修復建議：此操作會在測試環境產生一張真實發票並消耗字軌號碼（只能作廢、無法刪除），請勾選確認框後再送出。",
        )
    if HOST.rstrip("/") == PROD_HOST:
        raise HTTPException(
            status_code=400,
            detail="目前 OPAY_HOST 指向正式環境｜修復建議：本主控台僅供測試環境使用，請把 OPAY_HOST 改回 https://einvoice-stage.opay.tw。",
        )

    client = get_client()
    relate_number = body.relate_number or f"DEMO{int(time.time())}"
    items = [{
        "ItemName": body.item_name,
        "ItemCount": 1,
        "ItemWord": "個",
        "ItemPrice": body.sales_amount,
        "ItemAmount": body.sales_amount,
    }]
    extra: Dict[str, Any] = {}
    if body.customer_email:
        # 選填欄位一律以官方 PascalCase 原樣傳入
        extra["CustomerEmail"] = body.customer_email
    try:
        result = client.issue(
            relate_number=relate_number,
            print_mark="0",
            donation="0",
            tax_type="1",
            sales_amount=body.sales_amount,
            items=items,
            inv_type="07",
            **extra,
        )
    except OPayEInvoiceError as exc:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "relate_number": relate_number,
                "error": str(exc),
                "rtn_code": exc.rtn_code,
                "trans_code": exc.trans_code,
                "warning": "若錯誤訊息與字軌有關，請先用「查詢字軌」確認號碼是否已設定或已用罄。",
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "relate_number": relate_number,
            "result": result,
            "warning": "這張發票是測試環境的真實紀錄，已消耗一個字軌號碼；如需清除只能作廢（Invalid），無法刪除。",
        },
    )


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("缺少 uvicorn｜修復建議：請執行 `python3 -m pip install uvicorn` 後再啟動。")
    port = int(_env("PORT", "8080"))
    print(f"測試主控台啟動中：http://127.0.0.1:{port}（目前 host：{HOST}）")
    uvicorn.run(app, host="127.0.0.1", port=port)
