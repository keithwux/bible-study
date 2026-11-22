#!/bin/bash
# 雙擊即開啟本機查經網站（必要時先啟動服務）。
cd "$(dirname "$0")" || exit 1
PORT="${BIBLE_WEB_PORT:-8790}"
if ! curl -s -m 1 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  nohup python3 server.py >> /tmp/bibleapp.log 2>&1 &
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.4
    curl -s -m 1 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  done
fi
open "http://127.0.0.1:$PORT"
