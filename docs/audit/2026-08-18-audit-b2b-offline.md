# 獨立稽核報告：opay-invoice-skill 對 B2B(i200) 與 離線(i301) 官方文件的覆蓋度

- **稽核日期**：2026-08-18
- **稽核立場**：預設受稽核方有漏。repo 內任何自述、coverage 清單、「已完成」宣稱**一律不採信**，僅以官方技術文件轉出的純文字為事實來源。
- **事實來源**
  - `（官方技術文件轉為純文字後，未隨 repo 發布）歐付寶電子發票B2B介接技術文件(opay_i200).txt`（2941 行，V1.2.0 / 2025-09-10）
  - `（官方技術文件轉為純文字後，未隨 repo 發布）歐付寶離線電子發票介接技術文件(opay_i301).txt`（1234 行，V1.3.0 / 2025-09-10）
  - 註：`wc -l` 分別回報 2940 / 1233，因末行無換行字元；以 `split('\n')` 計為 2941 / 1234 行。**此差異本身即為下方發現 #2 的關鍵。**
- **受稽核對象**：``
- **稽核腳本**：`/tmp/audit/{extract2,diff,strict,typecheck,desc,desc2}.py`（全部輸出見附錄 A）

---

## 1. 結論

**有條件通過** —— B2B 27 支與離線 12 支的 endpoint 清單、欄位、型態長度、必填標記、列舉值、巢狀結構、範例與附錄均**逐欄位比對後缺漏 0、型態/必填錯誤 0、列舉壓縮 0**；但 repo 有 **2 處對官方原文的事實陳述錯誤**，以及 **i200 §1／§2 兩個非 API 章節（含平台商測試金鑰、財政部授權步驟、官方操作手冊連結）完全未被轉寫**，與離線文件的處理方式不對稱。

問題總數：**0 阻斷級／3 重要／3 建議**。

> 我必須明確記錄：我原本預期能找到大量欄位缺漏。**實際比對結果是找不到。** 這不是「沒認真找」——見第 4 節的腳本輸出與三種獨立比對法（欄位名 / 型態+必填 / 說明文字逐段），以及第 7 節逐字驗算的加密向量與 URLEncode 表。

---

## 2. 獨立重建的功能清單

### 2.1 交叉驗證方法

三條獨立路徑互相驗證，三者必須收斂到同一個數字：

1. **TOC 章名**：讀原文開頭目錄，逐章列出章名與頁碼。
2. **URL 掃描**：`grep -oE 'einvoice(-stage)?\.opay\.tw/[A-Za-z0-9/_-]+'` 全文抓取，去重取 endpoint 名。
3. **章 → endpoint 對應**：以每個 URL 出現位置切段，段落即該 API 的完整章節（四表 + 範例 + 注意事項），再回頭核對章名。

### 2.2 B2B（i200）— 27 支

TOC 共 **29 章 + 2 附錄**；其中 §1「B2B電子發票簡介」與 §2「前置準備事項」不含 API，**§3～§29 共 27 章 = 27 支 endpoint，1 章 1 支，無共用、無一章多支**。

| # | 章 | 章名 | Endpoint | 原文行 |
|---:|---:|---|---|---:|
| 1 | §3 | 交易對象維護 | `/B2BInvoice/MaintainMerchantCustomerData` | 84–176 |
| 2 | §4 | 發送通知 | `/B2BInvoice/Notify` | 177–260 |
| 3 | §5 | 字軌與配號設定 | `/B2BInvoice/AddInvoiceWordSetting` | 261–347 |
| 4 | §6 | 設定字軌號碼狀態 | `/B2BInvoice/UpdateInvoiceWordStatus` | 348–440 |
| 5 | §7 | 開立發票 | `/B2BInvoice/Issue` | 441–601 |
| 6 | §8 | 開立發票確認 | `/B2BInvoice/IssueConfirm` | 602–695 |
| 7 | §9 | 作廢發票 | `/B2BInvoice/Invalid` | 696–778 |
| 8 | §10 | 作廢發票確認 | `/B2BInvoice/InvalidConfirm` | 779–871 |
| 9 | §11 | 退回發票 | `/B2BInvoice/Reject` | 872–954 |
| 10 | §12 | 退回發票確認 | `/B2BInvoice/RejectConfirm` | 955–1050 |
| 11 | §13 | 開立折讓發票 | `/B2BInvoice/Allowance` | 1051–1162 |
| 12 | §14 | 折讓發票確認 | `/B2BInvoice/AllowanceConfirm` | 1163–1255 |
| 13 | §15 | 作廢折讓發票 | `/B2BInvoice/CancelAllowance` | 1256–1339 |
| 14 | §16 | 作廢折讓發票確認 | `/B2BInvoice/CancelAllowanceConfirm` | 1340–1412 |
| 15 | §17 | 註銷重開 | `/B2BInvoice/VoidWithReIssue` | 1413–1577 |
| 16 | §18 | 查詢發票 | `/B2BInvoice/GetIssue` | 1578–1756 |
| 17 | §19 | 查詢發票確認 | `/B2BInvoice/GetIssueConfirm` | 1757–1879 |
| 18 | §20 | 查詢作廢發票 | `/B2BInvoice/GetInvalid` | 1880–1986 |
| 19 | §21 | 查詢作廢發票確認 | `/B2BInvoice/GetInvalidConfirm` | 1987–2090 |
| 20 | §22 | 查詢退回發票 | `/B2BInvoice/GetReject` | 2091–2196 |
| 21 | §23 | 查詢退回發票確認 | `/B2BInvoice/GetRejectConfirm` | 2197–2300 |
| 22 | §24 | 查詢折讓發票 | `/B2BInvoice/GetAllowance` | 2301–2450 |
| 23 | §25 | 查詢折讓發票確認 | `/B2BInvoice/GetAllowanceConfirm` | 2451–2544 |
| 24 | §26 | 查詢作廢折讓發票 | `/B2BInvoice/GetAllowanceInvalid` ⚠️ | 2545–2644 |
| 25 | §27 | 查詢作廢折讓發票確認 | `/B2BInvoice/GetAllowanceInvalidConfirm` ⚠️ | 2645–2738 |
| 26 | §28 | 查詢字軌 | `/B2BInvoice/GetInvoiceWordSetting` | 2739–2852 |
| 27 | §29 | 統一編號驗證 | `/B2BInvoice/GetCompanyNameByTaxID` | 2853–2941 |

⚠️ 命名陷阱：「作廢折讓」的**動作** API 叫 `CancelAllowance`，但**查詢**該動作的 API 叫 `GetAllowanceInvalid`（不是 `GetCancelAllowance`）。repo 兩處皆正確。

