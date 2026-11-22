#!/bin/bash
# 在同一個 Wi-Fi 分享給手機與朋友：綁 0.0.0.0，並印出手機要打的網址。
cd "$(dirname "$0")" || exit 1
PORT="${BIBLE_WEB_PORT:-8790}"

# 若已有服務佔著這個埠，先關掉，改用對外模式重開
PID=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ -n "$PID" ]; then kill "$PID" 2>/dev/null; sleep 1; fi

BIBLE_WEB_HOST=0.0.0.0 nohup python3 server.py >> /tmp/bibleapp.log 2>&1 &
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 0.4
  curl -s -m 1 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
done

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
if [ -z "$IP" ]; then
  echo "找不到本機 Wi-Fi 位址；請確認已連上同一個網路。"
else
  echo
  echo "同一 Wi-Fi 的手機／平板／朋友，用瀏覽器打開："
  echo "    http://$IP:$PORT"
  echo
  echo "本機：http://127.0.0.1:$PORT"
  echo "（離開這個 Wi-Fi 就連不到；要跨網路請看 README 的說明）"
  echo
fi
open "http://127.0.0.1:$PORT"
