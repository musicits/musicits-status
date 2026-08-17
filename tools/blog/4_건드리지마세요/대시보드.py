#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0. 전체 보기 — 도구 4개의 최신 결과를 HTML(+PDF) 한 장으로 모은다.

    python3 대시보드.py            HTML + PDF
    python3 대시보드.py --no-pdf   HTML만 (더 빠름)

2_결과/ 안을 훑어 도구별 '가장 최근 회차'를 찾아 읽고 `2_결과/대시보드.html` 을 만든다.
도구를 새로 돌린 뒤 이걸 실행하면 최신 내용으로 다시 그려진다.

폴더를 하나하나 열어보기 번거롭다고 해서 만든 것이다. 원본이 필요하면 각 칸의
'폴더 열기' 링크를 누르면 그 회차 폴더로 간다.

한 번도 안 돌린 도구는 '아직 실행 안 함'으로 표시하고 넘어간다 — 하나가 없다고
전체가 안 나오면 곤란하다.

**이 파일은 창을 열지 않는다.** 여는 건 runner.py 가 한다(다른 도구와 같은 방식).
직접 돌리면 파일만 만들고 끝난다.

PDF 는 크롬 계열 브라우저의 헤드리스 인쇄 기능을 빌린다. 파이썬 PDF 라이브러리를
따로 깔지 않으려는 것이다(윈도우 새 PC에 부품을 늘리지 않는 게 이 도구모음의 방침).
윈도우는 엣지가 기본으로 깔려 있어 대개 그냥 된다. 하나도 없으면 HTML만 만들고
'브라우저에서 Ctrl+P 로 인쇄하세요'라고 안내한다.
"""

import argparse
import glob
import html
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(ROOT, "2_결과")
OUT = os.path.join(RESULTS, "대시보드.html")
PDF = os.path.join(RESULTS, "대시보드.pdf")

TOOLS = [
    ("1. 키워드 발굴", "데이터.json", "무엇을 쓸까"),
    ("2. 제목 진단", "데이터.json", "어떻게 쓸까"),
    ("3. 성과 추적", "데이터.json", "어떻게 됐나"),
    ("4. 이웃 발굴", "데이터.json", "어디서 소통할까"),
]


def newest(tool, filename):
    """2_결과/<도구>/날짜/시각/<파일> 중 가장 최근 것. (데이터, 폴더경로, 표시시각)"""
    base = os.path.join(RESULTS, tool)
    if not os.path.isdir(base):
        return None, None, None
    runs = []
    for day in os.listdir(base):
        dpath = os.path.join(base, day)
        if not os.path.isdir(dpath):
            continue
        for tm in os.listdir(dpath):
            tpath = os.path.join(dpath, tm)
            if os.path.isdir(tpath) and os.path.isfile(os.path.join(tpath, filename)):
                runs.append((day, tm, tpath))
    if not runs:
        return None, None, None
    runs.sort()
    day, tm, path = runs[-1]
    try:
        with open(os.path.join(path, filename), encoding="utf-8") as f:
            return json.load(f), path, "%s %s" % (day, tm)
    except (ValueError, OSError):
        return None, path, "%s %s" % (day, tm)


def e(x):
    return html.escape(str(x if x is not None else ""))


def link(path):
    """폴더로 가는 file:// 링크."""
    if not path:
        return ""
    return "file://" + path.replace(" ", "%20")


# ---------------------------------------------------------------- 섹션

def card(title, sub, path, when, body, empty=False):
    head = ('<div class="card%s"><div class="chead"><div>'
            '<h2>%s</h2><p class="sub">%s</p></div>'
            '<div class="when">%s%s</div></div>'
            % (" empty" if empty else "", e(title), e(sub),
               ('<span class="stamp">%s</span>' % e(when)) if when else "",
               ('<a class="folder" href="%s">폴더 열기</a>' % link(path)) if path else ""))
    return head + body + "</div>"


