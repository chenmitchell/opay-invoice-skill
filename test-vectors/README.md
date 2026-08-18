# 加解密測試向量（test-vectors）

> **來源**：官方向量逐字取自《歐付寶電子發票B2C介接技術文件》(opay_i100 V1.6.0) **附錄 3「參數加密方式說明」**（i200 附錄 2、i301 附錄 3 內容完全相同）。衍生向量為本專案依官方規格自行推導。
> 本目錄為非官方產出，僅供開發參考；若與官方文件不一致，**一律以官方文件為準**。

---

## 這裡有什麼

| 檔案 | 說明 |
|---|---|
| `aes-encryption.json` | **SSOT**（唯一事實來源）。所有向量與規格摘要都在這裡，兩支驗證器都讀它。 |
| `verify.py` | Python 驗證器（需 `pycryptodome`） |
| `verify-node.js` | Node.js 驗證器（只用內建 `crypto`，零相依） |
| `README.md` | 本檔 |

---

## 怎麼跑

```bash
# Python（在 repo 根目錄執行）
pip install pycryptodome
python3 test-vectors/verify.py

# Node.js
node test-vectors/verify-node.js
```

兩者輸出格式**刻意做成完全一致**：

```
opay-invoice-skill AES 測試向量驗證（Python / pycryptodome）
向量檔：aes-encryption.json

  ok    official-appendix3  (official)
  ok    dotnet-space-and-safe-symbols  (derived)
  ok    utf8-chinese  (derived)
  ok    plus-tilde-percent  (derived)

4/4 pass
```

- 全部通過 → 印 `N/N pass`，**exit 0**
- 任一失敗 → 印 `FAIL <id>` 與 expected/actual 差異，最後印 `failed: <ids>`，**exit 1**

兩支都可以直接掛進 CI（`python3 test-vectors/verify.py && node test-vectors/verify-node.js`）。

也可以指定其他向量檔：

```bash
python3 test-vectors/verify.py path/to/other.json
node    test-vectors/verify-node.js path/to/other.json
```

---

## 為什麼要跨語言雙驗證

**因為這份 Skill 的產出是「規格描述」，不是「某個語言的函式庫」。**

規格描述有沒有寫對，唯一的檢驗方式是：**兩個互不相干的實作，照著同一份文字各自寫一遍，能不能算出同樣的位元組。**

- 如果只有 Python 一份實作，「向量通過」只證明「這份 Python 程式碼跟這組向量互相一致」——很可能是我用同一段程式碼**生成**向量再拿去驗證，等於自己蓋章給自己。
- 加上一份用**不同 crypto 函式庫**（Node 內建 `crypto` vs pycryptodome）、**不同字串模型**（UTF-16 code unit vs Python str）、**不同 padding 預設值**的實作，才能抓到「我對規格的理解剛好被某個語言的預設值掩蓋」這類錯誤。

實務上這抓到的正是 .NET URLEncode 那一類問題：
`encodeURIComponent`（Node）不編 `!*()`、`quote_plus`（Python）編了 `!*()` 但不編 `~`、PHP `urlencode` 兩邊都編但空格處理又對了——**三個語言各錯一半**。若只用一種語言驗證，很容易把「這語言剛好對的部分」誤當成規格。

> 本專案另外用 PHP 8.4 的 `openssl_encrypt` 跑過同一組向量，四組全數通過。PHP 驗證器沒有進版控（避免 CI 多一個執行環境），實作見 [`references/encryption-aes.md` §5.3](../references/encryption-aes.md)。

---

## 每組向量在釘住什麼

| id | source | 釘住的行為 | 為什麼重要 |
|---|:---:|---|---|
| `official-appendix3` | **official** | 整條加密順序（JSON → URLEncode → AES-128-CBC/PKCS7 → Base64）＋ 十六進位**大寫** | 唯一具官方效力的向量。這組不過，其他都不用談。 |
| `dotnet-space-and-safe-symbols` | derived | 半形空格 → `+`（不是 `%20`）；`!` `*` `(` `)` **不編碼** | .NET 慣例與各語言內建函式最主要的兩處分歧。官方 i100 附錄 2 特別為此加了 `str_replace` 範例。 |
| `utf8-chinese` | derived | 中文以 **UTF-8** 逐位元組編成 `%XX`（大寫），且能與空格的 `+` 規則並存 | 發票的商品名稱、買受人名稱幾乎必然含中文。編碼設成 Big5 會整批亂碼。 |
| `plus-tilde-percent` | derived | `+` → `%2B`、`~` → `%7E`、`%` → `%25` | 三個最容易被誤放行的字元。真正的 `+` 沒編碼的話，解碼後 `1+1` 會變成 `1 1`；`%` 沒編碼會讓後兩碼被當成 escape 序列。 |