**結論：27 支，與宣稱一致。**

### 2.3 離線（i301）— 12 支

TOC 共 **15 章 + 3 附錄**；§1–§4 為簡介／關鍵字／前置／流程說明，**§5～§15 共 11 章對應 12 支 endpoint**，唯一的「一章兩支」在 §12。

| # | 章 | 章名 | Endpoint（前綴一律 `/B2CInvoice`） | 原文行 |
|---:|---:|---|---|---:|
| 1 | §5 | 查詢特店基本資料 | `GetOfflineMerchantInfo` | 86–155 |
| 2 | §6 | 查詢財政部配號結果 | `GetGovInvoiceWordSetting` | 156–241 |
| 3 | §7 | 管理發票機台 | `OfflineMerchantPosSetting` | 242–312 |
| 4 | §8 | 查詢發票機台 | `QueryOfflineMerchantPosSetting` | 313–390 |
| 5 | §9 | 字軌與配號設定 | `AddInvoiceWordSetting` | 391–478 |
| 6 | §10 | 設定字軌號碼狀態 | `UpdateInvoiceWordStatus` | 479–551 |
| 7 | §11 | 取得自動配發發票字軌號碼 | `GetOfflineInvoiceWordSettingWithAutoSplit` | 552–632 |
| 8 | §12-1 | 取得發票字軌號碼**區間** | `GetOfflineInvoiceWordSetting` | 633–715 |
| 9 | §12-2 | 取得發票字軌號碼**清單**(含隨機碼、加密資料) | `GetOfflineInvoiceWordSettingNumber` | 716–804 |
| 10 | §13 | 上傳開立發票 | `OfflineIssue` | 805–987 |
| 11 | §14 | 上傳作廢發票 | `OfflineInvalid` | 988–1063 |
| 12 | §15 | 查詢字軌 | `GetInvoiceWordSetting` | 1064–1234 |

**§12 兩支的證據**（原文第 626–628、711 行）：
```
626 取得發票字軌號碼
627 …歐付寶提供兩支取得發票字軌號碼API，功能相同但回傳內容有些許差異，特店請選擇其中一種方式串接即可…
628 取得發票字軌號碼區間                      → GetOfflineInvoiceWordSetting
711 取得發票字軌號碼清單(含隨機碼、加密資料)   → GetOfflineInvoiceWordSettingNumber
```

**結論：12 支，與宣稱一致。** repo 的 `offline-api-reference.md` §8／§9 兩節皆標「來源 i301 §12（12-1 / 12-2）」，處理正確。

---

## 3. 覆蓋比對結果

判定標準：reference 需有**獨立章節 + 完整四表（傳入外層／傳入 Data／回傳外層／回傳 Data）+ 範例 + 注意事項**；client 需有對應方法（以 endpoint 路徑字串出現於檔案內判定，並抽查方法簽章）；guide 需有提及。

### 3.1 B2B（i200）27/27

| # | Endpoint | ref 章節 | 四表 | 範例 | 注意事項 | py | node | php | guide 命中數 |
|---:|---|---|:--:|:--:|:--:|:--:|:--:|:--:|---:|
| 1 | MaintainMerchantCustomerData | §1 (L38) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 4 |
| 2 | Notify | §2 (L162) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 14 |
| 3 | AddInvoiceWordSetting | §3 (L294) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6 |
| 4 | UpdateInvoiceWordStatus | §4 (L437) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8 |
| 5 | Issue | §5 (L562) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 24 |
| 6 | IssueConfirm | §6 (L802) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 5 |
| 7 | Invalid | §7 (L935) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 13 |
| 8 | InvalidConfirm | §8 (L1103) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 4 |
| 9 | Reject | §9 (L1236) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6 |
| 10 | RejectConfirm | §10 (L1403) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 3 |
| 11 | Allowance | §11 (L1536) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15 |
| 12 | AllowanceConfirm | §12 (L1737) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 3 |
| 13 | CancelAllowance | §13 (L1869) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 3 |
| 14 | CancelAllowanceConfirm | §14 (L2038) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 15 | VoidWithReIssue | §15 (L2172) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6 |
| 16 | GetIssue | §16 (L2408) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15 |
| 17 | GetIssueConfirm | §17 (L2656) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 3 |
| 18 | GetInvalid | §18 (L2832) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 7 |
| 19 | GetInvalidConfirm | §19 (L2989) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 1 |
| 20 | GetReject | §20 (L3140) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 21 | GetRejectConfirm | §21 (L3295) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 1 |
| 22 | GetAllowance | §22 (L3450) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 7 |
| 23 | GetAllowanceConfirm | §23 (L3651) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 24 | GetAllowanceInvalid | §24 (L3794) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6 |
| 25 | GetAllowanceInvalidConfirm | §25 (L3945) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 26 | GetInvoiceWordSetting | §26 (L4088) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15 |
| 27 | GetCompanyNameByTaxID | §27 (L4246) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8 |

### 3.2 離線（i301）12/12

| # | Endpoint | ref 章節 | 四表 | 範例 | 注意事項 | py | node | php | guide |
|---:|---|---|:--:|:--:|:--:|:--:|:--:|:--:|---:|
| 1 | GetOfflineMerchantInfo | §1 (L42) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 2 | GetGovInvoiceWordSetting | §2 (L157) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6 |
| 3 | OfflineMerchantPosSetting | §3 (L289) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 4 | QueryOfflineMerchantPosSetting | §4 (L410) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 5 | AddInvoiceWordSetting | §5 (L538) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6 |
| 6 | UpdateInvoiceWordStatus | §6 (L677) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8 |
| 7 | GetOfflineInvoiceWordSettingWithAutoSplit | §7 (L805) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 1 |
| 8 | GetOfflineInvoiceWordSetting | §8 (L936) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 1 |
| 9 | GetOfflineInvoiceWordSettingNumber | §9 (L1070) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 1 |
| 10 | OfflineIssue | §10 (L1211) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 3 |
| 11 | OfflineInvalid | §11 (L1530) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 2 |
| 12 | GetInvoiceWordSetting | §12 (L1660) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 15 |

**client 去重端點數驗算**：三支 client 各出現 65 個唯一 `/B2xInvoice/...` 路徑。65 = B2C 30 + B2B 27 + 離線 12 − 4（離線與 B2C 共用 `AddInvoiceWordSetting`、`UpdateInvoiceWordStatus`、`GetGovInvoiceWordSetting`、`GetInvoiceWordSetting`）。命名以 `b2b_` / `offline_` 前綴避免撞名（`python/opay_einvoice.py:287` 有明文規則）。