def not_run(title, sub, how):
    return card(title, sub, None, None,
                '<p class="none">아직 실행하지 않았습니다. '
                '<b>%s</b> 를 눌러 한 번 돌리면 여기에 나옵니다.</p>' % e(how),
                empty=True)


def table(headers, rows, aligns=None):
    aligns = aligns or ["left"] * len(headers)
    h = "".join("<th class='%s'>%s</th>" % (a, e(x)) for x, a in zip(headers, aligns))
    body = []
    for r in rows:
        tds = []
        for v, a in zip(r, aligns):
            cls = a
            if isinstance(v, tuple):      # (값, 추가클래스)
                v, extra = v
                cls += " " + extra
            tds.append("<td class='%s'>%s</td>" % (cls, e(v)))
        body.append("<tr>%s</tr>" % "".join(tds))
    return ("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
            % (h, "".join(body)))


def score_cls(v, good=70, mid=50):
    return "good" if v >= good else ("mid" if v >= mid else "bad")


def sec_keywords(d, path, when):
    if not d:
        return not_run("1. 키워드 발굴", "무엇을 쓸까", "1_시작하기 폴더의 1. 키워드 발굴.bat")
    rows = sorted([r for r in d.get("rows", [])
                   if r["demand"]["state"] != "조회 실패"],
                  key=lambda r: -r["opp"]["score"])
    top = rows[:15]
    body = table(
        ["#", "키워드", "기회점수", "상태", "AI 인용", "그래서 뭘 하나"],
        [[i,
          r["keyword"],
          (round(r["opp"]["score"], 1), score_cls(r["opp"]["score"], 55, 45)),
          r["demand"]["state"],
          (r["ai_fit"], "good" if r["ai_fit"] == "높음" else
           ("bad" if r["ai_fit"].startswith("낮음") else "")),
          r["rx"]]
         for i, r in enumerate(top, 1)],
        ["num", "left", "num", "center", "center", "left"])

    dead = [r for r in rows if r["demand"]["state"] == "관심 미미"]
    extra = ('<p class="note">키워드 %d개 중 상위 15개입니다. '
             '검색이 거의 없는 표현 %d개는 엑셀 <b>발행추천</b> 시트 아래쪽에 있습니다.</p>'
             % (len(d.get("rows", [])), len(dead)))
    return card("1. 키워드 발굴", "무엇을 쓸까 — 기회점수 = 수요(40)+경쟁낮음(30)+AI적합(30)",
                path, when, body + extra)


def sec_titles(d, path, when):
    if not d:
        return not_run("2. 제목 진단", "어떻게 쓸까", "1_시작하기 폴더의 2. 제목 진단.bat")
    entries = d.get("entries", [])
    scored = sorted([x for x in entries if "score" in x], key=lambda x: -x["score"])
    rows = []
    for x in scored:
        pr = x["profile"]
        weak = min(x["axes"], key=lambda a: a[2] / max(a[1], 1)) if x.get("axes") else None
        rows.append([x["keyword"], x["my_title"],
                     (x["score"], score_cls(x["score"], 80, 60)),
                     "%d자" % len(x["my_title"]),
                     "%d~%d자" % (pr["len_p25"], pr["len_p75"]),
                     ("%s %d/%d" % (weak[0], weak[2], weak[1])) if weak else ""])
    body = table(["키워드", "내 제목", "점수", "길이", "상위권 주력", "가장 약한 항목"],
                 rows, ["left", "left", "num", "center", "center", "center"])
    only = [x for x in entries if "score" not in x]
    if only:
        body += ('<p class="note">제목 없이 표준형만 본 키워드: %s</p>'
                 % e(", ".join(x["keyword"] for x in only)))
    return card("2. 제목 진단", "어떻게 쓸까 — 상위 40개 제목의 표준형과 대조한 100점",
                path, when, body)


