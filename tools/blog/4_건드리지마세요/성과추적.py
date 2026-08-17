#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3. 성과 추적 — 어떻게 됐나.

통합 안내:
  [4. 블로그 추적기] + [7. 경쟁 벤치마킹] 을 합친 도구다.
  두 도구 모두 경쟁 블로그의 RSS(최근 50개)를 각자 읽고 있었고, 시드 목록도
  같은 20곳이었다(비교할블로그.txt / 경쟁블로그.txt). 이제 RSS를 한 번만 읽어
  '내 순위'와 '경쟁 스타일 비교'를 동시에 낸다.

  유형 판정도 서로 달랐다. 4번은 한 제목을 여러 유형에 중복으로 세는 비율 방식,
  7번은 하나만 고르는 배타 방식이었다. 같은 블로그가 도구마다 다른 수치로
  나오던 원인이다. 이제 둘 다 공용/classify.title_type (배타, 뉴스>상업>정보>기타)
  하나만 쓴다. **예전 회차 숫자와 직접 비교하지 말 것** — 기준이 바뀌었다.

무엇을 하나:
  1) 내 글 목록(RSS) 읽기
  2) 추적 검색어별 내 순위 확인 + 지난 회차 대비 변화
  3) 내 발행 페이스
  4) 내 글이 추적 검색어를 실제로 담고 있는지 대조 (아직 안 쓴 자리 찾기)
  5) 경쟁 블로그와 스타일 비교 + 갭 진단

사용:
    python3 성과추적.py --키워드 ../설정/추적할키워드.txt \\
                        --경쟁블로그 ../설정/경쟁블로그.txt --out 결과/추적

못 가져오는 값 (묻기 전에 답):
  조회수 · 방문자수 · 유입 검색어 · 댓글수 · 이웃수 · AI 브리핑 인용수는
  어떤 방법으로도 안 된다. blog.naver.com/robots.txt 가 전면 차단이다.
  AI 브리핑 인용수는 블로그 프로필에서 본인만 눈으로 볼 수 있다.

순위의 의미:
  검색 API sort=sim 이 주는 순서지 통합검색 VIEW 탭 순위가 아니다.
  절대값을 믿지 말고 회차 간 변화를 볼 것. 100위 안에 없으면 '미노출'이다.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 공용 import naver_api, rss                                  # noqa: E402
from 공용.classify import (normalize, title_type, tokenize,      # noqa: E402
                           words, hook_counts)

BLOG_ID = "musicits"
RANK_DEPTH = 100        # 몇 위까지 훑어볼지. 검색 API가 한 번에 주는 최대치.
COMPETITOR_DEPTH = 30   # 검색 결과에서 경쟁 블로거를 셀 때 상위 몇 개까지
HISTORY_KEEP = 60       # 추적기록.json 에 남길 최근 회차 수
KST = timezone(timedelta(hours=9))

# 회차 기록은 결과 폴더 '밖'에 둔다. 사용자는 오래된 결과 폴더를 통째로
# 지우는데, 기록이 거기 있으면 과거 비교가 같이 날아간다.
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "기록", "추적기록.json")

# blog.naver.com/musicits 뒤가 끝이거나 / ? # 로 이어질 때만 내 블로그다.
# 그냥 substring으로 보면 'musicits2' 같은 남의 블로그까지 내 것으로 잡힌다.
MINE_RE = re.compile(r"blog\.naver\.com/%s(?:[/?#]|$)" % re.escape(BLOG_ID))


def is_mine(item):
    return bool(MINE_RE.search((item.get("bloggerlink") or "") + " "
                               + (item.get("link") or "")))


# ---------------------------------------------------------------- 순위 추적

