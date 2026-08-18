# opay-test-console — 歐付寶電子發票測試環境全鏈路儀表板

三行啟動：

```bash
cp .env.example .env && python3 -m pip install fastapi uvicorn requests pycryptodome
set -a && . ./.env && set +a
python3 -m uvicorn backend:app --reload --port 8080   # 開啟 http://127.0.0.1:8080
```

## 三關流程

| 關卡 | 做什麼 | 會不會連外網 | 會不會產生資料 |
|---|---|---|---|
| ① 六步自我驗證 | AES 向量、URLEncode、外層組裝、時差、加解密往返、錯誤處理 | 否 | 否 |
| ② 唯讀 API 實測 | `CheckBarcode`、`CheckLoveCode`、`GetCompanyNameByTaxID`、`GetInvoiceWordSetting` | 是（測試環境） | 否 |
| ③ 開立測試發票 | `Issue` | 是（測試環境） | **會**，且無法刪除 |

- 第③關預設關閉，需在 `.env` 設 `OPAY_ALLOW_ISSUE_DEMO=true`，前端還要再勾一次確認框。
- 檔案：`backend.py`（FastAPI）、`console.html`（單檔前端，不用任何 CDN）、`.env.example`。
- 無障礙：深色底白字對比 ≥9:1、狀態採「顏色＋圖示＋文字」三重編碼、全鍵盤可操作且有白色 focus ring、觸控目標 ≥48px、每個輸入框都有 `<label>`、狀態變化以 `aria-live="polite"` 播報。