def sec_track(d, path, when):
    if not d:
        return not_run("3. 성과 추적", "어떻게 됐나", "1_시작하기 폴더의 3. 성과 추적.bat")
    ranks = d.get("ranks", [])
    mine, cmp_ = d.get("mine", {}), d.get("compare", {})
    med = cmp_.get("median", {})

    live = sorted([r for r in ranks if r["rank"]], key=lambda r: r["rank"])
    moved = [r for r in ranks if r["status"] in ("상승", "하락", "새로 진입", "이탈")]

    tiles = [("추적 검색어", "%d개" % len(ranks), ""),
             ("100위 안", "%d개" % len(live),
              "good" if live else "bad"),
             ("오른 검색어", "%d개" % sum(1 for r in ranks if r["status"] == "상승"), ""),
             ("아직 안 쓴 자리", "%d개" % len(d.get("gaps", [])), ""),
             ("주당 발행", "%.1f개" % mine.get("per_week", 0),
              "bad" if med.get("per_week") and mine.get("per_week", 0)
              < med["per_week"] - 1 else "")]
    tile_html = "".join(
        '<div class="tile"><span class="tv %s">%s</span><span class="tl">%s</span></div>'
        % (c, e(v), e(k)) for k, v, c in tiles)
    body = '<div class="tiles">%s</div>' % tile_html

    if moved:
        body += "<h3>순위가 움직인 검색어</h3>"
        body += table(["검색어", "지난", "이번", "변화"],
                      [[r["keyword"],
                        "%d위" % r["prev_rank"] if r["prev_rank"] else "미노출",
                        "%d위" % r["rank"] if r["rank"] else "미노출",
                        (r["status"], "good" if r["status"] in ("상승", "새로 진입")
                         else "bad")]
                       for r in moved[:10]],
                      ["left", "center", "center", "center"])
    elif live:
        body += "<h3>지금 순위에 잡힌 검색어</h3>"
        body += table(["검색어", "순위", "경쟁 문서수"],
                      [[r["keyword"], "%d위" % r["rank"], "{:,}".format(r["total"])]
                       for r in live[:10]],
                      ["left", "center", "num"])
    else:
        body += ('<p class="none">아직 100위 안에 잡힌 검색어가 없습니다. '
                 '아래 <b>나 vs 경쟁</b> 의 정보형 비중부터 손보는 게 빠릅니다.</p>')

    if med:
        body += "<h3>나 vs 경쟁 (중앙값)</h3>"
        pct = lambda v: "%d%%" % round(v * 100) if v is not None else "-"
        comp_rows = [
            ["정보형 제목", pct(mine.get("info")), pct(med.get("info")),
             ("늘려야 함", "bad") if med.get("info") and mine.get("info", 0) < med["info"] - .05
             else ("괜찮음", "good")],
            ["뉴스형 제목", pct(mine.get("news")), pct(med.get("news")),
             ("줄여야 함", "bad") if med.get("news") and mine.get("news", 0) > med["news"] + .10
             else ("괜찮음", "good")],
            ["상업형 제목", pct(mine.get("commerce")), pct(med.get("commerce")), ""],
            ["주당 발행", "%.1f개" % mine.get("per_week", 0),
             "%.1f개" % (med.get("per_week") or 0),
             ("적음", "bad") if med.get("per_week") and mine.get("per_week", 0)
             < med["per_week"] - 1 else ("괜찮음", "good")],
        ]
        body += table(["항목", "뮤직잇츠", "경쟁 중앙값", "판정"], comp_rows,
                      ["left", "center", "center", "center"])

    gaps = cmp_.get("gaps", [])
    if gaps:
        body += ("<h3>핵심 갭</h3><ul class='bullets'>%s</ul>"
                 % "".join("<li>%s</li>" % e(g) for g in gaps))

    if d.get("gaps"):
        body += "<h3>아직 안 쓴 자리 (경쟁 문서 많은 순)</h3>"
        body += table(["검색어", "경쟁 문서수"],
                      [[g["keyword"], "{:,}".format(g["total"])]
                       for g in d["gaps"][:10]],
                      ["left", "num"])

    note = ('<p class="note">순위는 검색 API sim 정렬이지 통합검색 VIEW 탭 순위가 '
            '아닙니다. 절대값보다 회차 간 변화를 보세요.')
    if d.get("prev_time"):
        note += " 지난 회차: %s" % e(d["prev_time"])
    note += "</p>"
    return card("3. 성과 추적", "어떻게 됐나 — 내 순위 + 경쟁 비교", path, when, body + note)


