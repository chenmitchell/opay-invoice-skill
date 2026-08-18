# SETUP.md — 各 AI 平台安裝步驟

> 本 Skill 是**非官方的個人專案**，與歐付寶電子支付股份有限公司無任何從屬或合作關係。若內容與官方文件不一致，以官方文件為準。

把 `opay-invoice-skill` 載入你慣用的 AI 助手，讓它回答歐付寶電子發票問題時**先查規格、再產程式碼**。

---

## 0. 共同的第一步：取得 repo

```bash
git clone https://github.com/chenmitchell/opay-invoice-skill.git
cd opay-invoice-skill

# 選擇性：先驗證加密實作（不需網路）
python3 test-vectors/verify.py     # 期望輸出：4/4 pass
node    test-vectors/verify-node.js
```

不想用 git 的話，在 GitHub 頁面按 **Code → Download ZIP** 也可以。

---

## 1. Claude Code / Claude Cowork

**載入檔**：[`CLAUDE.md`](CLAUDE.md)

Claude Code 會自動讀取工作目錄（與其上層目錄）中的 `CLAUDE.md`。

### 方式 A：整包放進專案（建議）

```bash
# 在你的專案根目錄
git clone https://github.com/chenmitchell/opay-invoice-skill.git .ai/opay-invoice-skill
```

然後在你專案自己的 `CLAUDE.md` 加一段：

```markdown
## 歐付寶電子發票

本專案的電子發票整合遵循 `.ai/opay-invoice-skill/`。
處理任何發票相關需求前，請先讀：
1. `.ai/opay-invoice-skill/SKILL.md` §0（四條鐵律）
2. `.ai/opay-invoice-skill/references/api-coverage.json`（69 支 API 索引）
3. 對應的 `references/*.md` 規格與 `guides/*.md` 指南
```

### 方式 B：直接在 repo 內工作

```bash
cd opay-invoice-skill
claude
```

Claude 會自動讀到根目錄的 `CLAUDE.md`。

### 方式 C：作為 Claude Skill 安裝

若你的 Claude 環境支援 skill 目錄（例如 `~/.claude/skills/`）：

```bash
git clone https://github.com/chenmitchell/opay-invoice-skill.git \
  ~/.claude/skills/opay-invoice-skill
```

### 驗證是否載入成功

問 Claude：

> 歐付寶電子發票的加密方式是什麼？請引用本專案的檔案路徑。

正確回答應包含「AES-128-CBC/PKCS7」並引用 `references/encryption-aes.md`。
若它回答「CheckMacValue」或「SHA256」，代表**沒讀到 Skill**（那是綠界的做法）。

---

## 2. Cursor

**載入檔**：`.cursor/rules/opay-invoice.mdc`

Cursor 使用 `.cursor/rules/` 目錄下的 `.mdc` 檔作為專案規則。

```bash
mkdir -p .cursor/rules
```

建立 `.cursor/rules/opay-invoice.mdc`，內容如下（front matter 是 Cursor 的規則設定）：

```markdown
---
description: 歐付寶電子發票 API 整合規則（非官方個人 Skill）
globs:
  - "**/*invoice*"
  - "**/*einvoice*"
  - "**/*opay*"
alwaysApply: false
---

# 歐付寶電子發票整合規則

本專案的電子發票整合以 `opay-invoice-skill/` 為唯一規格來源。

## 不可違反的鐵律

1. 加密是 **AES-128-CBC/PKCS7**，順序為「明文 JSON → URLEncode（.NET 慣例）→ AES → Base64」。
   **不是** CheckMacValue、**不是** SHA256（那是綠界 ECPay 的做法）。
2. **正式環境不得用 `Issue` 做健康檢查**——會產生真發票、消耗字軌，且只能作廢不能刪除。
3. **開立／作廢／折讓／註銷重開不可盲目重試**，逾時要先用 `GetIssue` 查詢。
4. **HashKey／HashIV 只進 `.env`**，嚴禁寫死在程式碼或前端。