def track_ranks(keywords, api_url, headers):
    """키워드마다 내 순위 + 상위권 블로거를 뽑는다."""
    rows = []
    competitors = defaultdict(lambda: {"name": "", "link": "", "keywords": [],
                                       "ranks": [], "titles": []})

    for i, kw in enumerate(keywords, 1):
        sys.stderr.write("\r  순위 확인 %d/%d  %s%s" % (i, len(keywords), kw, " " * 20))
        sys.stderr.flush()

        items, total = naver_api.search_once(kw, api_url, headers, RANK_DEPTH)

        my_rank, my_title, my_link = None, "", ""
        for it in items:
            if is_mine(it):
                my_rank = it["_rank"]
                my_title = rss.clean(it.get("title"))
                my_link = rss.post_key(it.get("link"))
                break

        for it in items[:COMPETITOR_DEPTH]:
            if is_mine(it):
                continue
            blink = (it.get("bloggerlink") or "").split("?")[0]
            if not blink:
                continue
            c = competitors[blink]
            c["name"] = rss.clean(it.get("bloggername")) or blink
            c["link"] = blink
            c["keywords"].append(kw)
            c["ranks"].append(it["_rank"])
            if len(c["titles"]) < 3:
                c["titles"].append({
                    "title": rss.clean(it.get("title")), "keyword": kw,
                    "rank": it["_rank"], "postdate": it.get("postdate", ""),
                })

        rows.append({
            "keyword": kw, "rank": my_rank, "my_title": my_title,
            "my_link": my_link, "total": total,
            "top": [{"rank": it["_rank"], "title": rss.clean(it.get("title")),
                     "blogger": rss.clean(it.get("bloggername")),
                     "postdate": it.get("postdate", ""), "mine": is_mine(it)}
                    for it in items[:10]],
        })
        time.sleep(0.1)   # 매너 딜레이

    sys.stderr.write("\r  순위 확인 %d개 완료%s\n" % (len(keywords), " " * 40))

    comp_rows = []
    for _, c in competitors.items():
        comp_rows.append({
            "name": c["name"], "link": c["link"],
            "hit_keywords": len(set(c["keywords"])), "hits": len(c["ranks"]),
            "best_rank": min(c["ranks"]),
            "avg_rank": round(sum(c["ranks"]) / len(c["ranks"]), 1),
            "samples": c["titles"],
        })
    # 여러 키워드에 걸쳐 나오는 블로거가 진짜 경쟁자다. 한 키워드에서 여러 번
    # 나오는 것(장악)보다 '키워드 개수'를 먼저 본다.
    comp_rows.sort(key=lambda r: (-r["hit_keywords"], -r["hits"], r["avg_rank"]))
    return rows, comp_rows


# ---------------------------------------------------------------- 발행 페이스

def pace(posts, today):
    """발행 간격과 카테고리 비중을 센다."""
    dated = sorted([p for p in posts if p["pubdate"]],
                   key=lambda p: p["pubdate"], reverse=True)
    if not dated:
        return {"total": len(posts), "last_date": "", "days_since": None,
                "last7": 0, "last30": 0, "last90": 0, "per_week": 0.0,
                "categories": [], "gap_avg": None, "recent_gaps": []}

    d7 = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    d30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    d90 = (today - timedelta(days=90)).strftime("%Y-%m-%d")

    last = dated[0]["pubdate"]
    days_since = (today - datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=KST)).days

    # 최근 12개 글의 발행 간격 (며칠에 하나씩 올리고 있나)
    gaps = []
    for a, b in zip(dated, dated[1:]):
        try:
            gap = (datetime.strptime(a["pubdate"], "%Y-%m-%d")
                   - datetime.strptime(b["pubdate"], "%Y-%m-%d")).days
        except ValueError:
            continue
        gaps.append(gap)
        if len(gaps) >= 12:
            break

    cats = Counter(p["category"] or "(분류 없음)" for p in posts)
    last30 = sum(1 for p in dated if p["pubdate"] >= d30)

    return {
        "total": len(posts), "last_date": last, "days_since": days_since,
        "last7": sum(1 for p in dated if p["pubdate"] >= d7),
        "last30": last30,
        "last90": sum(1 for p in dated if p["pubdate"] >= d90),
        "per_week": round(last30 / 30 * 7, 1),
        "categories": cats.most_common(),
        "gap_avg": round(sum(gaps) / len(gaps), 1) if gaps else None,
        "recent_gaps": gaps,
    }


# ---------------------------------------------------------------- 글별 매칭

