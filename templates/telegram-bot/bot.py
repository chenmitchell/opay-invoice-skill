#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot.py — 歐付寶電子發票 Telegram 通知／查詢機器人（模板）

用途
    以 Bind / Notify / Menu 三段結構，把電子發票事件推播到 Telegram，
    並提供值班同事最常用的查詢與（需二次確認的）作廢／折讓操作。

    Bind   ：/bind <ADMIN_TOKEN> 綁定聊天室，之後才會收到推播
    Notify ：① 商店系統 POST 事件到本機 notify 埠 ② 背景執行緒定時檢查字軌剩餘
    Menu   ：/today、/invoice、/words、/invalid、/allowance、/confirm、/cancel

對應規格
    references/b2c-api-reference.md
      §13 GetIssue（查發票明細）、§17 GetInvoiceWordSetting（查字軌剩餘）、
      §9 Invalid（作廢）、§8 Allowance（折讓）
    共用 client：templates/opay-einvoice-client/python/opay_einvoice.py

相依
    python3 -m pip install requests pycryptodome
    （不使用任何 Telegram 第三方 SDK，直接打 Bot API）

啟動
    cp .env.example .env  # 逐欄填寫
    set -a && . ./.env && set +a
    python3 bot.py

安全與稽核
    * 作廢與折讓**不可逆**：一律要求二次確認（/confirm <驗證碼>），並寫入 audit log。
    * 金額大只會加註警示，**不會阻擋**——擋下來會讓現場無法處理客訴。
    * 所有金鑰只從環境變數讀，程式碼內不得出現正式環境金鑰。
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import random
import sqlite3
import string
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
CLIENT_DIR = BASE_DIR.parent / "opay-einvoice-client" / "python"
if CLIENT_DIR.exists():
    sys.path.insert(0, str(CLIENT_DIR))


def die(message: str) -> "None":
    """印出繁體中文錯誤訊息並結束，不要讓使用者看到 traceback。"""
    print("\n[啟動失敗] " + message + "\n", file=sys.stderr)
    raise SystemExit(1)


try:
    import requests
except ImportError:
    die("缺少 requests 套件｜修復建議：執行 `python3 -m pip install requests pycryptodome` 後再啟動。")

try:
    from opay_einvoice import OPayEInvoiceClient, OPayEInvoiceError, STAGE_HOST  # type: ignore
except ImportError as exc:
    die(
        "找不到 opay_einvoice.py｜修復建議：確認 templates/opay-einvoice-client/python/opay_einvoice.py 存在，"
        f"或把該檔複製到本目錄。原始錯誤：{exc}"
    )


# --- 設定 -------------------------------------------------------------------

