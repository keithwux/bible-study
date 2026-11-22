# 用 Mac mini 當主機（零月費）

把查經站放在家裡那台 Mac mini 上跑，手機與朋友在同一個 Wi-Fi 就能用；要跨網路再用 Tailscale。

## 一、把東西搬過去

需要兩樣：**程式**（這個資料夾的 `index.html`、`server.py`、`deploy/`）與**資料**（`bible-lookup` 資料夾，約 282 MB）。

最簡單是 Finder／AirDrop：
1. 在 MacBook 上把 `~/OpenBot/Shared/bible-app` 整個拖到 AirDrop → Mac mini
2. 再把 `~/OpenBot/Shared/bible-lookup` 也 AirDrop 過去
3. 在 mini 上把資料放到 `~/bible-data`（改名或搬移都可，脚本只用路徑）

也可以用終端機（Mac mini 上執行，需 MacBook 先開「系統設定 → 一般 → 共享 → 遠端登入」）：

```bash
rsync -av --progress keithwux@192.168.0.242:OpenBot/Shared/bible-lookup/ ~/bible-data/
rsync -av --progress keithwux@192.168.0.242:OpenBot/Shared/bible-app/   ~/bible-app-src/
```

## 二、安裝（在 Mac mini 上）

```bash
cd ~/bible-app-src/deploy
chmod +x install-macmini.sh
./install-macmini.sh ~/bible-data 8790
```

腳本會：複製程式到 `~/bible-app`、寫一個 launchd 服務（開機自動啟動、當掉自動重啟）、綁 `0.0.0.0:8790`（同網段可連），最後印出網址。

驗證：`curl http://127.0.0.1:8790/api/health` 應回 JSON；mini 上瀏覽器開 `http://127.0.0.1:8790` 看得到經文。

## 三、讓它一直開著

- **不要睡眠**：系統設定 → 能源 → 「避免電腦在顯示器關閉時自動進入睡眠」打開；或終端機 `sudo pmset -a sleep 0 disksleep 0`
- **固定 IP**：路由器裡把 mini 的 MAC 綁一個固定 IP（DHCP 保留），否則重開機後網址可能變
- **開機自動啟動**：install 腳本已用 launchd 處理，mini 重開機會自己起來
- **防火牆**：系統設定 → 網路 → 防火牆，若開啟，允許 Python 接受連入

## 四、手機與朋友

同一個 Wi-Fi：`http://<mini 的 IP>:8790`（腳本會印出來）。

不同網路：裝 [Tailscale](https://tailscale.com/) 在 mini 與對方裝置上，登入同一個網路後用 `http://<mini 的機器名>:8790`。這樣不用對外開放。

## 五、注意

- 目前**沒有帳號密碼**，能連上的人都看得到全部內容。只在信任的網路分享；要對外請先加一層登入（可跟我說，我加）。
- 資料授權僅限個人研讀，不要放上公開網站。
- 更新程式：把新的 `index.html`／`server.py` 複製到 `~/bible-app`，再 `launchctl kickstart -k gui/$(id -u)/local.bible.host`