def match_posts(posts, keywords, rank_rows):
    """내 글이 추적 키워드를 실제로 담고 있는지 대조한다.

    제목/태그를 붙여서 검색어의 낱말이 전부 들어 있으면 '노리는 글'로 본다.
    ('이어폰 청소 방법' → 제목+태그에 이어폰·청소·방법이 다 있어야 매칭)
    """
    rank_by_kw = {r["keyword"]: r for r in rank_rows}
    post_rows, covered = [], set()

    for p in posts:
        haystack = normalize(p["title"] + " " + " ".join(p["tags"]))
        hits = []
        for kw in keywords:
            if all(normalize(t) and normalize(t) in haystack for t in words(kw)):
                hits.append(kw)
                covered.add(kw)
        # 그 글이 실제로 순위에 잡힌 키워드 (제목에 낱말이 있는 것과 별개다)
        ranked = [kw for kw in hits
                  if rank_by_kw.get(kw, {}).get("my_link") == p["guid"]]
        got = [rank_by_kw[k]["rank"] for k in ranked if rank_by_kw[k]["rank"]]
        post_rows.append({
            "title": p["title"], "guid": p["guid"], "url": p.get("url", ""),
            "pubdate": p["pubdate"], "category": p["category"],
            "tag_count": len(p["tags"]), "type": title_type(p["title"]),
            "matched": hits, "ranked": ranked,
            "best_rank": min(got) if got else None,
        })

    # 추적은 하는데 그걸 노린 글이 아예 없는 키워드 = 아직 안 쓴 자리
    gaps = []
    for kw in keywords:
        if kw in covered:
            continue
        r = rank_by_kw.get(kw, {})
        gaps.append({"keyword": kw, "total": r.get("total", 0),
                     "rank": r.get("rank")})
    gaps.sort(key=lambda g: -g["total"])
    return post_rows, gaps


# ---------------------------------------------------------------- 블로그 프로필

