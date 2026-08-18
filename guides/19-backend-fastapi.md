# 19 · FastAPI 後端骨架

用 [`templates/opay-einvoice-client/python/`](../templates/opay-einvoice-client/python/) 接起 FastAPI：`.env` 設計、路由分層、錯誤轉譯。

> **對應 API**：不新增 API；本文說明如何把 client 的 69 支方法接進 FastAPI 服務。規格見 [`references/`](../references/)。
> **前置條件**：Python 3.8+；已完成 [`02-preflight-checklist.md`](02-preflight-checklist.md)；已跑過 [`23-test-console.md`](23-test-console.md) 的六步自我驗證。

---

## 1. 專案結構

```
app/
├── main.py                 # FastAPI app、例外處理器
├── config.py               # 設定與環境變數（缺少即啟動失敗）
├── deps.py                 # 依賴注入：提供 OPayEInvoiceClient
├── routers/
│   ├── invoice.py          # 開立、作廢、註銷重開
│   ├── allowance.py        # 折讓
│   ├── query.py            # 查詢類（可安全重試）
│   ├── validation.py       # CheckBarcode / CheckLoveCode / TaxID
│   └── callbacks.py        # NotifyURL / ReturnURL 幕後通知
├── services/
│   ├── issue_service.py    # 冪等狀態機 + 業務邏輯
│   └── word_service.py     # 字軌餘量
├── models.py               # SQLAlchemy：發票狀態表
└── opay_einvoice.py        # ← 直接複製自 templates/，不要改寫
requirements.txt
.env.example
```

> **為什麼 client 要原樣複製而不是包一層**：`templates/opay-einvoice-client/python/opay_einvoice.py` 的加解密邏輯已用官方測試向量驗證過。**改寫它就等於重新承擔加解密出錯的風險**，而那類錯誤最難 debug。要加業務邏輯就加在 `services/`。

---

## 2. `.env` 設計

```bash
# ---- 環境 -------------------------------------------------------------
OPAY_ENV=stage                                  # stage | production
OPAY_HOST=https://einvoice-stage.opay.tw        # 由 OPAY_ENV 決定，不要手改

# ---- 憑證（缺少即啟動失敗，不得有預設值） -----------------------------
OPAY_MERCHANT_ID=
OPAY_HASH_KEY=
OPAY_HASH_IV=
OPAY_PLATFORM_ID=                               # 一般廠商留空

# ---- 業務 -------------------------------------------------------------
OPAY_INVOICE_CATEGORY=1                         # 1 B2C / 2 B2B / 4 離線
OPAY_WORD_REMAIN_THRESHOLD=500                  # 字軌剩餘警戒（張）
OPAY_TIMEOUT=15

# ---- 回呼 -------------------------------------------------------------
OPAY_NOTIFY_URL=https://shop.example.com/opay/notify
OPAY_RETURN_URL=https://shop.example.com/opay/allowance-callback

DATABASE_URL=postgresql+psycopg://user:pass@localhost/shop
```

```python
# config.py
import os, sys

class Settings:
    def __init__(self) -> None:
        self.env = os.environ.get("OPAY_ENV", "stage")
        self.merchant_id = self._require("OPAY_MERCHANT_ID")
        self.hash_key = self._require("OPAY_HASH_KEY")
        self.hash_iv = self._require("OPAY_HASH_IV")
        self.platform_id = os.environ.get("OPAY_PLATFORM_ID", "")
        self.host = ("https://einvoice.opay.tw" if self.env == "production"
                     else "https://einvoice-stage.opay.tw")
        self.timeout = int(os.environ.get("OPAY_TIMEOUT", "15"))
        # 金鑰長度在這裡就檢查，不要等到第一次呼叫 API 才發現
        for name, val in (("OPAY_HASH_KEY", self.hash_key), ("OPAY_HASH_IV", self.hash_iv)):
            if len(val.encode()) != 16:
                sys.exit(f"[啟動失敗] {name} 必須是 16 bytes（AES-128），實得 {len(val.encode())}")

    @staticmethod
    def _require(key: str) -> str:
        val = os.environ.get(key)
        if not val:
            sys.exit(f"[啟動失敗] 缺少環境變數 {key}｜修復建議：複製 .env.example 為 .env 並填入廠商後台取得的值。")
        return val

settings = Settings()
```