**未覆蓋的非 API 章節（見發現 #1）**：i200 §1、i200 §2、i200 Version History 表。

---

## 4. 欄位級缺漏清單（報告核心）

### 4.1 方法

三種**互相獨立**的自動比對，全部以「官方原文表格列」為基準：

| 腳本 | 比對什麼 | 抗什麼作弊 |
|---|---|---|
| `extract2.py` + `diff.py` | 欄位**名稱**（掃描表格列直到型態欄為止，支援 2/3 層巢狀縮排） | 漏抄欄位 |
| `typecheck.py` / `strict.py` | 欄位的**型態（含長度）** 與 **必填星號**，逐出現次數嚴格比對（multiset） | 型態長度被改、必填標反 |
| `desc.py` / `desc2.py` | 說明欄**全文逐 20 字切塊**比對，且限制在對應章節內 | 列舉值被壓縮、注意事項被砍、跨章節搬運 |

另加：官方 JSON 範例的**每個 key 與每個 value** 逐一在對應 repo 章節搜尋。

### 4.2 結果

```
### C. 欄位缺漏 diff（B2B）
repo sections: 27
official-only endpoints: []
repo-only endpoints: []
TOTAL MISSING FIELDS: 0

### D. 欄位缺漏 diff（離線）
repo sections: 12
official-only endpoints: []
repo-only endpoints: []
TOTAL MISSING FIELDS: 0

### E. 型態/必填 嚴格比對（B2B）
STRICT ISSUES: 0

### F. 型態/必填 嚴格比對（離線）
STRICT ISSUES: 0

### G. 說明/列舉文字逐段比對（章節內，B2B）
[VoidWithReIssue.CustomerEmail] L1447 lost 1 chunks e.g. ['測試僅驗規則格式檢核正規表達式為^A–Z']
SECTION-SCOPED LOSSES: 1

### H. 說明/列舉文字逐段比對（章節內，離線）
[OfflineIssue.CarrierNum] L888 lost 1 chunks e.g. ['<隱碼id>不會檢核正確性注意事項當Ca']
[OfflineIssue.CarrierNum2] L889 lost 1 chunks e.g. ['實體卡片的<顯碼id>以便發票查詢可以顯']
SECTION-SCOPED LOSSES: 2
```

範例比對（另一支腳本）：
```
B2B  EXAMPLE DIFFS: 0
離線 EXAMPLE DIFFS: 0
```

**G/H 的 3 筆全部是我的正規化器造成的偽陽性，已逐一人工排除：**