def profile(posts, today, name, blog_id):
    """RSS 글 목록 하나를 '어떤 글을 어떻게 쓰는 블로그인가'로 요약한다.

    [4. 블로그 추적기]의 profile() 과 [7. 경쟁 벤치마킹]의 analyze() 합집합.
    유형은 공용 기준(배타)으로 한 번만 센다 — 합이 100%가 된다.
    """
    p = pace(posts, today)
    titles = [x["title"] for x in posts if x["title"]]
    n = len(titles) or 1
    lengths = sorted(len(t) for t in titles) or [0]

    types = Counter(title_type(t) for t in titles)
    hooks = hook_counts(titles)

    tag_counter = Counter()
    for x in posts:
        for t in x["tags"]:
            tag_counter[t] += 1
    tokens = Counter()
    for t in titles:
        tokens.update(tokenize(t))

    # RSS 50개 상한 때문에 '50÷기간'은 활발한 블로그에서 주 300개로 폭발한다.
    # 28일 창으로 고정해 안정화한다(공용/rss.publish_rhythm).
    per_week_28, last_days = rss.publish_rhythm(posts)

    return {
        "blog_id": blog_id, "name": name or blog_id,
        "posts": len(posts),
        "per_week": per_week_28 if per_week_28 is not None else p["per_week"],
        "last30": p["last30"], "last_days": last_days, "gap_avg": p["gap_avg"],
        "title_len": round(sum(len(t) for t in titles) / n, 1),
        "len_median": lengths[len(lengths) // 2],
        "info": types.get("정보형", 0) / n,
        "commerce": types.get("상업형", 0) / n,
        "news": types.get("뉴스형", 0) / n,
        "etc": types.get("기타", 0) / n,
        "question": sum(1 for t in titles if "?" in t) / n,
        "number": sum(1 for t in titles if re.search(r"\d", t)) / n,
        "bracket": sum(1 for t in titles if re.search(r"[\(\[]", t)) / n,
        "avg_tags": round(sum(len(x["tags"]) for x in posts) / n, 1),
        "categories": p["categories"][:5],
        "top_tags": [t for t, _ in tag_counter.most_common(12)],
        "top_hooks": hooks.most_common(5),
        "top_tokens": tokens.most_common(20),
        "sample_titles": titles[:6],
    }


def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def compare_blogs(mine, rivals):
    """내 프로필과 경쟁 블로그들의 중앙값을 견줘 '어디가 다른지'를 뽑는다.

    평균이 아니라 중앙값을 쓴다. 한 블로그가 하루 열 개씩 쏟아내면 평균이
    통째로 끌려가서 '나는 게으르다'는 엉뚱한 결론이 나온다.
    """
    if not rivals:
        return {"rivals": [], "median": {}, "findings": [], "gaps": [],
                "gap_topics": [], "shared_topics": []}

    keys = ["per_week", "title_len", "len_median", "info", "commerce", "news",
            "question", "number", "bracket", "avg_tags"]
    med = {k: median([r[k] for r in rivals]) for k in keys}

    # 경쟁 블로그 사이에서 몇 곳이나 다루는 주제인가 (태그 기준)
    topic_blogs = defaultdict(set)
    label_of = {}
    for r in rivals:
        for t in r["top_tags"]:
            topic_blogs[normalize(t)].add(r["blog_id"])
            label_of.setdefault(normalize(t), t)
    my_topics = set(normalize(t) for t in mine["top_tags"])

    # 여러 경쟁자가 함께 다루는데 나는 안 다루는 주제 = 이 판의 주류
    gap_topics = sorted([(label_of[k], len(v)) for k, v in topic_blogs.items()
                         if len(v) >= 3 and k not in my_topics],
                        key=lambda x: -x[1])[:15]
    # 나도 다루고 남도 다루는 주제 = 정면 승부 구간
    shared_topics = sorted([(label_of[k], len(v)) for k, v in topic_blogs.items()
                            if len(v) >= 2 and k in my_topics],
                           key=lambda x: -x[1])[:15]

    def diff_note(key, label, unit="%"):
        mv, rv = mine.get(key), med.get(key)
        if mv is None or rv is None:
            return {"label": label, "mine": "-", "rivals": "-",
                    "direction": "알 수 없음", "notable": False}
        if unit == "%":
            mine_s, rival_s = "%d%%" % round(mv * 100), "%d%%" % round(rv * 100)
            delta = (mv - rv) * 100
            big = abs(delta) >= 10
        else:
            mine_s, rival_s = "%.1f" % mv, "%.1f" % rv
            delta = mv - rv
            big = abs(delta) >= max(0.15 * (rv or 1), 0.5)
        return {"label": label, "mine": mine_s, "rivals": rival_s,
                "direction": "높음" if delta > 0 else ("낮음" if delta < 0 else "같음"),
                "notable": big}

    findings = [
        diff_note("per_week", "주당 발행 수", unit="n"),
        diff_note("info", "정보형 제목 비중"),
        diff_note("commerce", "상업형 제목 비중"),
        diff_note("news", "뉴스형 제목 비중"),
        diff_note("title_len", "제목 길이(글자)", unit="n"),
        diff_note("question", "물음표 쓰는 비율"),
        diff_note("number", "숫자 넣는 비율"),
        diff_note("avg_tags", "글당 태그 수", unit="n"),
    ]

    # 갭 진단 — [7. 경쟁 벤치마킹]의 판정 기준을 그대로 옮겼다.
    # [[musicits-blog-keywords]] 전략(정보형→AI 인용)에 맞춰 정보형↑·뉴스형↓ 방향.
    gaps = []
    if med["info"] is not None and mine["info"] < med["info"] - 0.05:
        gaps.append("정보형이 %d%%로 경쟁 중앙값(%d%%)보다 낮습니다. "
                    "AI 인용을 노리려면 정보형을 늘리세요."
                    % (round(mine["info"] * 100), round(med["info"] * 100)))
    if med["news"] is not None and mine["news"] > med["news"] + 0.10:
        gaps.append("뉴스형이 %d%%로 경쟁 중앙값(%d%%)보다 크게 높습니다. "
                    "속보성은 뉴스 기사에 밀립니다 — 정보형으로 무게를 옮기세요."
                    % (round(mine["news"] * 100), round(med["news"] * 100)))
    if med["per_week"] is not None and mine["per_week"] < med["per_week"] - 1:
        gaps.append("발행이 주 %g개로 경쟁 중앙값(주 %g개)보다 적습니다. "
                    "꾸준함이 지수에 유리합니다."
                    % (mine["per_week"], med["per_week"]))
    if not gaps:
        gaps.append("주요 지표가 경쟁 중앙값과 비슷하거나 앞섭니다. 좋습니다.")

    return {"rivals": rivals, "median": med, "findings": findings, "gaps": gaps,
            "gap_topics": gap_topics, "shared_topics": shared_topics}


def read_blog_list(path):
    """경쟁블로그.txt 를 읽어 [(블로그아이디, 표시이름)] 로."""
    if not path or not os.path.exists(path):
        return []
    out, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            raw = parts[0]
            name = parts[1].strip() if len(parts) > 1 else ""
            # blog.naver.com/xxx, https://blog.naver.com/xxx, xxx 셋 다 받는다
            m = re.search(r"blog\.naver\.com/([A-Za-z0-9_\-]+)", raw)
            bid = m.group(1) if m else raw.strip("/")
            if not re.match(r"^[A-Za-z0-9_\-]+$", bid) or bid in seen or bid == BLOG_ID:
                continue
            seen.add(bid)
            out.append((bid, name))
    return out


def collect_rivals(blog_list, today):
    """경쟁 블로그 RSS를 한 번씩만 읽는다. 통합 전에는 두 도구가 따로 읽었다."""
    profiles = []
    for i, (bid, name) in enumerate(blog_list, 1):
        sys.stderr.write("\r  경쟁 블로그 %d/%d  %s%s" % (i, len(blog_list), bid, " " * 20))
        sys.stderr.flush()
        posts = rss.blog_posts(bid, soft=True)
        if not posts:
            continue
        profiles.append(profile(posts, today, name, bid))
        time.sleep(0.1)
    sys.stderr.write("\r  경쟁 블로그 %d곳 확인%s\n" % (len(profiles), " " * 40))
    return profiles


# ---------------------------------------------------------------- 회차 기록

def load_history():
    if not os.path.exists(HISTORY_PATH):
        return {"runs": [], "posts_seen": {}}
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            h = json.load(f)
    except (ValueError, OSError):
        # 기록이 깨졌다고 이번 추적까지 멈출 이유는 없다. 비교만 포기한다.
        sys.stderr.write("  (지난 기록을 읽지 못해 이번엔 변화 비교를 건너뜁니다)\n")
        return {"runs": [], "posts_seen": {}}
    h.setdefault("runs", [])
    h.setdefault("posts_seen", {})
    return h


def save_history(history, stamp, rank_rows, posts):
    """결과 파일을 다 쓴 '뒤에' 저장한다 — 중간에 죽으면 회차가 어긋난다."""
    history["runs"].append({
        "time": stamp,
        "ranks": {r["keyword"]: r["rank"] for r in rank_rows},
    })
    history["runs"] = history["runs"][-HISTORY_KEEP:]

    for p in posts:
        seen = history["posts_seen"].get(p["guid"], {})
        seen.update({"title": p["title"], "pubdate": p["pubdate"],
                     "category": p["category"]})
        seen.setdefault("first_seen", stamp)
        history["posts_seen"][p["guid"]] = seen

    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    tmp = HISTORY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)
    os.replace(tmp, HISTORY_PATH)


