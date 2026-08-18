# 歐付寶電子發票 — URLEncode 轉換表（.NET 編碼慣例）

> **來源**：《歐付寶電子發票B2C介接技術文件》(opay_i100 V1.6.0) **附錄 2「URLEncode轉換表」**；《歐付寶離線電子發票介接技術文件》(opay_i301 V1.3.0) 附錄 2 內容完全相同。（i200 未附此表，但加密規格與 i100 一致，同樣適用。）
> 本文件為非官方整理，僅供開發參考；若與官方文件不一致，**一律以官方文件為準**。
> 標記「本專案驗證」處，為實際執行 Python 3.11 / Node.js 22 / PHP 8.4 比對的結果。

---

## 1. 這張表在管什麼

歐付寶後端是 .NET 實作，`Data` 欄位在 AES 加密**之前**要做的 URLEncode，採用 **.NET 的編碼慣例**。這個慣例和 RFC 3986、和各語言內建的 encode 函式都**不完全一樣**。

- 「**編碼表**」欄＝一般（RFC）percent-encoding 的結果。
- 「**.NET編碼(opay)**」欄＝**歐付寶實際要的結果**。兩欄不同的地方，就是你要動手校正的地方。

加密的完整順序見 [`references/encryption-aes.md`](./encryption-aes.md)。

---

## 2. 完整轉換表（原表 34 列，一列不少）

| # | 符號 | 編碼表 | .NET編碼(opay) | 與一般編碼是否相同 |
|---:|:---:|:---:|:---:|:---|
| 1 | `-` | `%2d` | `-` | ❌ 不編碼 |
| 2 | `_` | `%5f` | `_` | ❌ 不編碼 |
| 3 | `.` | `%2e` | `.` | ❌ 不編碼 |
| 4 | `!` | `%21` | `!` | ❌ 不編碼 |
| 5 | `~` | `%7e` | `%7e` | ✅ 相同 |
| 6 | `*` | `%2a` | `*` | ❌ 不編碼 |
| 7 | `(` | `%28` | `(` | ❌ 不編碼 |
| 8 | `)` | `%29` | `)` | ❌ 不編碼 |
| 9 | `space` 空格 | `%20` | `+` | ❌ **編成加號** |
| 10 | `@` | `%40` | `%40` | ✅ 相同 |
| 11 | `#` | `%23` | `%23` | ✅ 相同 |
| 12 | `$` | `%24` | `%24` | ✅ 相同 |
| 13 | `%` | `%25` | `%25` | ✅ 相同 |
| 14 | `^` | `%5e` | `%5e` | ✅ 相同 |
| 15 | `&` | `%26` | `%26` | ✅ 相同 |
| 16 | `=` | `%3d` | `%3d` | ✅ 相同 |
| 17 | `+` | `%2b` | `%2b` | ✅ 相同 |
| 18 | `;` | `%3b` | `%3b` | ✅ 相同 |
| 19 | `?` | `%3f` | `%3f` | ✅ 相同 |
| 20 | `/` | `%2f` | `%2f` | ✅ 相同 |
| 21 | `\` | `%5c` | `%5c` | ✅ 相同 |
| 22 | `>` | `%3e` | `%3e` | ✅ 相同 |
| 23 | `<` | `%3c` | `%3c` | ✅ 相同 |
| 24 | `%` | `%25` | `%25` | ✅ 相同（原文重複列出，此處照抄不刪） |
| 25 | `` ` `` | `%60` | `%60` | ✅ 相同 |
| 26 | `[` | `%5b` | `%5b` | ✅ 相同 |
| 27 | `]` | `%5d` | `%5d` | ✅ 相同 |
| 28 | `{` | `%7b` | `%7b` | ✅ 相同 |
| 29 | `}` | `%7d` | `%7d` | ✅ 相同 |
| 30 | `:` | `%3a` | `%3a` | ✅ 相同 |
| 31 | `'` | `%27` | `%27` | ✅ 相同 |
| 32 | `"` | `%22` | `%22` | ✅ 相同 |
| 33 | `,` | `%2c` | `%2c` | ✅ 相同 |
| 34 | `\|` | `%7c` | `%7c` | ✅ 相同 |

> 第 13 列與第 24 列都是 `%`，這是官方原表就有的重複，本文照抄保留，方便你逐列對照原文。

