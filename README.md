# 查經 Bible Study

專案頁（截圖與說明）：<https://keithwux.github.io/bible-study/>

一個自用的離線查經網頁：左邊讀經文，右邊看原文、Strong 字典、CBOL 註解、各本註釋書與串珠。

- 單一 Python 檔後端（只用標準庫）＋ 單一 HTML 前端，無框架、無 build step
- 桌面／平板橫向：左右雙欄，中間細線可拖曳調寬度
- 平板直立／手機：單欄，上方「經文／研讀」分頁切換
- 資料全部在本機，斷網可讀；只有「原文字彙分析」第一次看某節時需要連線，之後自動快取

## 畫面與功能

| 區塊 | 內容 |
|---|---|
| 經文 | 和合本；可切換顯示 KJV／BSB／ASV |
| 原文字彙分析 | 原文語序逐字：和合本用詞、原文字、Strong 編號、英文音譯與音標、詞性字形、原型、字義 |
| 原文直譯 | 依原文語序的直譯句 |
| CBOL 註解重點 | 中文註解，四級大綱自動排版，經文參照可點 |
| 註解 | Matthew Henry／J.F.B.／Barnes／Tyndale，中文譯本＋英文原文可展開 |
| 串珠 | 相關經文，點擊直接跳該章該節 |
| 搜尋 | 經文參照、關鍵字、原文詞、Strong 編號 |

鍵盤：`↑` `↓` 換節、`←` `→` 換章、`/` 搜尋、`Esc` 關閉。字級有 A−／A／A+ 三級，選擇會記住。

## 需要什麼

程式本身不含聖經資料。執行前你需要一份本機資料集，當中含有：

- `bible.sqlite`：和合本經文（含每個字的 Strong 編號）、KJV／BSB／ASV 三種英文譯本、Strong 中英文字典
- `zh_commentary/md_merged/<USFM>.md`：各註釋書的中文與英文原文（66 卷）
- `en_commentary/tyndale/<USFM>.json`：Tyndale 英文註解
- `lookup.py`：資料查詢模組（本專案以 `import lookup` 使用）

本 repo 刻意**不上傳**這些資料，因為它們的授權只涵蓋個人使用（見下方版權）。資料來源是信望愛站（bible.fhl.net）的公開資料集，請自行依其授權取得。

## 安裝與啟動

```bash
git clone https://github.com/keithwux/bible-study.git
cd bible-study

# 指向你的資料目錄（預設 ~/OpenBot/Shared/bible-lookup）
export BIBLE_DATA=/path/to/your/bible-data

python3 server.py          # http://127.0.0.1:8790
BIBLE_WEB_PORT=9000 python3 server.py
BIBLE_WEB_HOST=0.0.0.0 python3 server.py   # 讓同網段其他裝置連進來
```

資料目錄預期結構：

```
bible-data/
├── bible.sqlite
├── lookup.py
├── zh_commentary/md_merged/GEN.md …
└── en_commentary/tyndale/GEN.json …
```

`cache.sqlite` 會在專案目錄自動建立，存放「原文字彙分析」抓過的節，可安全刪除。

## 檔案

| 檔案 | 用途 |
|---|---|
| `server.py` | HTTP 伺服器與 API：`/api/books`、`/api/chapter`、`/api/study`、`/api/parsing`、`/api/notes`、`/api/search` |
| `index.html` | 全部前端（HTML／CSS／JS 同一個檔） |
| `run.command` | macOS 雙擊啟動 |

## 在手機上用、分享給朋友

**同一個 Wi-Fi（最快，不用設定）**

```bash
./share.command                     # macOS 雙擊也可以
# 或手動：
BIBLE_WEB_HOST=0.0.0.0 python3 server.py
```

它會印出這台電腦的區網網址（形如 `http://192.168.0.242:8790`），手機或同一 Wi-Fi 的朋友用瀏覽器輸入即可。Mac 要開著、服務要跑著；離開這個網路就連不到。

**跨網路（手機用行動網路、朋友在別的地方）**

- [Tailscale](https://tailscale.com/)：把電腦和對方的裝置放進同一個私人網路，走 `http://<機器名>:8790`。不需要對外開放，資料不外流，最適合幾個人共用。
- Cloudflare Tunnel／ngrok 之類：可產生一個公開網址，但等於把整站公開到網際網路，任何人拿到連結都能讀；本專案的資料授權僅限個人研讀，公開前請自行評估。

**注意**：應用程式沒有帳號與密碼，能連到這個位址的人都能看到全部內容。只在信任的網路分享，用完把服務關掉（`kill $(lsof -t -i:8790)`）。

## 版權

- **經文**：和合本與 KJV／BSB／ASV 的授權各異，只在你取得資料的授權範圍內使用。
- **Strong 編號與字典、CBOL 註解、串珠**：來自信望愛站，供個人研讀使用，不得再散布。
- **註釋書**：Matthew Henry、Jamieson-Fausset-Brown、Barnes 為公有領域；Tyndale Study Bible 為 CC BY-SA 4.0。
- **本專案程式碼**：自由使用與修改；轉載資料前請自行確認上述授權。

本專案與信望愛站無隸屬關係。
