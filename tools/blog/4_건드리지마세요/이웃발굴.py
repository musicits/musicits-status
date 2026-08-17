#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4. 이웃 발굴 — 내 분야에서 활발한 블로그를 찾아 '여기 가서 소통하세요'로 짚는다.

통합 안내:
  [8. 이웃 소통 후보]를 그대로 옮긴 것이다. 기능이 겹치는 도구가 없어 병합은
  없고, 검색 API 호출·RSS 읽기·블로그 아이디 추출만 공용 모듈로 바꿨다.
  ([3. 성과 추적]도 검색 결과에서 블로거를 모으지만 목적이 다르다 —
   저쪽은 '내 검색어에서 마주치는 경쟁자', 이쪽은 '찾아가서 소통할 사람'.)

왜 이런 모양인가 (반드시 읽을 것):
  원래 원했던 '내 블로그에 달린 댓글/이웃을 모아 보여주기'는 만들 수 없다.
    · 네이버 블로그 댓글·이웃 데이터는 로그인해야만 보이고 공개 API가 없다.
    · blog.naver.com 은 robots.txt 가 전면 차단(Yeti·ClaudeBot 포함)이다.
  그래서 방향을 바꿨다 — '누가 내 분야에서 활발한가'를 검색 API로 찾아,
  내가 직접 찾아가 댓글 달고 이웃 신청할 '후보'를 뽑아준다.

하지 않는 것 (의도적):
  · 자동 댓글·자동 이웃신청: 어뷰징이라 만들지 않는다. 후보 제시까지만.
  · 조회수·댓글수·이웃수 수집: 불가(위 참조).

사용:
    python3 이웃발굴.py --out 결과/이웃후보
    python3 이웃발굴.py --no-rss          # 발행 리듬 확인 생략(더 빠름)
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 공용 import naver_api, rss                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NICHE_FILE = os.path.join(ROOT, "3_설정", "이웃분야키워드.txt")

MY_BLOG = "musicits"        # 나 자신은 후보에서 뺀다
PER_KEYWORD = 30            # 키워드당 검색 상위 몇 개에서 블로거를 모을까
SINCE = "2026-01-01"        # 이 날짜 이후 글만 (활동 중인 블로거를 보려고)
RSS_TOP = 25                # 상위 후보 몇 명까지 RSS로 발행 리듬을 확인할까

# 설정 파일이 없을 때 쓰는 기본값. 통합 전 이웃발굴.py 상단에 박혀 있던 목록이다.
DEFAULT_NICHE = [
    "이어폰 추천", "무선이어폰", "노이즈캔슬링 이어폰", "헤드폰 추천",
    "블루투스 스피커", "에어팟 후기", "갤럭시 버즈", "이어폰 리뷰",
    "DAC 추천", "음향기기", "게이밍 헤드셋", "이어폰 청소 방법",
    "블루투스 코덱", "LP 턴테이블", "바이닐 입문", "포노앰프",
    "가성비 이어폰", "이어폰 비교",
]


def read_niche(path):
    """설정/이웃분야키워드.txt 한 줄에 하나. 없으면 기본값."""
    if not os.path.isfile(path):
        return list(DEFAULT_NICHE)
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out or list(DEFAULT_NICHE)