def _load_env_file(path: Path) -> None:
    """若同目錄有 .env 就載入（不覆蓋既有環境變數），避免額外相依 python-dotenv。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
NOTIFY_TOKEN = os.environ.get("NOTIFY_TOKEN", "").strip()
NOTIFY_PORT = int(os.environ.get("NOTIFY_PORT", "8790") or 8790)
DB_PATH = os.environ.get("BOT_DB_PATH", str(BASE_DIR / "bot-state.sqlite3"))
AUDIT_LOG_PATH = os.environ.get("AUDIT_LOG_PATH", str(BASE_DIR / "audit.log"))

OPAY_MERCHANT_ID = os.environ.get("OPAY_MERCHANT_ID", "").strip()
OPAY_HASH_KEY = os.environ.get("OPAY_HASH_KEY", "").strip()
OPAY_HASH_IV = os.environ.get("OPAY_HASH_IV", "").strip()
OPAY_HOST = os.environ.get("OPAY_HOST", STAGE_HOST).strip() or STAGE_HOST

WORD_REMAIN_THRESHOLD = int(os.environ.get("WORD_REMAIN_THRESHOLD", "200") or 200)
WORD_CHECK_INTERVAL = int(os.environ.get("WORD_CHECK_INTERVAL", "3600") or 3600)
LARGE_AMOUNT_WARN = int(os.environ.get("LARGE_AMOUNT_WARN", "50000") or 50000)
CONFIRM_TTL_SECONDS = int(os.environ.get("CONFIRM_TTL_SECONDS", "300") or 300)

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")],
)
log = logging.getLogger("opay-telegram-bot")


def check_startup() -> None:
    """啟動前檢查，缺什麼就給明確的中文指示。"""
    if not TELEGRAM_BOT_TOKEN:
        die(
            "缺少 TELEGRAM_BOT_TOKEN｜修復建議：向 Telegram 的 @BotFather 申請機器人取得 token，"
            "寫進 .env 的 TELEGRAM_BOT_TOKEN，再重新啟動。"
        )
    if ":" not in TELEGRAM_BOT_TOKEN:
        die("TELEGRAM_BOT_TOKEN 格式不正確｜修復建議：正確格式類似 123456789:AAH...，請重新從 @BotFather 複製完整字串。")
    if not ADMIN_TOKEN:
        die(
            "缺少 ADMIN_TOKEN｜修復建議：自行產生一組隨機字串（例如 `openssl rand -hex 16`）寫進 .env 的 ADMIN_TOKEN，"
            "同事用 /bind <ADMIN_TOKEN> 綁定聊天室時要用。"
        )
    if len(ADMIN_TOKEN) < 12:
        die("ADMIN_TOKEN 太短（少於 12 碼）｜修復建議：改用至少 12 碼的隨機字串，避免被暴力猜中而讓外人綁定聊天室。")


# --- 資料層（綁定 / 事件 / 稽核 / 待確認） -----------------------------------

_db_lock = threading.Lock()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db_lock, db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bound_chats (
                chat_id TEXT PRIMARY KEY,
                bound_at TEXT NOT NULL,
                bound_by TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                invoice_no TEXT,
                relate_number TEXT,
                amount INTEGER DEFAULT 0,
                payload TEXT
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                actor TEXT,
                chat_id TEXT,
                action TEXT NOT NULL,
                target TEXT,
                reason TEXT,
                result TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS pending (
                code TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                actor TEXT,
                action TEXT NOT NULL,
                args TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )


def bound_chat_ids() -> List[str]:
    with _db_lock, db() as conn:
        return [row["chat_id"] for row in conn.execute("SELECT chat_id FROM bound_chats")]


def bind_chat(chat_id: str, actor: str) -> bool:
    with _db_lock, db() as conn:
        exists = conn.execute("SELECT 1 FROM bound_chats WHERE chat_id = ?", (chat_id,)).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO bound_chats (chat_id, bound_at, bound_by) VALUES (?, ?, ?)",
            (chat_id, datetime.now().isoformat(timespec="seconds"), actor),
        )
        return True


def unbind_chat(chat_id: str) -> bool:
    with _db_lock, db() as conn:
        cur = conn.execute("DELETE FROM bound_chats WHERE chat_id = ?", (chat_id,))
        return cur.rowcount > 0


def record_event(event_type: str, payload: Dict[str, Any]) -> None:
    with _db_lock, db() as conn:
        conn.execute(
            "INSERT INTO events (ts, event_type, invoice_no, relate_number, amount, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                event_type,
                str(payload.get("invoice_no") or payload.get("InvoiceNo") or ""),
                str(payload.get("relate_number") or payload.get("RelateNumber") or ""),
                int(payload.get("amount") or payload.get("SalesAmount") or 0),
                json.dumps(payload, ensure_ascii=False),
            ),
        )


def write_audit(actor: str, chat_id: str, action: str, target: str, reason: str, result: str, detail: str = "") -> None:
    """不可逆操作一律留稽核紀錄：誰、在哪個聊天室、對哪張發票、做了什麼、結果如何。"""
    with _db_lock, db() as conn:
        conn.execute(
            "INSERT INTO audit (ts, actor, chat_id, action, target, reason, result, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), actor, chat_id, action, target, reason, result, detail),
        )
    log.info("AUDIT actor=%s chat=%s action=%s target=%s reason=%s result=%s %s",
             actor, chat_id, action, target, reason, result, detail)


def today_summary() -> Tuple[int, int, int]:
    """回傳（今日開立成功張數, 今日開立成功金額, 今日開立失敗次數）。

    註：歐付寶 B2C 沒有「依日期批次查詢發票」的 API（GetIssue 一次只查一張），
    因此今日統計來自本機 events 表；請讓商店系統在每次開立後 POST 事件過來。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    with _db_lock, db() as conn:
        ok = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount), 0) s FROM events WHERE event_type = 'issue_success' AND ts LIKE ?",
            (today + "%",),
        ).fetchone()
        fail = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE event_type = 'issue_failed' AND ts LIKE ?",
            (today + "%",),
        ).fetchone()
    return int(ok["c"]), int(ok["s"]), int(fail["c"])


