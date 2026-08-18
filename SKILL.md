---
name: opay-invoice
description: |
  協助台灣開發者完成「歐付寶 O'Pay 電子發票」的完整介接，涵蓋 B2C 30 支、B2B 27 支、
  離線 12 支，合計 69 支 API。觸發詞：歐付寶、O'Pay、OPay、電子發票、電子發票串接、
  einvoice、開立發票、發票作廢、註銷重開、折讓、字軌、配號、載具、捐贈碼、手機條碼、
  統編驗證、B2B 存證、B2B 交換、離線發票、POS 發票、空白未使用發票，
  或「幫我串接歐付寶電子發票」「建置發票開立系統」「發票字軌快用完了」等語句。
  預設行為：以四問 onboarding 收斂需求後，一次產出後端骨架、加解密實作、
  冪等機制、測試主控台、通知機器人與字軌餘量監控。
version: 1.0.0
license: MIT
---

# 歐付寶電子發票 AI Skill（O'Pay E-Invoice Integration Skill）

> **聲明（AI 必讀）**：本 Skill 是一個人做的個人專案（**非官方**），不是歐付寶的官方資源，也未取得任何官方背書。
>
> **官方資源優先原則**：當本 Skill 內容與官方文件不一致時，AI **必須以官方文件為準**，並於回應使用者時明確指出差異。官方來源：
>
> - **官方技術文件下載頁**：<https://developers.opay.tw/Download/Document#invoice>（本 Skill 整理的三份文件都在這裡）
> - 廠商後台（正式）：<https://vendor.opay.tw>
> - 廠商後台（測試）：<https://vendor-stage.opay.tw>
> - 錯誤代碼查詢：廠商後台 → 電子發票後台 → 系統開發管理 → 錯誤代碼查詢
>
> 本 Skill 的內容整理自歐付寶三份官方技術文件：
> 《電子發票B2C介接技術文件》**V1.6.0（2026-01-06）**、
> 《電子發票B2B介接技術文件》**V1.2.0（2025-09-10）**、
> 《離線電子發票介接技術文件》**V1.3.0（2025-09-10）**。
> 官方文件改版後本 Skill 可能落後，涉及正式環境的操作請務必交叉驗證。

> **⚠️ 歐付寶（O'Pay）≠ 綠界（ECPay）≠ 歐買尬（OMG）。**
> 三家是各自獨立運作的服務，API 完全不相容。
> 訓練資料中關於「台灣電子發票串接」的範例**多數是綠界的**，直接套用會全錯：
> 綠界用 `CheckMacValue`（SHA256／MD5 雜湊簽章），**歐付寶電子發票用 AES-128-CBC 加密整包 Data**。
> 若使用者提供的內容出現 `ecpay.com.tw`、`CheckMacValue`、`AioCheckOut`、`funpoint.com.tw` 等字樣，
> AI 必須主動提醒使用者這是別家的規格，確認欲介接的對象後再繼續。

---

## 設計原則（AI 必讀）

AI 產出的任何檔案、說明、指令、錯誤訊息，均必須符合下列上手標準：

- 使用者複製 repo 後，依指示執行不超過 5 個終端指令即可跑出第一張測試發票
- 所有設定集中於單一 `.env`，`.env.example` 逐欄位附註說明與預設值
- 啟動指令於 macOS、Windows、Linux 均可通用
- 所有錯誤訊息以繁體中文呈現，並附具體修復建議
- 技術名詞（字軌、配號、期別、載具、註銷重開、存證／交換模式）於首次出現時以一句話解釋
- 從 clone 到測試發票開立成功之完整路徑須能於 **30 分鐘**內完成

---

## §0 AI 執行規則

