# commands/ —— slash command 指令總表

這個資料夾是給 **Claude Code、Cursor 等支援 slash command 的平台**用的。
每一份 `.md` 就是一個指令：frontmatter 的 `description` 是指令說明，內文是給 AI 的執行指示。

其他平台（ChatGPT、Gemini、Copilot）不支援 slash command，
但這些檔案的內容一樣可以直接貼進對話當作提示詞使用。

---

## 指令總表

| 指令 | 用途 | 有沒有不可逆操作 |
|---|---|---|
| [`/opay-invoice`](opay-invoice.md) | 整合總入口，走 `guides/00-onboarding.md` 四問後決定路徑 | 否 |
| [`/opay-issue`](opay-issue.md) | 開立一張發票，互動式收集必填欄位 | ⚠️ **是**（開立後只能作廢） |
| [`/opay-query`](opay-query.md) | 查詢發票／折讓／作廢明細與字軌 | 否（唯讀） |
| [`/opay-void`](opay-void.md) | 作廢或註銷重開 | ⚠️ **是**（必須二次確認） |
| [`/opay-allowance`](opay-allowance.md) | 開立折讓 | ⚠️ **是**（必須二次確認） |
| [`/opay-words`](opay-words.md) | 字軌管理與餘量檢查 | 部分（設定字軌會改狀態） |
| [`/opay-offline`](opay-offline.md) | 離線發票取號與上傳 | ⚠️ **是**（取號即消耗、上傳即開立） |
| [`/opay-b2b`](opay-b2b.md) | B2B 開立與確認流程 | ⚠️ **是** |
| [`/opay-doctor`](opay-doctor.md) | 串接健檢，輸出繁中診斷報告 | 否（只用唯讀 API） |

---

## 該用哪一個

```
不知道從哪開始           → /opay-invoice
打不通、一直失敗         → /opay-doctor
要開一張發票             → /opay-issue
開錯了，交易還算數       → /opay-void（選「註銷重開」）
交易取消了               → /opay-void（選「作廢」）
只退一部分金額           → /opay-allowance
想知道發票開成功了沒     → /opay-query
快到期別交界了           → /opay-words
門市會斷網               → /opay-offline
對方是公司行號           → /opay-b2b
```

---

## 所有指令共同遵守的規則

這幾條寫在每一份指令裡，也寫在 `SKILL.md` §0：

1. **加密是 AES-128-CBC / PKCS7**，不是 CheckMacValue、不是 SHA256
   （那是綠界 ECPay 的做法，本 Skill 不適用）。
2. **不可逆操作一律二次確認**，而且要求使用者回覆時帶上發票號碼，
   不接受「好」「嗯」這種回答。
3. **預設測試環境**。切到正式環境必須由使用者明確說出口。
4. **正式環境健康檢查只能用唯讀 API**，絕不可以用 `Issue` / `OfflineIssue`。
5. **金鑰只從環境變數讀**，不印出、不寫進報告、不進版控。
6. **不確定就去讀 `references/`**，不要憑印象編造欄位名稱。

---

## 安裝

### Claude Code

把整個 repo 放在專案目錄下，或把 `commands/` 複製到 `.claude/commands/`：

```bash
mkdir -p .claude
cp -r commands .claude/commands
```

### Cursor

參考 `vscode_copilot.md` 與 `SETUP.md` 的說明，把指令內容放進 `.cursor/rules`。

### 其他平台

見 `SETUP.md` 的各平台安裝章節，以及六份轉接檔
（`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`SKILL_OPENAI.md`、
`vscode_copilot.md`、`google_AI_studio.md`）。