def sec_neighbors(d, path, when):
    if not d:
        return not_run("4. 이웃 발굴", "어디서 소통할까", "1_시작하기 폴더의 4. 이웃 발굴.bat")

    # 내 위치 — 후보들과 같은 잣대로 재면 지금 어디쯤인가 (2026-08-13부터 기록됨)
    body = ""
    me = d.get("me")
    if me:
        total = len(d.get("rows", [])) + 1
        if me.get("kw_hits"):
            pw = (" · 주 %g개 발행" % me["per_week"]) \
                if me.get("per_week") is not None else ""
            last = (" · 최근 발행 %d일 전" % me["last_days"]) \
                if me.get("last_days") is not None else ""
            line = ("분야 키워드 %d개 중 <b>%d개</b>에 걸림%s%s — 같은 기준으로 "
                    "줄 세우면 <b>%d위</b> / %d명"
                    % (len(d.get("keywords", [])), me["kw_hits"], pw, last,
                       me.get("rank") or 0, total))
        else:
            line = "분야 키워드 검색 상위에 내 글이 아직 없습니다"
        missing = me.get("missing") or []
        if missing:
            line += ("<br>아직 안 걸리는 키워드: %s"
                     % e(", ".join(missing[:6])
                         + (" 외 %d개" % (len(missing) - 6) if len(missing) > 6 else "")))
        body += "<h3>내 위치 (musicits)</h3><p>%s</p>" % line

    rows = d.get("rows", [])[:12]
    body += table(["블로그", "겹치는 키워드", "주당 발행", "최근 글", "겹친 키워드"],
                 [[("<a href='%s'>%s</a>" % (r["link"], r["name"] or r["blog_id"])),
                   (r["kw_hits"], "good" if r["kw_hits"] >= 3 else ""),
                   ("주 %g개" % r["per_week"]) if r.get("per_week") is not None else "-",
                   ("%d일 전" % r["last_days"]) if r.get("last_days") is not None
                   else (r.get("latest") or "-"),
                   ", ".join(r.get("keywords", [])[:3])]
                  for r in rows],
                 ["left", "num", "center", "center", "left"])
    # 블로그 이름 칸만 링크를 살린다
    body = body.replace("&lt;a href=&#x27;", "<a target='_blank' href='").replace(
        "&#x27;&gt;", "'>").replace("&lt;/a&gt;", "</a>")
    body += ('<p class="note">후보 %d명 중 상위 12명입니다. 이름을 누르면 그 블로그로 '
             '갑니다. 댓글·이웃 신청은 직접 하셔야 합니다 — 자동은 만들지 않았습니다.</p>'
             % len(d.get("rows", [])))
    return card("4. 이웃 발굴", "어디서 소통할까 — 내 분야에서 활발한 블로그",
                path, when, body)


# ---------------------------------------------------------------- 페이지