| 偽陽性 | 原因 | 驗證 |
|---|---|---|
| `VoidWithReIssue.CustomerEmail`（i200 L1447） | repo 把 935 字元的 Email 正規表達式移到欄位表下方的 ```` ```text ```` 區塊，表格內留指標句 | 逐字元比對：**IDENTICAL: True，長度 935 = 935**（`b2b-api-reference.md:2260`） |
| `OfflineIssue.CarrierNum`（i301 L888） | 原文 `<隱碼id>`，repo 依 Markdown 規範寫成 `&lt;隱碼id&gt;` | `offline-api-reference.md:1303` 目視確認 |
| `OfflineIssue.CarrierNum2`（i301 L889） | 同上（`<顯碼id>`） | `offline-api-reference.md:1304` 目視確認 |

> **經 39 支（B2B 27 + 離線 12）逐欄位比對：**
> - **欄位缺漏 0**（B2B 534 個唯一欄位／700 個表格列出現次數；離線 184 個唯一欄位／241 個表格列出現次數，全數命中）
> - **型態（含長度）錯誤 0、必填標記錯誤 0**
> - **說明／列舉文字實質遺失 0**（3 筆偽陽性已排除）
> - **範例 key／value 遺失 0**

### 4.3 人工深入抽查（8 支，含指定的 8 支全部）

欄位總數逐一點算（官方表格列 vs repo 表格列）：

```
B2B Issue                                     official= 37 repo= 37 missing=[]
B2B VoidWithReIssue                           official= 39 repo= 39 missing=[]
B2B GetIssue                                  official= 57 repo= 57 missing=[]
B2B GetAllowance                              official= 45 repo= 45 missing=[]
B2B GetIssueConfirm                           official= 29 repo= 29 missing=[]
OFF OfflineIssue                              official= 43 repo= 43 missing=[]
OFF GetInvoiceWordSetting                     official= 21 repo= 21 missing=[]
OFF GetOfflineInvoiceWordSettingWithAutoSplit official= 16 repo= 16 missing=[]
```

**列舉值是否被壓縮**（全 39 章節掃描：抓出官方所有 `數字[:：]中文` 形式的列舉 token，逐一在對應 repo 章節搜尋）：
```
TOTAL ENUM TOKENS MISSING: 0
```

指定的 5 組列舉逐一人工確認：

| 列舉 | 官方原文位置 | 官方內容 | repo | 判定 |
|---|---|---|---|---|
| `ZeroTaxRateReason` 71–79 | i200 L472；i301 L818 | 九款全列（第一款外銷貨物 … 第九款保稅區營業人…物流中心以供外銷之貨物） | `b2b-api-reference.md:672`、`offline-api-reference.md:1275`、`enums.md:87-99` | ✅ **九款全在，一字不漏** |
| `SpecialTaxType` 1–8 含稅率 | i200 L475；i301 L892 | 1=25%／2=15%／3=2%／4=1%／5=5%／6=5%(103/07 後)／7=5%(103/06 前)／8=空白免稅 | `b2b-api-reference.md:675`、`offline-api-reference.md:1298`、`enums.md:63-84` | ✅ 八種與稅率全在；enums.md 另加「6/7 同為 5%、差在期間」的提醒 |
| `ExchangeMode` 存證/交換 | i200 L118 | `0:存證  1: 交換` + 兩段說明 | `b2b-api-reference.md:83`、`enums.md:517-529` | ✅ 含「僅適用於銷項發票」「請務必先至財政部平台設定由歐付寶接收」原文 |
| `InvoiceTag` B2B 交換 10 種 + 存證 4 種 | i200 L208 | 交換 1–10、存證 1–4，附「存證模式只允許買方開立作廢折讓」注意事項 | `b2b-api-reference.md:225`、`enums.md:330-346` | ✅ 10 + 4 全在，且與 B2C 的 `I/II/A/AI/AW` 明確區隔 |
| 離線 `CarrierType` 顯碼/隱碼 | i301 L886–889 | `""`、1–8；`CarrierNum`=隱碼、`CarrierNum2`=顯碼；4~7 卡片、8 信用卡（刷卡日期7碼+金額10碼左補0） | `offline-api-reference.md:1302-1304`、`enums.md:230-267` | ✅ 值與規則全在（但 `enums.md:244` 對來源的**陳述**有誤，見發現 #3） |

**巢狀結構逐項確認：**

| 巢狀 | 官方位置 | 子欄位 | repo |
|---|---|---|---|
| `Issue.Items[]` | i200 L477–484 | ItemSeq / ItemName / ItemCount / ItemWord / ItemPrice / ItemAmount / ItemTax / ItemRemark（8） | ✅ 8/8，型態長度一致（ItemName String(256)、ItemRemark String(200)） |
| `VoidWithReIssue.VoidModel` | i200 L1438–1439 | InvoiceNumber / VoidReason（2） | ✅ 2/2 |
| `VoidWithReIssue.IssueModel` | i200 L1440–1464 | RelateNumber…InvoiceRemark 含 `Items[]` 8 子欄位（共 39 欄位） | ✅ 39/39；ItemRemark 為 String(120)（與 Issue 的 200 不同），repo 未混淆 |
| `GetIssueConfirm.RtnData` | i200 L1846–1855 | MerchantID / InvoiceNumber / InvoiceDate / Buyer_Identifier / Seller_Identifier / ConfirmDate / Upload_Status / Upload_Date / ConfirmRemark（9） | ✅ 9/9 |
| `GetInvoiceWordSetting.InvoiceInfo[]`（B2B） | i200 L2804–2816 | TrackID…InvoiceLastDate（11） | ✅ 11/11 |
| `GetInvoiceWordSetting.InvoiceInfo[]`（離線） | i301 L1130–1142 | TrackID…MachineID（11，末欄為 MachineID 而非 InvoiceLastDate） | ✅ 11/11，未與 B2B 版混用 |
| `QueryOfflineMerchantPosSetting.MachineIDList[]` | i301 L367–370 | MachineID / CreateTime / Remark（3） | ✅ 3/3 |
| `OfflineIssue.Items[]` | i301 L855–862 | ItemSeq / ItemName / ItemCount / ItemWord / ItemPrice / ItemTaxType / ItemAmount / ItemRemark（8） | ✅ 8/8；ItemName String(100)、ItemRemark String(40)（與 B2B 不同），repo 未混淆 |

---

## 5. B2B 成對性稽核結果

### 5.1 五組動作↔確認：**5/5 完整，無任何一半被漏**

| 動作 API | ref 章 | 確認 API | ref 章 | py/node/php | 成對關係有被寫清楚嗎 |
|---|---|---|---|:--:|---|
| `Issue` | §5 | `IssueConfirm` | §6 | ✅ | ✅ |
| `Invalid` | §7 | `InvalidConfirm` | §8 | ✅ | ✅ |
| `Reject` | §9 | `RejectConfirm` | §10 | ✅ | ✅ |
| `Allowance` | §11 | `AllowanceConfirm` | §12 | ✅ | ✅ |
| `CancelAllowance` | §13 | `CancelAllowanceConfirm` | §14 | ✅ | ✅ |

成對規則明文出現在兩處：
- `references/b2b-api-reference.md:18`：`> **交換模式的成對規則**：Issue → IssueConfirm、Invalid → InvalidConfirm、Reject → RejectConfirm、Allowance → AllowanceConfirm、CancelAllowance → CancelAllowanceConfirm。`
- `guides/12-b2b-overview.md:111` §3.1「成對規則（背起來）」5 列表格 + 警語「只做開立不做確認 = 交易對象端永遠停在『等待確認』」。

### 5.2 12 支查詢／驗證 API：**12/12 完整**

`GetIssue`／`GetIssueConfirm`／`GetInvalid`／`GetInvalidConfirm`／`GetReject`／`GetRejectConfirm`／`GetAllowance`／`GetAllowanceConfirm`／`GetAllowanceInvalid`／`GetAllowanceInvalidConfirm`／`GetInvoiceWordSetting`／`GetCompanyNameByTaxID` — 全部有 ref 章節 + 三語言方法 + `guides/17-b2b-query.md` 決策表逐支對照（含查詢鍵：發票類用 `InvoiceNumber+InvoiceDate`／`RelateNumber`，折讓類一律 `AllowanceNo` 16 碼）。

### 5.3 額外查核：`ExchangeStatus` 在兩種模式下語意不同

`enums.md:539-547` 正確引用 i200 §18 原文：存證模式 `1`=完成（無 `0` 狀態）、交換模式 `0`=開立等待確認／`1`=接收開立確認，並標注「空值≠0」。這是成對性的實務關鍵，未被漏掉。

---

## 6. 離線特有稽核結果

### 6.1 路徑前綴 `/B2CInvoice`：✅ 正確，零錯誤

```
$ grep -rn "OfflineInvoice/"    → 0 筆
$ grep -c "B2CInvoice/" references/offline-api-reference.md          → 26
$ grep -c "B2BInvoice"   references/offline-api-reference.md         → 0
```
三語言 client 亦全部使用 `/B2CInvoice/...`（例：`python/opay_einvoice.py:1306,1335,1346,1407,1426,1445,1483,1502`）。`offline-api-reference.md:1863` 另有明文提醒「所有 API 皆走 `/B2CInvoice/` 路徑前綴」。

### 6.2 附錄 1「交易狀態代碼表」誠實性判定：✅ **誠實**

**官方原文（i301 L1173–1175）：**
```
1173 交易狀態代碼表
1174 因錯誤代碼一直在新增，詳細的錯誤代碼，請到廠商後台->系統開發管理->交易狀態代碼查詢。
1175  [[IMG]]
```
→ **代碼表本體確為圖片，純文字抽取後沒有任何表格列。**

**repo 的處理（`offline-api-reference.md:1985-2003`）：**
- 逐字照抄那一句原文；
- 明文寫「原文此附錄的『交易狀態代碼表』本身是一張圖片（純文字中僅餘圖片佔位，**位於原文第 1175 行**）…**沒有任何表格列可供照抄**」；
- 明文寫「因此本檔**無法**提供代碼清單，也**不自行補寫任何代碼**」；
- 只列出可從各章文字確認的 `TransCode=1` / `RtnCode=1` 兩列，並標注「非完整代碼表，僅供對照」。

**另交叉查核 `references/error-handling.md:0-40`**：同樣明文「官方沒有公開完整錯誤碼表」「🚫 本 Skill 不得自行編造錯誤碼」，只收錄官方文件內**明確寫出意義**的 4 個碼（`1` / `4000003` / `4000004` / `10000010`，全部來自 i100 §7 §20 §21）。

**判定：無任何自行編造的代碼表。阻斷級問題 0 筆。**

### 6.3 附錄 2 URLEncode 轉換表：✅ 逐列一致（34 vs 34）

腳本逐列比對（官方 L1178–1211 vs `offline-api-reference.md:2010-2044`）：
```
official rows: 34
repo rows:     34
DIFF row 33 ['', '', '%7c', '%7c'] || ['|', '%7c', '%7c']
```
唯一「差異」是最後一列：官方該列的符號欄就是半形直線 `|`，在管線分隔的純文字表中被解析成空欄；repo 寫成 `&#124;`（Markdown 表格內的正確跳脫）並在表下註明「最後一列符號為半形直線 `|`」。**這是正確處理，不是缺漏。**