| 規則 | 為什麼 |
|---|---|
| 缺少金鑰**直接 `sys.exit`**，不要有預設值 | 有 fallback 的話，環境變數設錯時程式會靜默用測試金鑰打正式環境，`TransCode` 全失敗但看不出原因 |
| `host` 由 `OPAY_ENV` 推導 | 兩個變數各自設定會有「host 是正式、金鑰是測試」的災難組合 |
| 金鑰長度在**啟動時**檢查 | 16 bytes 是硬性要求，早失敗好過晚失敗 |
| `.env` 進 `.gitignore` | 官方明訂金鑰不得外流 |

---

## 3. 依賴注入

```python
# deps.py
from functools import lru_cache
from opay_einvoice import OPayEInvoiceClient
from .config import settings

@lru_cache(maxsize=1)
def get_client() -> OPayEInvoiceClient:
    return OPayEInvoiceClient(
        merchant_id=settings.merchant_id,
        hash_key=settings.hash_key,
        hash_iv=settings.hash_iv,
        host=settings.host,
        platform_id=settings.platform_id,
        timeout=settings.timeout,
    )
```

> client 內部持有 `requests.Session()`，用 `lru_cache` 共用一個實例可以複用連線。**但 `Timestamp` 是每次呼叫才產生的**（`build_payload()` 內），不會因為 client 長壽而過期。

---

## 4. 路由分層

**依「可否安全重試」分層，而不是依 API 名稱分。**

| 層 | 路由 | 特性 | 中介層 |
|---|---|---|---|
| **唯讀** | `query.py`、`validation.py` | 冪等，可重試 | 自動重試 + 快取（統編可快取） |
| **設定** | `word_service` 相關 | 覆寫語意 | 需先讀後寫 |
| **🚫 財務動作** | `invoice.py`、`allowance.py` | **不可盲目重試** | 冪等鎖 + audit log + 二次確認 |
| **回呼** | `callbacks.py` | 外部呼入 | 冪等處理 + 回 `1\|OK` |

```python
# routers/invoice.py
from fastapi import APIRouter, Depends, HTTPException
router = APIRouter(prefix="/invoice", tags=["invoice"])

@router.post("/issue")
def issue(req: IssueRequest, svc: IssueService = Depends(get_issue_service)):
    """開立發票。冪等鍵為 req.order_id 推導出的 RelateNumber。"""
    return svc.issue_once(req)      # 冪等邏輯全部在 service，不在 router
```

> **為什麼冪等邏輯要在 service 不在 router**：router 會被多個入口呼叫（HTTP、排程、管理後台、CLI）。放在 router 只保護 HTTP 那一條路。

---

## 5. 冪等 service（核心）

```python
# services/issue_service.py
from sqlalchemy import select
from opay_einvoice import OPayEInvoiceError

class IssueService:
    def issue_once(self, req) -> dict:
        relate = to_relate_number(req.order_id)          # 穩定推導 + upper() + 截 30 碼

        with self.db.begin():
            # SELECT ... FOR UPDATE：同一筆訂單的併發請求會排隊
            row = self.db.execute(
                select(InvoiceState).where(InvoiceState.relate_number == relate)
                .with_for_update()
            ).scalar_one_or_none()

            if row and row.status == "SUCCEEDED":
                return row.result                        # 已開過，直接回，不重開
            if row and row.status == "IN_FLIGHT":
                raise HTTPException(409, "此訂單的發票正在處理中，請稍後查詢結果")
            if not row:
                row = InvoiceState(relate_number=relate, status="PENDING")
                self.db.add(row)
            row.status = "IN_FLIGHT"                     # ← 送出「前」就 commit
        # ↑ 交易在這裡 commit：IN_FLIGHT 已經落地

        try:
            result = self.client.issue(relate_number=relate, **req.to_opay_payload())
        except OPayEInvoiceError as exc:
            # timeout / 連線中斷 → 結果未知，保持 IN_FLIGHT，交給對帳排程
            if is_unknown_outcome(exc):
                raise HTTPException(503, "開立結果未知，系統將自動對帳，請勿重複送出")
            self._mark(relate, "FAILED_PERMANENT", exc)
            raise HTTPException(400, f"開立失敗：{exc.rtn_msg or exc}")

        self._mark(relate, "SUCCEEDED", result)
        return result
```

**關鍵順序**：`IN_FLIGHT` 必須在**發出 HTTP 請求之前** commit。順序反了，程式在送出後、寫入前崩潰，你就永遠不知道那筆送出去了沒有。完整說明見 [`22-idempotency-and-retry.md`](22-idempotency-and-retry.md)。

