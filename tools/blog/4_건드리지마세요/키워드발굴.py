#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1. 키워드 발굴 — 무엇을 쓸까.

통합 안내:
  [3. 검색어 트렌드] + [5. 발행 최적화] 를 합친 도구다.
  두 도구는 같은 데이터랩을 각자 호출하고 있었다(3번은 수요만, 5번은 수요 일부 +
  경쟁 + AI적합). 3번의 analyze()가 5번의 demand()의 상위집합이라, 진단은 3번 것을
  쓰고 점수 계산은 5번 것을 얹었다. 계절성·최고치대비·26주 추세는 3번에만 있던
  값인데 그대로 살렸다.

무엇을 하나:
  검색어마다 세 신호를 재서 기회점수(0~100)로 줄세운다.
    수요     40점  데이터랩 검색어트렌드 (관심도 · 상승률 · 빈구간)
    경쟁낮음 30점  검색 API 블로그 (최근30일 격전도 · 상위 장악 · 전체 문서수)
    AI적합   30점  규칙 판정 (정보형 30 / 중간 15 / 상업·뉴스형 0)

  '관심 미미'(빈구간 ≥ 50%)면 최종 점수를 ×0.5로 눌러 바닥으로 보낸다.

사용:
    python3 키워드발굴.py --out 결과/추천
    python3 키워드발굴.py --tier 1            # 정보형 본진만
    python3 키워드발굴.py "무선이어폰 추천"    # 임의 검색어

한계 (되살리지 말 것):
  · 조회수·체류시간: 네이버 비공개 → 불가.
  · 실제 VIEW 탭 순위: search.naver.com 크롤링 금지 → 불가.
  · AI 브리핑 인용: API 없음 → 검색어 형태로 추정만. 실제 인용수는 사람이 확인.
  · 사업자등록 없음 → 검색광고 API(월 검색량) 안 붙임. 다시 제안 금지.
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 공용 import naver_api, classify              # noqa: E402
from 공용.rss import clean                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYWORD_FILE = os.path.join(ROOT, "3_설정", "발굴키워드.txt")

# 데이터랩 눈금 맞추기용 기준 키워드. 1년 내내 꾸준하고 너무 크지도 작지도 않을 것.
ANCHOR = "에어팟"

DAILY_DAYS = 119        # 일별 — 최근 4개월. 지금 뜨는지 보는 용도(상승률)
WEEKLY_WEEKS = 53       # 주별 — 최근 1년. 빈구간·최고치 판정
MONTHLY_MONTHS = 36     # 월별 — 최근 3년. 매년 언제 뜨는지(계절성)

# 이 날짜 이전 데이터는 안 본다. 24개월 미만이면 리포트가 '매년'→'올해'로 바뀐다.
TREND_SINCE = "2026-01-01"
SEARCH_SINCE = "2026-01-01"   # 경쟁 신선도 판정 기준
SEARCH_COUNT = 40             # 키워드당 경쟁 판정에 쓸 상위 문서 수

# 기회점수 배점.
# 이 블로그의 전략은 정보형 → AI 브리핑 인용이다. 상업형·뉴스형이 검색 수요가
# 크다는 이유만으로 상위에 오르면 안 된다. AI적합 비중을 넉넉히 줘서
# '추천·후기'(적합 0점)는 아무리 수요가 커도 정보형 위로 못 오게 눌러둔다.
W_DEMAND = 40.0
W_LOWCOMP = 30.0
W_AIFIT = 30.0


# ---------------------------------------------------------------- 키워드 읽기

def read_keywords(path, tier=None):
    """설정/발굴키워드.txt → [(표시이름, [검색어들], 분류, 순위)].

    형식:  순위 | 분류 | 표시이름 | 검색어1, 검색어2
    검색어 칸이 비면 표시이름을 그대로 쓴다.
    """
    if not os.path.isfile(path):
        raise SystemExit("[오류] 키워드 파일이 없습니다: %s" % path)

    out, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                bad += 1
                continue
            try:
                t = int(parts[0])
            except ValueError:
                bad += 1
                continue
            cat, name = parts[1], parts[2]
            terms = [w.strip() for w in parts[3].split(",")] if len(parts) > 3 else []
            terms = [w for w in terms if w] or [name]
            if not name:
                bad += 1
                continue
            if tier and t != tier:
                continue
            out.append((name, terms, cat, t))

    if bad:
        sys.stderr.write("  (형식이 안 맞는 줄 %d개는 건너뜁니다)\n" % bad)
    if not out:
        raise SystemExit("[오류] 조사할 키워드가 없습니다. 설정/발굴키워드.txt 를 확인하세요.")
    return out