def apply_change(rank_rows, history):
    """지난 회차 순위를 붙여 변화량을 계산한다.

    순위는 작을수록 좋으므로 change = 지난순위 - 이번순위 (양수면 상승).
    미노출(None)은 숫자로 못 빼니 상태 문자열로 따로 표시한다.
    """
    runs = history["runs"]
    prev_time = runs[-1]["time"] if runs else ""

    for r in rank_rows:
        # 마지막 회차가 아니라 '그 검색어가 들어 있던 가장 최근 회차'를 찾는다.
        # 검색어를 뺐다가 다시 넣어도 예전 기록과 이어지게 하려는 것이다.
        # 마지막 회차만 보면 전부 '신규추적'으로 뜬다. 되돌리지 말 것.
        before, r["prev_time"] = "__none__", ""
        for run in reversed(runs):
            if r["keyword"] in run["ranks"]:
                before = run["ranks"][r["keyword"]]
                r["prev_time"] = run["time"]
                break

        r["prev_rank"] = None if before == "__none__" else before
        r["change"] = None

        if before == "__none__":
            r["status"] = "신규추적"
        elif before is None and r["rank"] is None:
            r["status"] = "계속 미노출"
        elif before is None and r["rank"] is not None:
            r["status"] = "새로 진입"
        elif before is not None and r["rank"] is None:
            r["status"] = "이탈"
        else:
            r["change"] = before - r["rank"]
            r["status"] = ("상승" if r["change"] > 0 else
                           "하락" if r["change"] < 0 else "유지")
    return prev_time


