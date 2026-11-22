#!/bin/bash
# 在 Mac mini 上執行：把查經站裝成「開機自動啟動」的本機服務。
#
#   ./install-macmini.sh [資料目錄] [埠]
#   例：./install-macmini.sh ~/bible-data 8790
#
# 需要：這個資料夾裡的 index.html、server.py，以及一份含 bible.sqlite 的資料目錄。
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
# 允許腳本放在專案子資料夾（如 deploy/）：程式在上層
if [ ! -f "$SRC/index.html" ] && [ -f "$SRC/../index.html" ]; then
  SRC="$(cd "$SRC/.." && pwd)"
fi
APP_DIR="$HOME/bible-app"
DATA_DIR="${1:-$HOME/bible-data}"
PORT="${2:-8790}"
LABEL="local.bible.host"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$SRC/index.html" ] || [ ! -f "$SRC/server.py" ]; then
  echo "錯誤：這個腳本要和 index.html、server.py 放在同一個資料夾。"; exit 1
fi
if [ ! -f "$DATA_DIR/bible.sqlite" ]; then
  echo "錯誤：$DATA_DIR 裡找不到 bible.sqlite。"
  echo "請先把資料放到那裡，或用參數指定，例如：./install-macmini.sh ~/bible-data"
  exit 1
fi
command -v python3 >/dev/null || { echo "錯誤：找不到 python3，請先安裝 Xcode 命令列工具或 Python。"; exit 1; }

mkdir -p "$APP_DIR"
cp "$SRC/index.html" "$SRC/server.py" "$APP_DIR/"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$APP_DIR/server.py</string>
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>BIBLE_DATA</key><string>$DATA_DIR</string>
    <key>BIBLE_WEB_HOST</key><string>0.0.0.0</string>
    <key>BIBLE_WEB_PORT</key><string>$PORT</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/bible-host.log</string>
  <key>StandardErrorPath</key><string>/tmp/bible-host.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 2

if curl -s -m 3 "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
  echo
  echo "裝好了，已設為開機自動啟動（launchd：$LABEL）。"
  echo "本機：http://127.0.0.1:$PORT"
  [ -n "$IP" ] && echo "同網段：http://$IP:$PORT"
  echo
  echo "日誌：/tmp/bible-host.log"
  echo "停止：launchctl bootout gui/$(id -u)/$LABEL"
else
  echo "服務沒起來，請看 /tmp/bible-host.log"; tail -20 /tmp/bible-host.log; exit 1
fi
