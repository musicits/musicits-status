#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""휴대폰에서 돌린 수집 결과를 cloud/index.html 한 장으로 그린다.

깃허브 Actions 안에서만 돌아간다(.github/workflows/collect.yml).
PC 에서 만드는 메인 페이지(index.html)와는 별개다 — 그쪽은 요약과 제목 후보까지
들어간 정식 보고서를 담고, 이쪽은 '방금 새 기사가 있었나'만 빠르게 보여준다.
"""
import html as H
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# 깃허브(리눅스)에서는 UTF-8 이지만, 확인차 윈도우에서 돌려볼 때 한글이 깨지지 않도록
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUNS = os.path.join(REPO, "cloud", "runs")
OUT = os.path.join(REPO, "cloud", "index.html")

KST = timezone(timedelta(hours=9))
KEEP = 20                       # 페이지에 담을 회차 수
CATEGORY_ORDER = ["IT 공식발표", "IT 루머", "오디오", "카메라"]


def e(x):
    return H.escape(str(x if x is not None else ""))


# 밝기 설정은 메인 페이지의 버튼에서 고른다. 여기서는 그 선택(localStorage)을 따라만 간다.
# 값 이름과 색은 메인 페이지(.claude/scripts/web.py)와 같아야 한다.
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
.sub{margin:0 0 16px;color:var(--mut);font-size:12.5px}
a.back{display:inline-block;margin:0 0 16px;color:var(--acc);font-size:13.5px;font-weight:600}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;
 margin:0 0 10px;overflow:hidden}
summary{cursor:pointer;padding:13px 15px;font-weight:600;font-size:14.5px;
 display:flex;justify-content:space-between;gap:10px;align-items:baseline}
summary::-webkit-details-marker{display:none}
summary .meta{font-weight:400;font-size:12px;color:var(--mut);white-space:nowrap}
.body{padding:6px 15px 16px;border-top:1px solid var(--line)}
.cat{display:inline-block;font-size:11.5px;font-weight:700;color:var(--acc);
 background:var(--bg);border:1px solid var(--line);border-radius:5px;
 padding:2px 8px;margin:14px 0 8px}
.item{margin:0 0 12px}
.item .t{font-size:14px;font-weight:600;display:block;color:var(--fg);text-decoration:none}
.item .s{font-size:12px;color:var(--mut)}
.empty{color:var(--mut);font-size:13.5px}
.note{font-size:12.5px;color:var(--mut);background:var(--card);border:1px solid var(--line);
 border-radius:9px;padding:11px 13px;margin:0 0 16px}
""".replace("__DARK__", DARK_CSS)

PAGE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#1f4fd8">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>휴대폰 수집 결과</title>
<script>%s</script>
<style>%s</style></head><body><div class="wrap">
<a class="back" href="../">← 전체 현황으로</a>
<h1>휴대폰 수집 결과</h1>
<p class="sub">%s 기준 · 회차 %d개</p>
<p class="note">여기는 <b>새 기사 목록</b>만 나옵니다. 요약·제목 후보가 들어간 정식 보고서는
PC 에서 Claude 가 씁니다. 이 목록은 PC 쪽 확인 기록과 따로 관리되므로, 여기서 본 기사도
PC 에서 보고서를 만들 때 다시 나옵니다.</p>
%s</div></body></html>
"""


def runs():
    if not os.path.isdir(RUNS):
        return []
    out = []
    for name in sorted(os.listdir(RUNS), reverse=True):
        path = os.path.join(RUNS, name, "새소식.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
        except (OSError, ValueError):
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})$", name)
        label = "%s %s:%s" % m.groups() if m else name
        out.append((label, items if isinstance(items, list) else []))
    return out[:KEEP]


def render(label, items):
    if not items:
        inner = '<p class="empty">새 소식이 없었습니다.</p>'
    else:
        blocks = []
        for cat in CATEGORY_ORDER:
            group = [i for i in items if i.get("category") == cat]
            if not group:
                continue
            blocks.append('<div class="cat">%s</div>' % e(cat))
            for i in group:
                blocks.append(
                    '<div class="item">'
                    '<a class="t" href="%s" target="_blank" rel="noopener">%s</a>'
                    '<span class="s">%s · %s</span></div>'
                    % (e(i.get("link")), e(i.get("title")),
                       e(i.get("source")), e(i.get("date_kst"))))
        inner = "".join(blocks)
    return ('<details%s><summary><span>%s</span>'
            '<span class="meta">%d건</span></summary>'
            '<div class="body">%s</div></details>'
            % ("", e(label), len(items), inner))


def main():
    rs = runs()
    body = ("".join(render(l, i) for l, i in rs) or
            '<p class="empty">아직 휴대폰에서 돌린 기록이 없습니다.</p>')
    page = PAGE % (HEAD_JS, CSS,
                   datetime.now(KST).strftime("%Y-%m-%d %H:%M"), len(rs), body)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("cloud/index.html 갱신 — 회차 %d개" % len(rs))


if __name__ == "__main__":
    main()