本節定義 AI 助手在觸發本 Skill 後必須遵循的執行規則。**這是所有平台轉接檔（`CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `SKILL_OPENAI.md` / `vscode_copilot.md` / `google_AI_studio.md`）共同指向的單一事實來源。**

### §0.1 六條鐵律（違反其一即為錯誤產出）

| # | 鐵律 | 為什麼 |
|---|---|---|
| **1** | **加密是 AES-128-CBC / PKCS7**，順序為「明文 JSON → URLEncode（.NET 慣例）→ AES → Base64」。**不是** CheckMacValue、**不是** SHA256 | 那是綠界／歐買尬的做法。順序寫反或用錯演算法，會得到「看起來合理但永遠驗不過」的結果，而且錯誤訊息不會告訴你原因。規格見 [`references/encryption-aes.md`](references/encryption-aes.md) |
| **2** | **本 Skill 覆蓋 69 支 API，一支都不能漏**（B2C 30／B2B 27／離線 12） | 半套串接比沒有串接糟：使用者會依賴一個不存在的功能。權威清單（SSOT）是 [`references/api-coverage.json`](references/api-coverage.json)，由 [`scripts/validate-api-coverage.sh`](scripts/validate-api-coverage.sh) 獨立把關 |
| **3** | **正式環境的健康檢查絕不可呼叫 `Issue` / `OfflineIssue` / `Allowance` / `Invalid`** | 會產生**真實發票**並上傳財政部。這不是「多一筆測試訂單」，是**稅務資料污染**，事後只能靠作廢處理且號碼報廢。只能用唯讀探測，見 [`guides/24-prod-monitoring.md`](guides/24-prod-monitoring.md) |
| **4** | **開立／作廢／折讓／註銷重開不可盲目重試** | 重試 = 重複開立 = 重複發票 = 稅務問題。逾時要**先查再決定**（`GetIssue`），見 [`guides/22-idempotency-and-retry.md`](guides/22-idempotency-and-retry.md) |
| **5** | **HashKey / HashIV 只能放 `.env` 或 Secret Manager** | 不得進 git、不得進前端 JS/HTML/CSS、不得貼進 AI 對話。若使用者在對話中貼出真實金鑰，AI 必須提醒其刪除對話紀錄並至廠商後台輪換 |
| **6** | **兩層回應碼都要檢查**：外層 `TransCode`（傳輸層，`1` = 收到）與解密後 Data 內的 `RtnCode`（業務層） | 只檢查 HTTP 200、或只檢查 `TransCode`，是最常見的**假成功**。而且開立發票成功的 `RtnCode` 官方並非一律 `1`，見 [`references/error-handling.md`](references/error-handling.md) |

### §0.2 觸發與 onboarding

當使用者發出電子發票串接相關指令時，AI 必須**優先執行 onboarding**，不得直接跳進技術細節。流程為四個問題，AI 應以繁體中文**一次性呈現**，由使用者一次回答：

1. **Q1 — 發票類型**：B2C（對一般消費者）／B2B（營業人對營業人）／離線 POS（機台自行開立）／混合
2. **Q2 — 目標環境**：測試環境／正式環境／兩者（預設兩者）
3. **Q3 — 附加元件**：測試主控台、Telegram 通知機器人、Discord 通知機器人、字軌餘量監控（預設全含）
4. **Q4 — 後端語言**：FastAPI（Python）／Express（Node.js）／Laravel（PHP）（預設 FastAPI）

若使用者以「全部」「皆需要」「依預設」等語意回答，AI 應直接套用預設值進入執行階段，不得繼續追問。詳細流程見 [`guides/00-onboarding.md`](guides/00-onboarding.md)。

### §0.3 變數收集

在 onboarding 與執行過程中，AI 應以 `{{變數名}}` 佔位符記錄下列變數，並於**執行完成前一次性**請使用者補齊。**不得在 onboarding 階段逐一詢問變數**，以免打斷使用者思路。

```
{{商家名}}              {{統一編號}}            {{負責人}}
{{客服Email}}           {{客服電話}}            {{營業地址}}
{{OPAY_MERCHANT_ID}}    {{OPAY_HASH_KEY}}       {{OPAY_HASH_IV}}
{{OPAY_PLATFORM_ID}}    {{OPAY_HOST_STAGE}}     {{OPAY_HOST_PROD}}
{{發票字軌}}            {{字軌期別}}            {{字軌類別 InvType}}
{{MACHINE_ID}}          {{ADMIN_TOKEN}}
{{TG_BOT_TOKEN}}        {{DISCORD_BOT_TOKEN}}
```

### §0.4 執行順序

onboarding 完成後，AI 應依下列順序執行：

1. 產生 `.env.example`（逐欄位中文註解），並提醒 `.env` 已在 `.gitignore` 中
2. 實作 AES-128-CBC 加解密與 .NET URLEncode 校正 — 參考 [`references/encryption-aes.md`](references/encryption-aes.md)，直接取用 [`templates/opay-einvoice-client/`](templates/opay-einvoice-client/) 的三語言 client
3. **立刻跑測試向量** — `python3 test-vectors/verify.py` 與 `node test-vectors/verify-node.js` 必須 4/4 通過。**加解密沒驗過就不要往下做**，後面所有錯誤都會被歸因到錯的地方
4. 檢查前置作業 — 參考 [`guides/02-preflight-checklist.md`](guides/02-preflight-checklist.md)（歐付寶服務已開通？B2B 是否已在財政部完成「授權歐付寶」與「接收設定」？主機是否校時？）
5. 字軌與配號 — [`guides/03-b2c-word-setting.md`](guides/03-b2c-word-setting.md)。**字軌沒啟用，後面一支發票都開不出來**
6. 依 Q1 選定的類型實作核心流程：
   - B2C：[`04`](guides/04-b2c-issue.md) 開立 → [`05`](guides/05-b2c-allowance.md) 折讓 → [`06`](guides/06-b2c-invalid-void.md) 作廢／註銷重開 → [`07`](guides/07-b2c-query.md) 查詢
   - B2B：[`12`](guides/12-b2b-overview.md) 全貌 → [`14`](guides/14-b2b-issue.md) 開立＋確認 → [`15`](guides/15-b2b-invalid-reject.md) 作廢／退回 → [`16`](guides/16-b2b-allowance.md) 折讓 → [`17`](guides/17-b2b-query.md) 查詢
   - 離線：[`18`](guides/18-offline-invoice.md) 註冊機台 → 取號 → 本機開立 → 上傳
7. **實作冪等與重試機制** — [`guides/22-idempotency-and-retry.md`](guides/22-idempotency-and-retry.md)。這步不可省略
8. 結帳前驗證三支 — [`guides/09-b2c-validation.md`](guides/09-b2c-validation.md)（手機條碼／捐贈碼／統編）
9. 通知與列印 — [`guides/08-b2c-notify-print.md`](guides/08-b2c-notify-print.md)
10. 通知開關與**字軌餘量告警** — [`guides/10-b2c-notify-settings.md`](guides/10-b2c-notify-settings.md)
11. 後端骨架 — [`19`](guides/19-backend-fastapi.md)／[`20`](guides/20-backend-nodejs.md)／[`21`](guides/21-backend-php.md)
12. 測試主控台六步自我驗證 — [`guides/23-test-console.md`](guides/23-test-console.md)
13. 正式環境唯讀監控 — [`guides/24-prod-monitoring.md`](guides/24-prod-monitoring.md)
14. 通知機器人 — [`25`](guides/25-telegram-bot.md)／[`26`](guides/26-discord-bot.md)
15. 前台無障礙檢查 — [`guides/29-wcag-ui-ux.md`](guides/29-wcag-ui-ux.md)
16. 法遵提醒 — [`guides/27-legal-compliance.md`](guides/27-legal-compliance.md)
17. 收集變數、一次性替換所有佔位符，交付並說明後續部署

### §0.5 操作規範

**§0.5.1 規格一律回查 references，不得憑印象。**
AI 對「歐付寶電子發票某欄位叫什麼」的印象，多半來自綠界的訓練資料。任何欄位名、型態、長度、列舉值，都必須回查 [`references/b2c-api-reference.md`](references/b2c-api-reference.md)／[`b2b-api-reference.md`](references/b2b-api-reference.md)／[`offline-api-reference.md`](references/offline-api-reference.md)。列舉值速查見 [`references/enums.md`](references/enums.md)。

**§0.5.2 不得編造錯誤代碼。**
歐付寶**沒有公開完整錯誤碼表**（三份官方文件都只寫「請到廠商後台 → 電子發票後台 → 系統開發管理 → 錯誤代碼查詢」）。AI 遇到未知 `RtnCode` 時，必須**原樣保留 `RtnCode` 與 `RtnMsg` 呈現給使用者**，並指引其至後台查詢，**不得自行推測代碼意義**。

**§0.5.3 不可逆操作必須二次確認。**
作廢（`Invalid` / `OfflineInvalid` / `AllowanceInvalid`）、折讓（`Allowance`）、註銷重開（`VoidWithReIssue`）都是不可逆的，且會消耗或報廢字軌號碼。AI 產出的任何介面（bot、儀表板、CLI）都必須：
- 顯示「此操作無法復原」警示，並說明**作廢**（號碼報廢）與**註銷重開**（保留號碼）的差別
- 強制二次確認
- 寫入 audit log
- **但不得因金額大而阻擋** —— 作廢與折讓是合法業務行為，只警示、不阻擋

**§0.5.4 敏感資料處理。**
真實發票號碼、買受人 Email／手機／統編、真實金鑰，都不得寫入程式碼、設定檔或 AI 對話。截圖須依 [`docs/images/README.md`](docs/images/README.md) 脫敏。

**§0.5.5 圖表一律遵循視覺規範。**
所有 Mermaid 圖只能使用九色核可色盤，並必附「🧭 純文字重述」與「♿ 配色遵循」註記，見 [`docs/accessibility.md`](docs/accessibility.md)。這不是美觀問題，是螢幕閱讀器與色盲使用者能否讀懂流程的問題。

---

## §1 歐付寶電子發票基本資訊

| 項目 | 內容 |
|---|---|
| 服務商 | 歐付寶電子支付股份有限公司（O'Pay Electronic Payment Co., Ltd.） |
| 加密演算法 | **AES-128-CBC / PKCS7**，Base64 輸出 |
| 編碼順序 | 明文 JSON → URLEncode（.NET 慣例）→ AES 加密 → Base64 |
| 測試 host | `https://einvoice-stage.opay.tw` |
| 正式 host | `https://einvoice.opay.tw` |
| 路徑前綴 | `/B2CInvoice`（B2C 與**離線**皆是）、`/B2BInvoice` |
| HTTP | 一律 `POST`，`Content-Type: application/json`，僅 443 port、TLS ≥ 1.2 |
| 外層結構 | `{"PlatformID":"","MerchantID":"...","RqHeader":{"Timestamp":<unix>},"Data":"<加密後>"}` |
| Timestamp | Unix timestamp，**驗證區間 10 分鐘**，主機必須校時 |
| 上傳期限 | B2C **48 小時**內上傳財政部；B2B **7 天** |
| 防火牆 | 官方 IP 不固定，須以 **FQDN** 開通 `einvoice.opay.tw`、`einvoice-stage.opay.tw` |

