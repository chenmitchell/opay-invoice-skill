# CONTRIBUTING.md — 貢獻指南

歡迎！本專案是**非官方的個人專案**，由 Mitchell Chen 一個人撰寫與維護。

一個人做的東西一定有盲點，所以**歡迎開 issue、也歡迎送 PR**。你指出的每一個錯誤，都會讓下一個讀到它的人少踩一次雷。

**你不需要是工程師才能貢獻。** 指出「這段我看不懂」就是很有價值的回報。

> 因為只有我一個人在看 issue 與 PR，回覆時間無法保證。不是不理你，是排隊中。

---

## 目錄

- [最有價值的五種貢獻](#最有價值的五種貢獻)
- [開 issue 之前](#開-issue-之前)
- [提交 PR 的流程](#提交-pr-的流程)
- [寫作規範](#寫作規範)
- [Mermaid 圖規範](#mermaid-圖規範)
- [程式碼規範](#程式碼規範)
- [絕對不可以出現在 PR 裡的東西](#絕對不可以出現在-pr-裡的東西)
- [本地驗證](#本地驗證)
- [Commit 訊息](#commit-訊息)
- [審查標準](#審查標準)

---

## 最有價值的五種貢獻

| 優先 | 類型 | 為什麼有價值 |
|---|---|---|
| ★★★ | **規格錯誤回報** | 錯的規格比沒有規格更危險。請附官方文件版本與章節。 |
| ★★★ | **實務踩坑經驗** | 官方文件沒寫、只有真的串過才知道的事。 |
| ★★ | **看不懂的段落** | 你看不懂，代表寫得不夠好。這是校正寫作品質最直接的訊號。 |
| ★★ | **其他語言的 client 模板** | Go、Java、C#、Ruby、Rust 都歡迎。 |
| ★ | **錯字與用語校對** | 繁體中文用語一致性（「登入」不是「登陸」、「介面」不是「界面」）。 |

其他也很歡迎的：無障礙改進、Mermaid 圖優化、guides 補充、已脫敏的截圖、術語表補充。

---

## 開 issue 之前

1. **先搜尋既有 issue**，避免重複。
2. **確認是本 repo 的問題**，不是歐付寶服務本身的問題。
3. **安全問題請勿開公開 issue** → 見 [`SECURITY.md`](SECURITY.md)。
4. **脫敏**：不要貼真實發票號碼、統編、Email、手機、金鑰。

### 規格錯誤回報範本

```markdown
## 哪裡錯了
`references/b2c-api-reference.md` §7 `Issue` 的 `CarrierType` 欄位

## 目前寫的
（貼上目前 repo 中的內容）

## 應該是
（貼上正確內容）

## 依據
《歐付寶電子發票B2C介接技術文件》V1.6.0 第 X 章，第 Y 頁

## 我怎麼發現的
（例如：照文件寫的送出，得到 RtnCode=X，改成 Z 才成功）
```

### 踩坑經驗回報範本

```markdown
## 情境
（例如：期別交界當天，B2C 開立）

## 症狀
（錯誤碼、錯誤訊息、行為，已脫敏）

## 原因
（你查到的真正原因）

## 解法
（怎麼修好的）

## 建議補在哪
（例如：guides/03-b2c-word-setting.md 或 references/error-handling.md）
```

---

## 提交 PR 的流程

```bash
# 1. Fork 後 clone
git clone https://github.com/<你的帳號>/opay-invoice-skill.git
cd opay-invoice-skill

# 2. 開分支（用有意義的名字）
git checkout -b fix/b2c-carriertype-enum

# 3. 修改

# 4. 本地驗證（見下方「本地驗證」）
python3 test-vectors/verify.py
node    test-vectors/verify-node.js

# 5. commit 並 push
git commit -m "fix(references): 修正 B2C Issue 的 CarrierType 列舉值"
git push origin fix/b2c-carriertype-enum

# 6. 開 PR，說明「改了什麼」與「依據是什麼」
```

### PR 描述請包含

- **改了什麼**（一句話）
- **為什麼**（依據哪份官方文件的哪一章，或實測結果）
- **影響範圍**（有沒有連帶要改 `api-coverage.json`、guides、templates）
- **驗證方式**（跑了哪些檢查）

---

## 寫作規範

本 repo 的文件有明確的風格要求，請盡量對齊。

### 語言

- **一律繁體中文（zh-Hant）**，台灣用語。
- 技術名詞保留英文原文，第一次出現時附中文說明：「字軌（Invoice Word）」。
- API 名稱、欄位名稱**保持原始大小寫**並用反引號包住：`` `AllowanceByCollegiate` ``、`` `CarrierType` ``。

### 常見用語對照

| ✅ 用 | ❌ 不用 |
|---|---|
| 登入 | 登陸 |
| 介面 | 界面 |
| 程式 / 程式碼 | 代碼 |
| 網路 | 網絡 |
| 資料庫 | 數據庫 |
| 預設 | 默認 |
| 支援 | 支持 |
| 專案 | 項目 |
| 伺服器 | 服務器 |
| 快取 | 緩存 |

### 結構要求

- **每段規格都要標註來源**：`- **來源**：i100 §7`
- **標題階層不可跳號**（`##` 之後不可直接 `####`）
- **表格必須有表頭列**
- **程式碼區塊要標語言**
- **連結文字要能單獨讀懂**：寫 `` [`references/enums.md`](references/enums.md) ``，不要寫「點這裡」

### 語氣

- 直接、具體、不繞圈子。
- **多寫「做錯會怎樣」**，這是本 repo 最有價值的部分。
- 不確定的地方就說不確定，**不要編造**。官方沒寫清楚就寫「官方文件未明確說明，實測結果為…」。
- 不宣稱官方背書、不宣稱法規符合性。

---

## Mermaid 圖規範

所有圖表必須遵循 [`docs/accessibility.md`](docs/accessibility.md)。重點：

### 1. 固定的 init 標頭（逐字複製）

```
%%{init: {'flowchart': {'curve':'step','htmlLabels':true,'useMaxWidth':true},'themeVariables': {'fontSize':'16px','fontFamily':'ui-sans-serif, system-ui, sans-serif'}}}%%
```

### 2. 只能用這九個 `fill:` 色

`#1E3A8A` `#3730A3` `#581C87` `#164E63` `#134E4A` `#78350F` `#1F2937` `#14532D`（成功） `#7F1D1D`（失敗）

一律搭配 `stroke:#FFFFFF,stroke-width:3px,color:#FFFFFF`。

### 3. 節點標籤：圖示 ＋ 中文 ＋ 英文

```
A["🧾 開立發票<br/>Issue Invoice"]
```

### 4. 圖前圖後各一行標註

圖前：
```
> 🧭 **純文字重述（螢幕閱讀器友善）**：…（完整句子描述流程與分支）
```

圖後（子目錄請改相對路徑）：
```
> ♿ 配色遵循 [`docs/accessibility.md`](docs/accessibility.md)：WCAG AAA 對比 ≥7:1、Okabe-Ito 色盲安全色盤、16px 字體、直角連線、圖示＋文字雙編碼。
```

> 純文字重述**不是裝飾**。把圖遮起來只讀文字，讀者仍應能理解整個流程。

---

## 程式碼規範

### 通則

- **不使用歐付寶官方 SDK**（本專案刻意不依賴，以保持可攜性）。
- **相依最小化**：能用內建就用內建。
- **註解用繁體中文**，說明「為什麼」而不只是「做什麼」。
- **錯誤訊息要帶修復建議**，不要只丟 `Exception: failed`。
- **金鑰只從環境變數讀**。

### 各語言

| 語言 | 最低版本 | 風格 |
|---|---|---|
| Python | 3.8+ | PEP 8、type hints |
| Node.js | 18+ | 只用內建 `crypto` 與 `fetch` |
| PHP | 7.4+ | PSR-12、只用內建 `openssl` 與 cURL |

### 新增 client 語言的最低要求

1. 涵蓋全部 **69 支 API**（以 `references/api-coverage.json` 為準）。
2. 兩層錯誤（`TransCode` 與 `RtnCode`）都要檢查。
3. 可獨立執行的自我測試，用 `test-vectors/aes-encryption.json` 驗證，**不發任何網路請求**。
4. 選填欄位以 `extra` 參數用官方 PascalCase 原樣傳入。
5. README 中的 5 行上手範例。

---

## 絕對不可以出現在 PR 裡的東西

> [!WARNING]
> 以下任一項出現在 PR 中，會被直接關閉：

| # | 禁止 |
|---|---|
| 1 | **正式環境的 `HashKey` / `HashIV` / `MerchantID`** |
| 2 | **真實買受人個資**：Email、手機、姓名、地址、統編、載具號碼 |
| 3 | **真實發票號碼與隨機碼** |
| 4 | **未脫敏的截圖**（見 [`docs/images/README.md`](docs/images/README.md)） |
| 5 | **任何組織的內部資訊**：內部系統網址、內部專案代號、內部文件連結 |
| 6 | **宣稱官方背書**的措辭 |
| 7 | **宣稱法規符合性**的措辭（「已符合法規」「保證合規」） |
| 8 | **未核可的 Mermaid 顏色** |
| 9 | **無授權的第三方內容**（複製他人文件、未授權圖片） |

測試用的資料請用：`AA00000000`（發票號碼）、`00000000`（統編）、`user@example.com`、`0900000000`、`ORDER-0001`。

---

## 本地驗證

提交前請跑過：

```bash
# 1. 加密測試向量（必須 4/4 pass）
python3 test-vectors/verify.py
node    test-vectors/verify-node.js

# 2. client 自我測試（不發網路請求）
python3 templates/opay-einvoice-client/python/opay_einvoice.py
node    templates/opay-einvoice-client/nodejs/opay-einvoice.js
php     templates/opay-einvoice-client/php/OPayEInvoice.php

# 3. Mermaid 色盤檢查
grep -rhno 'fill:#[0-9A-Fa-f]\{6\}' --include='*.md' . \
  | grep -v -E 'fill:#(1E3A8A|3730A3|581C87|164E63|134E4A|78350F|1F2937|14532D|7F1D1D)' \
  && echo '❌ 有未核可色' || echo '✅ 色盤合規'

# 4. 疑似金鑰檢查
#    下列四個字串是官方文件公開列出的「僅測試環境」值，故排除；
#    其餘任何 16 碼金鑰出現在 diff 中都要人工確認。
git diff --cached | grep -nE 'Hash(Key|IV).{0,10}[A-Za-z0-9]{16}' \
  | grep -v -E 'ejCk326UnaZWKisg|q9jcZX8Ib9LM8wYk|9XWzRmj7UJESChyn|sriQzbe1llJqk67P' \
  && echo '⚠️ 疑似金鑰，請確認' || echo '✅ 未偵測到非公開金鑰'
```

若 `scripts/` 下有對應的驗證腳本，請一併執行。CI 會跑同樣的檢查。

---

## Commit 訊息

採用 Conventional Commits：

```
<type>(<scope>): <繁體中文描述>
```

| type | 用於 |
|---|---|
| `feat` | 新增內容（新 API 說明、新模板、新指南） |
| `fix` | 修正錯誤（規格錯、程式錯、連結壞） |
| `docs` | 純文件調整（錯字、排版、用語） |
| `refactor` | 結構調整，內容不變 |
| `test` | 測試向量或驗證器 |
| `chore` | CI、設定、雜項 |

常用 scope：`references`、`guides`、`templates`、`test-vectors`、`docs`、`readme`、`ci`

範例：

```
fix(references): 修正 B2C Issue 的 CarrierType 列舉值（依 i100 V1.6.0 §7）
feat(templates): 新增 Go 語言 client，涵蓋 69 支 API
docs(guides): 補充期別交界時字軌設定的踩坑說明
```

---

## 審查標準

我會依這五點審查 PR：

1. **正確性**：與官方文件一致嗎？有標註來源嗎？
2. **一致性**：術語、格式、色盤、檔案結構與現有內容一致嗎？
3. **完整性**：改了規格，`api-coverage.json`、guides、templates 有連帶更新嗎？
4. **安全性**：有沒有金鑰、個資、內部資訊？
5. **可讀性**：一個沒串過電子發票的人讀得懂嗎？

> 被要求修改不代表貢獻沒價值。本 repo 對正確性要求高，是因為**錯的規格會讓人開錯發票**。

---

## 行為準則

參與本專案即表示你同意遵守 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

---

## 授權

提交 PR 即表示你同意你的貢獻以 **MIT License** 授權釋出。

---

**謝謝你願意花時間讓這份文件更好。** 🧾