CSS = """
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:#f4f5f7;color:#1a1d21;
 font:15px/1.6 -apple-system,'Segoe UI','Malgun Gothic','맑은 고딕',sans-serif}
.wrap{max-width:1100px;margin:0 auto}
header{margin-bottom:22px}
h1{margin:0 0 6px;font-size:26px;letter-spacing:-.3px}
header .sub{margin:0;color:#6b7280;font-size:14px}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:20px 22px;
 margin-bottom:18px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card.empty{background:#fafbfc;border-style:dashed}
.chead{display:flex;justify-content:space-between;align-items:flex-start;
 gap:16px;flex-wrap:wrap;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #eef0f3}
h2{margin:0;font-size:19px}
.chead .sub{margin:3px 0 0;color:#6b7280;font-size:13px}
.when{text-align:right;font-size:12px;color:#8a9099;white-space:nowrap}
.stamp{display:block}
.folder{display:inline-block;margin-top:4px;color:#2563eb;text-decoration:none}
.folder:hover{text-decoration:underline}
h3{margin:20px 0 8px;font-size:14px;color:#374151;font-weight:600}
h3 .cnt{color:#9aa1ab;font-weight:400}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{background:#f7f8fa;color:#4b5563;font-weight:600;text-align:left;
 padding:8px 10px;border-bottom:1px solid #e3e6ea;white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid #f1f3f5;vertical-align:top}
tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.center,th.center{text-align:center}
td.good{color:#047857;font-weight:600}
td.mid{color:#b45309;font-weight:600}
td.bad{color:#b91c1c;font-weight:600}
a{color:#2563eb}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.tile{flex:1;min-width:110px;background:#f7f8fa;border:1px solid #eef0f3;
 border-radius:9px;padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tv{font-size:21px;font-weight:700;font-variant-numeric:tabular-nums}
.tv.good{color:#047857}.tv.bad{color:#b91c1c}
.tl{font-size:12px;color:#6b7280}
.note{margin:12px 0 0;font-size:12.5px;color:#6b7280;line-height:1.55}
.none{margin:6px 0;color:#6b7280;font-size:14px}
.bullets{margin:6px 0;padding-left:20px;font-size:13.5px}
.bullets li{margin-bottom:5px}
ul.news{list-style:none;margin:4px 0 0;padding:0;font-size:13.5px}
ul.news li{padding:5px 0;border-bottom:1px solid #f1f3f5}
ul.news li:last-child{border-bottom:0}
ul.news .meta{display:block;color:#9aa1ab;font-size:11.5px;margin-top:1px}
ul.news .more{color:#9aa1ab}
footer{margin-top:26px;color:#8a9099;font-size:12.5px;line-height:1.7}
@media print{
 @page{size:A4;margin:14mm 12mm}
 body{background:#fff;padding:0;font-size:11.5px}
 .wrap{max-width:none}
 h1{font-size:21px}
 .card{break-inside:avoid;page-break-inside:avoid;box-shadow:none;
  border-color:#d6dae0;margin-bottom:12px;padding:14px 16px}
 .card.empty{display:none}          /* 안 돌린 도구는 인쇄에서 뺀다 */
 .folder{display:none}              /* 종이에서 못 누르는 링크는 뺀다 */
 table{font-size:10.5px}
 th,td{padding:5px 7px}
 tr{break-inside:avoid}
 h3{margin:12px 0 6px}
 a{color:#1a1d21;text-decoration:none}
 .tile{background:#fff;border-color:#d6dae0}
 footer{border-top:1px solid #e3e6ea;padding-top:8px}
}
@media (max-width:640px){.chead{flex-direction:column}.when{text-align:left}
 table{font-size:12.5px}th,td{padding:6px 7px}}
"""

FOOTER = """
<footer>
  이 페이지는 <b>0. 전체 보기</b> 를 누를 때마다 각 도구의 가장 최근 회차를 다시 읽어 그립니다.
  도구를 새로 돌린 뒤 다시 눌러주세요.<br>
  조회수·방문자수·댓글수·이웃수·AI 브리핑 인용수는 네이버가 공개하지 않아 어떤 도구로도 가져올 수 없습니다.<br>
  '순위'는 검색 API 의 유사도 정렬 순서지 통합검색 VIEW 탭 순위가 아닙니다.
</footer>
"""