**表外的字元怎麼辦**：官方只列了符號。英數字 `A-Z` `a-z` `0-9` 不編碼；中文等非 ASCII 字元先用 **UTF-8** 編成位元組，每個位元組再各自編成 `%XX`。例如 `王` (U+738B) → UTF-8 `E7 8E 8B` → `%E7%8E%8B`。（**本專案驗證**，見向量 `utf8-chinese`。）

---

## 3. 十六進位大小寫：表是小寫，範例是大寫

上表寫的是小寫（`%2d`、`%7b`…），但 **i100 附錄 3 的加密範例，URLEncode 結果是大寫**：

```
{"Name":"Test","ID":"A123456789"}
  ↓
%7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D
```

**本專案驗證**：只有用**大寫**才能重現官方公布的密文
`uvI4yrErM37XNQkXGAgRgJAgHn2t72jahaMZzYhWL1HmvH4WV18VJDP2i9pTbC+tby5nxVExLLFyAkbjbS2Dvg==`；
用小寫算出來的 Base64 完全不同。

👉 **本 Skill 一律採大寫十六進位。** 上表的小寫視為文件書寫風格，不是規格。

> 補充（推論，非官方陳述）：percent-decoding 對十六進位大小寫不敏感（RFC 3986 §6.2.2.1），伺服器解出來理論上一樣。但官方範例是大寫、官方又明說要「符合檢查規則」，沒必要賭。

---

## 4. 官方 PHP `str_replace` 校正範例（原文照抄）

i100 附錄 2 表格下方的注意事項，原文如下：

> ※注意事項：
> 請確認您的語言的 UrlEncode function 轉換後的結果符合附錄 Urlencode 轉換表中的「.NET編碼(opay)」欄位值，若有不符合的字元，請用字元替換功能處理，以免無法符合檢查規則。
>
> 例如：PHP urlencode function 會將 `!` 字元編碼成 `%21`，不符合「.NET編碼(opay)」，所以在 PHP urlencode 後需用 str_replace function 將 `%21` 轉回 `!` 字元。以下僅以 PHP 轉換範例說明：
>
> ```php
> $sMacValue = str_replace('%21', '!', $sMacValue);
> $sMacValue = str_replace('%2a', '*', $sMacValue);
> $sMacValue = str_replace('%28', '(', $sMacValue);
> $sMacValue = str_replace('%29', ')', $sMacValue);
> ```
>
> 其它程式語言的轉換功能，請閱該程式語言的編碼轉換規則改寫。

> ⚠️ **這段官方範例有個雷**：`'%2a'` 是小寫，但 **PHP 8 的 `urlencode()` 實際輸出是大寫 `%2A`**（**本專案驗證**：`php -r 'echo urlencode("*");'` → `%2A`）。照抄小寫會替換不到，`*` 就會留在 `%2A` 的狀態送出去。請改成大寫，或用 `str_ireplace()`。

---

## 5. 三語言校正實作

以下三段皆**本專案驗證**：對全部可列印 ASCII（U+0020–U+007E）加上 CJK 字元做逐字掃描，三者輸出完全一致，且都能重現官方測試向量。

### 5.1 PHP — 修正版

```php
<?php
/**
 * PHP 的 urlencode() 已經做對三件事：
 *   空格 -> '+'、'~' -> '%7E'、輸出大寫十六進位
 * 只差 ! * ( ) 這四個被多編了，補一次 str_replace 即可。
 */
function opay_urlencode(string $text): string
{
    return str_replace(
        ['%21', '%2A', '%28', '%29'],   // ← 大寫！官方範例寫小寫是錯的
        ['!',   '*',   '(',   ')'],
        urlencode($text)
    );
}

function opay_urldecode(string $text): string
{
    // urldecode() 會把 '+' 還原成空格，正是 .NET 慣例要的。
    // 不要用 rawurldecode()，它會把 '+' 原封不動留下來。
    return urldecode($text);
}
```

> ❌ 不要用 `rawurlencode()`：它不編 `~`（留成 `~`）、且空格編成 `%20` 而不是 `+`，要多修兩處。

### 5.2 Python — 修正版