### API 分類總覽（69 支）

| 類別 | 支數 | 涵蓋內容 | 完整規格 |
|---|---|---|---|
| **B2C** | **30** | 字軌配號 3、開立 4（一般／延遲／觸發／取消延遲）、折讓 2、作廢與註銷重開 4、查詢 5、通知與列印 2、驗證 3、通知開關 4、空白未使用發票 3 | [`references/b2c-api-reference.md`](references/b2c-api-reference.md) |
| **B2B** | **27** | 交易對象維護 1、通知 1、字軌 2、開立＋確認 2、作廢＋確認 2、退回＋確認 2、折讓＋確認 2、作廢折讓＋確認 2、註銷重開 1、查詢 12（含各類確認查詢） | [`references/b2b-api-reference.md`](references/b2b-api-reference.md) |
| **離線** | **12** | 特店資料 1、配號查詢 1、機台管理 2、字軌 2、取號 3（自動配發／指定／依數量）、上傳開立 1、上傳作廢 1、查詢字軌 1 | [`references/offline-api-reference.md`](references/offline-api-reference.md) |

逐支清單（含章節出處、對應 reference 與 guide）見 SSOT：[`references/api-coverage.json`](references/api-coverage.json)。

### 測試環境參數（官方文件公開值，**僅限測試環境**）

