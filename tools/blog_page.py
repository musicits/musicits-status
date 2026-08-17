#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""휴대폰에서 돌린 블로그 도구 결과를 cloud/blog/index.html 한 장으로 그린다.

깃허브 Actions 안에서만 돌아간다(.github/workflows/blog.yml).
도구가 만든 `리포트.txt` 를 도구별·회차별로 모아 보여주기만 한다. 수치를 다시
계산하지 않는다 — 두 벌로 두면 한쪽이 낡는다.
"""
import html as H
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blogview  # noqa: E402  (PC 메인 페이지와 같은 화면을 쓴다)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RESULTS = os.path.join(REPO, "tools", "blog", "2_결과")
OUT = os.path.join(REPO, "cloud", "blog", "index.html")

KST = timezone(timedelta(hours=9))
KEEP = 8                 # 도구마다 보여줄 회차 수
TOOLS = ("1. 키워드 발굴", "2. 제목 진단", "3. 성과 추적", "4. 이웃 발굴")

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^(\d{2})시(\d{2})분$")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def e(x):
    return H.escape(str(x if x is not None else ""))


def linkify(escaped):
    return URL_RE.sub(
        lambda m: '<a href="%s" target="_blank" rel="noopener">%s</a>'
        % (m.group(0), m.group(0)), escaped)


DARK_VARS = ("--bg:#15171a;--fg:#e6e8ea;--card:#1e2126;--line:#2c3037;"
             "--mut:#9aa1a9;--acc:#7ea2ff")
DARK_CSS = ('@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){%s}}\n'
            ':root[data-theme="dark"]{%s}' % (DARK_VARS, DARK_VARS))

HEAD_JS = ("try{var t=localStorage.getItem('theme');"
           "if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}")

CSS = """
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{--bg:#f4f5f7;--fg:#1a1d21;--card:#fff;--line:#e3e6ea;--mut:#6b7280;--acc:#1f4fd8}
__DARK__
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
 font:15px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic',sans-serif}
.wrap{max-width:860px;margin:0 auto;
 padding:18px 14px calc(60px + env(safe-area-inset-bottom,0px))}
h1{margin:0 0 4px;font-size:20px;letter-spacing:-.4px}
h2{margin:22px 0 9px;font-size:15px}
.sub{margin:0 0 16px;color:var(--mut);font-size:12.5px}
a.back{display:inline-block;margin:0 0 16px;color:var(--acc);font-size:13.5px;font-weight:600}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;
 margin:0 0 8px;overflow:hidden}
summary{cursor:pointer;padding:13px 15px;min-height:48px;font-weight:600;font-size:14px;
 display:flex;justify-content:space-between;gap:10px;align-items:center}
summary::-webkit-details-marker{display:none}
details[open] summary{color:var(--acc)}
summary .meta{font-weight:400;font-size:12px;color:var(--mut);white-space:nowrap}
.body{padding:6px 15px 16px;border-top:1px solid var(--line)}
pre{margin:0;font:12.5px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;
 white-space:pre-wrap;word-break:break-word}
a{color:var(--acc);word-break:break-all}
.empty{color:var(--mut);font-size:13.5px}
.note{font-size:12.5px;color:var(--mut);background:var(--card);border:1px solid var(--line);
 border-radius:9px;padding:11px 13px;margin:0 0 16px}
.tiles{display:flex;flex-wrap:wrap;gap:14px;margin:2px 0 4px}
.tile{min-width:70px}
.tv{display:block;font-size:19px;font-weight:700;letter-spacing:-.3px}
.tl{display:block;font-size:11.5px;color:var(--mut);margin-top:1px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:11.5px}
""".replace("__DARK__", DARK_CSS) + blogview.CSS

PAGE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#1f4fd8">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>휴대폰 블로그 도구 결과</title>
<script>%s</script>
<style>%s</style></head><body><div class="wrap">
<a class="back" href="../../">← 전체 현황으로</a>
<h1>휴대폰 블로그 도구 결과</h1>
<p class="sub">%s 기준</p>
<p class="note">여기 쌓이는 것은 <b>깃허브에서 돌린</b> 결과입니다. PC 에서 돌린 것과는
회차가 따로 관리되고, 성과 추적의 '지난 회차 대비' 비교도 각자 자기 기록을 봅니다.
엑셀 파일은 만들지 않습니다.</p>
%s</div></body></html>
"""


def runs(tool):
    """<2_결과>/<도구>/YYYY-MM-DD/HH시MM분/ 을 최신순으로."""
    base = os.path.join(RESULTS, tool)
    found = []
    if not os.path.isdir(base):
        return found
    for day in os.listdir(base):
        dp = os.path.join(base, day)
        if not os.path.isdir(dp) or not DAY_RE.match(day):
            continue
        for tm in os.listdir(dp):
            m = TIME_RE.match(tm)
            if not m or not os.path.isdir(os.path.join(dp, tm)):
                continue
            try:
                when = datetime.strptime(day, "%Y-%m-%d").replace(
                    hour=int(m.group(1)), minute=int(m.group(2)))
            except ValueError:
                continue
            found.append((when, os.path.join(dp, tm)))
    found.sort(key=lambda x: x[0], reverse=True)
    return found[:KEEP]


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main():
    blocks, total = [], 0
    for tool in TOOLS:
        found = runs(tool)
        total += len(found)
        blocks.append("<h2>%s</h2>" % e(tool))
        if not found:
            blocks.append('<p class="empty">아직 여기서 돌린 적이 없습니다.</p>')
            continue
        for when, path in found:
            report = read(os.path.join(path, "리포트.txt"))
            data = read_json(os.path.join(path, "데이터.json"))
            if not report and data is None:
                inner = '<p class="empty">결과가 만들어지지 않았습니다.</p>'
            else:
                inner = blogview.render(tool, data)
                if report:
                    inner += ('<details class="raw"><summary>원문 리포트 보기</summary>'
                              '<pre>%s</pre></details>' % linkify(e(report)))
            blocks.append('<details><summary><span>%s</span>'
                          '<span class="meta">%s</span></summary>'
                          '<div class="body">%s</div></details>'
                          % (e(when.strftime("%Y-%m-%d %H:%M")),
                             "리포트 있음" if report else "리포트 없음", inner))

    page = PAGE % (HEAD_JS, CSS, datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                   "".join(blocks))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("cloud/blog/index.html 갱신 - 회차 %d개" % total)


if __name__ == "__main__":
    main()
