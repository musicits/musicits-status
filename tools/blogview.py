#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""블로그 도구 네 개의 `데이터.json` 을 읽어 화면용 HTML 조각으로 만든다.

리포트.txt 를 그대로 <pre> 로 붙이면 폰에서 읽기 나쁘다. 여기서는 같은 내용을
표와 점수 막대로 그린다. 원문 리포트는 각 도구 아래 접어서 그대로 남긴다 —
여기서 못 보여주는 항목이 있어도 확인할 데가 있어야 한다.

**이 파일은 두 곳에서 쓴다.** PC 가 만드는 메인 페이지(web.py)와 깃허브가 만드는
휴대폰 결과 페이지(tools/blog_page.py). 둘이 같은 화면이어야 하므로 그리는 코드는
여기 한 벌만 둔다. 저장소로는 web.py 가 복사해 넣는다.
"""

import html as H

TOOL_KEYWORDS = "1. 키워드 발굴"
TOOL_TITLES = "2. 제목 진단"
TOOL_TRACK = "3. 성과 추적"
TOOL_NEIGHBORS = "4. 이웃 발굴"

TOP_KEYWORDS = 15        # 기회점수 상위 몇 개까지 보여줄지
TOP_NEIGHBORS = 20


def e(x):
    return H.escape(str(x if x is not None else ""))


def num(x, digits=0):
    """숫자를 사람이 읽는 모양으로. 값이 없으면 —."""
    if x is None:
        return "—"
    try:
        return ("{:,.%df}" % digits).format(float(x))
    except (TypeError, ValueError):
        return e(x)


def tiles(items):
    """(값, 라벨) 목록을 요약 타일 줄로."""
    inner = "".join(
        '<div class="tile"><span class="tv">%s</span><span class="tl">%s</span></div>'
        % (e(v), e(k)) for v, k in items if v is not None)
    return '<div class="tiles">%s</div>' % inner if inner else ""


def bar(pct, tone=""):
    """0~100 짜리 가로 막대."""
    pct = max(0, min(100, pct or 0))
    return '<div class="bar %s"><i style="width:%.1f%%"></i></div>' % (tone, pct)


def chip(text, tone=""):
    return '<span class="chip %s">%s</span>' % (tone, e(text)) if text else ""


# ------------------------------------------------------------------ 1. 키워드 발굴

# 수요 상태별 색. 도구가 쓰는 말 그대로 받는다(모르는 말이 와도 회색으로 나온다).
DEMAND_TONE = {"급상승": "up", "상승": "up", "유지": "", "식는 중": "down",
               "관심 미미": "muted"}
AI_TONE = {"높음": "ai", "중간": "", "낮음": "muted"}


def view_keywords(d):
    rows = d.get("rows") or []
    ranked = sorted(rows, key=lambda r: (r.get("opp") or {}).get("score") or 0,
                    reverse=True)[:TOP_KEYWORDS]
    out = [tiles([(len(rows), "분석한 키워드"),
                  (d.get("anchor"), "기준 키워드"),
                  (d.get("since"), "집계 시작")])]
    if not ranked:
        return "".join(out) + '<p class="empty">키워드가 없습니다.</p>'

    out.append('<h4 class="vh">기회점수 상위 %d개</h4>' % len(ranked))
    top = (ranked[0].get("opp") or {}).get("score") or 100
    for r in ranked:
        opp = r.get("opp") or {}
        dem = r.get("demand") or {}
        score = opp.get("score") or 0
        out.append(
            '<div class="vrow">'
            '<div class="vhead"><span class="vname">%s</span>'
            '<span class="vnum">%s</span></div>%s'
            '<div class="vmeta">%s%s</div></div>'
            % (e(r.get("keyword")), num(score, 1),
               bar(score / top * 100 if top else 0),
               chip(dem.get("state"), DEMAND_TONE.get(dem.get("state"), "")),
               chip("AI 인용 " + str(r.get("ai_fit") or "—"),
                    AI_TONE.get(r.get("ai_fit"), ""))))
    return "".join(out)


# ------------------------------------------------------------------ 2. 제목 진단

def view_titles(d):
    entries = d.get("entries") or []
    out = [tiles([(len(entries), "진단한 제목"),
                  (d.get("top_count"), "비교한 상위권 글")])]
    if not entries:
        return "".join(out) + '<p class="empty">진단할 제목이 없습니다. 3_설정의 진단할제목.txt 를 채우세요.</p>'

    for en in entries:
        score = en.get("score")
        prof = en.get("profile") or {}
        axes = en.get("axes") or []
        out.append('<div class="vcard">')
        out.append('<div class="vhead"><span class="vname">%s</span>'
                   '<span class="vnum big">%s</span></div>'
                   % (e(en.get("keyword")), num(score)))
        out.append('<p class="vtitle">%s</p>' % e(en.get("my_title")))
        out.append(bar(score if isinstance(score, (int, float)) else 0))

        for ax in axes:
            # [항목, 만점, 받은점수, 설명]
            if len(ax) < 4:
                continue
            name, full, got, why = ax[0], ax[1] or 0, ax[2] or 0, ax[3]
            tone = "" if got >= full else ("down" if got <= full / 2 else "warn")
            out.append('<div class="axis"><div class="vhead">'
                       '<span class="aname">%s</span>'
                       '<span class="anum">%s / %s</span></div>%s'
                       '<p class="awhy">%s</p></div>'
                       % (e(name), num(got), num(full),
                          bar(got / full * 100 if full else 0, tone), e(why)))

        hooks = prof.get("top_hooks") or []
        if hooks:
            out.append('<p class="vsub">상위권이 자주 쓰는 말: %s</p>'
                       % "".join(chip(h) for h in hooks[:6]))
        if prof.get("len_median"):
            out.append('<p class="vsub">상위권 제목 길이는 %s자 근처입니다 '
                       '(주력 구간 %s~%s자).</p>'
                       % (num(prof.get("len_median")), num(prof.get("len_p25")),
                          num(prof.get("len_p75"))))

        out.append(_title_suggestions(en.get("suggest")))
        out.append("</div>")
    return "".join(out)


def _title_suggestions(suggest):
    """제안 제목은 [[[제목, 길이], ...], 권장길이] 모양으로 온다."""
    try:
        items, best = suggest[0], suggest[1]
    except (TypeError, IndexError):
        return ""
    if not items:
        return ""
    rows = "".join('<div class="sug"><span>%s</span><span class="slen">%s자</span></div>'
                   % (e(t[0]), num(t[1])) for t in items if t)
    return ('<p class="vsub">이렇게 바꿔보세요 (권장 %s자)</p>%s' % (num(best), rows))


# ------------------------------------------------------------------ 3. 성과 추적

RANK_TONE = {"상승": "up", "새로 진입": "up", "하락": "down", "계속 미노출": "muted"}


def view_track(d):
    pace = d.get("pace") or {}
    mine = d.get("mine") or {}
    ranks = d.get("ranks") or []
    days = pace.get("days_since")
    out = [tiles([
        (num(pace.get("total")), "전체 글"),
        (num(pace.get("per_week"), 1), "주당 발행"),
        (num(pace.get("last30")), "최근 30일"),
        ("오늘" if days == 0 else ("%s일 전" % num(days)) if days is not None else None,
         "마지막 발행"),
    ])]

    got = [r for r in ranks if r.get("rank")]
    out.append('<h4 class="vh">검색 순위 (%d / %d개 노출)</h4>' % (len(got), len(ranks)))
    if got:
        got.sort(key=lambda r: r["rank"])
        trs = []
        for r in got:
            change, status = r.get("change"), r.get("status")
            mark = ""
            if isinstance(change, (int, float)) and change:
                mark = ("▲ %d" % change) if change > 0 else ("▼ %d" % -change)
            trs.append('<tr><td>%s</td><td class="rk">%s위</td>'
                       '<td>%s %s</td><td class="dim">%s</td></tr>'
                       % (e(r.get("keyword")), num(r.get("rank")),
                          chip(status, RANK_TONE.get(status, "")), mark,
                          num(r.get("total"))))
        out.append('<div class="scroll"><table><tr><th>키워드</th><th>순위</th>'
                   '<th>변화</th><th>전체 문서</th></tr>%s</table></div>'
                   % "".join(trs))
    else:
        out.append('<p class="empty">아직 상위 노출된 키워드가 없습니다. '
                   '추적 중인 키워드는 %d개입니다.</p>' % len(ranks))

    cats = mine.get("categories") or pace.get("categories") or []
    if cats:
        top = max(c[1] for c in cats) or 1
        out.append('<h4 class="vh">카테고리 분포</h4>')
        for name, n in cats[:6]:
            out.append('<div class="vrow tight"><div class="vhead">'
                       '<span class="vname">%s</span><span class="vnum">%s편</span>'
                       '</div>%s</div>' % (e(name), num(n), bar(n / top * 100)))
    return "".join(out)


# ------------------------------------------------------------------ 4. 이웃 발굴

def view_neighbors(d):
    rows = d.get("rows") or []
    me = d.get("me") or {}
    ranked = sorted(rows, key=lambda r: (r.get("kw_hits") or 0, r.get("posts") or 0),
                    reverse=True)[:TOP_NEIGHBORS]
    out = [tiles([(len(rows), "찾은 후보"),
                  (len(d.get("keywords") or []), "분야 키워드"),
                  (num(me.get("per_week"), 1), "내 주당 발행")])]
    if not ranked:
        return "".join(out) + '<p class="empty">후보가 없습니다.</p>'

    out.append('<h4 class="vh">겹치는 주제가 많은 순 %d곳</h4>' % len(ranked))
    for r in ranked:
        kws = r.get("keywords") or []
        last = r.get("last_days")
        out.append(
            '<div class="vrow">'
            '<div class="vhead"><a class="vname" href="%s" target="_blank" '
            'rel="noopener">%s</a><span class="vnum">키워드 %s개</span></div>'
            '<div class="vmeta">%s%s%s</div>'
            '<p class="vsub dim">%s</p></div>'
            % (e(r.get("link")), e(r.get("name") or r.get("blog_id")),
               num(r.get("kw_hits")),
               chip("글 %s편" % num(r.get("posts"))),
               chip("주 %s편" % num(r.get("per_week"), 1)),
               chip("오늘 활동" if last == 0 else
                    ("%s일 전" % num(last)) if last is not None else "", "muted"),
               ", ".join(e(k) for k in kws[:6])))
    return "".join(out)


VIEWS = {
    TOOL_KEYWORDS: view_keywords,
    TOOL_TITLES: view_titles,
    TOOL_TRACK: view_track,
    TOOL_NEIGHBORS: view_neighbors,
}


def render(tool, data):
    """도구 이름과 데이터.json 내용을 받아 HTML 조각. 못 그리면 빈 문자열."""
    fn = VIEWS.get(tool)
    if not fn or not isinstance(data, dict):
        return ""
    try:
        return fn(data)
    except Exception as exc:                                    # noqa: BLE001
        # 자료 모양이 바뀌어도 페이지 전체가 죽지는 않아야 한다.
        # 원문 리포트는 그대로 남으므로 내용을 못 보는 일은 없다.
        return ('<p class="empty">이 도구의 화면을 그리지 못했습니다 (%s). '
                '아래 원문 리포트를 보세요.</p>' % e(type(exc).__name__))


CSS = """
.vh{margin:20px 0 9px;font-size:13.5px;color:var(--mut);font-weight:700}
.vh:first-child{margin-top:6px}
.vrow{padding:11px 0;border-bottom:1px solid var(--line)}
.vrow.tight{padding:8px 0}
.vrow:last-child{border-bottom:0}
.vcard{border:1px solid var(--line);border-radius:12px;padding:13px 14px;margin:0 0 12px}
.vhead{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.vname{font-size:14px;font-weight:600;word-break:break-word}
a.vname{color:var(--acc);text-decoration:none}
.vnum{font-size:13px;font-weight:700;white-space:nowrap;color:var(--mut)}
.vnum.big{font-size:22px;color:var(--acc)}
.vtitle{margin:7px 0 9px;font-size:14px;word-break:break-word}
.vsub{margin:9px 0 4px;font-size:12.5px;color:var(--mut)}
.vsub.dim{margin-top:6px}
.bar{height:6px;border-radius:99px;background:var(--line);overflow:hidden;margin:6px 0 0}
.bar i{display:block;height:100%;border-radius:99px;background:var(--acc)}
.bar.up i{background:#1a9d4d}
.bar.warn i{background:#c98a00}
.bar.down i{background:#c8503f}
.vmeta{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.chip{display:inline-block;font-size:11.5px;font-weight:600;padding:2px 8px;
 border-radius:99px;background:var(--bg);border:1px solid var(--line);color:var(--mut)}
.chip.up{color:#1a7f3c;border-color:#a6dcbb}
.chip.down{color:#a52222;border-color:#e7b4b4}
.chip.ai{color:var(--acc);border-color:var(--acc)}
.chip.muted{opacity:.65}
.axis{margin:11px 0 0}
.aname{font-size:12.5px;font-weight:600}
.anum{font-size:12px;color:var(--mut);white-space:nowrap}
.awhy{margin:5px 0 0;font-size:12.5px;color:var(--mut);word-break:break-word}
.sug{display:flex;justify-content:space-between;gap:10px;padding:8px 0;
 border-bottom:1px solid var(--line);font-size:13.5px}
.sug:last-child{border-bottom:0}
.slen{color:var(--mut);font-size:12px;white-space:nowrap}
td.rk{font-weight:700;white-space:nowrap}
td.dim{color:var(--mut)}
.raw{margin-top:18px}
.raw summary{padding:11px 0;font-size:13px;color:var(--mut);min-height:0}
"""
