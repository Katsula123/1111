# 台灣汽車日報｜GitHub Pages 專案

這個專案包含靜態網站、RSS 新聞整理程式，以及每天自動更新新聞資料的 GitHub Actions 工作流程。

## 專案檔案

- `index.html`：網站首頁、樣式與前端 JavaScript。
- `news.json`：前端讀取的新聞資料；第一次更新前為空資料。
- `scripts/fetch_news.py`：讀取公開 RSS／Google 新聞 RSS 搜尋結果、整理分類與去重。
- `requirements.txt`：Python 依賴套件。
- `.github/workflows/update-news.yml`：每天自動更新與手動執行的工作流程。

## 部署到 GitHub Pages

1. 在 GitHub 建立一個新的 repository，例如 `taiwan-auto-daily`。
2. 將這個資料夾內的所有檔案與資料夾上傳到 repository 根目錄。請保留 `.github/workflows/` 這個隱藏資料夾。
3. 開啟 repository 的 **Settings → Pages**。
4. 在 **Build and deployment** 中選擇 **Deploy from a branch**。
5. Branch 選 `main`，資料夾選 `/(root)`，再按 **Save**。
6. 開啟 **Actions** 分頁，選擇 **Update Taiwan Auto Daily News**，按 **Run workflow** 執行首次更新。
7. 等待工作流程完成，再開啟 Pages 網址並重新整理。

如果看不到 Actions 工作流程，請確認 `.github/workflows/update-news.yml` 已上傳到正確路徑。若工作流程不能推送 `news.json`，請到 **Settings → Actions → General → Workflow permissions**，確認允許工作流程有寫入 repository 的權限（如組織政策允許）。

## 自動更新時間

排程設為每天 UTC 22:20，約為台灣時間隔日 06:20。GitHub Actions 的排程可能延遲，不能保證精確到分鐘。首次上傳時，workflow 也會因程式檔案變更而自動觸發；也可在 Actions 中手動執行。

## 新聞來源與限制

- 以 Google News RSS 搜尋結果彙整台灣新車、試駕、車價、品牌、交通法規與產業消息，並包含交通部 RSS。
- 新聞來源與 RSS 格式可能變更；部分來源不一定提供摘要或圖片。若沒有圖片，網站會顯示汽車示意圖。
- Google News RSS 的文章連結通常會導向新聞發布來源；若來源或 Google 改變連結行為，可能需要調整程式。
- 本專案只展示標題、短摘要、來源與連結，不複製全文。請遵守各來源的 RSS 使用規範與授權條款；公開或商業用途前，請逐一確認來源的使用條件。
- `news.json` 只有在 GitHub Actions 成功執行並推送更新後才會有新聞。若沒有新聞，請在 Actions 檢查執行紀錄。

## 修改更新頻率

編輯 `.github/workflows/update-news.yml` 中的 `cron`。目前 `20 22 * * *` 表示每天 UTC 22:20，也就是台灣時間隔日約 06:20。