```python
import urllib.parse

def opay_urlencode(text: str) -> str:
    """
    quote_plus 已經做對：空格 -> '+'、輸出大寫十六進位。
    要補兩件事：
      1. safe="!*()" 讓這四個字元不被編碼
      2. Python 3.7+ 把 '~' 視為 unreserved 不編碼，要手動補回 %7E
    """
    return urllib.parse.quote_plus(text, safe="!*()").replace("~", "%7E")

def opay_urldecode(text: str) -> str:
    # unquote_plus 會把 '+' 還原成空格。不要用 unquote()，它不處理 '+'。
    return urllib.parse.unquote_plus(text)
```

> ❌ 不要用 `urllib.parse.quote()`：預設 `safe='/'`，`/` **不會**被編碼，但 opay 要 `%2F`。手機條碼載具是 `/ABC1234` 開頭，這個預設值會安靜地把你坑掉。

### 5.3 Node.js — 修正版

```javascript
/**
 * encodeURIComponent 不編碼這些字元：A-Z a-z 0-9 - _ . ! ~ * ' ( )
 * 對照 .NET 慣例，其中 ! * ( ) - _ . 剛好正確，另外三處要修：
 *   ' -> %27 、 ~ -> %7E 、 %20 -> +
 * 輸出本來就是大寫十六進位，不用另外處理。
 */
function opayUrlencode(text) {
  return encodeURIComponent(text)
    .replace(/'/g, '%27')
    .replace(/~/g, '%7E')
    .replace(/%20/g, '+');
}

function opayUrldecode(text) {
  // decodeURIComponent 不會把 '+' 還原成空格，必須先自己處理。
  // 但要小心：不能直接 replace('+',' ')，因為明文裡真正的 '+' 是 %2B，
  // 此時尚未被解碼，所以這個順序是安全的。
  return decodeURIComponent(text.replace(/\+/g, '%20'));
}
```

### 5.4 不想相信任何內建函式？逐位元組自己編

最保險、也最好 code review 的寫法（Python 版；Node / PHP 對應版本見
[`test-vectors/verify-node.js`](../test-vectors/verify-node.js) 與 [`encryption-aes.md`](./encryption-aes.md) §5）：

```python
_SAFE = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.!*()"
)

def opay_urlencode(text: str) -> str:
    out = []
    for byte in text.encode("utf-8"):
        char = chr(byte)
        if char in _SAFE:
            out.append(char)
        elif char == " ":
            out.append("+")
        else:
            out.append("%%%02X" % byte)
    return "".join(out)
```

三行規則、零隱藏預設值，跟上表一一對得起來。

---

## 6. 各語言內建函式差異速查（本專案驗證）

輸入 `!*()~ +%`（含空格），實測輸出：

| 語言 / 函式 | 輸出 | 差幾處 |
|---|---|---|
| **目標**（.NET / opay） | `!*()%7E+%2B%25` | — |
| PHP `urlencode()` | `%21%2A%28%29%7E+%2B%25` | 4（`!*()`） |
| PHP `rawurlencode()` | `%21%2A%28%29~%20%2B%25` | 6（`!*()` + `~` + 空格） |
| Node `encodeURIComponent()` | `!*()~%20%2B%25` | 2（`~` + 空格）＋ `'` 未編 |
| Python `quote_plus()` | `%21%2A%28%29~+%2B%25` | 5（`!*()` + `~`） |
| Python `quote()` | `%21%2A%28%29~%20%2B%25` | 6，且預設 `safe='/'` 會漏掉 `/` |

**沒有任何一個內建函式可以直接用**，這就是官方要附這張表的原因。

---

## 7. 怎麼確認自己改對了

跑本 Skill 的向量驗證器，四組向量分別釘住不同行為：

```bash
python3 test-vectors/verify.py
node    test-vectors/verify-node.js
```

| 向量 id | 釘住什麼 |
|---|---|
| `official-appendix3` | 官方向量：整條加密順序 + 大寫十六進位 |
| `dotnet-space-and-safe-symbols` | 空格 → `+`、`!` `*` `(` `)` 不編碼 |
| `utf8-chinese` | 中文走 UTF-8 逐位元組 `%XX` |
| `plus-tilde-percent` | `+`→`%2B`、`~`→`%7E`、`%`→`%25` |

詳見 [`test-vectors/README.md`](../test-vectors/README.md)。