def main():
    ap = argparse.ArgumentParser(description="이웃·소통 후보 발굴 (검색 API + RSS)")
    ap.add_argument("--out", help="결과 저장 프리픽스")
    ap.add_argument("--no-rss", action="store_true",
                    help="RSS 발행 리듬 확인 생략(더 빠름)")
    args = ap.parse_args()

    api_url, headers, mode = naver_api.search_credentials()
    niche = read_niche(NICHE_FILE)

    sys.stderr.write("분야 키워드 %d개로 후보를 찾습니다. (%s)\n\n" % (len(niche), mode))

    # 1) 키워드마다 검색해서 블로거를 모은다.
    #    나 자신(MY_BLOG)은 후보에서 빼되, 따로 모아서 '내 위치'로 보여준다.
    cand = defaultdict(lambda: {"name": "", "keywords": set(),
                                "posts": 0, "latest": ""})
    mine = {"keywords": set(), "posts": 0, "latest": ""}
    for i, kw in enumerate(niche, 1):
        sys.stderr.write("\r분야 키워드 검색 %d/%d ... (%s)          "
                         % (i, len(niche), kw))
        sys.stderr.flush()
        items, _ = naver_api.search(kw, PER_KEYWORD, api_url, headers,
                                    since=SINCE, verbose=False)
        for it in items:
            bid = rss.blog_id_from_link(it.get("bloggerlink") or it.get("link"))
            if not bid:
                continue
            if bid == MY_BLOG:
                mine["keywords"].add(kw)
                mine["posts"] += 1
                pd = it.get("postdate", "")
                if pd > mine["latest"]:
                    mine["latest"] = pd
                continue
            c = cand[bid]
            c["name"] = rss.clean(it.get("bloggername", "")) or c["name"]
            c["keywords"].add(kw)
            c["posts"] += 1
            pd = it.get("postdate", "")
            if pd > c["latest"]:
                c["latest"] = pd
    sys.stderr.write("\r분야 키워드 검색 완료. 후보 %d명 발견.                        \n"
                     % len(cand))

    # 2) 점수 = 겹치는 키워드 수(관련성) 우선, 그다음 등장 글 수, 그다음 최신성
    rows = []
    for bid, c in cand.items():
        rows.append({
            "blog_id": bid, "name": c["name"],
            "link": "https://blog.naver.com/%s" % bid,
            "kw_hits": len(c["keywords"]), "posts": c["posts"],
            "latest": c["latest"], "keywords": sorted(c["keywords"]),
            "per_week": None, "last_days": None,
        })
    rows.sort(key=lambda r: (r["kw_hits"], r["posts"], r["latest"]), reverse=True)

    # 3) 상위 후보는 RSS로 활동 확인 (내 블로그도 같은 잣대로)
    me = {"blog_id": MY_BLOG, "kw_hits": len(mine["keywords"]),
          "posts": mine["posts"], "latest": mine["latest"],
          "keywords": sorted(mine["keywords"]),
          "missing": [k for k in niche if k not in mine["keywords"]],
          "per_week": None, "last_days": None, "rank": None}
    if not args.no_rss:
        for i, r in enumerate(rows[:RSS_TOP], 1):
            sys.stderr.write("\r상위 후보 활동 확인 %d/%d ...          "
                             % (i, min(RSS_TOP, len(rows))))
            sys.stderr.flush()
            posts = rss.blog_posts(r["blog_id"], soft=True)
            if posts:
                r["per_week"], r["last_days"] = rss.publish_rhythm(posts)
            time.sleep(0.12)
        my_posts = rss.blog_posts(MY_BLOG, soft=True)
        if my_posts:
            me["per_week"], me["last_days"] = rss.publish_rhythm(my_posts)
        sys.stderr.write("\r활동 확인 완료.                                   \n")

    # 내 위치: 후보들과 같은 기준(겹침→글수→최신)으로 줄 세우면 몇 위쯤인가
    my_key = (me["kw_hits"], me["posts"], me["latest"])
    me["rank"] = 1 + sum(1 for r in rows
                         if (r["kw_hits"], r["posts"], r["latest"]) > my_key)

    # 리포트
    print("")
    print("=" * 70)
    print("  이웃·소통 후보 발굴 — 내 분야에서 활발한 블로그")
    print("  분야 키워드 %d개로 검색 · %s 이후 글 기준 · %s"
          % (len(niche), SINCE, datetime.now().strftime("%Y-%m-%d")))
    print("=" * 70)
    # 내 위치 먼저 — 후보들과 같은 잣대로 재면 지금 어디쯤인가
    print("")
    print("  ■ 내 위치 (%s)" % MY_BLOG)
    if me["kw_hits"]:
        last = ""
        if me["last_days"] is not None:
            last = " · 최근 발행 %d일 전" % me["last_days"]
        pw = " · 주 %g개 발행" % me["per_week"] if me["per_week"] is not None else ""
        print("    분야 키워드 %d개 중 %d개의 검색 상위 %d에 걸립니다.%s%s"
              % (len(niche), me["kw_hits"], PER_KEYWORD, pw, last))
        print("    후보들과 같은 기준으로 줄 세우면 %d위쯤입니다. (전체 %d명 기준)"
              % (me["rank"], len(rows) + 1))
    else:
        print("    분야 키워드 %d개의 검색 상위 %d 안에 내 글이 없습니다."
              % (len(niche), PER_KEYWORD))
    if me["missing"]:
        show = me["missing"][:6]
        more = " 외 %d개" % (len(me["missing"]) - 6) if len(me["missing"]) > 6 else ""
        print("    아직 안 걸리는 키워드: %s%s" % (", ".join(show), more))

    print("\n  후보 %d명 중, 여러 키워드에 걸치고 활발한 순으로 정리했습니다." % len(rows))
    print("  ↓ 여기 가서 '직접' 댓글 달고 이웃 신청하세요. (자동 아님)")
    print("")
    print("  %-20s %4s %4s %-9s %s" % ("블로그", "겹침", "글수", "최근글", "겹친 키워드(예)"))
    print("  " + "-" * 66)
    for r in rows[:30]:
        last = ""
        if r["last_days"] is not None:
            last = "%d일 전" % r["last_days"]
        elif r["latest"]:
            last = "%s-%s-%s" % (r["latest"][:4], r["latest"][4:6], r["latest"][6:])
        pw = "  주%g" % r["per_week"] if r["per_week"] is not None else ""
        print("  %-20s %4d %4d %-9s %s%s"
              % (r["name"][:20] or r["blog_id"], r["kw_hits"], r["posts"], last,
                 ", ".join(r["keywords"][:3]), pw))
    print("\n  · '겹침' = 내 분야 키워드 중 이 블로그가 걸린 개수 (많을수록 관련성 큼)")
    print("  · 링크는 엑셀/CSV에 있습니다. 클릭해서 바로 방문하세요.")
    print("  · 이 도구는 후보만 찾습니다. 실제 소통은 직접 하셔야 지수에도 도움이 됩니다.")
    print("  · 분야 키워드는 설정/이웃분야키워드.txt 에서 바꿀 수 있습니다.")
    print("")

    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump({"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                       "keywords": niche, "me": me, "rows": rows},
                      f, ensure_ascii=False, indent=1)
        with open(args.out + "_이웃후보.csv", "w", encoding="utf-8-sig",
                  newline="") as f:
            w = csv.writer(f)
            w.writerow(["순위", "블로그", "아이디", "링크", "겹치는키워드수", "등장글수",
                        "최근글", "주당발행", "최근발행(일전)", "겹친키워드"])
            for i, r in enumerate(rows, 1):
                w.writerow([i, r["name"], r["blog_id"], r["link"], r["kw_hits"],
                            r["posts"], r["latest"], r["per_week"],
                            r["last_days"], " / ".join(r["keywords"])])
        print("저장: %s.json , %s_이웃후보.csv\n" % (args.out, args.out))


if __name__ == "__main__":
    main()
