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
TLS_PORT="${3:-8791}"     # 第二個埠，HTTPS（手機瀏覽器強制 HTTPS 時用；0 表示不開）
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
DATA_DIR="$(cd "$DATA_DIR" && pwd)"     # 存進 plist 前轉成絕對路徑
command -v python3 >/dev/null || { echo "錯誤：找不到 python3，請先安裝 Xcode 命令列工具或 Python。"; exit 1; }

mkdir -p "$APP_DIR"
cp "$SRC/index.html" "$SRC/server.py" "$APP_DIR/"

# 自簽憑證（HTTPS 用）：有 openssl 就產生，沒有就只跑 HTTP
TLS_ENV=""
if [ "$TLS_PORT" != "0" ] && command -v openssl >/dev/null; then
  CERT_DIR="$APP_DIR/certs"; mkdir -p "$CERT_DIR"
  IP0=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
  LNAME="$(scutil --get LocalHostName 2>/dev/null || echo mac).local"
  SAN="DNS:localhost,DNS:$LNAME,IP:127.0.0.1"
  [ -n "$IP0" ] && SAN="$SAN,IP:$IP0"
  if [ ! -f "$CERT_DIR/cert.pem" ]; then
    openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
      -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
      -subj "/CN=$LNAME" -addext "subjectAltName=$SAN" >/dev/null 2>&1 && chmod 600 "$CERT_DIR/key.pem" || TLS_PORT=0
  fi
  [ -f "$CERT_DIR/cert.pem" ] || TLS_PORT=0
else
  TLS_PORT=0
fi

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
    <key>BIBLE_WEB_TLS_PORT</key><string>$TLS_PORT</string>
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
  if [ "$TLS_PORT" != "0" ]; then
    echo "HTTPS："
    [ -n "$IP" ] && echo "  手機：https://$IP:$TLS_PORT   ← 瀏覽器只准 HTTPS 時用這個"
    echo "  自簽憑證，第一次會跳警告，選「繼續前往／進階 → 繼續」即可。"
  fi
  echo
  echo "日誌：/tmp/bible-host.log"
  echo "停止：launchctl bootout gui/$(id -u)/$LABEL"
else
  echo "服務沒起來，請看 /tmp/bible-host.log"; tail -20 /tmp/bible-host.log; exit 1
fi
