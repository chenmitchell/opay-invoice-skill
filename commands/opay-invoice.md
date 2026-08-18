---
description: 啟動完整的歐付寶電子發票整合流程 —— 先問清楚四件事，再決定要走 B2C、B2B 還是離線
---

# /opay-invoice —— 電子發票整合總入口

你現在要協助使用者完成歐付寶（O'Pay）電子發票的介接。**先問，再做。**

## 第一步：先讀規則，不要憑印象

在回答任何技術問題之前，先讀這三份：

1. `SKILL.md` §0 核心規則
2. `guides/00-onboarding.md`（四問導引）
3. `references/api-coverage.json`（69 支 API 的權威清單）

**鐵律提醒（如果你正想寫 `CheckMacValue`，停下來）**：
歐付寶電子發票的加密是 **AES-128-CBC / PKCS7**，順序是
「明文 JSON → URLEncode（.NET 慣例）→ AES 加密 → Base64」。
沒有 `CheckMacValue` 這個欄位，那是綠界 ECPay 的做法，本 Skill 不適用。
規格見 `references/encryption-aes.md`。

## 第二步：問這四個問題（一次問完，不要一題一題擠牙膏）

依 `guides/00-onboarding.md`：

1. **你要開給誰？**
   - 開給一般消費者（個人）→ **B2C**，30 支 API，`/B2CInvoice`
   - 開給公司行號（營業人對營業人，需雙方確認）→ **B2B**，27 支 API，`/B2BInvoice`
   - POS／門市可能斷網，需要先取號再補傳 → **離線電子發票**，12 支 API
2. **你用什麼語言？** Python／Node.js／PHP／其他
   （前三種在 `templates/opay-einvoice-client/` 有現成 client，涵蓋全部 69 支）
3. **你現在在哪一步？** 還沒申請帳號／有測試帳號／已經在測試環境跑通／要上正式環境
4. **你有沒有既有系統要整合？** 電商平台／自建後台／POS／會計系統

## 第三步：依答案給出路徑（不要一次倒完所有文件）

| 情境 | 先讀 | 再讀 | 範本 |
|---|---|---|---|
| B2C 從零開始 | `guides/01-quickstart.md` | `guides/02-preflight-checklist.md` → `03` → `04` | `templates/opay-einvoice-client/` |
| B2B | `guides/12-b2b-overview.md` | `14`（開立）→ `15`（作廢退回）→ `16`（折讓） | 同上，方法名以 `b2b_` 開頭 |
| 離線 | `guides/18-offline-invoice.md` | `references/offline-api-reference.md` | 同上，方法名以 `offline_` 開頭 |
| 上正式環境前 | `guides/02-preflight-checklist.md` | `guides/24-prod-monitoring.md` | `templates/opay-test-console/` |

## 第四步：每一段程式碼都要交代三件事

1. 這支 API 在官方文件的哪一章（例：i100 §7）
2. 必填欄位有哪些、格式限制是什麼
3. 失敗時 `RtnCode` 要怎麼判讀（見 `references/error-handling.md`）

## 你**不可以**做的事

- ❌ 不可以憑記憶編造欄位名稱。不確定就去讀 `references/`。
- ❌ 不可以在程式碼裡寫死金鑰。一律 `os.environ` / `getenv` / `process.env`。
- ❌ 不可以叫使用者「先打正式環境試試看」。開立類 API 一送出就是真發票。
- ❌ 不可以對開立／作廢／折讓做盲目重試。逾時要先用 `GetIssue` 查（`guides/22-idempotency-and-retry.md`）。

## 最後

做完之後，提醒使用者跑 `/opay-doctor` 做串接健檢。