## 查閱順序

1. `opay-invoice-skill/SKILL.md` §0
2. `opay-invoice-skill/references/api-coverage.json`（69 支 API 索引）
3. `opay-invoice-skill/references/{b2c,b2b,offline}-api-reference.md`
4. `opay-invoice-skill/references/enums.md`（列舉值不要憑記憶寫）
5. `opay-invoice-skill/templates/opay-einvoice-client/`（直接複製既有實作）

## 主機

- 測試：`https://einvoice-stage.opay.tw`
- 正式：`https://einvoice.opay.tw`
- 路徑前綴：`/B2CInvoice`（B2C 與離線）、`/B2BInvoice`（B2B）
```

> Cursor 也支援舊版的專案根目錄 `.cursorrules` 單檔格式；若你的版本較舊，把上面內容（去掉 front matter）存成 `.cursorrules` 即可。

### 使用技巧

在 Composer / Chat 中用 `@` 明確引用檔案，效果最好：

```
@opay-invoice-skill/references/b2c-api-reference.md
幫我用 TypeScript 實作 Issue 這支 API，欄位要照規格。
```

---

## 3. ChatGPT（GPTs）

**載入檔**：[`SKILL_OPENAI.md`](SKILL_OPENAI.md)

### 步驟

1. 前往 ChatGPT → 左側 **Explore GPTs** → **Create**。
2. 切到 **Configure** 分頁。
3. **Name**：`歐付寶電子發票助手（非官方）`
4. **Description**：
   ```
   協助台灣開發者串接歐付寶（O'Pay）電子發票 API。涵蓋 B2C／B2B／離線共 69 支 API。
   非官方個人專案，內容與官方文件不一致時以官方為準。
   ```
5. **Instructions**：把 [`SKILL_OPENAI.md`](SKILL_OPENAI.md) 全文貼進去。
   > GPTs 的 Instructions 有字數上限（約 8,000 字元），`SKILL_OPENAI.md` 已為此壓縮過。
6. **Knowledge**：上傳以下檔案（依重要性排序，GPTs 上限 20 個檔案）：

   | 優先 | 檔案 |
   |---|---|
   | ★★★ | `references/b2c-api-reference.md` |
   | ★★★ | `references/b2b-api-reference.md` |
   | ★★★ | `references/offline-api-reference.md` |
   | ★★★ | `references/encryption-aes.md` |
   | ★★★ | `references/enums.md` |
   | ★★ | `references/error-handling.md` |
   | ★★ | `references/urlencode-table.md` |
   | ★★ | `references/api-coverage.json` |
   | ★★ | `templates/opay-einvoice-client/python/opay_einvoice.py` |
   | ★ | `test-vectors/aes-encryption.json` |
   | ★ | `GLOSSARY.md` |

7. **Capabilities**：勾選 **Code Interpreter**（讓它能實際跑加密驗證），其餘視需求。
8. 儲存後測試：問「歐付寶開立發票的加密順序？」

### 注意

- 檔案較大時 GPTs 的檢索可能只讀到片段，**請在提問時明確指出 API 名稱**（例如「`AllowanceByCollegiate` 的必填欄位」），檢索命中率會高很多。
- 不要在 GPT 對話中貼正式環境金鑰或真實買受人個資。

---

## 4. Google Gemini

**載入檔**：[`GEMINI.md`](GEMINI.md)

### 方式 A：Gemini CLI

Gemini CLI 會讀取工作目錄的 `GEMINI.md` 作為脈絡。

```bash
cd opay-invoice-skill
gemini
```

或在你自己的專案中：

```bash
cp opay-invoice-skill/GEMINI.md ./GEMINI.md
# 再依實際路徑調整檔案中的相對路徑
```

### 方式 B：Gemini 網頁版（Gem）

1. 開啟 Gemini → **Gems** → **新增 Gem**。
2. **名稱**：`歐付寶電子發票助手（非官方）`
3. **操作說明**：貼上 [`GEMINI.md`](GEMINI.md) 全文。
4. **知識**：上傳 `references/` 下的規格檔（同 GPTs 的優先順序）。

### 方式 C：長脈絡直接貼

Gemini 的脈絡視窗很大，可以直接把整份 `references/b2c-api-reference.md`（約 4,950 行）貼進對話開頭，再開始問。這是**準確度最高**的用法，代價是每次對話都要重貼。

---

## 5. GitHub Copilot（VS Code）

**載入檔**：[`vscode_copilot.md`](vscode_copilot.md)

### 步驟

1. 在專案根目錄建立 `.github/copilot-instructions.md`：

   ```bash
   mkdir -p .github
   cp opay-invoice-skill/vscode_copilot.md .github/copilot-instructions.md
   ```

2. 在 VS Code 設定中確認已啟用（`settings.json`）：

   ```json
   {
     "github.copilot.chat.codeGeneration.useInstructionFiles": true
   }
   ```

3. 重新載入視窗（`Ctrl/Cmd + Shift + P` → **Developer: Reload Window**）。

### 使用技巧

Copilot Chat 支援 `#file:` 引用，明確引用規格檔可大幅提升準確度：