其餘 33 列（含官方自身重複出現兩次的 `%` 列）**逐字元一致**，repo 亦註明「原文中 `%` 一列出現兩次，此處照抄保留」。
表後的 ※注意事項與 4 行 PHP `str_replace` 範例亦完整照抄。

### 6.4 附錄 3 加密範例：✅ 五項逐字一致，且**實際跑過驗算**

| 項目 | 官方（i301 L1215–1234） | repo（`offline-api-reference.md:2087-2130`） | 一致 |
|---|---|---|:--:|
| Key | `A123456789012345` | `A123456789012345` | ✅ |
| IV | `B123456789012345` | `B123456789012345` | ✅ |
| 明文 | `{"Name":"Test","ID":"A123456789"}` | 同 | ✅ |
| URLEncode | `%7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D` | 同 | ✅ |
| 密文 | `7woM9RorZKAtXJRVccAb0qhHYm+5lnlhBzyfh5EZdNck7PacNsRHgv/Jvp//ajJidqcQcs0UmAgPQVjXQHeziw==` | 同 | ✅ |

**獨立驗算**（AES-128-CBC/PKCS7）：
```
$ python3 -c "AES(k=A123456789012345, iv=B123456789012345).encrypt(pad(urlencoded))"
7woM9RorZKAtXJRVccAb0qhHYm+5lnlhBzyfh5EZdNck7PacNsRHgv/Jvp//ajJidqcQcs0UmAgPQVjXQHeziw==
```
→ **與官方密文完全相同**。同法驗算 i200 附錄 2 的 `Key=ejCk326UnaZWKisg / IV=q9jcZX8Ib9LM8wYk`：
```
uvI4yrErM37XNQkXGAgRgJAgHn2t72jahaMZzYhWL1HmvH4WV18VJDP2i9pTbC+tby5nxVExLLFyAkbjbS2Dvg==
```
→ 亦與官方一致。**repo 收錄的加密規格是可執行、可驗證的正確規格。**

### 6.5 §4「離線電子發票流程說明」：✅ 完整帶入

官方 §4 為一張 9 列表格（處理角色／流程名稱／處理說明，L67–76）+ 1 段 ※注意事項（L78–79）。
repo `offline-api-reference.md:1927-1950` 完整轉寫 9 列表格（逐字）+ ※注意事項逐字照抄 + 純文字重述 + Mermaid 流程圖（圖上明標「原文 §4 僅提供流程表格，未附圖；作廢分支為依 §14 語意補繪」）。**無缺漏，且對「哪部分是原文、哪部分是重繪」有誠實區隔。**

### 6.6 其他離線前置章節

| 官方章 | repo | 狀態 |
|---|---|---|
| Version History（4 列） | `offline-api-reference.md:1843` | ✅ 逐字 |
| §1 離線電子發票簡介 | L1854 | ✅ 逐字 |
| §2 關鍵字一覽表（7 列） | L1866 | ✅ 逐字，7/7 |
| §3 前置準備事項（測試環境表 + 介接注意事項 12 條） | L1882 | ✅ 逐字；MerchantID `2045501`／HashKey `9XWzRmj7UJESChyn`／HashIV `sriQzbe1llJqk67P`／統編 `40044335` 與官方 L38–45 一致 |
| §4 流程說明 | L1927 | ✅（見 6.5） |

---

## 7. 正確性錯誤清單

### 7.1 「歐付寶加密被寫成 CheckMacValue / SHA256」：✅ **零違規，不構成阻斷級問題**

全 repo `grep -rn "CheckMacValue\|SHA256\|sha256"` 共 20 餘處命中，**逐一檢視後全部是「反面警告」語境**，例如：
- `SKILL.md:34`：「綠界用 `CheckMacValue`（SHA256／MD5 雜湊簽章），**歐付寶電子發票用 AES-128-CBC 加密整包 Data**」
- `GLOSSARY.md:212`：「**這裡沒有 `CheckMacValue`**——那是綠界 ECPay 的做法」
- `vscode_copilot.md:56`：「看到補全出現 `CheckMacValue`、`SHA256`…一律按 Esc 拒絕」
- `scripts/validate-not-ecpay-or-omg.sh`：CI 關卡，主動阻擋綠界做法混入

**沒有任何一處把 CheckMacValue／SHA256 當成歐付寶的正確做法。**

另註：`references/b2b-api-reference.md:2286` 出現 `"CustomerEmail": "test@ecpay.com.tw"` —— 這是**官方 i200 第 1492 行原文範例**的逐字照抄（官方文件自身的複製貼上瑕疵），非 repo 引入。

### 7.2 抽查 12 個欄位的正確性（型態長度／必填／列舉語意／路徑／體系歸屬）