def create_pending(chat_id: str, actor: str, action: str, args: Dict[str, Any]) -> str:
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    with _db_lock, db() as conn:
        conn.execute("DELETE FROM pending WHERE created_at < ?", (time.time() - CONFIRM_TTL_SECONDS,))
        conn.execute(
            "INSERT INTO pending (code, chat_id, actor, action, args, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (code, chat_id, actor, action, json.dumps(args, ensure_ascii=False), time.time()),
        )
    return code


def take_pending(code: str, chat_id: str, actor: str) -> Optional[Dict[str, Any]]:
    """取出待確認動作；只有「同一個人、同一個聊天室、未逾時」才算數。"""
    with _db_lock, db() as conn:
        row = conn.execute("SELECT * FROM pending WHERE code = ?", (code.upper(),)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM pending WHERE code = ?", (code.upper(),))
    if row["chat_id"] != chat_id or row["actor"] != actor:
        return {"error": "這組驗證碼不是你在這個聊天室建立的｜修復建議：請由原提出者在原聊天室確認，或重新發起指令。"}
    if time.time() - row["created_at"] > CONFIRM_TTL_SECONDS:
        return {"error": f"驗證碼已逾時（超過 {CONFIRM_TTL_SECONDS // 60} 分鐘）｜修復建議：請重新發起指令取得新的驗證碼。"}
    return {"action": row["action"], "args": json.loads(row["args"])}


# --- 歐付寶 client ----------------------------------------------------------

def get_opay_client() -> Optional[OPayEInvoiceClient]:
    """金鑰不齊時回 None，由呼叫端回覆中文提示（機器人仍可正常啟動與推播）。"""
    if not (OPAY_MERCHANT_ID and OPAY_HASH_KEY and OPAY_HASH_IV):
        return None
    try:
        return OPayEInvoiceClient(OPAY_MERCHANT_ID, OPAY_HASH_KEY, OPAY_HASH_IV, OPAY_HOST)
    except ValueError as exc:
        log.error("建立歐付寶 client 失敗：%s", exc)
        return None


MISSING_OPAY_HINT = (
    "尚未設定歐付寶金鑰，無法查詢｜修復建議：在 .env 補上 OPAY_MERCHANT_ID、OPAY_HASH_KEY、OPAY_HASH_IV "
    "（測試環境可用官方公開值），重新啟動機器人。"
)


# --- Telegram API 薄封裝 -----------------------------------------------------

def tg_api(method: str, payload: Dict[str, Any], timeout: int = 35) -> Dict[str, Any]:
    try:
        resp = requests.post(f"{API_BASE}/{method}", json=payload, timeout=timeout)
    except requests.RequestException as exc:
        log.error("呼叫 Telegram %s 失敗：%s", method, exc)
        return {"ok": False, "description": str(exc)}
    try:
        body = resp.json()
    except ValueError:
        return {"ok": False, "description": f"Telegram 回應不是 JSON：{resp.text[:200]}"}
    if not body.get("ok"):
        log.error("Telegram %s 回報錯誤：%s", method, body.get("description"))
    return body


def send_message(chat_id: str, text: str) -> None:
    tg_api("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})


def broadcast(text: str) -> int:
    """推播給所有已綁定的聊天室，回傳成功送出的數量。"""
    chats = bound_chat_ids()
    if not chats:
        log.warning("目前沒有任何已綁定的聊天室，推播內容僅寫入 log：%s", text.replace("\n", " / ")[:120])
    for chat_id in chats:
        send_message(chat_id, text)
    return len(chats)


# --- Notify：事件推播 --------------------------------------------------------

EVENT_TEMPLATES = {
    "issue_success": "✅ 發票開立成功",
    "issue_failed": "❌ 發票開立失敗",
    "invalid": "🗑️ 發票已作廢",
    "allowance": "💸 已開立折讓",
    "word_low": "⚠️ 字軌剩餘數量不足",
}


def format_event(event_type: str, data: Dict[str, Any]) -> str:
    title = EVENT_TEMPLATES.get(event_type, f"ℹ️ 事件：{event_type}")
    lines = [title]
    field_labels = [
        ("invoice_no", "發票號碼"),
        ("relate_number", "特店自訂編號"),
        ("invoice_date", "開立時間"),
        ("amount", "金額"),
        ("reason", "原因"),
        ("allowance_no", "折讓單號"),
        ("track", "字軌"),
        ("remain", "剩餘可用號碼"),
        ("message", "訊息"),
    ]
    for key, label in field_labels:
        if data.get(key) not in (None, ""):
            lines.append(f"{label}：{data[key]}")
    if event_type == "issue_failed":
        lines.append("修復建議：先用 /invoice <發票號碼> 或商店系統的 RelateNumber 確認是否其實已開立，避免重複開立；再對照錯誤代碼修正欄位。")
    if event_type == "word_low":
        lines.append("修復建議：立刻到歐付寶廠商後台或用 AddInvoiceWordSetting 配號，字軌用完會直接開不出發票。")
    if event_type in ("invalid", "allowance"):
        lines.append("提醒：此操作不可復原，已寫入 audit log。")
    return "\n".join(lines)


def notify_event(event_type: str, data: Dict[str, Any]) -> int:
    record_event(event_type, data)
    return broadcast(format_event(event_type, data))


class NotifyHandler(BaseHTTPRequestHandler):
    """商店系統把發票事件 POST 到這裡，機器人負責推播到 Telegram。

    範例：
        curl -X POST http://127.0.0.1:8790/notify \
             -H "X-Notify-Token: <NOTIFY_TOKEN>" -H "Content-Type: application/json" \
             -d '{"event":"issue_success","invoice_no":"AA12345678","amount":1050}'
    """

    server_version = "OPayInvoiceNotify/1.0"

    def _reply(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/notify":
            self._reply(404, {"ok": False, "error": "路徑錯誤｜修復建議：請 POST 到 /notify。"})
            return
        if NOTIFY_TOKEN and self.headers.get("X-Notify-Token", "") != NOTIFY_TOKEN:
            self._reply(401, {"ok": False, "error": "X-Notify-Token 不正確｜修復建議：與 .env 的 NOTIFY_TOKEN 必須一致。"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._reply(400, {"ok": False, "error": "請求內容不是合法 JSON｜修復建議：Content-Type 用 application/json，內容為單層物件。"})
            return
        event_type = str(data.pop("event", "")).strip()
        if event_type not in EVENT_TEMPLATES:
            self._reply(400, {"ok": False, "error": f"未知的 event「{event_type}」｜修復建議：可用值為 {'、'.join(EVENT_TEMPLATES)}。"})
            return
        sent = notify_event(event_type, data)
        self._reply(200, {"ok": True, "sent_to": sent})

    def log_message(self, fmt: str, *args: Any) -> None:  # 交給 logging，避免污染 stdout
        log.debug("notify %s", fmt % args)


def start_notify_server() -> None:
    def _run() -> None:
        try:
            httpd = HTTPServer(("127.0.0.1", NOTIFY_PORT), NotifyHandler)
        except OSError as exc:
            log.error("notify 埠 %s 無法啟動：%s｜修復建議：換一個 NOTIFY_PORT 或先關掉占用該埠的程式。", NOTIFY_PORT, exc)
            return
        log.info("事件接收埠已啟動：http://127.0.0.1:%s/notify", NOTIFY_PORT)
        httpd.serve_forever()

    threading.Thread(target=_run, name="notify-server", daemon=True).start()


# --- Notify：字軌剩餘警示 ----------------------------------------------------

def check_word_remaining(silent_when_ok: bool = True) -> List[Dict[str, Any]]:
    """查字軌剩餘數量，低於門檻就推播警示。回傳每個字軌的剩餘統計。"""
    client = get_opay_client()
    if client is None:
        return []
    year = str(datetime.now().year - 1911)
    try:
        result = client.get_invoice_word_setting(year, 1)
    except OPayEInvoiceError as exc:
        log.error("查詢字軌失敗：%s", exc)
        return []
    infos = result.get("InvoiceInfo") or []
    if isinstance(infos, dict):  # 官方範例曾以物件形式回傳，容錯處理
        infos = [infos]
    stats = []
    for info in infos:
        try:
            start = int(info.get("InvoiceStart") or 0)
            end = int(info.get("InvoiceEnd") or 0)
            used = int(info.get("InvoiceNo") or 0)
        except (TypeError, ValueError):
            continue
        remain = (end - used) if used >= start else (end - start + 1)
        stats.append({
            "track": f"{info.get('InvoiceHeader', '')}{info.get('InvoiceStart', '')}-{info.get('InvoiceEnd', '')}",
            "use_status": info.get("UseStatus"),
            "remain": remain,
        })
        # UseStatus 2 = 使用中，只有使用中的字軌才需要警示
        if remain <= WORD_REMAIN_THRESHOLD and info.get("UseStatus") == 2:
            notify_event("word_low", {
                "track": stats[-1]["track"],
                "remain": remain,
                "message": f"低於警戒值 {WORD_REMAIN_THRESHOLD} 張",
            })
    if not silent_when_ok and stats:
        log.info("字軌剩餘統計：%s", stats)
    return stats


def start_word_watcher() -> None:
    def _run() -> None:
        while True:
            try:
                check_word_remaining()
            except Exception as exc:  # noqa: BLE001 背景執行緒不可因單次錯誤結束
                log.error("字軌檢查發生未預期錯誤：%s", exc)
            time.sleep(max(60, WORD_CHECK_INTERVAL))

    threading.Thread(target=_run, name="word-watcher", daemon=True).start()


# --- Menu：指令處理 ----------------------------------------------------------

HELP_TEXT = """歐付寶電子發票機器人指令：
/bind <ADMIN_TOKEN> — 綁定本聊天室以接收推播
/unbind — 解除綁定
/today — 今日開立張數與金額
/invoice <發票號碼> [開立日期 yyyy-MM-dd] — 查發票明細
/words — 查字軌剩餘數量
/invalid <發票號碼> <開立日期 yyyy-MM-dd> <原因> — 作廢發票（需二次確認，不可復原）
/allowance <發票號碼> <開立日期 yyyy-MM-dd> <折讓金額> <品名> — 開立折讓（需二次確認，不可復原）
/confirm <驗證碼> — 確認上一個危險操作
/cancel <驗證碼> — 取消上一個危險操作
/help — 顯示本說明"""


def require_bound(chat_id: str) -> bool:
    return chat_id in bound_chat_ids()


def handle_bind(chat_id: str, actor: str, args: List[str]) -> str:
    if not args:
        return "用法：/bind <ADMIN_TOKEN>｜修復建議：ADMIN_TOKEN 由系統管理員提供，請勿在公開群組貼出。"
    supplied = args[0]
    # 用固定時間比較，避免以回應時間差猜出 token
    if not hmac.compare_digest(supplied, ADMIN_TOKEN):
        write_audit(actor, chat_id, "bind", "-", "-", "拒絕", "ADMIN_TOKEN 不正確")
        return "ADMIN_TOKEN 不正確，未綁定｜修復建議：向系統管理員索取正確的 ADMIN_TOKEN（就是 .env 裡的那一組）。"
    created = bind_chat(chat_id, actor)
    write_audit(actor, chat_id, "bind", "-", "-", "成功" if created else "已存在")
    if not created:
        return "本聊天室先前已綁定，無需重複綁定。"
    return "✅ 綁定成功，本聊天室之後會收到發票事件推播。\n" + HELP_TEXT


def handle_today() -> str:
    count, amount, failed = today_summary()
    return (
        f"📊 今日（{datetime.now().strftime('%Y-%m-%d')}）開立統計\n"
        f"成功張數：{count} 張\n"
        f"成功金額：{amount:,} 元\n"
        f"失敗次數：{failed} 次\n"
        "資料來源：本機事件庫（歐付寶 B2C 無依日期批次查詢的 API，需商店系統於開立後 POST 事件到 /notify）。"
    )


def handle_invoice(args: List[str]) -> str:
    if not args:
        return "用法：/invoice <發票號碼> [開立日期 yyyy-MM-dd]｜修復建議：發票號碼為 2 碼字軌加 8 碼數字，例如 AA12345678。"
    client = get_opay_client()
    if client is None:
        return MISSING_OPAY_HINT
    invoice_no = args[0]
    invoice_date = args[1] if len(args) > 1 else datetime.now().strftime("%Y-%m-%d")
    try:
        result = client.get_issue(invoice_no=invoice_no, invoice_date=invoice_date)
    except OPayEInvoiceError as exc:
        return f"查詢失敗：{exc}"
    lines = [f"🧾 發票 {invoice_no} 明細"]
    for key, label in [
        ("IIS_Number", "發票號碼"), ("IIS_Create_Date", "開立時間"), ("IIS_Sales_Amount", "銷售金額"),
        ("IIS_Tax_Amount", "稅額"), ("IIS_Identifier", "買受人統編"), ("IIS_Customer_Name", "買受人"),
        ("IIS_Invalid_Status", "作廢狀態"), ("IIS_Upload_Status", "上傳狀態"), ("IIS_Carrier_Num", "載具號碼"),
        ("IIS_Love_Code", "捐贈碼"), ("IIS_Relate_Number", "特店自訂編號"),
    ]:
        if result.get(key) not in (None, ""):
            lines.append(f"{label}：{result[key]}")
    items = result.get("Items") or []
    if isinstance(items, list) and items:
        lines.append("品項：")
        for item in items[:10]:
            lines.append(f"  ・{item.get('ItemName', '')} x{item.get('ItemCount', '')} = {item.get('ItemAmount', '')}")
        if len(items) > 10:
            lines.append(f"  …另有 {len(items) - 10} 筆")
    return "\n".join(lines)


def handle_words() -> str:
    client = get_opay_client()
    if client is None:
        return MISSING_OPAY_HINT
    stats = check_word_remaining(silent_when_ok=False)
    if not stats:
        return "查不到字軌資料｜修復建議：確認今年度字軌已在廠商後台配號，或改用 AddInvoiceWordSetting 設定；也請確認金鑰對應的特店正確。"
    lines = ["🔢 字軌剩餘數量"]
    for stat in stats:
        flag = "⚠️ 不足" if stat["remain"] <= WORD_REMAIN_THRESHOLD else "✅ 充足"
        lines.append(f"{flag}｜{stat['track']}｜剩餘 {stat['remain']} 張｜使用狀態代碼 {stat['use_status']}")
    lines.append(f"警戒值：{WORD_REMAIN_THRESHOLD} 張（可用 .env 的 WORD_REMAIN_THRESHOLD 調整）")
    return "\n".join(lines)


def handle_invalid_request(chat_id: str, actor: str, args: List[str]) -> str:
    if len(args) < 3:
        return ("用法：/invalid <發票號碼> <開立日期 yyyy-MM-dd> <原因>\n"
                "例如：/invalid AA12345678 2026-08-18 客戶重複下單\n"
                "修復建議：原因為必填，會一併送交財政部與寫入 audit log。")
    invoice_no, invoice_date = args[0], args[1]
    reason = " ".join(args[2:])
    code = create_pending(chat_id, actor, "invalid", {"invoice_no": invoice_no, "invoice_date": invoice_date, "reason": reason})
    write_audit(actor, chat_id, "invalid_request", invoice_no, reason, "待確認", f"code={code}")
    return (
        "⚠️ 你正要**作廢**發票，此操作無法復原。\n"
        f"發票號碼：{invoice_no}\n開立日期：{invoice_date}\n作廢原因：{reason}\n\n"
        f"確認請輸入：/confirm {code}\n取消請輸入：/cancel {code}\n"
        f"（驗證碼 {CONFIRM_TTL_SECONDS // 60} 分鐘內有效，且只有你本人在本聊天室可確認）"
    )


def handle_allowance_request(chat_id: str, actor: str, args: List[str]) -> str:
    if len(args) < 4:
        return ("用法：/allowance <發票號碼> <開立日期 yyyy-MM-dd> <折讓金額> <品名>\n"
                "例如：/allowance AA12345678 2026-08-18 100 退回一件商品\n"
                "修復建議：折讓金額為含稅金額的整數，且不可超過原發票金額。")
    invoice_no, invoice_date, amount_text = args[0], args[1], args[2]
    item_name = " ".join(args[3:])
    try:
        amount = int(amount_text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return f"折讓金額「{amount_text}」不是正整數｜修復建議：請填寫大於 0 的整數，例如 100。"
    code = create_pending(chat_id, actor, "allowance", {
        "invoice_no": invoice_no, "invoice_date": invoice_date, "amount": amount, "item_name": item_name,
    })
    write_audit(actor, chat_id, "allowance_request", invoice_no, item_name, "待確認", f"code={code} amount={amount}")
    warn = ""
    if amount >= LARGE_AMOUNT_WARN:
        # 只警示、不阻擋：現場常有大額折讓的正當需求，擋下來會讓客訴無法處理。
        warn = f"\n🔴 大額提醒：折讓金額 {amount:,} 元已達警戒值 {LARGE_AMOUNT_WARN:,} 元，請再次核對後再確認。\n"
    return (
        "⚠️ 你正要開立**折讓**，此操作無法復原。\n"
        f"發票號碼：{invoice_no}\n開立日期：{invoice_date}\n折讓金額：{amount:,} 元\n品名：{item_name}\n"
        f"{warn}\n確認請輸入：/confirm {code}\n取消請輸入：/cancel {code}\n"
        f"（驗證碼 {CONFIRM_TTL_SECONDS // 60} 分鐘內有效，且只有你本人在本聊天室可確認）"
    )


def execute_invalid(actor: str, chat_id: str, args: Dict[str, Any]) -> str:
    client = get_opay_client()
    if client is None:
        return MISSING_OPAY_HINT
    try:
        result = client.invalid(args["invoice_no"], args["invoice_date"], args["reason"])
    except OPayEInvoiceError as exc:
        write_audit(actor, chat_id, "invalid", args["invoice_no"], args["reason"], "失敗", str(exc))
        return f"作廢失敗：{exc}"
    write_audit(actor, chat_id, "invalid", args["invoice_no"], args["reason"], "成功", json.dumps(result, ensure_ascii=False))
    notify_event("invalid", {"invoice_no": args["invoice_no"], "reason": args["reason"]})
    return f"✅ 發票 {args['invoice_no']} 已作廢（不可復原，已記錄稽核）。\n回應：{result.get('RtnMsg', '')}"


def execute_allowance(actor: str, chat_id: str, args: Dict[str, Any]) -> str:
    client = get_opay_client()
    if client is None:
        return MISSING_OPAY_HINT
    items = [{
        "ItemSeq": 1,
        "ItemName": args["item_name"],
        "ItemCount": 1,
        "ItemWord": "式",
        "ItemPrice": args["amount"],
        "ItemAmount": args["amount"],
    }]
    try:
        # AllowanceNotify：S=簡訊、E=Email、A=兩者、N=不通知。此處用 N，通知由本機器人負責。
        result = client.allowance(args["invoice_no"], args["invoice_date"], "N", args["amount"], items)
    except OPayEInvoiceError as exc:
        write_audit(actor, chat_id, "allowance", args["invoice_no"], args["item_name"], "失敗", str(exc))
        return f"折讓失敗：{exc}"
    write_audit(actor, chat_id, "allowance", args["invoice_no"], args["item_name"], "成功", json.dumps(result, ensure_ascii=False))
    notify_event("allowance", {
        "invoice_no": args["invoice_no"],
        "allowance_no": result.get("IA_Allow_No", ""),
        "amount": args["amount"],
    })
    return (f"✅ 發票 {args['invoice_no']} 折讓 {args['amount']:,} 元已開立（不可復原，已記錄稽核）。\n"
            f"折讓單號：{result.get('IA_Allow_No', '（回傳未含單號）')}")


def handle_confirm(chat_id: str, actor: str, args: List[str]) -> str:
    if not args:
        return "用法：/confirm <驗證碼>｜修復建議：驗證碼是發起 /invalid 或 /allowance 時回覆的 6 碼英數字。"
    if get_opay_client() is None:
        # 先檢查再取用，避免驗證碼被消耗掉卻沒真的執行。
        return MISSING_OPAY_HINT
    pending = take_pending(args[0], chat_id, actor)
    if pending is None:
        return "找不到這組驗證碼（可能已使用或已逾時）｜修復建議：請重新發起 /invalid 或 /allowance 取得新的驗證碼。"
    if "error" in pending:
        return pending["error"]
    if pending["action"] == "invalid":
        return execute_invalid(actor, chat_id, pending["args"])
    if pending["action"] == "allowance":
        return execute_allowance(actor, chat_id, pending["args"])
    return f"未知的待確認動作「{pending['action']}」｜修復建議：請重新發起指令。"


def handle_cancel(chat_id: str, actor: str, args: List[str]) -> str:
    if not args:
        return "用法：/cancel <驗證碼>"
    pending = take_pending(args[0], chat_id, actor)
    if pending is None:
        return "找不到這組驗證碼（可能已使用或已逾時），沒有任何操作被執行。"
    if "error" in pending:
        return pending["error"]
    write_audit(actor, chat_id, pending["action"] + "_cancel", str(pending["args"].get("invoice_no", "")), "-", "已取消")
    return "已取消，未對發票做任何變更。"


def dispatch(chat_id: str, actor: str, text: str) -> Optional[str]:
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return None
    command = parts[0].split("@")[0].lower()
    args = parts[1:]

    if command in ("/start", "/help"):
        return HELP_TEXT
    if command == "/bind":
        return handle_bind(chat_id, actor, args)
    if command == "/unbind":
        removed = unbind_chat(chat_id)
        write_audit(actor, chat_id, "unbind", "-", "-", "成功" if removed else "本來就未綁定")
        return "已解除綁定，本聊天室不會再收到推播。" if removed else "本聊天室原本就沒有綁定。"

    if not require_bound(chat_id):
        return "本聊天室尚未綁定｜修復建議：請先執行 /bind <ADMIN_TOKEN>（ADMIN_TOKEN 向系統管理員索取）。"

    if command == "/today":
        return handle_today()
    if command == "/invoice":
        return handle_invoice(args)
    if command == "/words":
        return handle_words()
    if command == "/invalid":
        return handle_invalid_request(chat_id, actor, args)
    if command == "/allowance":
        return handle_allowance_request(chat_id, actor, args)
    if command == "/confirm":
        return handle_confirm(chat_id, actor, args)
    if command == "/cancel":
        return handle_cancel(chat_id, actor, args)
    return f"未知指令 {command}｜修復建議：輸入 /help 查看可用指令。"


# --- 主迴圈（long polling） --------------------------------------------------

def poll_loop() -> None:
    offset = 0
    log.info("開始接收 Telegram 訊息（long polling）")
    while True:
        body = tg_api("getUpdates", {"offset": offset, "timeout": 30})
        if not body.get("ok"):
            desc = str(body.get("description", ""))
            if "401" in desc or "Unauthorized" in desc:
                die("TELEGRAM_BOT_TOKEN 被 Telegram 拒絕（401）｜修復建議：token 可能已被 @BotFather 重置，請重新取得後更新 .env。")
            time.sleep(5)
            continue
        for update in body.get("result", []):
            offset = max(offset, update.get("update_id", 0) + 1)
            message = update.get("message") or update.get("edited_message")
            if not message or "text" not in message:
                continue
            chat_id = str(message["chat"]["id"])
            user = message.get("from", {})
            actor = user.get("username") or str(user.get("id", "unknown"))
            try:
                reply = dispatch(chat_id, actor, message["text"])
            except Exception as exc:  # noqa: BLE001 任何未預期錯誤都要轉成中文訊息，不能讓機器人掛掉
                log.exception("處理指令時發生未預期錯誤")
                reply = f"處理指令時發生未預期錯誤：{exc}｜修復建議：請把這段訊息與時間點提供給維運人員，並查看 {AUDIT_LOG_PATH}。"
            if reply:
                send_message(chat_id, reply)


def main() -> None:
    check_startup()
    init_db()
    me = tg_api("getMe", {}, timeout=15)
    if not me.get("ok"):
        die(
            "無法連線 Telegram Bot API｜修復建議：(1) 確認 TELEGRAM_BOT_TOKEN 正確 (2) 確認主機可連外並允許 api.telegram.org "
            f"(3) 若在企業網路請設定 HTTPS_PROXY。原始訊息：{me.get('description')}"
        )
    log.info("機器人已啟動：@%s", me["result"].get("username"))
    start_notify_server()
    start_word_watcher()
    try:
        poll_loop()
    except KeyboardInterrupt:
        log.info("收到中斷訊號，機器人結束。")


if __name__ == "__main__":
    main()
