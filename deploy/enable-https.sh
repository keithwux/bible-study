#!/bin/bash
# 在 Mac mini 上執行：替查經站加上 HTTPS（第二個埠，自簽憑證）。
#
#   ./enable-https.sh [HTTPS 埠]     # 預設 8791
#
# 為什麼要這個：部分手機瀏覽器（Chrome 的「永遠使用安全連線」、
# 或 App 內建瀏覽器）會拒絕或強制升級 http:// 網址。
# 這個腳本產生一張自簽憑證（IP + 電腦名稱），寫入 launchd 設定並重啟服務，
# 之後 https://<IP>:8791 就能開；憑證不是公信機構簽的，手機會跳一次警告，
# 選「繼續前往」即可。
set -e

LABEL="local.bible.host"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_DIR="$HOME/bible-app"
TLS_PORT="${1:-8791}"
CERT_DIR="$APP_DIR/certs"

[ -f "$PLIST" ] || { echo "錯誤：找不到 $PLIST，請先跑 install-macmini.sh"; exit 1; }
[ -f "$APP_DIR/server.py" ] || { echo "錯誤：找不到 $APP_DIR/server.py"; exit 1; }
command -v openssl >/dev/null || { echo "錯誤：找不到 openssl"; exit 1; }

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
HOSTNAME_LOCAL="$(hostname -s 2>/dev/null || scutil --get LocalHostName 2>/dev/null || echo mac).local"

mkdir -p "$CERT_DIR"

SAN="DNS:localhost,DNS:$HOSTNAME_LOCAL,IP:127.0.0.1"
[ -n "$IP" ] && SAN="$SAN,IP:$IP"

echo "產生自簽憑證（$SAN）…"
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
  -subj "/CN=$HOSTNAME_LOCAL" \
  -addext "subjectAltName=$SAN" >/dev/null 2>&1
chmod 600 "$CERT_DIR/key.pem"

echo "寫入 launchd 設定（HTTPS 埠 $TLS_PORT）…"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:BIBLE_WEB_TLS_PORT string $TLS_PORT" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:BIBLE_WEB_TLS_PORT $TLS_PORT" "$PLIST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 2

if curl -sk -m 5 "https://127.0.0.1:$TLS_PORT/api/health" | grep -q '"ok": true'; then
  echo
  echo "HTTPS 已開啟。"
  echo "本機：https://127.0.0.1:$TLS_PORT"
  [ -n "$IP" ] && echo "同網段：https://$IP:$TLS_PORT   ← 手機用這個"
  echo
  echo "手機第一次開會顯示「連線不是私人連線」（因為不是公信機構簽的）："
  echo "  iPhone Safari：顯示詳細資料 → 造訪此網站"
  echo "  Android Chrome：進階 → 繼續前往"
  echo "想完全沒有警告，要換成有網域 + 公信憑證的方式（例如 Tailscale 的 https）。"
  echo "日誌：/tmp/bible-host.log"
else
  echo "HTTPS 沒起來，請看 /tmp/bible-host.log"; tail -20 /tmp/bible-host.log; exit 1
fi
