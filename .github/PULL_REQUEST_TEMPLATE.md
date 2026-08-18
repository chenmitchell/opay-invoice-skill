## 這個 PR 做了什麼

<!-- 一到三句話說清楚。若對應某個 issue，請寫 Closes #123。 -->

## 變更類型

- [ ] 修正規格錯誤（references/）
- [ ] 新增或改寫教學（guides/）
- [ ] 範本程式（templates/）
- [ ] 檢查腳本（scripts/）／CI
- [ ] slash command（commands/）
- [ ] 文件與說明（README、SETUP、六份轉接檔等）
- [ ] 無障礙改進

## 官方文件依據

<!-- 涉及規格變更時必填：哪一份文件、哪一版、第幾章。
     例：《歐付寶電子發票B2C介接技術文件》V1.6.0 第 7 章 -->

## 送出前檢查清單

**安全（不可跳過）**

- [ ] 我**沒有**把真實金鑰、真實 token、私鑰放進這個 PR
- [ ] 我**沒有**把真實發票資料、真實統一編號、真實客戶個資放進這個 PR
- [ ] 範例一律使用官方公開測試值（特店 `2000132`、HashKey `ejCk326UnaZWKisg`、HashIV `q9jcZX8Ib9LM8wYk`）
- [ ] 我沒有 commit `.env`（只能改 `.env.example`，且值必須留空或為官方測試值）

**檢查機制**

- [ ] 我在本機跑過 `bash scripts/run-all-gates.sh`，**而且全綠**
- [ ] 如果我動到 `scripts/`，我是在**加嚴**而不是放寬檢查
- [ ] 如果我新增了 API，我已經同步更新 `references/api-coverage.json`（SSOT），
      並確認 `scripts/validate-api-coverage.sh` 的統計仍是 `合計 69/69`（或更新後的正確數字）

**內容品質**

- [ ] 新增的 mermaid 圖只用了九色核可色盤，且圖前有 🧭 純文字重述、圖後有 ♿ 配色註記
- [ ] 新增的內部連結我都點過，指得到真實檔案
- [ ] 我沒有把綠界 ECPay／歐買尬 OMG 的做法（`CheckMacValue`、`AioCheckOut` 等）寫進非對照段落
- [ ] 若涉及正式環境，我沒有示範用 `Issue` / `OfflineIssue` 做健康檢查
- [ ] 文字為繁體中文，術語與 `GLOSSARY.md` 一致

## 本機執行結果

<!-- 把 scripts/run-all-gates.sh 的彙總表貼在這裡 -->

```
（貼上彙總表）
```