# ---------------------------------------------------------------- 수요 (데이터랩)

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def slope(xs):
    """최소제곱 기울기. 값이 커질수록 우상향."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = (n - 1) / 2.0
    my = mean(xs)
    num = sum((i - mx) * (v - my) for i, v in enumerate(xs))
    den = sum((i - mx) ** 2 for i in range(n))
    return num / den if den else 0.0


def demand(name, category, daily_v, weekly_p, weekly_v, monthly_p, monthly_v):
    """검색 수요를 진단한다. [3. 검색어 트렌드]의 analyze()를 그대로 옮긴 것."""
    now7 = mean(daily_v[-7:])
    prev28 = mean(daily_v[-35:-7])
    year_max = max(weekly_v) if weekly_v else 0.0

    # 상승률 — 최근 7일이 그 앞 4주보다 얼마나 올랐나.
    # 바닥이 거의 0이면 나눗셈이 폭주하므로 하한을 둔다. 하한은 그 검색어
    # 자기 최고치에 비례해야 한다. 고정값(0.05 등)을 쓰면 눈금이 큰 키워드에
    # 맞춰져서, 관심도 0.2짜리 정보형 키워드가 통째로 '하락'으로 찍힌다.
    base = max(prev28, year_max * 0.02, 1e-9)
    momentum = (now7 / base - 1) * 100 if now7 or prev28 else 0.0
    momentum = max(-100.0, min(999.0, momentum))

    # 관심도가 아주 작은 키워드는 상승률이 요동친다. 관심도 0.01짜리가 한 주
    # 사이에 두 배가 되면 +100%지만 그건 유행이 아니라 잡음이다. 지우지는
    # 않는다 — 정보형 키워드는 원래 작고 그게 이 블로그의 노림수다.
    weak_signal = year_max < 0.10

    # 검색량이 정말 없는가 — 데이터랩은 값이 0인 구간을 아예 안 준다.
    # 그 '빈 구간 비율'이 API가 주는 유일한 절대 신호다. 관심 미미 판정은
    # 이걸로 해야 한다. 상대 수치로 자르면 1등 키워드가 크기만 해도
    # 나머지가 전부 미미로 밀려난다(실제로 겪었다).
    zero_ratio = (sum(1 for v in weekly_v if v <= 0) / len(weekly_v)
                  if weekly_v else 1.0)

    peak_ratio = (now7 / year_max * 100) if year_max > 0 else 0.0

    # 연중 언제 뜨는가 — 월별 3년치를 달(1~12)로 접어서 평균
    by_month = defaultdict(list)
    for p, v in zip(monthly_p, monthly_v):
        m = int(p[5:7]) if len(p) >= 7 else 0
        if m:
            by_month[m].append(v)
    month_avg = {m: mean(vs) for m, vs in by_month.items()}
    overall = mean(month_avg.values()) if month_avg else 0.0
    best_months = sorted([m for m, _ in
                          sorted(month_avg.items(), key=lambda x: -x[1])[:2]])
    seasonality = ((max(month_avg.values()) / overall - 1) * 100
                   if month_avg and overall > 0 else 0.0)

    peak_period = weekly_p[weekly_v.index(year_max)] if weekly_v else None

    if zero_ratio >= 0.5:
        state = "관심 미미"
    elif momentum >= 60:
        state = "급상승"
    elif momentum >= 20:
        state = "상승"
    elif momentum <= -35:
        state = "하락"
    elif momentum <= -15:
        state = "식는 중"
    else:
        state = "유지"

    return {
        "keyword": name, "category": category,
        "level": round(now7, 3), "prev": round(prev28, 3),
        "momentum": round(momentum, 1), "peak_ratio": round(peak_ratio, 1),
        "year_max": round(year_max, 3), "peak_period": peak_period,
        "trend26": round(slope(weekly_v[-26:]), 4),
        "zero_ratio": round(zero_ratio, 3), "weak_signal": bool(weak_signal),
        "state": state,
        "month_avg": {str(m): round(v, 2) for m, v in sorted(month_avg.items())},
        "best_months": best_months, "seasonality": round(seasonality, 1),
    }


# ---------------------------------------------------------------- 경쟁 (검색 API)

def competition(items, total):
    """상위 문서 집단에서 경쟁 강도를 뽑는다. 값이 클수록 뚫기 어렵다.

    sim 정렬 상위 40건 표본이라 거친 프록시다. sim 상위는 오래된 권위글이
    많아 신흥 격전을 과소평가할 수 있다. 방향만 신뢰할 것.
    """
    import re
    from collections import Counter

    n = len(items)
    now = datetime.now()
    fresh30 = 0
    for it in items:
        raw = it.get("postdate", "")
        if re.match(r"^\d{8}$", raw or ""):
            if (now - datetime.strptime(raw, "%Y%m%d")).days <= 30:
                fresh30 += 1
    fresh30_ratio = (fresh30 / n * 100) if n else 0.0

    bloggers = Counter(clean(it.get("bloggername", "")) for it in items)
    dominance = sum(c for _, c in bloggers.items() if c >= 2)   # 2건 이상 장악
    dominance_ratio = (dominance / n * 100) if n else 0.0

    return {
        "total_docs": total,
        "sampled": n,
        "fresh30_ratio": round(fresh30_ratio, 1),
        "dominance_ratio": round(dominance_ratio, 1),
    }


# ---------------------------------------------------------------- 기회점수

def opportunity(d, c, ai_pts, level_max):
    """세 축을 묶어 0~100점. 각 축의 원점수도 함께 줘서 근거를 보여준다."""
    if d["state"] == "조회 실패":
        # 수요를 못 받았으니 점수를 매길 수 없다. 0점으로 두되 순위에서 빼낸다.
        return {"score": 0.0, "demand_pts": 0.0, "lowcomp_pts": 0.0,
                "ai_pts": round(ai_pts, 1), "hardness": 0.0}

    # 수요(0~40): 관심도를 이번 실행 최댓값 대비로 환산. 검색이 거의 없으면 0.
    if d["state"] == "관심 미미":
        demand_pts = 0.0
    else:
        rel = (d["level"] / level_max) if level_max > 0 else 0.0
        # 정보형은 대체로 작다. 제곱근으로 펴서 작은 실수요가 0으로 뭉개지지 않게.
        demand_pts = (rel ** 0.5) * W_DEMAND
        if d["weak_signal"]:
            demand_pts *= 0.6                                # 신호 약하면 감점
        if d["state"] in ("급상승", "상승"):
            demand_pts = min(W_DEMAND, demand_pts * 1.15)    # 오르는 중이면 가점

    # 경쟁낮음(0~30): 격전도 절반 + 장악 3할 + 주제크기 2할. 낮을수록 점수↑.
    fresh = min(c["fresh30_ratio"], 100.0) / 100.0
    dom = min(c["dominance_ratio"], 100.0) / 100.0
    size = c["total_docs"] or 0
    size_hard = min(math.log10(size + 1) / 5.0, 1.0) if size > 0 else 0.0  # 10만건≈1.0
    hardness = fresh * 0.5 + dom * 0.3 + size_hard * 0.2
    lowcomp_pts = (1.0 - hardness) * W_LOWCOMP

    total = demand_pts + lowcomp_pts + ai_pts
    # 검색이 거의 없는 표현은 경쟁·AI적합이 아무리 좋아도 '지금 쓸 키워드'가 아니다.
    if d["state"] == "관심 미미":
        total *= 0.5
    return {
        "score": round(total, 1),
        "demand_pts": round(demand_pts, 1),
        "lowcomp_pts": round(lowcomp_pts, 1),
        "ai_pts": round(ai_pts, 1),
        "hardness": round(hardness * 100, 1),
    }


def season_phrase(d, today, multi_year):
    """계절성 한 마디. 쓸 말이 없으면 None.

    지난 달을 두고 '뜁니다'라고 하면 안 된다. 8월에 "올해 1·3월에 뜁니다,
    그 앞에 올려두세요"는 이미 지나간 달을 미래처럼 말하는 것이다.
    데이터가 한 해치뿐이면 예측이 아니라 관찰만 말할 수 있다.
    """
    peak = d["best_months"]
    if d["seasonality"] < 40 or not peak:
        return None
    # 검색량이 거의 없는 키워드는 한 달만 값이 있어도 계절성이 상한까지 튄다.
    # 엉뚱한 달을 짚게 되므로 아예 말하지 않는다(리포트 계절성 목록과 같은 기준).
    if d["state"] in ("관심 미미", "조회 실패") or d["weak_signal"]:
        return None

    months = "·".join("%d월" % m for m in peak)
    ahead = [m for m in peak if m > today.month]

    if multi_year:
        # 여러 해를 겹쳐 봤으니 '매년 그렇다'고 말해도 된다 = 예측 가능
        nxt = ahead[0] if ahead else peak[0]
        gap = (nxt - today.month) % 12
        if gap <= 2:
            return "매년 %d월에 오릅니다. 지금부터 준비해 %d월 초에 올리세요." % (nxt, nxt)
        return "매년 %s에 뜁니다. 그때 맞춰 미리 준비하세요." % months

    # 한 해치뿐 — '올해 이랬다'까지만 말할 수 있다
    if ahead:
        return ("올해는 %s에 높았습니다. %d월이 아직 남았으니 그 앞에 올려두세요."
                % (months, ahead[0]))
    # 고점이 이미 지났고 비교할 작년도 없다 → 시기 조언을 할 근거가 없다
    return None


def prescription(row, multi_year, today):
    """한 줄 처방 — 지금 쓸지, 언제 쓸지, 각도를 어떻게 틀지."""
    d, ai = row["demand"], row["ai_fit"]
    st = d["state"]
    seasonal = season_phrase(d, today, multi_year)

    if st == "조회 실패":
        return "데이터랩 일시 오류로 이번엔 수요를 못 받았습니다. 다시 실행하면 대개 나옵니다."
    if st == "관심 미미":
        return "이 표현은 검색이 거의 없습니다. 말을 바꿔보세요('~란'→'~ 뜻', '원리'→'왜')."
    if ai.startswith("낮음"):
        return "검색은 되지만 AI 인용은 어려운 형태입니다(뉴스·상업형). 정보형으로 각도를 트세요."
    if st == "급상승":
        if d.get("weak_signal"):
            return "올랐지만 원래 검색량이 아주 작아 흔들린 것일 수 있습니다. 몇 주 더 보세요."
        if d["category"] in ("루머", "공식뉴스", "뉴스"):
            return "지금 터지는 중입니다. 오늘내일 안에 쓰세요. 늦으면 묻힙니다."
        return "관심이 확 올랐습니다. 이번 주 안에 정보형으로 쓰세요."
    if st == "상승":
        return "올라오는 중입니다. 지금 써두면 정점에 맞춰집니다."
    if st in ("하락", "식는 중"):
        if seasonal:
            return seasonal
        return "관심이 식는 중이라 급하지 않습니다. 우선순위 뒤로."
    # 유지
    if seasonal:
        return "평소엔 잔잔합니다. " + seasonal
    return "1년 내내 꾸준한 정보형입니다. AI 인용 노리기 딱 좋은 자리 — 아무 때나 쓰세요."


# ---------------------------------------------------------------- 출력

def bar(v, vmax, width=20):
    filled = int(round(min(v / max(vmax, 0.0001), 1.0) * width))
    return "█" * filled + "·" * (width - filled)


def report(all_rows, since, today, multi_year, tier):
    # 수요를 못 받은 것은 점수 순위에서 빼낸다 — 0점으로 섞이면 '기회 없음'처럼 읽힌다.
    failed = [r for r in all_rows if r["demand"]["state"] == "조회 실패"]
    rows = sorted([r for r in all_rows if r["demand"]["state"] != "조회 실패"],
                  key=lambda r: -r["opp"]["score"])
    out = []
    p = out.append
    scope = {1: " · 1순위(정보형)만", 2: " · 2순위(상업·뉴스형)만"}.get(tier, "")
    p("")
    p("=" * 70)
    p("  키워드 발굴 리포트 — 지금 어떤 검색어로 쓸까")
    p("  %s ~ %s%s · 키워드 %d개" % (since, today, scope, len(all_rows)))
    p("  기회점수 = 수요(40) + 경쟁낮음(30) + AI적합(30)")
    p("=" * 70)

    if failed:
        p("\n■ 이번에 수요를 못 받은 검색어 %d개 (데이터랩 일시 오류)" % len(failed))
        p("  아래 점수 순위에서 빼놨습니다. 다시 실행하면 대개 나옵니다.")
        for r in failed[:12]:
            p("  · %s" % r["keyword"])
        if len(failed) > 12:
            p("  ... 외 %d개" % (len(failed) - 12))

    p("\n■ 이번 주 이거 쓰세요 (기회점수 TOP 15)")
    p("  %-24s %5s  %-8s %-10s" % ("키워드", "점수", "상태", "AI인용"))
    p("  " + "-" * 62)
    for r in rows[:15]:
        p("  %-24s %5.1f  %-8s %-10s" % (
            r["keyword"][:24], r["opp"]["score"], r["demand"]["state"], r["ai_fit"]))

    p("\n■ 왜 이 점수인가 (TOP 15 근거)")
    p("  %-22s %5s =  수요  + 경쟁낮음 + AI    (경쟁난이도 %%)" % ("키워드", "점수"))
    p("  " + "-" * 66)
    for r in rows[:15]:
        o = r["opp"]
        p("  %-22s %5.1f =  %4.1f  +   %4.1f   + %3.0f    (%4.1f)" % (
            r["keyword"][:22], o["score"], o["demand_pts"], o["lowcomp_pts"],
            o["ai_pts"], o["hardness"]))

    p("\n■ 지금 뜨는 정보형 (상승 + AI 인용 높음)")
    rising = [r for r in rows if r["demand"]["state"] in ("급상승", "상승")
              and r["ai_fit"] == "높음"]
    rising.sort(key=lambda r: -r["demand"]["momentum"])
    if not rising:
        p("  이번 주 눈에 띄게 오른 정보형 키워드는 없습니다. (정보형은 원래 꾸준한 편)")
    for r in rising[:10]:
        d = r["demand"]
        p("  %-22s %+6.0f%%  관심도 %.2f  %s%s" % (
            r["keyword"][:22], d["momentum"], d["level"], d["state"],
            "  (신호 약함)" if d["weak_signal"] else ""))

    # ── 여기부터는 [3. 검색어 트렌드]에만 있던 것. 통합하면서 살렸다. ──
    p("\n■ 연중 언제 뜨나 (계절성 강한 것부터)")
    every = "매년" if multi_year else "올해"
    # 검색량이 거의 없는 키워드는 한 달만 값이 있어도 계절성이 상한(+600%)까지
    # 튄다. 유행이 아니라 잡음이라 이 목록에서만 빼낸다(점수 계산엔 영향 없음).
    seasonal = [r for r in rows if r["demand"]["seasonality"] >= 40
                and r["demand"]["best_months"]
                and r["demand"]["state"] != "관심 미미"
                and not r["demand"]["weak_signal"]]
    seasonal.sort(key=lambda r: -r["demand"]["seasonality"])
    if not seasonal:
        p("  뚜렷한 계절성을 보이는 키워드가 없습니다.")
        p("  (검색량이 아주 작은 키워드는 한 달만 값이 있어도 계절성이 튀어서 제외했습니다)")
    if not multi_year:
        p("  * 데이터가 한 해치뿐이라 '매년'이라 말할 수 없습니다. '올해는 이랬다'로만 읽으세요.")
        p("  * ← 표시는 그 달이 아직 안 지나서 이번에 노려볼 수 있다는 뜻입니다.")
    this_month = datetime.now().month
    for r in seasonal[:12]:
        d = r["demand"]
        ahead = [m for m in d["best_months"] if m > this_month]
        verb = "뜀" if multi_year else "높았음"
        mark = "  ← %d월 남음" % ahead[0] if (ahead and not multi_year) else ""
        p("  %-22s %s %-7s %s (평균 대비 +%.0f%%)%s" % (
            r["keyword"][:22], every,
            "·".join("%d월" % m for m in d["best_months"]),
            verb, d["seasonality"], mark))

    p("\n■ 1년 최고치 대비 지금 어디쯤")
    live = [r for r in rows if r["demand"]["state"] != "관심 미미"]
    live.sort(key=lambda r: -r["demand"]["peak_ratio"])
    p("  %-22s %6s  %s" % ("키워드", "최고대비", "지금 위치"))
    p("  " + "-" * 56)
    for r in live[:12]:
        d = r["demand"]
        p("  %-22s %5.0f%%  %s" % (r["keyword"][:22], d["peak_ratio"],
                                   bar(d["peak_ratio"], 100)))

    p("\n■ 수요는 있는데 경쟁이 빡센 것 (각도를 틀거나 롱테일로)")
    hard = [r for r in rows if r["demand"]["state"] != "관심 미미"
            and r["opp"]["hardness"] >= 55]
    hard.sort(key=lambda r: -r["opp"]["hardness"])
    if not hard:
        p("  없음 — 후보 키워드 경쟁이 대체로 낮습니다.")
    for r in hard[:10]:
        c = r["comp"]
        p("  %-22s 경쟁 %4.1f%%  (최근30일 %4.1f%% · 장악 %4.1f%% · 문서 %s건)" % (
            r["keyword"][:22], r["opp"]["hardness"], c["fresh30_ratio"],
            c["dominance_ratio"], format(c["total_docs"], ",")))

    p("\n■ 검색이 거의 없는 표현 (말을 바꿔야 함)")
    dead = [r for r in rows if r["demand"]["state"] == "관심 미미"]
    if not dead:
        p("  없음.")
    for r in dead[:15]:
        p("  · %s" % r["keyword"])
    if len(dead) > 15:
        p("  ... 외 %d개 (엑셀·CSV에 전부 있습니다)" % (len(dead) - 15))

    p("\n■ 그래서 뭘 쓰나 (기회점수 순 처방)")
    for r in rows[:20]:
        p("  · %-22s %s" % (r["keyword"][:22], r["rx"]))

    p("")
    p("  * 관심도는 데이터랩 상대값이라 '같은 실행 안에서만' 비교할 수 있습니다.")
    p("  * 경쟁은 sim 정렬 상위 %d건 표본이라 거친 어림값입니다. 방향만 보세요." % SEARCH_COUNT)
    p("")
    return "\n".join(out)


def save_csv(rows, path):
    rows = sorted(rows, key=lambda r: -r["opp"]["score"])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["순위", "키워드", "분류", "기회점수", "수요점수", "경쟁낮음점수",
                    "AI점수", "경쟁난이도%", "상태", "관심도", "상승률%", "최고대비%",
                    "빈구간비율", "계절성%", "뜨는달", "최근30일%", "장악%",
                    "전체문서수", "AI인용적합", "처방"])
        for i, r in enumerate(rows, 1):
            d, c, o = r["demand"], r["comp"], r["opp"]
            w.writerow([i, r["keyword"], r["category"], o["score"], o["demand_pts"],
                        o["lowcomp_pts"], o["ai_pts"], o["hardness"], d["state"],
                        d["level"], d["momentum"], d["peak_ratio"], d["zero_ratio"],
                        d["seasonality"],
                        "·".join("%d월" % m for m in d["best_months"]),
                        c["fresh30_ratio"], c["dominance_ratio"], c["total_docs"],
                        r["ai_fit"], r["rx"]])


# ---------------------------------------------------------------- 실행

def month_start(d, months_back):
    y, m = d.year, d.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


def main():
    ap = argparse.ArgumentParser(description="키워드 발굴 — 수요 + 경쟁 + AI적합")
    ap.add_argument("keywords", nargs="*", help="직접 지정할 검색어. 생략하면 설정 파일")
    ap.add_argument("--tier", type=int, choices=[1, 2], help="1=정보형만 2=상업·뉴스형만")
    ap.add_argument("--out", help="결과 저장 프리픽스 (.json / _추천.csv)")
    args = ap.parse_args()

    search_url, search_h, mode = naver_api.search_credentials()
    trend_h = naver_api.trend_credentials()

    if args.keywords:
        targets = [(kw, [kw], "직접입력", 0) for kw in args.keywords]
    else:
        targets = read_keywords(KEYWORD_FILE, args.tier)
    names = [t[0] for t in targets]

    # 기간 계산 (데이터랩)
    today = date.today()
    end = today - timedelta(days=1)          # 어제까지. 오늘치는 아직 안 찬다.
    end_s = end.isoformat()
    floor = max(date(2016, 1, 1),
                datetime.strptime(TREND_SINCE, "%Y-%m-%d").date())
    d_start = max(end - timedelta(days=DAILY_DAYS), floor).isoformat()
    w_start = max(end - timedelta(weeks=WEEKLY_WEEKS), floor).isoformat()
    m_start = max(month_start(end, MONTHLY_MONTHS), floor).isoformat()
    months = (end.year - floor.year) * 12 + (end.month - floor.month) + 1
    multi_year = months >= 24

    sys.stderr.write("키워드 %d개 · 검색 API + 데이터랩 두 곳을 조회합니다. (%s)\n"
                     % (len(targets), mode))
    sys.stderr.write("수요 조회 기간: %s ~ %s\n\n" % (floor.isoformat(), end_s))

    # 1) 데이터랩 — 검색 수요
    sys.stderr.write("[검색 수요 조회 — 데이터랩]\n")
    trend_targets = [(n, terms, cat) for n, terms, cat, _ in targets]
    _, dv, f1 = naver_api.trend_collect(trend_h, trend_targets, d_start, end_s,
                                        "date", "일별  ", ANCHOR)
    wp, wv, f2 = naver_api.trend_collect(trend_h, trend_targets, w_start, end_s,
                                         "week", "주별  ", ANCHOR)
    mp, mv, f3 = naver_api.trend_collect(trend_h, trend_targets, m_start, end_s,
                                         "month", "월별  ", ANCHOR)
    naver_api.rescale([dv, wv, mv])

    # 세 단위 중 하나라도 못 받은 키워드는 수요를 말할 수 없다. 0으로 채우면
    # '관심 미미'로 둔갑해서 "이 표현은 검색이 거의 없습니다"라는 틀린 처방이
    # 나간다. 따로 빼서 '조회 실패'로 표시한다.
    unavailable = f1 | f2 | f3
    if unavailable:
        sys.stderr.write("  * 데이터랩 일시 오류로 %d개는 수요를 못 받았습니다. "
                         "다시 실행하면 대개 됩니다.\n" % len(unavailable))

    # 이번 달이 안 끝났으면 계절성 계산에서 뺀다 (반 달치가 낮게 잡혀 왜곡됨)
    last_day = (month_start(end, -1) - timedelta(days=1)) == end
    if mp and not last_day:
        mp = mp[:-1]
        for k in mv:
            mv[k] = mv[k][:-1]

    demands = {}
    for name, _, cat, _ in targets:
        d = demand(name, cat, dv.get(name, []), wp, wv.get(name, []),
                   mp, mv.get(name, []))
        if name in unavailable:
            d["state"] = "조회 실패"
        demands[name] = d
    level_max = max((d["level"] for n, d in demands.items()
                     if n not in unavailable), default=1.0) or 1.0

    # 2) 검색 API — 경쟁
    sys.stderr.write("\n[경쟁 조회 — 검색 API]\n")
    comps = {}
    for i, name in enumerate(names, 1):
        items, total = naver_api.search(name, SEARCH_COUNT, search_url, search_h,
                                        since=SEARCH_SINCE, verbose=False)
        comps[name] = competition(items, total)
        sys.stderr.write("\r  경쟁 ... %d/%d (%s)                    "
                         % (i, len(names), name[:18]))
        sys.stderr.flush()
    sys.stderr.write("\r  경쟁 ... 완료 (%d개)                                \n" % len(names))

    # 3) 결합
    rows = []
    for name, terms, cat, tier in targets:
        d, c = demands[name], comps[name]
        fit, ai_pts, ai_why = classify.ai_fit(name, cat)
        o = opportunity(d, c, ai_pts, level_max)
        row = {"keyword": name, "terms": terms, "category": cat, "tier": tier,
               "demand": d, "comp": c, "ai_fit": fit, "ai_why": ai_why, "opp": o}
        row["rx"] = prescription(row, multi_year, today)
        rows.append(row)

    print(report(rows, floor.isoformat(), end_s, multi_year, args.tier))

    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump({"generated": end_s, "since": floor.isoformat(),
                       "multi_year": multi_year, "tier": args.tier,
                       "anchor": ANCHOR, "rows": rows},
                      f, ensure_ascii=False, indent=1)
        save_csv(rows, args.out + "_추천.csv")
        print("저장: %s.json , %s_추천.csv\n" % (args.out, args.out))


if __name__ == "__main__":
    main()