# ---------------------------------------------------------------- 리포트

def bar(value, total, width=20):
    if not total:
        return ""
    filled = int(round(value / total * width))
    return "█" * filled + "·" * (width - filled)


def rank_text(rank):
    return "%d위" % rank if rank else "미노출"


def report(data):
    out = []
    p = out.append
    mine = data["mine"]
    cmp_ = data["compare"]
    ranks = data["ranks"]
    pc = data["pace"]

    p("")
    p("=" * 70)
    p("  성과 추적 리포트 — 뮤직잇츠")
    p("  %s · 검색어 %d개 · 내 글 %d개 · 경쟁 블로그 %d곳"
      % (data["stamp"], len(ranks), pc["total"], len(cmp_["rivals"])))
    if data["prev_time"]:
        p("  지난 회차: %s 와 비교" % data["prev_time"])
    else:
        p("  (첫 회차입니다. 다음부터 순위 변화를 비교해 드립니다)")
    p("=" * 70)

    # ── 1. 순위 변화 ─────────────────────────────────────────────
    p("\n■ 1. 순위가 움직인 검색어")
    moved = [r for r in ranks if r["status"] in ("상승", "하락", "새로 진입", "이탈")]
    moved.sort(key=lambda r: (r["status"] != "새로 진입", -(r["change"] or 0)))
    if not moved:
        p("  움직인 검색어가 없습니다. (첫 회차거나 그대로입니다)")
    for r in moved[:20]:
        mark = {"상승": "▲", "하락": "▼", "새로 진입": "★", "이탈": "×"}[r["status"]]
        delta = ("%+d" % r["change"]) if r["change"] else r["status"]
        p("  %s %-24s %-7s → %-7s  %s"
          % (mark, r["keyword"][:24], rank_text(r["prev_rank"]),
             rank_text(r["rank"]), delta))

    p("\n■ 2. 지금 순위에 잡힌 검색어 (좋은 순)")
    live = sorted([r for r in ranks if r["rank"]], key=lambda r: r["rank"])
    if not live:
        p("  아직 100위 안에 잡힌 검색어가 없습니다.")
    for r in live[:20]:
        p("  %4s  %-26s  경쟁 문서 %s건" % (rank_text(r["rank"]), r["keyword"][:26],
                                        format(r["total"], ",")))
    if len(live) > 20:
        p("  ... 외 %d개 (엑셀 '검색어순위' 시트에 전부 있습니다)" % (len(live) - 20))

    p("\n■ 3. 아직 안 쓴 자리 (추적은 하는데 노린 글이 없는 검색어)")
    p("     경쟁 문서가 많은 순 = 수요가 있다는 뜻입니다.")
    if not data["gaps"]:
        p("  없습니다 — 추적 검색어를 전부 글로 덮었습니다.")
    for g in data["gaps"][:15]:
        p("  · %-30s 경쟁 문서 %s건" % (g["keyword"][:30], format(g["total"], ",")))
    if len(data["gaps"]) > 15:
        p("  ... 외 %d개" % (len(data["gaps"]) - 15))

    # ── 4. 발행 페이스 ───────────────────────────────────────────
    p("\n■ 4. 내 발행 페이스")
    p("  최근 글      %s (%s일 전)" % (pc["last_date"], pc["days_since"]))
    p("  최근 7일 %d개 · 30일 %d개 · 90일 %d개" % (pc["last7"], pc["last30"], pc["last90"]))
    p("  주당 발행    %.1f개" % mine["per_week"])
    if pc["gap_avg"] is not None:
        p("  평균 간격    %.1f일에 한 개" % pc["gap_avg"])
    if pc["categories"]:
        p("  카테고리     " + " / ".join("%s %d" % (c, n)
                                      for c, n in pc["categories"][:5]))
    p("  제목 유형    정보형 %d%% · 상업형 %d%% · 뉴스형 %d%% · 기타 %d%%"
      % (round(mine["info"] * 100), round(mine["commerce"] * 100),
         round(mine["news"] * 100), round(mine["etc"] * 100)))

    # ── 5. 글별 점검 ─────────────────────────────────────────────
    p("\n■ 5. 글별 점검 (최근 12개)")
    for pr in data["posts"][:12]:
        got = ("%d위" % pr["best_rank"]) if pr["best_rank"] else "-"
        p("  %s  %-40s %s" % (pr["pubdate"] or "        ", pr["title"][:40], got))
        if pr["matched"]:
            p("       노린 검색어: %s" % ", ".join(pr["matched"][:4]))

    # ── 6. 경쟁 비교 ─────────────────────────────────────────────
    if cmp_["rivals"]:
        p("\n■ 6. 나 vs 경쟁 (한눈에)")
        p("  %-18s %10s %12s   %s" % ("", "뮤직잇츠", "경쟁 중앙값", "차이"))
        p("  " + "-" * 56)
        for f in cmp_["findings"]:
            mark = " ←" if f["notable"] else ""
            p("  %-18s %10s %12s   %s%s"
              % (f["label"], f["mine"], f["rivals"], f["direction"], mark))

        p("\n■ 7. 핵심 갭 — 경쟁은 이렇게 하는데 나는")
        for g in cmp_["gaps"]:
            p("  · %s" % g)

        p("\n■ 8. 발행이 활발한 경쟁 블로그")
        active = sorted([o for o in cmp_["rivals"] if o["per_week"] is not None],
                        key=lambda o: -o["per_week"])[:10]
        for o in active:
            p("  %-24s 주 %4.1f개  제목 %d자  정보형 %d%%  뉴스형 %d%%"
              % (o["name"][:24], o["per_week"], o["len_median"],
                 round(o["info"] * 100), round(o["news"] * 100)))

        p("\n■ 9. 정보형을 많이 쓰는 경쟁 (제목을 참고하세요)")
        for o in sorted(cmp_["rivals"], key=lambda o: -o["info"])[:4]:
            p("  %s — 정보형 %d%%" % (o["name"], round(o["info"] * 100)))
            for t in o["sample_titles"][:3]:
                p("       · %s" % t)

        if cmp_["gap_topics"]:
            p("\n■ 10. 경쟁 여러 곳이 다루는데 나는 안 다루는 주제")
            p("     " + ", ".join("%s(%d곳)" % (t, c)
                                 for t, c in cmp_["gap_topics"][:12]))

        p("\n■ 11. 경쟁이 자주 쓰는 제목 낱말 (★ = 내가 최근에 안 쓴 것)")
        my_tokens = set(tok for tok, _ in mine.get("top_tokens", []))
        allt = Counter()
        for o in cmp_["rivals"]:
            for tok, c in o["top_tokens"]:
                allt[tok] += c
        line = "  "
        for tok, c in allt.most_common(30):
            chunk = "%s%s(%d)  " % ("★" if tok not in my_tokens else "", tok, c)
            if len(line) + len(chunk) > 66:
                p(line)
                line = "  "
            line += chunk
        p(line)

    # ── 12. 검색 API가 본 경쟁자 ─────────────────────────────────
    if data["search_rivals"]:
        p("\n■ 12. 내 검색어에서 자주 마주치는 블로그 (검색 API 기준)")
        for c in data["search_rivals"][:10]:
            p("  %-26s 검색어 %2d개  최고 %2d위  평균 %.1f위"
              % (c["name"][:26], c["hit_keywords"], c["best_rank"], c["avg_rank"]))

    p("")
    p("  * 순위는 검색 API sort=sim 순서입니다. 통합검색 VIEW 탭 순위가 아닙니다.")
    p("    절대값보다 회차 간 변화를 보세요. 100위 밖은 '미노출'입니다.")
    p("  * 조회수·방문자수·댓글수·이웃수·AI 브리핑 인용수는 가져올 수 없습니다.")
    p("    (네이버 비공개 + robots.txt 전면 차단)")
    p("  * 유형 판정 기준이 통합되면서 바뀌었습니다.")
    p("    2026-08-12 이전 회차의 정보형/뉴스형 % 와 직접 비교하지 마세요.")
    p("")
    return "\n".join(out)