```
#file:references/b2c-api-reference.md
#file:references/enums.md
幫我實作 B2C Issue，買受人使用手機條碼載具。
```

也可以把常用規格加進 workspace context：

```
@workspace 歐付寶的 CarrierType 有哪些值？
```

### 注意

- Copilot 的 inline 補全**不會**完整讀取 instructions 檔，複雜邏輯請用 Copilot Chat。
- Copilot 特別容易把綠界的 `CheckMacValue` 補進來（訓練資料中綠界的範例遠多於歐付寶），**看到 `CheckMacValue` 一律刪掉**。

---

## 6. Google AI Studio

**載入檔**：[`google_AI_studio.md`](google_AI_studio.md)

### 步驟

1. 前往 [Google AI Studio](https://aistudio.google.com/) → **Create Prompt**。
2. 右側 **System Instructions** 欄位：貼上 [`google_AI_studio.md`](google_AI_studio.md) 全文。
3. 在對話區用 **＋ → Upload File** 上傳規格檔（`references/*.md`）。
4. 建議設定：

   | 參數 | 建議值 | 理由 |
   |---|---|---|
   | Model | 具長脈絡能力的最新版本 | 規格檔很長 |
   | Temperature | **0.1 ～ 0.3** | 規格類問答不需要創意，要的是照抄正確 |
   | Output length | 較長 | 完整程式碼容易被截斷 |
   | Safety settings | 預設即可 | — |

5. 存成 **Saved Prompt**，之後可直接開啟續用。

### 注意

- AI Studio 的對話**可能被用於改善服務**（依你的帳號設定而定）。**不要貼正式環境金鑰或真實買受人個資。**
- 需要程式化呼叫時，可把 System Instructions 直接放進 API 請求的 `systemInstruction` 欄位。

---

## 7. OpenAI Codex / Agents SDK

**載入檔**：[`AGENTS.md`](AGENTS.md)

`AGENTS.md` 是跨工具的 agent 指令慣例，Codex 與多數 agent 框架會自動讀取專案根目錄的這個檔案。

### 步驟

```bash
# 在你的專案根目錄
cp opay-invoice-skill/AGENTS.md ./AGENTS.md
# 若 Skill 不在根目錄，記得調整檔案內的相對路徑
```

若專案已有 `AGENTS.md`，把本 Skill 的內容以獨立章節合併進去：

```markdown
## 歐付寶電子發票（opay-invoice-skill）

<把 AGENTS.md 的「四條鐵律」與「查閱順序」章節貼在這裡>
```

### 巢狀 AGENTS.md

多數實作支援巢狀規則：離工作檔案最近的 `AGENTS.md` 優先。若你的發票程式碼集中在 `src/billing/`，可以只在該目錄放一份，避免污染全專案脈絡。

```
your-project/
├── AGENTS.md                 ← 全專案通則
└── src/billing/
    └── AGENTS.md             ← 歐付寶電子發票專用規則
```

### 沙箱與網路

Codex 預設在沙箱中執行。若要讓它跑 `test-vectors/verify.py`：

```bash
pip install pycryptodome    # 需要允許網路安裝
python3 test-vectors/verify.py
```

`test-vectors/verify-node.js` **零相依**（只用 Node 內建 `crypto`），在無網路沙箱中也能跑，建議優先用它驗證。

> ⚠️ **不要讓 agent 自動對正式環境發送任何開立／作廢／折讓請求。** 這些操作不可復原。建議在沙箱設定中封鎖 `einvoice.opay.tw`，只允許 `einvoice-stage.opay.tw`。

---

## 8. 其他平台通則

沒有專屬轉接檔的平台（例如 Windsurf、Cline、Continue、Zed），照這個順序處理：

1. 找該平台的「專案規則／系統指令」檔案位置。
2. 把 [`CLAUDE.md`](CLAUDE.md) 的內容貼進去（它是最完整的通用版本）。
3. 確認四條鐵律有進到指令中。
4. 用下面的驗證題測一次。

---

## 9. 載入成功的驗證題

不論用哪個平台，問這四題。**四題全對才算載入成功。**

| # | 問題 | 正確答案的關鍵字 | 錯誤答案（代表沒載入） |
|---|---|---|---|
| 1 | 歐付寶電子發票的加密方式？ | AES-128-CBC / PKCS7、URLEncode、Base64 | CheckMacValue、SHA256、MD5 |
| 2 | 歐付寶電子發票共有幾支 API？ | **69**（B2C 30／B2B 27／離線 12） | 含糊帶過、數字不對 |
| 3 | 呼叫 `Issue` 逾時可以直接重送嗎？ | **不行**，要先用 `GetIssue` 查 | 「可以，加上重試機制即可」 |
| 4 | B2C 與 B2B 的上傳期限？ | B2C **48 小時**、B2B **7 天** | 兩者相同、或說不知道 |

第 1 題答錯是最嚴重的——代表 AI 把綠界 ECPay 的做法套過來了。此時請確認：

- 規格檔真的有被讀到（路徑對不對、檔案有沒有超過平台上限）
- 系統指令中的「鐵律 ①」有沒有被截斷

---

## 10. 疑難排解

| 症狀 | 可能原因 | 處理 |
|---|---|---|
| AI 回答 `CheckMacValue` | 沒讀到 Skill，或指令被截斷 | 重新確認載入路徑；把鐵律移到指令最前面 |
| AI 編造不存在的欄位名 | 規格檔太大，檢索沒命中 | 提問時明確指出 API 名稱，或直接 `@` / `#file:` 引用該段 |
| AI 說「歐付寶和綠界一樣」 | 訓練資料混淆 | 在提問開頭重申「這是歐付寶 O'Pay，不是綠界 ECPay」 |
| 程式碼跑起來 `TransCode != 1` | 校時、金鑰與 MerchantID 不成對 | 先跑 `test-vectors` 驗證加密，再檢查 NTP |
| 加密結果與官方向量不同 | URLEncode 沒用 .NET 慣例 | 見 [`references/urlencode-table.md`](references/urlencode-table.md) |
| GPTs 檢索不到上傳的檔案 | 超過檔案數或大小限制 | 只留 `references/` 的核心五個檔 |

---

## 11. 安全提醒（所有平台適用）

> [!WARNING]
> - **不要**把正式環境的 `HashKey` / `HashIV` / `MerchantID` 貼進任何 AI 對話。
> - **不要**把真實的發票號碼、買受人 Email／手機／統一編號貼進 AI 對話。
> - 需要 AI 協助除錯時，先脫敏：金鑰換 `<REDACTED>`、發票號碼換 `AA00000000`、統編換 `00000000`。
> - 若不慎外洩，**立即到歐付寶廠商後台輪換金鑰**。

詳見 [`SECURITY.md`](SECURITY.md)。
