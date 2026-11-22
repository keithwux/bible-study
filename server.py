#!/usr/bin/env python3
""" Minimal local web app for the bible-lookup data.

    python3 server.py            # http://127.0.0.1:8790
    BIBLE_WEB_PORT=9000 python3 server.py

    Read-only: it never writes to the bible-lookup data directory.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("BIBLE_DATA", os.path.expanduser("~/OpenBot/Shared/bible-lookup"))
DB = os.path.join(DATA, "bible.sqlite")
# 字彙分析（信望愛 qp.php）快取：抓過的節寫在這裡，之後離線也有
CACHE_DB = os.path.join(HERE, "cache.sqlite")
LOOKUP = os.path.join(DATA, "lookup.py")
PORT = int(os.environ.get("BIBLE_WEB_PORT", "8790"))
HOST = os.environ.get("BIBLE_WEB_HOST", "127.0.0.1")

# 串珠用的縮寫，順序同 USFM 正典順序
SHORT = ("創 出 利 民 申 書 士 得 撒上 撒下 王上 王下 代上 代下 拉 尼 斯 伯 詩 箴 傳 歌 "
         "賽 耶 哀 結 但 何 珥 摩 俄 拿 彌 鴻 哈 番 該 亞 瑪 太 可 路 約 徒 羅 林前 林後 "
         "加 弗 腓 西 帖前 帖後 提前 提後 多 門 來 雅 彼前 彼後 約一 約二 約三 猶 啟").split()
CODES = ("GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO "
         "ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT MRK "
         "LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE "
         "1JN 2JN 3JN JUD REV").split()
ABBR_TO_CODE = dict(zip(SHORT, CODES))
CODE_TO_ABBR = {v: k for k, v in ABBR_TO_CODE.items()}


def db():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_books():
    with db() as c:
        rows = c.execute("select idx, usfm, name, engs, nch from books order by idx").fetchall()
    books = [dict(r) for r in rows]
    order = {code: i for i, code in enumerate(CODES)}
    books.sort(key=lambda b: order.get(b["usfm"], 99))
    return books


def chapter(code, ch):
    with db() as c:
        b = c.execute("select idx, usfm, name, engs, nch from books where usfm=?", (code,)).fetchone()
        if b is None:
            return None
        if not (1 <= ch <= b["nch"]):
            return None
        zh = c.execute("select vn, t from verses where book=? and ch=? order by vn",
                       (b["idx"], ch)).fetchall()
        en = c.execute("select ver, vn, t from en where book=? and ch=? order by vn",
                       (b["idx"], ch)).fetchall()
    en_map = {}
    for r in en:
        en_map.setdefault(r["vn"], {})[r["ver"]] = r["t"]
    verses = []
    for r in zh:
        toks = json.loads(r["t"])
        text = clean_zh("".join(t[0] for t in toks).replace("\u3000", " "))
        verses.append({"v": r["vn"], "zh": text, "en": en_map.get(r["vn"], {})})
    return {"code": b["usfm"], "name": b["name"], "ch": ch, "nch": b["nch"], "verses": verses}


# ---------- 字彙分析（信望愛 qp.php，線上抓、本機快取） ----------
QP_URL = "https://bible.fhl.net/api/qp.php"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 虛字：冠詞、受詞記號（וְאֵת 這種複合也一併視為虛字）
FUNC_SN = {"H853", "H854", "G3588"}

# 註釋書顯示順序：名稱、版權、中文狀態
NOTES_META = {
    "matthew-henry": ("Matthew Henry", "公有領域", "中文譯本"),
    "jamieson-fausset-brown": ("Jamieson-Fausset-Brown", "公有領域", "中文譯本"),
    "barnes": ("Barnes", "公有領域", "中文譯本"),
    "hodge": ("Hodge", "公有領域", "中文譯本"),
    "tyndale": ("Tyndale Study Bible", "CC BY-SA 4.0", ""),
}


def cache_conn():
    conn = sqlite3.connect(CACHE_DB, timeout=10)
    conn.execute("""create table if not exists parsing(
        code text not null, ch integer not null, v integer not null,
        fetched integer not null, payload text not null,
        primary key(code, ch, v))""")
    return conn


def sn_norm(sn):
    """07225 → H7225，03779 → G25（依書卷新舊約決定字母）。"""
    digits = "".join(c for c in str(sn or "") if c.isdigit())
    if not digits:
        return ""
    return digits


_LEX = {}


def strong_lex(sn):
    """本機 Strong 字典第一行的「音譯 {音標}」，如 G25 → ('agapao', "ag-ap-ah'-o")。"""
    if not sn:
        return "", ""
    if sn in _LEX:
        return _LEX[sn]
    letter, digits = sn[0].upper(), "".join(c for c in str(sn)[1:] if c.isdigit())
    tr = ph = ""
    if digits:
        num = str(int(digits))
        try:
            with db() as conn:
                if letter == "H":
                    row = conn.execute(
                        "select zh from strong where substr(code,1,1)='1'"
                        " and ltrim(substr(code,2),'0')=? limit 1", (num,)).fetchone()
                else:
                    row = conn.execute(
                        "select zh from strong where substr(code,1,1)='0'"
                        " and ltrim(code,'0')=? limit 1", (num,)).fetchone()
            m = re.match(r"^\s*\d+\s+(\S+)\s*\{([^}]*)\}", (row[0] if row else "") or "")
            if m:
                tr, ph = m.group(1).strip(), m.group(2).strip()
        except Exception:
            pass
    _LEX[sn] = (tr, ph)
    return _LEX[sn]


def with_lexicon(payload):
    """每一列補上音譯／音標（快取裡沒有的舊資料也一併補）。"""
    for r in payload.get("rows") or []:
        if r.get("tr") is None:
            r["tr"], r["ph"] = strong_lex(r.get("sn"))
    return payload


def fetch_parsing(code, ch, v):
    """回傳 {literal, rows, is_ot}；先讀快取，沒有才連線抓。"""
    with cache_conn() as c:
        row = c.execute("select payload from parsing where code=? and ch=? and v=?",
                        (code, ch, v)).fetchone()
    if row:
        return with_lexicon(json.loads(row[0])), "cache"
    if code not in CODES:
        return None, "unknown-book"
    bid = CODES.index(code) + 1
    url = f"{QP_URL}?bid={bid}&chap={ch}&sec={v}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = json.loads(r.read().decode("utf-8"))
    is_ot = str(raw.get("N", "0")) == "1"
    prefix = "H" if is_ot else "G"
    literal, rows = "", []
    for rec in raw.get("record") or []:
        if int(rec.get("wid") or 0) == 0:
            literal = (rec.get("exp") or "").strip()
            continue
        code_digits = sn_norm(rec.get("sn"))
        sn = prefix + str(int(code_digits)) if code_digits else ""
        pro = (rec.get("pro") or "").strip()
        wform = " ".join((rec.get("wform") or "").split())
        is_func = sn in FUNC_SN or pro in ("冠詞", "受詞記號") or "受詞記號" in wform
        remark = re.sub(r"\[#[^\]]*#\]", "", rec.get("remark") or "").strip()
        rows.append({"word": (rec.get("word") or "").strip(), "sn": sn,
                     "pro": pro, "wform": wform,
                     "orig": (rec.get("orig") or "").strip(),
                     "exp": " ".join((rec.get("exp") or "").split()),
                     "remark": remark,
                     "func": is_func})
    payload = {"literal": literal, "rows": rows, "is_ot": is_ot}
    with cache_conn() as c:
        c.execute("insert or replace into parsing(code,ch,v,fetched,payload) values(?,?,?,?,?)",
                  (code, ch, v, int(time.time()), json.dumps(payload, ensure_ascii=False)))
    return with_lexicon(payload), "live"


def sn_label(raw):
    """token 裡的編號（10481 → H481、01063 → G2316 這類）。"""
    x = str(raw or "").strip()
    if not x:
        return ""
    letter = "H" if x[0] == "1" else "G"
    digits = re.sub(r"\D", "", x[1:] if letter == "H" else x)
    if not digits:
        return ""
    return letter + str(int(digits))


def verse_tokens(code, ch, vn):
    if code not in CODES:
        return []
    with db() as conn:
        b = conn.execute("select idx from books where usfm=?", (code,)).fetchone()
        if not b:
            return []
        row = conn.execute("select t from verses where book=? and ch=? and vn=?",
                           (b[0], ch, vn)).fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return []


def zh_for_sn(code, ch, vn, sn):
    """該節和合本裡對應這個 Strong 的中文詞。"""
    out = []
    for tok in verse_tokens(code, ch, vn):
        if len(tok) < 2:
            continue
        if sn not in [sn_label(x) for x in str(tok[1]).split(",")]:
            continue
        w = re.sub(r"^[\s，。、；：（）「」『』！？]+", "", str(tok[0])).strip()
        if w and w not in out:
            out.append(w)
    return out


def notes_for(code, ch, vn):
    """註釋書：直接讀合併 MD（每則含中文與英文原文），Tyndale 另讀 en_commentary。"""
    if code not in CODES:
        return []
    import importlib
    global _BL
    try:
        _BL
    except NameError:
        if DATA not in sys.path:
            sys.path.insert(0, DATA)
        _BL = importlib.import_module("lookup")
    md = _BL.md_book(code)
    out = []
    for work, (name, lic, cn_lbl) in NOTES_META.items():
        zh = en = ""
        verses = []
        label = ""
        entries = (md.get(work) or {}).get(ch) or []
        picked = [e for e in entries if vn in (e[0] or [])]
        if picked:
            e = min(picked, key=lambda x: len(x[0] or []))
            verses = list(e[0] or [])
            zh, en = (e[2] or "").strip(), (e[3] or "").strip()
        elif work == "tyndale":
            en, label = _tyndale_for(code, ch, vn)
            verses = [vn]
        if not (zh or en):
            continue
        out.append({"key": work, "name": name, "lic": lic, "cn": cn_lbl,
                    "verses": verses, "range": label, "whole": len(verses) > 12,
                    "zh": zh, "en": en})
    return out


_TYN = {}


def _tyndale_for(code, ch, vn):
    """Tyndale 只有英文，且常以「2:1-3」這種範圍掛在起始節；找不到就往前找最近一則。"""
    path = os.path.join(DATA, "en_commentary", "tyndale", code + ".json")
    if not os.path.exists(path):
        return "", ""
    if path not in _TYN:
        with open(path, encoding="utf-8") as fh:
            _TYN[path] = json.load(fh)
    ents = (_TYN[path].get("chapters", {}).get(str(ch), {}) or {}).get("content", []) or []
    items = []
    for e in ents:
        if e.get("type") != "verse":
            continue
        txt = " ".join(x for x in e.get("content", []) if isinstance(x, str)).strip()
        if not txt:
            continue
        try:
            num = int(str(e.get("number")))
        except (TypeError, ValueError):
            num = None
        items.append((num, txt))
    for num, txt in items:
        if num != vn:
            continue
        m = _RANGE_HEAD.match(txt)
        return txt, (m.group(0).strip().rstrip(".") if m else "")
    for num, txt in items:
        if num is None or num > vn:
            continue
        m = _RANGE_HEAD.match(txt)
        if not m:
            continue
        a = int(m.group(2))
        b = int(m.group(4) or m.group(2))
        if a <= vn <= b:
            return txt, m.group(0).strip().rstrip(".")
    return "", ""


_RANGE_HEAD = re.compile(r"^(\d+):(\d+)(?:-(\d+):)?(\d+)?")


def run_lookup(args):
    try:
        p = subprocess.run([sys.executable, "-I", LOOKUP] + args,
                           capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "查詢逾時，請縮小範圍。"
    out = (p.stdout or "").strip()
    if not out and p.stderr:
        out = p.stderr.strip()
    return out


REF_LINE = re.compile(r"^-\s*(\S+)\s+(\d+):(\d+)\s*(.*)$")


def clean_zh(t):
    """去掉中文字之間多餘的半形空白（原文資料逐詞標記留下的）。"""
    t = (t or "").replace("\xa0", " ")
    t = re.sub(r"(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _xref(abbr, ch, v, text, rest=False):
    code = ABBR_TO_CODE.get(abbr)
    if not code:
        return None
    return {"code": code, "abbr": abbr, "ch": int(ch), "v": int(v),
            "label": f"{abbr} {ch}:{v}",
            "text": clean_zh(text), "rest": rest}


def parse_xrefs(body):
    """串珠段落 → 結構化參照，讓前端可以點到那一章。"""
    items = []
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            m = REF_LINE.match(line)
            if m:
                item = _xref(m.group(1), m.group(2), m.group(3), m.group(4))
                if item:
                    items.append(item)
        elif line.startswith("其餘:"):
            for seg in line[3:].split(";"):
                m = re.match(r"^\s*(\S+)\s+(\d+):([\d,]+)\s*$", seg)
                if not m:
                    continue
                for vv in m.group(3).split(","):
                    if vv.isdigit():
                        item = _xref(m.group(1), m.group(2), vv, "", rest=True)
                        if item:
                            items.append(item)
    # 同一節可能重複
    seen, out = set(), []
    for it in items:
        key = (it["code"], it["ch"], it["v"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def parse_card(md):
    """把 lookup.py --card 的 markdown 拆成 標題 / 譯本 / 段落 / 串珠。"""
    title = ""
    translations = []
    sections = []
    cur = None
    for raw in md.splitlines():
        line = raw.rstrip()
        if cur is None and line.startswith("## ") and not title:
            title = line[3:].strip()
            continue
        if line.startswith("### "):
            cur = {"title": line[4:].strip(), "body": []}
            sections.append(cur)
            continue
        if cur is None:
            m = re.match(r"^\*\*(.+?)\*\*[:：]\s*(.*)$", line)
            if m:
                translations.append({"label": m.group(1), "text": clean_zh(m.group(2))})
            continue
        cur["body"].append(raw)
    xrefs = []
    kept = []
    for sec in sections:
        if sec["title"].startswith("串珠"):
            xrefs = parse_xrefs(sec["body"])
            continue
        body = "\n".join(sec["body"]).strip()
        if body:
            kept.append({"title": sec["title"], "body": body})
    return {"title": title, "translations": translations,
            "sections": kept, "xrefs": xrefs}


def parse_hits(md):
    """搜尋結果 → 可點的經文命中。"""
    hits, rest = [], []
    for raw in md.splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            rest.append(raw)
            continue
        m = REF_LINE.match(line)
        if not m:
            rest.append(raw)
            continue
        code = ABBR_TO_CODE.get(m.group(1))
        if not code:
            rest.append(raw)
            continue
        hits.append({"code": code, "ch": int(m.group(2)), "v": int(m.group(3)),
                     "label": f"{m.group(1)} {m.group(2)}:{m.group(3)}",
                     "text": clean_zh(m.group(4))})
    return hits, "\n".join(rest).strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "BibleApp/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self):
        with open(os.path.join(HERE, "index.html"), "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        one = lambda k, d="": (q.get(k) or [d])[0]
        try:
            if u.path in ("/", "/index.html"):
                self.send_html()
                return
            if u.path == "/api/health":
                self.send_json({"ok": True, "data": DATA, "port": PORT})
                return
            if u.path == "/api/books":
                self.send_json({"books": list_books()})
                return
            if u.path == "/api/chapter":
                data = chapter(one("code", "GEN"), int(one("ch", "1") or 1))
                if data is None:
                    self.send_json({"error": "找不到書卷或章"}, 404)
                else:
                    self.send_json(data)
                return
            if u.path == "/api/card":
                ref = one("ref").strip()
                if not ref:
                    self.send_json({"error": "缺少 ref"}, 400)
                    return
                args = [ref, "--card"]
                if one("nodict") == "1":
                    args.append("--no-dict")
                if one("nozhcom") == "1":
                    args.append("--no-zhcom")
                if one("noencom") == "1":
                    args.append("--no-encom")
                self.send_json({"ref": ref, "markdown": run_lookup(args)})
                return
            if u.path == "/api/study":
                ref = one("ref").strip()
                if not ref:
                    self.send_json({"error": "缺少 ref"}, 400)
                    return
                args = [ref, "--card"]
                if one("noencom") == "1":
                    args.append("--no-encom")
                md = run_lookup(args)
                data = parse_card(md)
                data["ref"] = ref
                data["markdown"] = md
                self.send_json(data)
                return
            if u.path == "/api/parsing":
                code = one("code", "").strip().upper()
                try:
                    ch, v = int(one("ch", "0")), int(one("v", "0"))
                except ValueError:
                    self.send_json({"ok": False, "error": "章節格式錯誤"}, 400)
                    return
                if not code or ch < 1 or v < 1:
                    self.send_json({"ok": False, "error": "缺少 code / ch / v"}, 400)
                    return
                try:
                    payload, source = fetch_parsing(code, ch, v)
                except Exception as exc:
                    self.send_json({"ok": False, "error": f"線上取得失敗：{exc}"})
                    return
                if payload is None:
                    self.send_json({"ok": False, "error": f"不認得的書卷 {code}"})
                    return
                self.send_json({"ok": True, "source": source, **payload})
                return
            if u.path == "/api/forms":
                code = one("code", "").strip().upper()
                sn = one("sn", "").strip().upper()
                try:
                    ch, v = int(one("ch", "0")), int(one("v", "0"))
                except ValueError:
                    self.send_json({"ok": False, "error": "章節格式錯誤"}, 400)
                    return
                try:
                    payload, _src = fetch_parsing(code, ch, v)
                except Exception as exc:
                    self.send_json({"ok": False, "error": f"線上取得失敗：{exc}"})
                    return
                rows = (payload or {}).get("rows") or []
                forms = [{"word": r.get("word"), "tr": r.get("tr"), "ph": r.get("ph"),
                          "pro": r.get("pro"), "wform": r.get("wform")}
                         for r in rows if r.get("sn") == sn]
                self.send_json({"ok": True, "sn": sn, "forms": forms})
                return
            if u.path == "/api/notes":
                code = one("code", "").strip().upper()
                try:
                    ch, v = int(one("ch", "0")), int(one("v", "0"))
                except ValueError:
                    self.send_json({"ok": False, "error": "章節格式錯誤"}, 400)
                    return
                try:
                    src = notes_for(code, ch, v)
                except Exception as exc:
                    self.send_json({"ok": False, "error": f"讀註解失敗：{exc}"})
                    return
                self.send_json({"ok": True, "sources": src})
                return
            if u.path == "/api/search":
                kind, term = one("kind", "grep"), one("q").strip()
                if not term:
                    self.send_json({"error": "缺少 q"}, 400)
                    return
                flag = {"grep": "--grep", "strong": "--strong", "word": "--word"}.get(kind)
                if flag is None:
                    self.send_json({"error": "kind 必須是 grep / strong / word"}, 400)
                    return
                md = run_lookup([flag, term])
                hits, rest = parse_hits(md)
                if kind == "strong":
                    sn = term.upper().strip()
                    tr, ph = strong_lex(sn)
                    for h in hits:
                        h["sn"] = sn
                        h["zh"] = zh_for_sn(h["code"], h["ch"], h["v"], sn)
                        h["tr"], h["ph"] = tr, ph
                title = ""
                for line in md.splitlines():
                    if line.startswith("## "):
                        title = line[3:].strip()
                        break
                self.send_json({"q": term, "kind": kind, "title": title,
                                "hits": hits, "rest": rest, "markdown": md})
                return
            self.send_json({"error": "not found"}, 404)
        except BrokenPipeError:
            pass
        except Exception as exc:  # keep the server alive on a bad request
            self.send_json({"error": str(exc)}, 500)


def start_tls():
    """同一個程序再開一個 HTTPS 埠（手機瀏覽器強制 HTTPS 時用）。

    由環境變數開啟：BIBLE_WEB_TLS_PORT；憑證預設 <程式目錄>/certs/cert.pem 與 key.pem，
    可用 BIBLE_TLS_CERT / BIBLE_TLS_KEY 指定。找不到憑證就只跑 HTTP。
    """
    tls_port = (os.environ.get("BIBLE_WEB_TLS_PORT") or "").strip()
    if not tls_port:
        return None
    cert = os.environ.get("BIBLE_TLS_CERT") or os.path.join(HERE, "certs", "cert.pem")
    key = os.environ.get("BIBLE_TLS_KEY") or os.path.join(HERE, "certs", "key.pem")
    if not (os.path.exists(cert) and os.path.exists(key)):
        print(f"（未開 HTTPS：找不到憑證 {cert}）", file=sys.stderr)
        return None
    import ssl
    import threading
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv = ThreadingHTTPServer((HOST, int(tls_port)), Handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"查經網站(HTTPS): https://{HOST}:{tls_port}")
    return srv


def main():
    if not os.path.exists(DB):
        print("找不到 bible.sqlite：", DB, "\n先執行 python3 -I bible_db.py --build", file=sys.stderr)
        raise SystemExit(1)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"查經網站: http://{HOST}:{PORT}   資料: {DATA}")
    start_tls()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()