# ---------------------------------------------------------------- 저장

def save_rank_csv(ranks, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["검색어", "이번 순위", "지난 순위", "변화", "상태",
                    "경쟁 문서수", "내 글 제목", "지난 회차"])
        for r in sorted(ranks, key=lambda x: (x["rank"] is None, x["rank"] or 0)):
            w.writerow([r["keyword"], r["rank"] or "미노출",
                        r["prev_rank"] or ("-" if r["prev_rank"] is None else ""),
                        r["change"] if r["change"] is not None else "",
                        r["status"], r["total"], r["my_title"], r["prev_time"]])


def save_compare_csv(mine, cmp_, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["블로그", "아이디", "글수", "주당발행", "제목길이(중앙)",
                    "정보형%", "상업형%", "뉴스형%", "기타%", "물음표%", "숫자%",
                    "글당태그", "마지막글(일전)"])

        def row(o, label):
            return [label, o["blog_id"], o["posts"], o["per_week"],
                    o["len_median"], round(o["info"] * 100),
                    round(o["commerce"] * 100), round(o["news"] * 100),
                    round(o["etc"] * 100), round(o["question"] * 100),
                    round(o["number"] * 100), o["avg_tags"],
                    o["last_days"] if o["last_days"] is not None else ""]

        w.writerow(row(mine, "★ 뮤직잇츠 (나)"))
        for o in sorted(cmp_["rivals"], key=lambda x: -(x["per_week"] or 0)):
            w.writerow(row(o, o["name"]))