> `source` 欄的意義：
> - `official` = **逐字取自官方文件**，具官方效力。
> - `derived` = **本專案依官方規格自行推導**，並經 Python / Node.js（另加 PHP）交叉驗證。它證明的是「三種實作對規格的理解一致」，**不是**「歐付寶伺服器認可這組密文」。若日後與官方新版文件衝突，以官方為準。

---

## `aes-encryption.json` 結構

```jsonc
{
  "$schema_note": "...",
  "spec": {
    "algorithm": "AES-128-CBC",
    "padding": "PKCS7",
    "key_bits": 128,
    "encode_order": ["1. 組出明文 JSON 字串", "2. opay_urlencode（.NET 慣例）", ...],
    "decode_order": ["1. Base64 解碼", "2. AES-128-CBC / PKCS7 解密", ...],
    "urlencode": {
      "unreserved": "A-Z a-z 0-9 - _ . ! * ( )",
      "space": "+",
      "other": "UTF-8 位元組逐一編為 %XX，十六進位使用大寫",
      "hex_case_note": "..."
    },
    "official_source": "i100 附錄 3 / i200 附錄 2 / i301 附錄 3"
  },
  "disclaimer": "...",
  "vectors": [
    {
      "id":          "official-appendix3",   // 向量識別碼
      "source":      "official",             // official | derived
      "description": "這組在釘住什麼行為",
      "key":         "ejCk326UnaZWKisg",     // HashKey（測試環境公開金鑰）
      "iv":          "q9jcZX8Ib9LM8wYk",     // HashIV （測試環境公開金鑰）
      "plaintext":   "{\"Name\":\"Test\",\"ID\":\"A123456789\"}",
      "urlencoded":  "%7B%22Name%22%3A...",  // 中間產物，單獨驗證可快速定位錯在哪一步
      "ciphertext":  "uvI4yrErM37XNQkX..."   // Base64
    }
  ]
}
```

**每組向量會被驗三件事**：

1. `opay_urlencode(plaintext)` == `urlencoded`　← 錯在這裡代表 **URLEncode 慣例**沒做對
2. `opay_encrypt(key, iv, plaintext)` == `ciphertext`　← 前一項對、這項錯，代表 **AES 參數或 padding** 不對
3. `opay_decrypt(key, iv, ciphertext)` == `plaintext`　← 反向路徑（含 URLDecode）是否對稱

把 `urlencoded` 這個中間產物寫進向量檔，就是為了讓失敗訊息能直接告訴你**錯在哪一步**，而不是只丟一句「密文不符」。

---

## 加新向量時

1. 只用官方 Key/IV（`ejCk326UnaZWKisg` / `q9jcZX8Ib9LM8wYk`）。這是官方文件公開的**測試環境**金鑰。
2. `source` 填 `derived`，`description` 寫清楚**這組在釘住什麼行為**——不會有人記得三個月前為什麼加了某組資料。
3. 加完後**兩支驗證器都要跑過**。只有一支過，代表向量是照某一個實作生成的，失去交叉驗證的意義。
4. 🚫 **絕對不要**放正式環境的 HashKey / HashIV，也不要放真實的客戶姓名、統編、手機號碼、載具編號。

---

## 安全提醒

> ⚠️ 本目錄裡的 `ejCk326UnaZWKisg` / `q9jcZX8Ib9LM8wYk` 是**官方文件公開的測試環境金鑰**，可以放心 commit。
> **正式環境的 HashKey / HashIV 一個字元都不能進這個 repo**，只能放 `.env`，且嚴禁寫進前端 JS/HTML/CSS。詳見 [`references/encryption-aes.md` §7](../references/encryption-aes.md)。

---

## 相關檔案

| 檔案 | 用途 |
|---|---|
| [`references/encryption-aes.md`](../references/encryption-aes.md) | 加解密完整規格 + Python / Node.js / PHP 可執行實作 |
| [`references/urlencode-table.md`](../references/urlencode-table.md) | i100 附錄 2 完整 34 列轉換表 |
| [`references/error-handling.md`](../references/error-handling.md) | `TransCode` / `RtnCode` 兩層判讀與重試策略 |