| # | 欄位 | 官方原文（行） | repo | 判定 |
|---:|---|---|---|:--:|
| 1 | `Issue.Items[].ItemName` | i200 L479 `String(256)` | `b2b-api-reference.md:678` `String(256)` | ✅ |
| 2 | `Issue.Items[].ItemRemark` | i200 L484 `String(200)` | 同章 `String(200)` | ✅ |
| 3 | `VoidWithReIssue.IssueModel.Items[].ItemName` | i200 L1466 `String(2)`（原文誤植） | `b2b-api-reference.md:2246` `String(2)` + ⚠️ 標註「與商品名稱語意不符，疑為原文誤植」 | ✅ 照抄且標註 |
| 4 | `VoidWithReIssue.IssueModel.Items[].ItemRemark` | i200 L1473 `String(120)` | repo `String(120)`（未寫成 Issue 的 200） | ✅ |
| 5 | `VoidWithReIssue.IssueModel.RelateNumber` | i200 L1442 `String(50)` 必填 | repo `String(50)` ✅必填 | ✅（未寫成 Issue 的 String(20)） |
| 6 | `OfflineIssue.Items[].ItemName` | i301 L857 `String(100)` | `offline-api-reference.md:1290` `String(100)` | ✅ |
| 7 | `OfflineIssue.Items[].ItemRemark` | i301 L862 `String(40)` | repo `String(40)` | ✅ |
| 8 | `OfflineIssue.RelateNumber` | i301 L836 `String(30)` 必填 | repo `String(30)` ✅ | ✅（未寫成 B2B 的 20/50） |
| 9 | `UpdateInvoiceWordStatus.RqHeader`（B2B） | i200 L356 **無**紅色星號 | `b2b-api-reference.md:475` 必填欄標「—」+ 註「原文此列未標紅色星號（其他 API 皆為必填）」 | ✅ 必填未被擅自標反 |
| 10 | `OfflineIssue.RqHeader` | i301 L811 **無**星號 | `offline-api-reference.md:1249` 標「—」+「原文此列未標示紅色星號」 | ✅ |
| 11 | `InvoiceStatus`（離線 §12） | i301 L659 `1:啟用，2:備用字軌` | `enums.md:186-189` 定義 B；並在 §10.1 明示與「設定字軌號碼狀態」的 `0/1/2`（1=暫停、2=啟用）**數字撞號意義相反** | ✅ 語意未錯位 |
| 12 | `Upload_Status` 空值條件 | i200 L1846 `GetIssueConfirm`：`InvoiceCategory=0` 時空值；i200 L2383 `GetAllowance`：`InvoiceCategory=1` 時空值 | repo 兩章各自照抄 `=0` / `=1`，未互相污染 | ✅ |

另：全 39 章節的**章節歸屬檢查**（`desc2.py` 限制在對應章節內比對）通過，代表**沒有把某章的欄位說明搬到別章**；`b2b-api-reference.md` 全檔僅 1 處出現 `B2CInvoice`（L9 的 B2C/B2B 對照表），`offline-api-reference.md` 全檔 0 處出現 `B2BInvoice`。

### 7.3 實際找到的正確性錯誤（2 筆）

#### ❌ 錯誤 A — B2B 附錄 2：對原文的事實陳述錯誤（重要）

- **檔案**：`references/b2b-api-reference.md:4478`
- **repo 寫的**：
  > ⚠️ 原文（官方文件轉為純文字後）在此行後即結束，**未擷取到 (3) 的實際內容**。依 (1) 加密前資料與 (2) 解密結果反推，應還原為 `{"Name":"Test","ID":"A123456789"}`，但本文件不擅自填入…
- **官方原文實際內容（i200 第 2938–2941 行）**：
  ```
  2938 (2)AES 解密結果：
  2939 %7B%22Name%22%3A%22Test%22%2C%22ID%22%3A%22A123456789%22%7D
  2940 (3)URLDecode解碼後結果：
  2941 {"Name":"Test","ID":"A123456789"}
  ```
- **問題**：原文**確實有**第 2941 行。`wc -l` 回報 2940 是因為末行無換行字元——repo 顯然被這點誤導。同一份 repo 在離線文件（i301，末行同樣無換行）卻**正確**轉寫了 `offline-api-reference.md:2126` 的 `{"Name":"Test","ID":"A123456789"}`，處理不一致。
- **影響**：內容值本身猜對了，不會造成串接錯誤；但這是一句**可被證偽的、關於原文的斷言**，直接損害本 repo「只照抄、不編造」的可信度基礎。

#### ❌ 錯誤 B — enums.md：對 i301 CarrierType 的事實陳述錯誤（重要）

- **檔案**：`references/enums.md:244`
- **repo 寫的**：
  > ℹ️ i301（離線）的 `CarrierType` 說明只寫「空字串：無載具」，其餘值請比照 i100。
- **官方原文（i301 第 887 行，`OfflineIssue` 的 Data 表）**：
  ```
  | CarrierType | CarrierType | 載具類別 | String(1) | 空字串：無載具
  列印註記[Print] =1(列印發票) 時，統一編號[CustomerIdentifier]有值時
  1：歐付寶電子發票載具 2：自然人憑證號碼 3：手機條碼載具 4：悠遊卡 5：icash 6：一卡通 7：金融卡 8：信用卡 |
  ```
- **問題**：i301 **明列了 1~8 的完整定義**，並非「只寫空字串」。連帶造成 `enums.md:235-243` 的「來源」欄把 `1`~`8` 全部只標成 `i100 §7`，離線串接者若依此表回查 i301 會以為文件沒寫。
- **佐證此為 enums.md 單點錯誤、非系統性**：`references/offline-api-reference.md:1302` 本身**有**完整照抄 i301 的 1~8，所以規格資料沒錯，錯的是 enums.md 的來源註記與那句斷言。
- **加重情節**：i301 Version History 明載 `V1.2.0 (2025/05/12) 調整非共通性載具_顯碼/隱碼`（i301 L34），亦即載具值是 i301 自己維護的內容，不是「比照 i100」。

---

## 8. 原文瑕疵的處理方式查核（此為正確處理，不算缺漏）

repo 在 `b2b-api-reference.md` 用了 103 個 ⚠️、`offline-api-reference.md` 34 個、`enums.md` 40 個。我逐一驗證了以下 12 處，**全部屬實**：