# ---------------------------------------------------------------- 실행

def read_keywords(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser(description="성과 추적 — 내 순위 + 경쟁 비교")
    ap.add_argument("--키워드", "--keywords", dest="kwfile", required=True)
    ap.add_argument("--경쟁블로그", "--rivals", dest="rivalfile")
    ap.add_argument("--out", help="결과 저장 프리픽스")
    args = ap.parse_args()

    api_url, headers, mode = naver_api.search_credentials()
    keywords = read_keywords(args.kwfile)
    if not keywords:
        raise SystemExit("추적할 검색어가 없습니다. 설정/추적할키워드.txt 를 확인하세요.")

    today = datetime.now(KST)
    stamp = today.strftime("%Y-%m-%d %H:%M")

    sys.stderr.write("검색어 %d개 · 경쟁 블로그 비교까지 한 번에 합니다. (%s)\n\n"
                     % (len(keywords), mode))

    # 1) 내 글
    sys.stderr.write("[1/4] 내 글 목록 (RSS)\n")
    posts = rss.blog_posts(BLOG_ID, soft=False)
    sys.stderr.write("  내 글 %d개\n" % len(posts))

    # 2) 순위
    sys.stderr.write("\n[2/4] 검색어 순위 (검색 API)\n")
    rank_rows, search_rivals = track_ranks(keywords, api_url, headers)

    history = load_history()
    prev_time = apply_change(rank_rows, history)

    # 3) 내 프로필 + 글별 매칭
    mine = profile(posts, today, "뮤직잇츠", BLOG_ID)
    post_rows, gaps = match_posts(posts, keywords, rank_rows)
    pc = pace(posts, today)

    # 4) 경쟁 블로그 (RSS 한 번만)
    sys.stderr.write("\n[3/4] 경쟁 블로그 (RSS)\n")
    blog_list = read_blog_list(args.rivalfile)
    rivals = collect_rivals(blog_list, today) if blog_list else []
    cmp_ = compare_blogs(mine, rivals)

    sys.stderr.write("\n[4/4] 리포트 작성\n")
    data = {
        "stamp": stamp, "prev_time": prev_time, "blog_id": BLOG_ID,
        "ranks": rank_rows, "search_rivals": search_rivals, "mine": mine,
        "pace": pc, "posts": post_rows, "gaps": gaps, "compare": cmp_,
    }
    print(report(data))

    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        save_rank_csv(rank_rows, args.out + "_순위.csv")
        save_compare_csv(mine, cmp_, args.out + "_경쟁.csv")
        print("저장: %s.json , %s_순위.csv , %s_경쟁.csv\n"
              % (args.out, args.out, args.out))

    # 기록은 결과 파일을 다 쓴 뒤에 저장한다.
    save_history(history, stamp, rank_rows, posts)


if __name__ == "__main__":
    main()