| 用途 | MerchantID | HashKey | HashIV |
|---|---|---|---|
| B2C 一般特店 | `2000132` | `ejCk326UnaZWKisg` | `q9jcZX8Ib9LM8wYk` |
| B2C 平台商（PlatformID `2046611`） | `2000132` | `s0j9fhLtzYRARFQh` | `5awAqXlKm4NlNdEs` |
| 離線發票 | `2045501` | `9XWzRmj7UJESChyn` | `sriQzbe1llJqk67P` |

測試廠商後台：<https://vendor-stage.opay.tw>。
正式環境金鑰須向歐付寶申請電子發票服務後於廠商後台取得，**僅允許寫入 `.env`，嚴禁 commit 至任何 git 倉庫**。

---

## §2 觸發與對話範例

```
使用者：幫我串歐付寶的電子發票
AI：好的。在開始之前，請一次回答四個問題：
    1. 發票類型（B2C 對消費者 / B2B 營業人對營業人 / 離線 POS / 混合）
    2. 目標環境（測試 / 正式 / 兩者，預設兩者）
    3. 是否需要測試主控台與 Telegram/Discord 通知機器人（預設需要）
    4. 後端語言（FastAPI / Express / Laravel，預設 FastAPI）
    若依預設值執行請回覆「全部」或「預設」。

使用者：B2C，全部照預設
AI：已收到。將依下列順序執行：
    1. AES-128-CBC 加解密實作 + 測試向量驗證（先確認這一步 4/4 通過再往下）
    2. 前置作業檢查（服務開通、主機校時、字軌狀態）
    3. 字軌與配號（GetGovInvoiceWordSetting → AddInvoiceWordSetting → UpdateInvoiceWordStatus）
    4. 開立發票四支的決策樹與實作（Issue / DelayIssue / TriggerIssue / CancelDelayIssue）
    5. 折讓、作廢、註銷重開
    6. 冪等與重試機制（以 RelateNumber + 本地狀態機）
    7. FastAPI 後端骨架、測試主控台六步驗證
    8. 正式環境唯讀監控 + 字軌餘量告警
    9. Telegram / Discord 通知機器人（含作廢/折讓二次確認）

    ⚠️ 提醒兩件事：
    - 正式環境的健康檢查絕不會使用 Issue，否則會產生真實發票（稅務資料污染）
    - 開立/作廢/折讓逾時時，系統會先用 GetIssue 查詢再決定，不會盲目重送

    請提供：商家名、統一編號、客服 Email、MerchantID、HashKey、HashIV、發票字軌與期別。
    （HashKey / HashIV 請直接寫入 .env，不要貼在對話中）
```