| # | 原文瑕疵 | 官方行 | repo 標註位置 | 屬實 |
|---:|---|---:|---|:--:|
| 1 | `MaintainMerchantCustomerData` 範例出現參數表沒有的 `CustomerIdentifier` | i200 L143 | `b2b:106` | ✅ |
| 2 | `Notify` 範例 4 個 key 前多半形空白（`" InvoiceNumber"` 等） | i200 L216-219 | `b2b:241` | ✅ |
| 3 | `InvoiceTag` 型態 String(1) 但範例帶數值 `1` | i200 L218 | `b2b:241` | ✅ |
| 4 | `UpdateInvoiceWordStatus` 外層 `RqHeader` 未標必填星號 | i200 L356 | `b2b:475` | ✅ |
| 5 | `VoidWithReIssue.IssueModel.Items[].ItemName` 型態誤植 `String(2)` | i200 L1466 | `b2b:2262` | ✅ |
| 6 | `VoidWithReIssue.IssueModel.Items[].ItemTax` 型態欄空白 | i200 L1471 | `b2b:2263` | ✅ |
| 7 | `TotalAmount` 說明拼字 `SalesAmountAmount` / `TaxAomunt` | i200 §17 | `b2b:2264` | ✅ |
| 8 | `Items` 未標星號但子欄位皆必填 | i200 L1465 | `b2b:2269` | ✅ |
| 9 | `ItemTaxType` 只出現在範例、參數表未列 | i200 L1509,1519,1529 | `b2b:2338` | ✅ |
| 10 | 查詢類 API 傳入 Data 無 `InvoiceCategory`，回傳說明卻以其值決定空值 | i200 §24 §26 §27 §28 | `b2b:3647,3790,3941,4084` | ✅ |
| 11 | `GetInvoiceWordSetting` 範例 `InvoiceCategory:1` 與表述「2:B2B」不符、`Array` 卻缺 `[ ]` | i200 L2822,2804 | `b2b:4235` | ✅ |
| 12 | `GetCompanyNameByTaxID` 傳入範例 key 是 `LoveCode` 而非 `UnifiedBusinessNo` | i200 L2882 | `b2b:4300` | ✅ |
| 13 | i301 §3 注意事項提到「請參照第七章開立發票列印相關參數」，但 i301 §7 是管理發票機台 | i301 L48 | `offline:1921` | ✅ |
| 14 | i301 `MachineIDList` 範例 JSON 缺逗號、`"EFGH` 引號未閉合 | i301 L376-383 | `offline:521` 區 | ✅ |
| 15 | i301 `vat` 說明欄空白 | i301 L879 | 見發現 #5（未標） | ⚠️ |

**這是我在本次稽核中看到最紮實的一項工程**：repo 沒有「順手把原文修對」，而是照抄 + 標註 + 指向官方確認。這正是規格文件應有的處理。

---

## 9. 建議修正事項（依嚴重度排序）

### 🟥 阻斷級：**0 筆**

明確記錄：
- 未自行編造離線附錄 1 的交易狀態代碼表 → 通過
- 未自行編造任何錯誤碼表 → 通過
- 未把歐付寶加密講成 CheckMacValue / SHA256（那是綠界 ECPay 與歐買尬 OMG 的做法，歐付寶電子發票不適用，正確為 AES-128-CBC/PKCS7）→ 通過
- 未寫錯離線路徑前綴 → 通過
- 未漏任何 endpoint、任何欄位 → 通過

### 🟧 重要：3 筆

**#1 · i200 §1／§2／Version History 完全未被轉寫（覆蓋不對稱）**
- 證據：
  ```
  $ grep -rl "支援7天內將B2B電子發票上傳至財政部"  → 0 檔（i200 L50，§1 簡介）
  $ grep -rl "當您完成授權歐付寶後"                → 0 檔（i200 L57，§2 字軌準備步驟）
  $ grep -rl "EinvoiceManual"                      → 0 檔（i200 L61，官方操作手冊 PDF 連結）
  $ grep -rl "平台商測試資料"                      → 0 檔（i200 L67，測試環境表欄名）
  $ grep -rl "新增支援平台商功能"                  → 0 檔（i200 L42，Version History V1.1.0）
  $ grep -rl "新增註銷重開章節"                    → 0 檔（i200 L43，Version History V1.2.0）
  ```
- 具體遺失內容：i200 §2 的**平台商測試資料**（`PlatformID 2046611`／`HashKey s0j9fhLtzYRARFQh`／`HashIV 5awAqXlKm4NlNdEs`／「PlatformID(2046611) 已將 MerchantID(2000132) 設定為子廠商」）、財政部「授權歐付寶／接收設定」兩項前置、字軌與配號設定 4 步驟、`https://vendor.opay.tw/Content/themes/new20150706/EinvoiceManual.pdf`、介接環境注意事項表（TLS 1.2、FQDN、punycode…）。
- 為什麼是重要：`b2b-api-reference.md` 的 27 個 API 章節都用到 `PlatformID`，但整份 B2B reference 沒有一處告訴讀者平台商測試金鑰在哪；且 **離線文件的 §1–§4 與 Version History 全部有轉寫**，B2B 卻沒有——同一個 repo 兩套標準。
- 建議：在 `references/b2b-api-reference.md` 尾端補「附錄 0／前置章節（i200 §1–§2 + Version History）」，格式比照 `offline-api-reference.md:1843-1983`。

**#2 · `b2b-api-reference.md:4478` 對原文的斷言錯誤**（詳見 7.3 錯誤 A）
- 建議：刪除「原文在此行後即結束」的說法，直接照抄 i200 L2941 的 `{"Name":"Test","ID":"A123456789"}`（與 `offline-api-reference.md:2126` 的處理一致）。
- 連帶建議：稽核 repo 內所有「原文未擷取到／原文到此為止」的說法，確認不是被「末行無換行 → `wc -l` 少 1」誤導。

**#3 · `enums.md:244` 對 i301 CarrierType 的斷言錯誤**（詳見 7.3 錯誤 B）
- 建議：刪除該行，並把 `enums.md:235-243` 的「來源」欄由 `i100 §7` 改為 `i100 §7；i301 §13`；`4`~`8` 的「非共通性（顯碼/隱碼）」另可補註 i301 V1.2.0（2025/05/12）「調整非共通性載具_顯碼/隱碼」。

### 🟨 建議：3 筆

**#4 · `enums.md:128` 的 `vat` 來源標註同樣過寬**
- `vat` 的 `1:含稅(預設) / 0:未稅` 定義只出現在 i100（L424 等）；i301 L879 的說明欄是**空白**。但 `enums.md:128` 的「來源」欄寫 `i100 §7 §12；i301 §13`，未如 CarrierType 那樣加註。建議統一為「值定義來源 = i100；i301 §13 有此欄位但未給值」。

**#5 · `api-coverage.json` 的 `chapters` 欄語意含混**
- 現值：`i200: chapters 27`、`i301: chapters 11`。官方 TOC 實際章數是 **29**（i200）與 **15**（i301），差額即非 API 章節。
- 建議改名為 `api_chapters`，或另加 `total_chapters` 欄，避免被當成「文件章數」誤讀。

**#6 · B2B `InvoiceTag` 的 String(1) vs 值 `10` 矛盾未被標註**
- 官方 i200 L208 宣告 `String(1)`，列舉卻含兩碼的 `10:作廢折讓確認`。repo 兩者都照抄了（`b2b:225`），但 `b2b:241` 的 ⚠️ 只提到「範例帶數值而非字串」，沒提長度矛盾。
- repo 對其他同類矛盾（如 `ItemName String(2)`）都有標註，此處遺漏建議補上，以維持一致性。

---

## 附錄 A · 稽核腳本完整輸出

（腳本位於 `/tmp/audit/`；官方文件路徑省略）