def build():
    parts = []
    stamps = []
    getters = [sec_keywords, sec_titles, sec_track, sec_neighbors]
    for (tool, fname, _), fn in zip(TOOLS, getters):
        data, path, when = newest(tool, fname)
        if when:
            stamps.append("%s %s" % (tool.split(".")[0], when))
        parts.append(fn(data, path, when))

    sub = ("만든 시각 %s · 각 도구의 가장 최근 회차를 모았습니다"
           % datetime.now().strftime("%Y-%m-%d %H:%M"))
    page = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>뮤직잇츠 블로그 대시보드</title><style>%s</style></head><body>"
            "<div class='wrap'><header><h1>뮤직잇츠 블로그 대시보드</h1>"
            "<p class='sub'>%s</p></header>%s%s</div></body></html>"
            % (CSS, e(sub), "".join(parts), FOOTER))

    os.makedirs(RESULTS, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("")
    print("대시보드를 만들었습니다: 2_결과/대시보드.html")
    for s in stamps:
        print("   %s" % s)
    if not stamps:
        print("   (아직 실행한 도구가 없습니다. 1~4번을 한 번씩 돌려보세요.)")
    return OUT


# ---------------------------------------------------------------- PDF

# 크롬 계열 브라우저를 찾는 자리들. 윈도우는 엣지가 기본 설치라 대개 걸린다.
BROWSERS_MAC = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
BROWSERS_WIN = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
]


def find_browser():
    cands = BROWSERS_WIN if sys.platform == "win32" else BROWSERS_MAC
    for p in cands:
        if os.path.isfile(p) and (sys.platform == "win32" or os.access(p, os.X_OK)):
            return p
    if sys.platform == "win32":
        # 사용자 계정 아래 설치된 크롬도 본다
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            for pat in (r"Google\Chrome\Application\chrome.exe",
                        r"Microsoft\Edge\Application\msedge.exe"):
                hits = glob.glob(os.path.join(local, pat))
                if hits:
                    return hits[0]
    return None


def to_pdf(html_path, pdf_path):
    """헤드리스 브라우저로 HTML을 PDF로 인쇄한다. 성공하면 True."""
    browser = find_browser()
    if not browser:
        print("")
        print("  PDF 는 건너뜁니다 — 크롬/엣지 계열 브라우저를 못 찾았습니다.")
        print("  대시보드.html 을 브라우저로 연 뒤 %s 를 눌러 'PDF로 저장'하면 됩니다."
              % ("Ctrl+P" if sys.platform == "win32" else "Cmd+P"))
        return False

    url = "file://" + html_path.replace(" ", "%20")
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--print-to-pdf=" + pdf_path, url]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=90)
    except (OSError, subprocess.SubprocessError):
        r = None

    # 구버전 크롬은 --headless=new 를 모른다. 옛 플래그로 한 번 더.
    if (r is None or r.returncode != 0 or not os.path.isfile(pdf_path)):
        cmd[1] = "--headless"
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=90)
        except (OSError, subprocess.SubprocessError):
            pass

    if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 1000:
        return True
    print("")
    print("  PDF 만들기에 실패했습니다. 대시보드.html 을 열어 %s 로 저장해 주세요."
          % ("Ctrl+P" if sys.platform == "win32" else "Cmd+P"))
    return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="전체 보기 대시보드 만들기")
    ap.add_argument("--no-pdf", action="store_true", help="PDF는 건너뛰고 HTML만")
    args = ap.parse_args()

    out = build()
    if not args.no_pdf:
        print("")
        print("PDF로도 만드는 중... (10초쯤 걸립니다)")
        if to_pdf(out, PDF):
            print("  PDF 저장: 2_결과/대시보드.pdf")
    # 파일을 여는 건 runner.py 가 한다. 여기서 열면 두 번 뜬다.