---

## 6. 錯誤轉譯

**三層錯誤，三種對外呈現。**

| 來源 | 對外 HTTP | 對外訊息 | 內部記錄 |
|---|---|---|---|
| 設定錯誤（金鑰、時間） | 500 | 「系統設定異常，已通知維運」 | 完整 `TransCode`/`TransMsg` |
| 業務失敗（欄位、字軌） | 400 | 通用文案 + 客服可見的參考碼 | **`RtnCode`/`RtnMsg` 原樣** |
| 結果未知（timeout） | 503 | 「處理中，請勿重複送出」 | 標記 `IN_FLIGHT` |

```python
# main.py
@app.exception_handler(OPayEInvoiceError)
def opay_error_handler(request: Request, exc: OPayEInvoiceError):
    # 🚫 不要翻譯、不要分類 RtnCode —— 官方沒有公開完整錯誤碼表
    log.error("opay_error endpoint=%s trans=%s/%s rtn=%s/%s",
              exc.endpoint, exc.trans_code, exc.trans_msg, exc.rtn_code, exc.rtn_msg)
    ref = save_error_for_support(exc)          # 客服查得到的參考碼
    return JSONResponse(status_code=400, content={
        "message": "發票處理失敗，請聯繫客服",
        "reference": ref,                       # 只給參考碼，不給 RtnMsg
    })
```

> 🚫 **不要在程式裡建一張自己編的錯誤碼對照表。** 官方三份文件的附錄都只寫「錯誤代碼一直在新增，請到廠商後台查詢」。硬編一張猜測的表，會在正式環境造成「你的程式說是 A 錯誤，實際是 B 錯誤」的誤導。詳見 [`error-handling.md` §0](../references/error-handling.md)。
>
> **對外訊息不要直接吐 `RtnMsg`**：它可能包含內部欄位名，對消費者沒有意義，還可能洩漏系統細節。給參考碼，讓客服去查。

---

## 7. 回呼路由

```python
# routers/callbacks.py
@router.post("/notify")                # DelayIssue 的 NotifyURL
async def delay_issue_notify(request: Request):
    form = await request.form()        # ⚠️ 表單編碼，不是 JSON
    tsr = form.get("tsr")
    if form.get("invoicenumber"):
        mark_issued(tsr, form.get("invoicenumber"), form.get("invoicedate"))
    else:
        mark_issue_failed(tsr, form.get("inv_error"))
    return PlainTextResponse("1|OK")   # ⚠️ 必須正確回應，否則會被重送
```

| 規則 | 說明 |
|---|---|
| 內容是**表單編碼**（`application/x-www-form-urlencoded`），不是 JSON | 用 `await request.form()` |
| 必須回 `1\|OK` | 沒回會被重送 |
| 處理必須**冪等** | 因為會被重送 |
| 測試環境**不提供 `NotifyURL` 通知** | 這段邏輯只能在正式環境驗 |
| 防火牆要放行 `postgate(-stage).opay.com.tw` TCP 443 | 見 [`02-preflight-checklist.md`](02-preflight-checklist.md) §2.9 |

---

## 8. 排程任務

```python
# 建議用 APScheduler 或外部 cron
每 5 分鐘   → 對帳：把逾時的 IN_FLIGHT 用 GetIssue 收斂
每 1 小時   → 字軌餘量檢查（GetInvoiceWordSetting），低於門檻推播
每日 09:00  → B2B：掃描「等待確認」與「被退回」的發票
每期首日    → 檢查下一期字軌是否已啟用；處理上一期空白未使用發票
```

---

### 常見錯誤

1. **金鑰有預設值。** 環境變數設錯時程式靜默用測試金鑰打正式環境，全部失敗但看不出原因。**缺少就啟動失敗。**
2. **`host` 與金鑰分別設定。** 會出現「host 正式、金鑰測試」的組合。用 `OPAY_ENV` 推導 host。
3. **改寫 client 的加解密邏輯。** 那份程式已用官方測試向量驗證過。業務邏輯加在 `services/`。
4. **冪等邏輯寫在 router。** 排程與 CLI 走不到 router，保護不到。
5. **在程式裡建自己的錯誤碼對照表。** 官方沒有公開完整清單，猜測會造成誤導。原樣記錄即可。
6. **回呼路由用 `await request.json()`。** 歐付寶送的是**表單編碼**，會解析失敗。