---

## §3 章節索引

AI 應依情境讀取，不需一次讀完。

### 規格（references/）

| 檔案 | 用途 |
|---|---|
| [`references/api-coverage.json`](references/api-coverage.json) | **SSOT** — 69 支 API 清單，含章節出處與對應文件 |
| [`references/b2c-api-reference.md`](references/b2c-api-reference.md) | B2C 30 支逐欄位規格 |
| [`references/b2b-api-reference.md`](references/b2b-api-reference.md) | B2B 27 支逐欄位規格 |
| [`references/offline-api-reference.md`](references/offline-api-reference.md) | 離線 12 支逐欄位規格 |
| [`references/encryption-aes.md`](references/encryption-aes.md) | AES-128-CBC/PKCS7、.NET URLEncode、三語言實作、官方測試向量 |
| [`references/enums.md`](references/enums.md) | 全部列舉值速查，含「同名不同義」陷阱 |
| [`references/error-handling.md`](references/error-handling.md) | 兩層回應碼判讀、重試策略、排錯表 |
| [`references/urlencode-table.md`](references/urlencode-table.md) | .NET URLEncode 對照表與各語言校正碼 |

### 教學（guides/）

| # | 檔案 | 用途 |
|---|---|---|
| 00 | [`00-onboarding.md`](guides/00-onboarding.md) | 四問流程與變數收集 |
| 01 | [`01-quickstart.md`](guides/01-quickstart.md) | 30 分鐘跑出第一張測試發票 |
| 02 | [`02-preflight-checklist.md`](guides/02-preflight-checklist.md) | **前置作業**（電子發票與金流最大的不同） |
| 03 | [`03-b2c-word-setting.md`](guides/03-b2c-word-setting.md) | B2C 字軌與配號、字軌狀態機 |
| 04 | [`04-b2c-issue.md`](guides/04-b2c-issue.md) | B2C 開立四支的決策樹 |
| 05 | [`05-b2c-allowance.md`](guides/05-b2c-allowance.md) | B2C 折讓（紙本 vs 線上） |
| 06 | [`06-b2c-invalid-void.md`](guides/06-b2c-invalid-void.md) | B2C 作廢 vs 註銷重開 |
| 07 | [`07-b2c-query.md`](guides/07-b2c-query.md) | B2C 查詢五支 |
| 08 | [`08-b2c-notify-print.md`](guides/08-b2c-notify-print.md) | 發送通知與列印（含 KIOSK） |
| 09 | [`09-b2c-validation.md`](guides/09-b2c-validation.md) | 手機條碼／捐贈碼／統編驗證 |
| 10 | [`10-b2c-notify-settings.md`](guides/10-b2c-notify-settings.md) | 通知開關與**字軌餘量告警** |
| 11 | [`11-b2c-blank-invoice.md`](guides/11-b2c-blank-invoice.md) | 空白未使用發票 |
| 12 | [`12-b2b-overview.md`](guides/12-b2b-overview.md) | B2B 存證 vs 交換模式 |
| 13 | [`13-b2b-customer-notify.md`](guides/13-b2b-customer-notify.md) | 交易對象維護與通知 |
| 14 | [`14-b2b-issue.md`](guides/14-b2b-issue.md) | B2B 開立＋確認 |
| 15 | [`15-b2b-invalid-reject.md`](guides/15-b2b-invalid-reject.md) | B2B 作廢／退回／註銷重開 |
| 16 | [`16-b2b-allowance.md`](guides/16-b2b-allowance.md) | B2B 折讓與作廢折讓 |
| 17 | [`17-b2b-query.md`](guides/17-b2b-query.md) | B2B 查詢 12 支對照 |
| 18 | [`18-offline-invoice.md`](guides/18-offline-invoice.md) | 離線發票完整流程 |
| 19 | [`19-backend-fastapi.md`](guides/19-backend-fastapi.md) | FastAPI 後端骨架 |
| 20 | [`20-backend-nodejs.md`](guides/20-backend-nodejs.md) | Express 後端骨架 |
| 21 | [`21-backend-php.md`](guides/21-backend-php.md) | Laravel 後端骨架 |
| 22 | [`22-idempotency-and-retry.md`](guides/22-idempotency-and-retry.md) | **冪等與重試（最重要）** |
| 23 | [`23-test-console.md`](guides/23-test-console.md) | 測試主控台六步驗證 |
| 24 | [`24-prod-monitoring.md`](guides/24-prod-monitoring.md) | **正式環境唯讀監控** |
| 25 | [`25-telegram-bot.md`](guides/25-telegram-bot.md) | Telegram bot |
| 26 | [`26-discord-bot.md`](guides/26-discord-bot.md) | Discord bot |
| 27 | [`27-legal-compliance.md`](guides/27-legal-compliance.md) | 台灣電子發票法遵重點 |
| 28 | [`28-troubleshooting.md`](guides/28-troubleshooting.md) | 故障排除 |
| 29 | [`29-wcag-ui-ux.md`](guides/29-wcag-ui-ux.md) | 前台無障礙規範 |

