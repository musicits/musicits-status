#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""휴대폰에서 돌린 수집 결과를 cloud/index.html 한 장으로 그린다.

깃허브 Actions 안에서만 돌아간다(.github/workflows/collect.yml).
PC 에서 만드는 메인 페이지(index.html)와는 별개다 — 저쪽은 Claude 가 쓴 정식
보고서와 뉴스 쿼터를 담고, 이쪽은 폰에서 돌린 것만 따로 쌓인다. 둘은 확인 기록이
따로여서 같은 기사가 양쪽에 다 나온다. 그러라고 나눠 둔 것이다.

요약.json 이 있으면 보고서 모양으로, 없으면 목록만 그린다. 예전 회차의 요약.json 은
'report' 칸이 없는데, 그때 것은 그때 모양(주요 이슈 + 카테고리별 목록)으로 그린다.
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
.cat.pick{color:#fff;background:var(--acc);border-color:var(--acc)}
.rule{border-top:1px solid var(--line);margin:18px 0 4px}
.item{margin:0 0 12px}
.item .t{font-size:14px;font-weight:600;display:block;color:var(--fg);text-decoration:none}
.item .o{display:block;font-size:12px;color:var(--mut);margin:2px 0 1px}
.item .s{font-size:12px;color:var(--mut)}
.why{margin:-8px 0 14px;font-size:13px;padding-left:9px;
 border-left:2px solid var(--acc);color:var(--fg)}
.empty{color:var(--mut);font-size:13.5px}
.note{font-size:12.5px;color:var(--mut);background:var(--card);border:1px solid var(--line);
 border-radius:9px;padding:11px 13px;margin:0 0 16px}
.head{border:1px solid var(--line);border-radius:9px;padding:10px 12px;margin:10px 0 4px}
.kv{display:flex;gap:8px;font-size:12.5px;margin:0 0 3px}
.kv .k{color:var(--mut);flex:0 0 62px}
.kv .v{color:var(--fg);flex:1;min-width:0}
.warn{margin:6px 0 0;font-size:12px;color:var(--mut)}
.pk{border-top:1px solid var(--line);padding:12px 0 2px}
.pk:first-of-type{border-top:0}
.pk .tag{display:inline-block;font-size:11px;font-weight:700;color:var(--acc);
 border:1px solid var(--line);border-radius:5px;padding:1px 7px;margin:0 5px 6px 0}
.pk .tag.fed{color:var(--mut)}
.pk .t{font-size:15px;font-weight:700;display:block;color:var(--fg);
 text-decoration:none;line-height:1.45}
.pk .o{display:block;font-size:12px;color:var(--mut);margin:3px 0 1px}
.pk .s{display:block;font-size:12px;color:var(--mut);margin:0 0 8px}
.pk .b{margin:0 0 10px;font-size:14px}
.pk .line{margin:0 0 8px;font-size:13.5px;padding-left:9px;
 border-left:2px solid var(--acc)}
.pk .idea{margin:0 0 3px;font-size:13px;color:var(--fg)}
.pk .idea b{color:var(--mut);font-weight:600}
.rest{margin:0 0 11px;font-size:13.5px}
.rest .n{color:var(--mut);font-weight:700;margin-right:5px}
.rest a{color:var(--fg);text-decoration:none}
.rest .s{display:block;font-size:12px;color:var(--mut)}
""".replace("__DARK__", DARK_CSS)

PAGE = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#1f4fd8">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>휴대폰 수집 보고서</title>
<script>%s</script>
<style>%s</style></head><body><div class="wrap">
<a class="back" href="../">← 전체 현황으로</a>
<h1>휴대폰 수집 보고서</h1>
<p class="sub">%s 기준 · 회차 %d개</p>
<p class="note">폰에서 돌린 결과만 여기 쌓입니다. 주요 소식은 기사 원문을 열어 읽고
쓰지만, <b>PC 보고서와는 별개</b>입니다 — 저쪽은 Claude 가 쓰고 뉴스 쿼터까지 같이 봅니다.
확인 기록도 서로 따로라 여기서 본 기사가 PC 보고서에 다시 나옵니다.</p>
%s</div></body></html>
"""


def read_json(path):
    """없거나 깨졌으면 None. 보고서가 없어도 목록은 나와야 한다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_head(path):
    """새소식.txt 머리말에서 확인 범위와 접속 실패를 가져온다.

    collect.py 는 PC 와 같은 프로그램이라 여기서 고치지 않는다. 그래서 이미 적어둔
    것을 읽어 쓴다.
    """
    head = {"range": "", "notes": []}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    break
                if line.startswith("확인 범위:"):
                    m = re.search(r"→\s*(.+?)\s*이후 기사", line)
                    head["range"] = (m.group(1) + " 이후") if m else line[6:].strip()
                elif line.startswith("접속 실패:") or line.startswith("※"):
                    head["notes"].append(line)
    except OSError:
        pass
    return head


def runs():
    if not os.path.isdir(RUNS):
        return []
    out = []
    for name in sorted(os.listdir(RUNS), reverse=True):
        run = os.path.join(RUNS, name)
        items = read_json(os.path.join(run, "새소식.json"))
        if items is None:
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})$", name)
        label = "%s %s:%s" % m.groups() if m else name
        out.append((label, items if isinstance(items, list) else [],
                    read_json(os.path.join(run, "요약.json")) or {},
                    read_head(os.path.join(run, "새소식.txt"))))
    return out[:KEEP]


def article(idx, item, titles):
    """기사 한 줄. 번역이 있으면 한국어를 앞에 놓고 원문을 아래에 남긴다.

    원문 제목을 지우지 않는 이유: 번역이 어색하거나 제품명을 잘못 옮겼을 때
    바로 확인할 데가 있어야 한다.
    """
    ko = titles.get(str(idx))
    head = e(ko) if ko else e(item.get("title"))
    orig = ('<span class="o">%s</span>' % e(item.get("title"))) if ko else ""
    return ('<div class="item">'
            '<a class="t" href="%s" target="_blank" rel="noopener">%s</a>%s'
            '<span class="s">%s · %s</span></div>'
            % (e(item.get("link")), head, orig,
               e(item.get("source")), e(item.get("date_kst"))))


def head_block(head, report):
    """머리말. 무엇을 얼마나 추렸는지 한눈에 보이게 한다."""
    rows = []
    if head.get("range"):
        rows.append(("확인 범위", e(head["range"])))
    if report:
        c = report.get("counts") or {}
        rest = max(c.get("kept", 0) - c.get("picked", 0), 0)
        rows.append(("추린 과정", "수집 %d건 → 기기 소식 %d건 → 주요 %d건 + 한줄 %d건"
                     % (c.get("collected", 0), c.get("kept", 0),
                        c.get("picked", 0), rest)))
        dropped = report.get("dropped") or []
        if dropped:
            rows.append(("거른 것", e(" · ".join("%s %d건" % (k, n)
                                                for k, n in dropped))))
    if not rows and not head.get("notes"):
        return ""
    notes = "".join('<p class="warn">%s</p>' % e(n) for n in head.get("notes") or [])
    return ('<div class="head">%s%s</div>'
            % ("".join('<div class="kv"><span class="k">%s</span>'
                       '<span class="v">%s</span></div>' % (k, v) for k, v in rows),
               notes))


def pick_block(no, item, titles, pick):
    """주요 소식 한 꼭지. PC 보고서의 한 꼭지와 같은 차례로 놓는다."""
    ko = titles.get(str(no)) or item.get("title")
    tags = ['<span class="tag">%s</span>' % e(item.get("category"))]
    if pick.get("verdict"):
        tags.append('<span class="tag">%s</span>' % e(pick["verdict"]))
    read = pick.get("read") or ""
    if read and not read.startswith("원문"):
        # 원문을 못 읽었으면 숨기지 않는다. 그래야 내용이 얇은 이유를 안다.
        tags.append('<span class="tag fed">%s</span>' % e(read))

    out = ['<div class="pk">', "".join(tags),
           '<a class="t" href="%s" target="_blank" rel="noopener">%s</a>'
           % (e(item.get("link")), e(ko))]
    if ko != item.get("title"):
        out.append('<span class="o">%s</span>' % e(item.get("title")))
    out.append('<span class="s">%s · %s</span>'
               % (e(item.get("source")), e(item.get("date_kst"))))
    if pick.get("body"):
        out.append('<p class="b">%s</p>' % e(pick["body"]))
    line = pick.get("blog_line") or pick.get("why")
    if line:
        out.append('<p class="line">📝 %s</p>' % e(line))
    for n, idea in enumerate(pick.get("title_ideas") or [], 1):
        out.append('<p class="idea"><b>✏️ 제목 후보 %d</b> %s</p>' % (n, e(idea)))
    out.append("</div>")
    return "".join(out)


def rest_block(n, item, line):
    return ('<div class="rest"><span class="n">%d.</span>'
            '<a href="%s" target="_blank" rel="noopener">[%s] %s</a>'
            '<span class="s">%s · %s</span></div>'
            % (n, e(item.get("link")), e(item.get("category")), e(line),
               e(item.get("source")), e(item.get("date_kst"))))


def report_body(items, digest, head):
    """보고서 모양. 요약.json 에 'report' 칸이 있을 때만 쓴다."""
    report = digest["report"]
    titles = digest.get("titles") or {}
    picks = [p for p in report.get("picks") or []
             if isinstance(p.get("no"), int) and 0 <= p["no"] < len(items)]
    rest = [r for r in report.get("rest") or []
            if isinstance(r.get("no"), int) and 0 <= r["no"] < len(items)]

    out = [head_block(head, report)]
    if picks:
        out.append('<div class="cat pick">주요 소식 %d건</div>' % len(picks))
        out.extend(pick_block(p["no"], items[p["no"]], titles, p) for p in picks)
    if rest:
        out.append('<div class="rule"></div>')
        out.append('<div class="cat">나머지 소식 %d건</div>' % len(rest))
        out.extend(rest_block(len(picks) + n, items[r["no"]], r.get("line"))
                   for n, r in enumerate(rest, 1))
    if not picks and not rest:
        out.append('<p class="empty">기기 소식으로 남은 기사가 없습니다.</p>')
    return "".join(out)


def list_body(items, digest, head):
    """보고서가 없을 때. 예전 회차와 번역이 안 붙은 회차가 여기로 온다."""
    titles = digest.get("titles") or {}
    out = [head_block(head, None)]
    picks = [h for h in digest.get("highlights") or []
             if isinstance(h.get("no"), int) and 0 <= h["no"] < len(items)]
    if picks:
        out.append('<div class="cat pick">주요 이슈</div>')
        for h in picks:
            out.append(article(h["no"], items[h["no"]], titles))
            out.append('<p class="why">%s</p>' % e(h.get("why")))
        out.append('<div class="rule"></div>')
    for cat in CATEGORY_ORDER:
        group = [(i, it) for i, it in enumerate(items) if it.get("category") == cat]
        if not group:
            continue
        out.append('<div class="cat">%s</div>' % e(cat))
        out.extend(article(i, it, titles) for i, it in group)
    return "".join(out)


def render(label, items, digest, head, first=False):
    """회차 하나. 맨 위(가장 최근) 회차는 펼쳐서 내보낸다."""
    if not items:
        inner, meta = '<p class="empty">새 소식이 없었습니다.</p>', "0건"
    elif digest.get("report"):
        inner = report_body(items, digest, head)
        meta = "%d건 · 보고서" % len(items)
    else:
        inner = list_body(items, digest, head)
        meta = "%d건%s" % (len(items), " · 번역됨" if digest.get("titles") else "")
    return ('<details%s><summary><span>%s</span>'
            '<span class="meta">%s</span></summary>'
            '<div class="body">%s</div></details>'
            % (" open" if first else "", e(label), e(meta), inner))


def main():
    rs = runs()
    body = ("".join(render(l, i, d, h, first=(n == 0))
                    for n, (l, i, d, h) in enumerate(rs)) or
            '<p class="empty">아직 휴대폰에서 돌린 기록이 없습니다.</p>')
    page = PAGE % (HEAD_JS, CSS,
                   datetime.now(KST).strftime("%Y-%m-%d %H:%M"), len(rs), body)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)

    when = datetime.now(KST)
    if rs:
        try:
            when = datetime.strptime(rs[0][0], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        except (ValueError, TypeError):
            pass
    latest = {"at": when.isoformat(timespec="minutes"),
              "count": len(rs[0][1]) if rs else 0, "runs": len(rs)}
    with open(os.path.join(REPO, "cloud", "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False)
    print("cloud/index.html 갱신 — 회차 %d개" % len(rs))


if __name__ == "__main__":
    main()
