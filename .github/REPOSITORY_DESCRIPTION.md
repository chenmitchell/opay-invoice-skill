# Repository 簡介與 GitHub 設定建議

這份檔案不是給程式讀的，是給**維護者設定 GitHub repo 時複製貼上用的**。
GitHub 的 About 欄位、Topics、專案健康度設定都沒有版本控制，寫在這裡才不會每次改版都要重想。

---

## 一、About → Description（一行簡介，350 字元上限）

**建議版本（繁體中文，224 字元）：**

```
歐付寶 O'Pay 電子發票 AI Skill：完整覆蓋 69 支 API（B2C 30／B2B 27／離線 12），含三語言 client、測試向量、30 份繁中指南與 CI 獨立檢查機制。加密為 AES-128-CBC/PKCS7，不是 CheckMacValue。非官方個人整理。
```

**英文備選（給國際搜尋用）：**

```
AI Skill for O'Pay (歐付寶) Taiwan e-invoice API — all 69 endpoints (B2C 30 / B2B 27 / offline 12), AES-128-CBC/PKCS7, Python/Node/PHP clients, test vectors, 30 Traditional-Chinese guides, CI validators. Unofficial.
```

---

## 二、About → Website

填 `https://github.com/chenmitchell/opay-invoice-skill#readme`（或未來的文件站網址）。

---

## 三、About → Topics（建議 15～20 個）

GitHub 上限 20 個。以下依「有人真的會這樣搜」排序，前 10 個是必留的：

```
opay
einvoice
e-invoice
taiwan
taiwan-einvoice
ai-skill
claude-skill
llm-tools
invoice-api
aes-128-cbc
fintech
accounting
python
nodejs
php
traditional-chinese
mcp
developer-tools
api-documentation
accessibility
```

**為什麼放 `accessibility`**：本 repo 的所有圖表都用九色核可色盤並附純文字重述，
這在 API 文件類專案裡很少見，是值得被搜到的特色。

**刻意不放的 topic**：`ecpay`、`綠界`。
把別家品牌放進 topics 會讓搜尋 ECPay 的人誤入，而本 Skill 的規格對他們是錯的。

---

## 四、Repository 設定建議

| 設定 | 建議值 | 理由 |
|---|---|---|
| Default branch | `main` | — |
| Issues | 開啟 | 規格錯誤要有地方回報 |
| Discussions | 開啟 | 「這算不算 bug」的問題不該塞在 issue |
| Projects | 關閉 | 用 ROADMAP.md 就夠了 |
| Wiki | 關閉 | 內容一律進 repo，才會被 CI 檢查到 |
| Sponsorships | 依維護者意願 | — |
| Preserve this repository | 開啟 | Arctic Code Vault／存檔 |

### Branch protection（`main`）

- ✅ Require a pull request before merging
- ✅ Require approvals：**1**
- ✅ Require review from Code Owners（搭配 `.github/CODEOWNERS`）
- ✅ Require status checks to pass before merging
  - 必選 check：**`全關卡檢查（Ubuntu）`**（來自 `.github/workflows/validate.yml`）
- ✅ Require branches to be up to date before merging
- ✅ Require conversation resolution before merging
- ✅ Do not allow bypassing the above settings

> 這一段是本 repo「獨立檢查機制」真正生效的地方。
> 腳本寫得再好，如果 CI 紅燈還能 merge，那就只是裝飾。

### Security

- ✅ Private vulnerability reporting（搭配 `SECURITY.md`）
- ✅ Dependabot alerts（只收安全警示；刻意不啟用 security updates 的自動 PR，避免機器人在一個人維護的 repo 裡持續開 PR）
- ✅ Secret scanning + Push protection
  —— repo 內的 `scripts/validate-no-leaks.sh` 是第一道，GitHub 的 push protection 是第二道，兩道都要開。

---

## 五、Social preview 圖

建議尺寸 1280×640。內容建議只放三行大字：

```
歐付寶電子發票 AI Skill
69 支 API．AES-128-CBC．繁體中文
非官方個人整理
```

配色請從九色核可色盤選（見 [`docs/accessibility.md`](../docs/accessibility.md)），
底色建議 `#1E3A8A`，文字純白，確保縮圖在深色與淺色模式下都讀得清楚。

---

## 六、README badge 建議

```markdown
[![獨立檢查機制](https://github.com/chenmitchell/opay-invoice-skill/actions/workflows/validate.yml/badge.svg)](https://github.com/chenmitchell/opay-invoice-skill/actions/workflows/validate.yml)
```

這顆 badge 的意義是：**當下這一版的 69 支 API 覆蓋率、機密掃描、無障礙配色全部是綠的。**
它比任何「我很用心」的自我宣稱都有說服力。