```
### A. endpoint 重建（B2B）— 格式：endpoint 起始行 結束行 唯一欄位數
27
MaintainMerchantCustomerData 84 176 24      Notify 177 260 16
AddInvoiceWordSetting 261 347 18            UpdateInvoiceWordStatus 348 440 12
Issue 441 601 37                            IssueConfirm 602 695 13
Invalid 696 778 14                          InvalidConfirm 779 871 13
Reject 872 954 14                           RejectConfirm 955 1050 13
Allowance 1051 1162 26                      AllowanceConfirm 1163 1255 12
CancelAllowance 1256 1339 13                CancelAllowanceConfirm 1340 1412 12
VoidWithReIssue 1413 1577 39                GetIssue 1578 1756 57
GetIssueConfirm 1757 1879 29                GetInvalid 1880 1986 25
GetInvalidConfirm 1987 2090 23              GetReject 2091 2196 24
GetRejectConfirm 2197 2300 23               GetAllowance 2301 2450 45
GetAllowanceConfirm 2451 2544 19            GetAllowanceInvalid 2545 2644 21
GetAllowanceInvalidConfirm 2645 2738 19     GetInvoiceWordSetting 2739 2852 22
GetCompanyNameByTaxID 2853 2942 12

### B. endpoint 重建（離線）
12
GetOfflineMerchantInfo 86 155 11                        GetGovInvoiceWordSetting 156 241 16
OfflineMerchantPosSetting 242 312 12                    QueryOfflineMerchantPosSetting 313 390 13
AddInvoiceWordSetting 391 478 18                        UpdateInvoiceWordStatus 479 551 11
GetOfflineInvoiceWordSettingWithAutoSplit 552 632 16    GetOfflineInvoiceWordSetting 633 715 17
GetOfflineInvoiceWordSettingNumber 716 804 18           OfflineIssue 805 987 43
OfflineInvalid 988 1063 13                              GetInvoiceWordSetting 1064 1235 21

### C. 欄位缺漏 diff（B2B）
repo sections: 27
official-only endpoints: []
repo-only endpoints: []
TOTAL MISSING FIELDS: 0

### D. 欄位缺漏 diff（離線）
repo sections: 12
official-only endpoints: []
repo-only endpoints: []
TOTAL MISSING FIELDS: 0

### E. 型態/必填 嚴格比對（B2B）— 534 唯一欄位 / 700 表格列出現次數
STRICT ISSUES: 0

### F. 型態/必填 嚴格比對（離線）— 184 唯一欄位 / 241 表格列出現次數
STRICT ISSUES: 0

### G. 說明/列舉文字逐段比對（限章節內，B2B）
[VoidWithReIssue.CustomerEmail] L1447 lost 1 chunks e.g. ['測試僅驗規則格式檢核正規表達式為^A–Z']
SECTION-SCOPED LOSSES: 1        ← 偽陽性（935 字元 regex 移入 code block，逐字元 IDENTICAL: True）

### H. 說明/列舉文字逐段比對（限章節內，離線）
[OfflineIssue.CarrierNum]  L888 lost 1 chunks e.g. ['<隱碼id>不會檢核正確性注意事項當Ca']
[OfflineIssue.CarrierNum2] L889 lost 1 chunks e.g. ['實體卡片的<顯碼id>以便發票查詢可以顯']
SECTION-SCOPED LOSSES: 2        ← 偽陽性（`<` `>` 於 Markdown 中跳脫為 &lt; &gt;）

### I. 官方 JSON 範例 key/value 比對
B2B  EXAMPLE DIFFS: 0
離線 EXAMPLE DIFFS: 0

### J. 列舉 token 完整性（全 39 章節，抓 `數字[:：]中文`）
TOTAL ENUM TOKENS MISSING: 0

### K. 8 支指定 API 的欄位總數點算
B2B Issue                                     official= 37 repo= 37 missing=[]
B2B VoidWithReIssue                           official= 39 repo= 39 missing=[]
B2B GetIssue                                  official= 57 repo= 57 missing=[]
B2B GetAllowance                              official= 45 repo= 45 missing=[]
B2B GetIssueConfirm                           official= 29 repo= 29 missing=[]
OFF OfflineIssue                              official= 43 repo= 43 missing=[]
OFF GetInvoiceWordSetting                     official= 21 repo= 21 missing=[]
OFF GetOfflineInvoiceWordSettingWithAutoSplit official= 16 repo= 16 missing=[]

### L. 加密向量獨立驗算
i301 附錄3 (A123456789012345/B123456789012345) → 7woM9Ror...QHeziw==  ✅ 與官方一致
i200 附錄2 (ejCk326UnaZWKisg/q9jcZX8Ib9LM8wYk) → uvI4yrEr...S2Dvg==   ✅ 與官方一致

### M. URLEncode 轉換表逐列比對
official rows: 34 / repo rows: 34
DIFF row 33 ['', '', '%7c', '%7c'] || ['|', '%7c', '%7c']   ← 官方該列符號即為 `|`，repo 用 &#124; 正確跳脫

### N. 路徑前綴與品牌污染檢查
grep -rn "OfflineInvoice/"                          → 0
grep -c  "B2BInvoice"  offline-api-reference.md      → 0
grep -c  "B2CInvoice"  b2b-api-reference.md          → 1（L9 的 B2C/B2B 對照表，正確）
CheckMacValue/SHA256 命中                             → 全部為「這是綠界的做法、歐付寶不適用」的反面警告
```

---

## 附錄 B · 稽核未涵蓋範圍（誠實聲明）

1. **未涵蓋 i100（B2C）**：本次委託範圍為 B2B 與離線。`b2c-api-reference.md`（4954 行，宣稱 30 支）**未經稽核**，其宣稱不應因本報告而被視為已驗證。
2. **圖片內容**：兩份原文的 `[[IMG]]` 一律無法從純文字取得。repo 對每張圖都以「純文字重述 + Mermaid 重繪 + ⚠️ 圖內細節未能自官方文件的文字內容取得，本圖依 API 語意重繪」處理。**我無法驗證重繪內容是否符合原圖**，只能確認其標註方式誠實。
3. **三語言 client**：以 endpoint 路徑字串命中 + 抽查 `b2b_issue` / `b2b_issue_confirm` / 離線 12 支方法簽章為主，**未做全部 65 個方法的參數逐一比對**，亦未實際對 stage 環境發送請求。
4. **guides 全文**：僅逐一驗證 guides 12–18 的關鍵斷言（成對規則、7 天期限、`Upload_Status` 三值、離線取號三支擇一），未逐句稽核 30 份 guide。