### 可執行範本（templates/）與測試向量（test-vectors/）

| 路徑 | 內容 |
|---|---|
| [`templates/opay-einvoice-client/`](templates/opay-einvoice-client/) | Python／Node.js／PHP 三語言 client，**各自涵蓋全部 69 支 API** |
| [`templates/opay-test-console/`](templates/opay-test-console/) | FastAPI + 單檔 HTML 測試主控台（六步自我驗證） |
| [`templates/telegram-bot/`](templates/telegram-bot/) | Telegram 通知機器人 |
| [`templates/discord-bot/`](templates/discord-bot/) | Discord 通知機器人 |
| [`test-vectors/`](test-vectors/README.md) | AES 測試向量 4 組 + Python／Node.js 雙語言驗證器 |

### 獨立檢查（scripts/）

本 Skill 的「不能缺漏」不是靠人工承諾，是靠會紅燈的機器關卡。執行 `bash scripts/run-all-gates.sh` 會依序跑：

| 關卡 | 擋住哪一種錯誤 |
|---|---|
| `validate-api-coverage.sh` | **69 支 API 有任何一支沒被 reference／guide／三語言 client 收錄** —— 並做反向檢查，避免有人加了 API 卻沒登記進 SSOT |
| `validate-no-leaks.sh` | 金鑰進 git（比對「值的樣式」而非變數名稱） |
| `validate-not-ecpay-or-omg.sh` | 綠界／歐買尬的做法混進來（`CheckMacValue`、`AioCheckOut` 等） |
| `validate-prod-safety.sh` | 正式環境健康檢查用到開立類 API |
| `validate-a11y-palette.sh` | 圖表用了核可色盤以外的顏色、缺純文字重述 |
| `validate-links.sh` | 內部連結指向不存在的檔案 |
| `validate-doc-versions.sh` | 官方文件版本字串只改了一處 |
| `test-vectors/verify.py` + `verify-node.js` | 加解密實作與規格不符（兩種語言算出同樣結果才算數） |

