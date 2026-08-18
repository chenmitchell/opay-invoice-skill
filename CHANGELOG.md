# CHANGELOG

本檔記錄本專案的所有重要變更。

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本編號遵循 [語意化版本](https://semver.org/lang/zh-TW/)。

> **本專案的版本語意**
> - **MAJOR**：檔案結構或載入方式的破壞性變更（例如 `SKILL.md` 章節重編）
> - **MINOR**：新增 API 覆蓋、新增指南、新增模板語言、新增 AI 平台支援
> - **PATCH**：規格修正、錯字、連結修復、無障礙調整
>
> 官方技術文件的版本（i100 V1.6.0 等）**與本專案版本無關**，另以「對應官方文件版本」段落標示。

---

## [未發布 Unreleased]

規劃中的項目請見 [`ROADMAP.md`](ROADMAP.md)。

---

## [1.0.0] — 2026-08

**首個公開版本。**

### 新增 Added

#### 規格文件（`references/`）
- `api-coverage.json` — SSOT，收錄歐付寶電子發票**全部 69 支 API**（B2C 30／B2B 27／離線 12），含來源文件、章節、對應 reference 與 guide
- `b2c-api-reference.md` — B2C 30 支 API 完整規格（約 4,950 行），含共通事項、錯誤代碼、URLEncode 轉換表、加密說明三個附錄
- `b2b-api-reference.md` — B2B 27 支 API 完整規格（約 4,490 行），含「B2B 與 B2C 的根本差異」與交換模式成對規則
- `offline-api-reference.md` — 離線 12 支 API 完整規格（約 2,130 行），含離線流程說明與交易狀態代碼表
- `encryption-aes.md` — AES-128-CBC/PKCS7 加解密規格，明訂「明文 JSON → URLEncode → AES → Base64」順序鐵律
- `enums.md` — 57 個列舉值整理，含「同名不同義的陷阱」專章
- `error-handling.md` — 兩層回應碼（`TransCode` / `RtnCode`）、排錯表、重試策略
- `urlencode-table.md` — .NET 慣例 URLEncode 完整轉換表（34 列）與三語言校正實作

#### 測試向量（`test-vectors/`）
- `aes-encryption.json` — SSOT，4 組加密測試向量（1 組官方 ＋ 3 組衍生）
- `verify.py` — Python 驗證器（`pycryptodome`）
- `verify-node.js` — Node.js 驗證器（零相依，僅用內建 `crypto`）
- 兩支驗證器輸出格式刻意一致，皆可直接掛進 CI

#### 程式碼模板（`templates/`）
- `opay-einvoice-client/python/` — Python 3.8+ client，涵蓋全部 69 支 API
- `opay-einvoice-client/nodejs/` — Node.js 18+ client，零外部相依
- `opay-einvoice-client/php/` — PHP 7.4+ client，僅用內建 `openssl` 與 cURL
- `opay-test-console/` — FastAPI ＋ 單檔 HTML 測試主控台，六步自我驗證，第一關完全離線
- `telegram-bot/` — 發票事件推播、字軌餘量告警、值班查詢與二次確認
- `discord-bot/` — 同上，Discord 版

#### 整合指南（`guides/`）
- 30 份繁體中文指南（`00-onboarding` ～ `29-wcag-ui-ux`），涵蓋 onboarding、B2C、B2B、離線、三語言後端整合、冪等性、測試、監控、bot、法遵注意事項、排錯與無障礙 UI

#### AI 平台轉接檔
- `CLAUDE.md` — Claude Code / Cowork
- `AGENTS.md` — OpenAI Codex / Agents SDK
- `GEMINI.md` — Google Gemini
- `SKILL_OPENAI.md` — ChatGPT GPTs
- `vscode_copilot.md` — GitHub Copilot（VS Code）
- `google_AI_studio.md` — Google AI Studio
- 六份皆包含相同的**四條不可違反的鐵律**

#### 門面文件
- `README.md` — 完整專案說明，含 8 張 Mermaid 圖與 69 支 API 覆蓋總表
- `SETUP.md` — 七個 AI 平台的實際安裝步驟與載入驗證題
- `GLOSSARY.md` — 電子發票術語表，每條含「白話解釋」與「什麼時候會遇到」
- `MANIFESTO.md` — 專案定位與 g0v 精神
- `SECURITY.md` — 金鑰處理、AI 對話脫敏、外洩處置、漏洞回報
- `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`CHANGELOG.md`、`ROADMAP.md`、`LICENSE`、`CITATION.cff`
- `docs/accessibility.md` — 全 repo 的視覺與無障礙規範（九色核可色盤與實測對比值）
- `docs/prompt-examples.md` — 自然語言指令範例
- `docs/images/README.md` — 截圖規範與脫敏規則

### 品質保證 Quality
- 69 支 API 以 `api-coverage.json` 為 SSOT，逐支比對，無遺漏
- 加密規格經 Python / Node.js / PHP 三種實作交叉驗證官方向量，`4/4 pass`
- 所有 Mermaid 圖遵循 `docs/accessibility.md`：九色核可色盤、WCAG AAA 對比 ≥7:1、16px 字體、直角連線、圖示＋文字雙編碼、每張圖附純文字重述
- 全文繁體中文（台灣用語）

### 對應官方文件版本
| 文件 | 版本 | 日期 |
|---|---|---|
| 《電子發票B2C介接技術文件》 | V1.6.0 | 2026-01-06 |
| 《電子發票B2B介接技術文件》 | V1.2.0 | 2025-09-10 |
| 《離線電子發票介接技術文件》 | V1.3.0 | 2025-09-10 |

### 已知限制 Known Limitations
- 官方**未公開完整錯誤碼表**，`references/error-handling.md` 以「症狀 → 可能原因 → 檢查什麼」的排錯表補足，非窮舉
- 部分官方文件本身存在章節引用不一致之處，已於對應段落標註提醒，介接前請向歐付寶確認
- 內容由 AI 協助自官方技術文件轉寫並經多輪獨立稽核，仍可能存在轉寫誤差；**若與官方文件不一致，以官方文件為準**

### 安全 Security
- 本 repo 不含任何正式環境金鑰
- 文件中出現的金鑰皆為官方技術文件公開列出的測試環境值，且逐處標註「僅測試環境」
- 測試主控台的「開立測試發票」預設關閉，需同時設定環境變數與前端確認才會送出

---

[未發布 Unreleased]: https://github.com/chenmitchell/opay-invoice-skill/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/chenmitchell/opay-invoice-skill/releases/tag/v1.0.0