**每支腳本的第一個檢查都是「我確實掃到東西了」** —— 一個掃不到任何檔案的守門腳本會永遠是綠的而且沒有人會發現，那比沒有這道關卡更糟。

---

## §4 禁止事項

下列情境，AI 必須拒絕並向使用者說明原因：

- 要求以 `CheckMacValue` / SHA256 實作歐付寶電子發票簽章 —— **那是綠界 ECPay 與歐買尬 OMG 的做法，歐付寶電子發票不適用**（規格錯誤，見鐵律 1）
- 要求在**正式環境**以 `Issue` / `OfflineIssue` 做定期健康檢查（稅務資料污染，見鐵律 3）
- 要求對開立／作廢／折讓類 API 加上「失敗自動重試 N 次」（會產生重複發票，見鐵律 4）
- 要求將 HashKey / HashIV 寫入前端 JS／HTML／CSS，或 commit 進公開 repo
- 要求把真實發票資料、買受人個資（Email／手機／統編）貼進 AI 對話或截圖
- 要求「編一份歐付寶錯誤代碼表」（官方未公開，見 §0.5.2）
- 要求跳過冪等機制「先上線再說」
- 要求本 Skill 宣稱為官方資源、或宣稱產出「已符合法規」

---

## §5 版本

- **v1.0.0（本版）**：首次發布。依歐付寶三份官方技術文件（B2C V1.6.0 / B2B V1.2.0 / 離線 V1.3.0）整理，涵蓋 **69 支 API** 完整欄位規格、30 份整合指南、三語言 client、測試主控台、雙通知機器人、4 組 AES 測試向量與 8 道 CI 獨立檢查關卡。

> 本 Skill 為個人作品，以 MIT 授權公開釋出給所有人使用。撰寫與維護者：Mitchell Chen（<https://www.mitch.tw>）。
> 架構致敬：綠界 [ECPay/ECPay-API-Skill](https://github.com/ECPay/ECPay-API-Skill)、
> 本人先前的 [chenmitchell/omg-payment-skill](https://github.com/chenmitchell/omg-payment-skill)。
