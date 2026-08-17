#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2. 제목 진단 — 어떻게 쓸까.

통합 안내:
  [1. 블로그 키워드 분석] + [6. 상위노출 진단] 을 합친 도구다.
  두 도구는 똑같이 '검색 API 상위 문서에서 제목 패턴을 뽑는' 일을 하고 있었다.
  1번의 analyze() 와 6번의 profile() 이 같은 계산을 각자 하고 있었고,
  6번이 거기에 '내 제목 채점'을 얹은 상위집합이었다.

  profile() 은 두 함수의 합집합이다. 6번에 없던 것(구분자 패턴 · 자주 쓰는
  낱말/두낱말 · 신선도 구간 · 반복 블로거 · 연도/영문 비율)은 1번에서 가져왔다.

무엇을 하나:
  키워드마다 상위 40개 문서에서 '이겨온 제목의 표준형'을 만들고,
  내 제목을 그 표준과 대조해 100점으로 채점한다.

  제목을 안 적고 키워드만 쓰면 표준형과 패턴 통계만 보여준다
  (= 예전 [1. 블로그 키워드 분석]이 하던 일).

사용:
    python3 제목진단.py --입력 ../설정/진단할제목.txt --out 결과/진단
    python3 제목진단.py "노이즈캔슬링 원리 | 노캔 원리 완벽 정리"

한계 (되살리지 말 것):
  · 검색 API 순위 ≠ 실제 VIEW 탭 순위. search.naver.com 크롤링은 robots가 막음.
  · 조회수·체류시간·본문 품질: 다루지 않음(네이버 비공개 / 범위 밖).
  · 제안 제목은 고정 템플릿 기반 예시다.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 공용 import naver_api, classify             # noqa: E402
from 공용.rss import clean                       # noqa: E402
from 공용.classify import (keyword_position, title_type, tokenize,  # noqa: E402
                           josa, hook_counts)

TOP_COUNT = 40          # 표준형을 만들 상위 문서 수
SINCE = "2026-01-01"    # 이 날짜 이후 글만 (옆 도구들과 같은 기준)

# 제목에서 자주 쓰이는 구분자. 통합 전 [1. 블로그 키워드 분석]에만 있던 것.
SEPARATORS = {
    "대괄호 []": r"\[.+?\]",
    "소괄호 ()": r"\(.+?\)",
    "물결 ~": r"~",
    "파이프 |": r"\|",
    "쉼표 ,": r",",
    "콜론 :": r":",
    "하이픈 -": r"\s-\s|\s—\s",
    "느낌표 !": r"!",
    "물음표 ?": r"\?",
    "이모지": r"[\U0001F300-\U0001FAFF☀-➿]",
}


# ---------------------------------------------------------------- 표준형

def profile(keyword, items):
    """상위 문서 집단에서 '이겨온 제목의 표준형'을 뽑는다.

    [6. 상위노출 진단]의 profile() + [1. 블로그 키워드 분석]의 analyze() 합집합.
    """
    titles = [clean(it.get("title", "")) for it in items]
    titles = [t for t in titles if t]
    n = len(titles)
    if n == 0:
        return None

    lengths = sorted(len(t) for t in titles)
    positions = Counter(keyword_position(t, keyword)[0] for t in titles)
    types = Counter(title_type(t) for t in titles)
    hooks = hook_counts(titles)
    top_hooks = [w for w, _ in hooks.most_common(6)]

    with_digit = sum(1 for t in titles if re.search(r"\d", t))
    with_q = sum(1 for t in titles if "?" in t)
    with_year = sum(1 for t in titles if re.search(r"20[2-3]\d", t))
    with_eng = sum(1 for t in titles if re.search(r"[A-Za-z]{2,}", t))

    # ── 아래는 통합 전 [1. 블로그 키워드 분석]에만 있던 것들 ──
    seps = {}
    for label, pat in SEPARATORS.items():
        hit = sum(1 for t in titles if re.search(pat, t))
        if hit:
            seps[label] = hit

    unigrams, bigrams = Counter(), Counter()
    kw_tokens = set(tokenize(keyword))
    for t in titles:
        toks = tokenize(t)
        unigrams.update(tok for tok in toks if tok not in kw_tokens)
        for a, b in zip(toks, toks[1:]):
            bigrams[a + " " + b] += 1

    now = datetime.now()
    buckets, dates = Counter(), []
    fresh30 = 0
    for it in items:
        raw = it.get("postdate", "")
        if not re.match(r"^\d{8}$", raw or ""):
            continue
        d = datetime.strptime(raw, "%Y%m%d")
        dates.append(d)
        age = (now - d).days
        if age <= 30:
            buckets["30일 이내"] += 1
            fresh30 += 1
        elif age <= 90:
            buckets["90일 이내"] += 1
        elif age <= 365:
            buckets["1년 이내"] += 1
        else:
            buckets["1년 초과"] += 1

    bloggers = Counter(clean(it.get("bloggername", "")) for it in items)
    dominance = sum(c for _, c in bloggers.items() if c >= 2)

    return {
        "keyword": keyword,
        "n": n,
        "len_median": lengths[n // 2],
        "len_avg": round(sum(lengths) / n, 1),
        "len_p25": lengths[int(n * 0.25)],
        "len_p75": lengths[int(n * 0.75)],
        "len_min": lengths[0],
        "len_max": lengths[-1],
        "pos_dominant": positions.most_common(1)[0][0] if positions else "앞부분",
        "positions": dict(positions),
        "type_dominant": types.most_common(1)[0][0] if types else "기타",
        "types": dict(types),
        "top_hooks": top_hooks,
        "hooks": hooks.most_common(15),
        "hook_ratio": round(sum(1 for t in titles
                                if any(h.lower() in t.lower() for h in top_hooks))
                            / n * 100, 0),
        "digit_ratio": round(with_digit / n * 100, 0),
        "q_ratio": round(with_q / n * 100, 0),
        "year_ratio": round(with_year / n * 100, 0),
        "english_ratio": round(with_eng / n * 100, 0),
        "separators": seps,
        "unigrams": unigrams.most_common(25),
        "bigrams": [(g, c) for g, c in bigrams.most_common(15) if c >= 2],
        "freshness": dict(buckets),
        "fresh30_ratio": round(fresh30 / n * 100, 0),
        "latest_post": max(dates).strftime("%Y-%m-%d") if dates else None,
        "dominance": dominance,
        "repeat_bloggers": [(b, c) for b, c in bloggers.most_common(5) if c >= 2],
        "sample_titles": titles[:8],
        "titles": titles,
    }


# ---------------------------------------------------------------- 채점

def diagnose(my_title, kw, pr):
    """내 제목을 표준형과 대조해 채점하고 고칠 점을 만든다. (총점, 축별내역)"""
    t = my_title.strip()
    L = len(t)
    axes = []          # (축, 배점, 점수, 코멘트)

    # 1) 길이 (25)
    if pr["len_p25"] <= L <= pr["len_p75"]:
        axes.append(("길이", 25, 25, "%d자 — 상위권 주력 구간(%d~%d자) 안. 좋습니다."
                     % (L, pr["len_p25"], pr["len_p75"])))
    elif pr["len_min"] <= L <= pr["len_max"]:
        axes.append(("길이", 25, 15,
                     "%d자 — 나쁘진 않지만 주력 구간(%d~%d자)으로 맞추면 더 안전."
                     % (L, pr["len_p25"], pr["len_p75"])))
    else:
        near = pr["len_p25"] if L < pr["len_p25"] else pr["len_p75"]
        gap = abs(L - near)
        sc = max(0, 12 - gap)
        verb = "너무 짧습니다" if L < pr["len_p25"] else "너무 깁니다"
        axes.append(("길이", 25, sc,
                     "%d자 — %s. 상위권은 %d~%d자. %d자 안팎으로 맞추세요."
                     % (L, verb, pr["len_p25"], pr["len_p75"], pr["len_median"])))

    # 2) 키워드 위치 (20)
    #    앞부분이 검색 노출에 가장 유리하다는 건 절대 기준이다. 상위권 다수가
    #    키워드를 변형해 써서 pos_dominant가 '미포함'으로 나와도, 내 글은 앞부분에
    #    그대로 넣는 게 항상 유리하므로 앞배치를 감점하지 않는다.
    #    (이 함정 때문에 처음에 앞배치가 감점됐었다 — 되돌리지 말 것.)
    pos = keyword_position(t, kw)[0]
    if pos == "미포함":
        axes.append(("키워드 위치", 20, 0,
                     "제목에 '%s'%s 통째로 안 들어갔습니다. 앞부분에 그대로 넣으세요."
                     % (kw, josa(kw, "이/가"))))
    elif pos == "앞부분":
        axes.append(("키워드 위치", 20, 20,
                     "'%s'%s 앞부분에 뒀습니다 — 검색 노출에 가장 유리합니다."
                     % (kw, josa(kw, "을/를"))))
    elif pos == "중간":
        axes.append(("키워드 위치", 20, 14,
                     "'%s'%s 중간에 있습니다. 앞부분으로 당기면 더 유리합니다."
                     % (kw, josa(kw, "이/가"))))
    else:
        axes.append(("키워드 위치", 20, 8,
                     "'%s'%s 뒷부분에 있습니다. 앞부분으로 옮기세요."
                     % (kw, josa(kw, "이/가"))))

    # 3) 유형 (25) — 이 블로그는 정보형이 노림수
    my_type = title_type(t)
    win = pr["type_dominant"]
    if my_type == win:
        axes.append(("유형", 25, 25,
                     "%s 제목 — 상위권 다수(%s)와 같은 결." % (my_type, win)))
    elif my_type == "정보형":
        axes.append(("유형", 25, 20,
                     "정보형 제목입니다. 상위권은 %s가 많지만, 정보형은 "
                     "AI 브리핑 인용에 유리하니 유지 OK." % win))
    elif my_type == "기타":
        axes.append(("유형", 25, 8,
                     "유형이 뚜렷하지 않습니다. "
                     "'원리/이유/방법/차이/뜻' 같은 정보형 표지어를 넣으세요."))
    else:
        axes.append(("유형", 25, 5,
                     "%s 제목입니다. 이 블로그 전략(정보형→AI 인용)과 어긋납니다. "
                     "'방법/이유/차이'로 트세요." % my_type))

    # 4) 훅 단어 (15)
    has_hook = any(h.lower() in t.lower() for h in pr["top_hooks"])
    kw_has_hook = any(h.lower() in kw.lower() for h in pr["top_hooks"])
    if has_hook or kw_has_hook:
        axes.append(("훅 단어", 15, 15, "훅 단어가 들어 있습니다."))
    elif pr["top_hooks"]:
        axes.append(("훅 단어", 15, 5,
                     "상위권이 자주 쓰는 훅(%s)이 없습니다. 하나 넣어보세요."
                     % ", ".join(pr["top_hooks"][:3])))
    else:
        axes.append(("훅 단어", 15, 12, "이 키워드는 훅 단어가 크게 중요치 않습니다."))

    # 5) 숫자·물음표 (15) — 상위권 관습에 맞으면 가점
    sc5, notes = 0, []
    if pr["digit_ratio"] >= 40:
        if re.search(r"\d", t):
            sc5 += 8
            notes.append("숫자 있음(상위권 %d%%가 숫자 사용) 좋습니다" % pr["digit_ratio"])
        else:
            notes.append("상위권 %d%%가 제목에 숫자를 씀 — '5가지/3단계' 같은 숫자 고려"
                         % pr["digit_ratio"])
    else:
        sc5 += 8
    if pr["q_ratio"] >= 30:
        if "?" in t:
            sc5 += 7
            notes.append("물음표 있음(상위권 %d%%) 좋습니다" % pr["q_ratio"])
        else:
            notes.append("상위권 %d%%가 물음표를 씀 — 질문형 제목도 방법" % pr["q_ratio"])
    else:
        sc5 += 7
    axes.append(("숫자·물음표", 15, sc5, " / ".join(notes) if notes else "특이사항 없음"))

    return sum(sc for _, _, sc, _ in axes), axes


def suggest(kw, pr):
    """표준형에 맞춘 제목안. 정보형 프레이밍을 기본으로 자연스러운 문장만."""
    tips = [
        "%s, 쉽게 정리했습니다" % kw,
        "%s 원리부터 차근차근 알려드릴게요" % kw,
        "%s 총정리 — 핵심만 빠르게" % kw,
        "%s 제대로 이해하기, 원인과 해결까지" % kw,
    ]
    if pr["digit_ratio"] >= 40:
        tips.insert(2, "%s 핵심 3가지만 짚어드립니다" % kw)
    if pr["q_ratio"] >= 30:
        tips.insert(1, "%s, 왜 그럴까요?" % kw)
    return [(s, len(s)) for s in tips], pr["len_median"]


# ---------------------------------------------------------------- 출력

def bar(count, total, width=20):
    filled = int(round(count / max(total, 1) * width))
    return "█" * filled + "·" * (width - filled)


def grade(score):
    if score >= 80:
        return "상위권 관습에 잘 맞습니다"
    if score >= 60:
        return "무난합니다 — 몇 가지만 손보세요"
    if score >= 40:
        return "고칠 곳이 있습니다"
    return "많이 고쳐야 합니다"


def render(entry):
    kw = entry["keyword"]
    pr = entry["profile"]
    out = []
    p = out.append
    p("")
    p("=" * 66)
    p("  키워드: %s   (상위 %d개 문서 기준)" % (kw, pr["n"]))
    p("=" * 66)

    p("\n■ 이 키워드의 '이겨온 제목 표준형'")
    p("  길이        주력 %d~%d자 (중앙값 %d자, 평균 %.1f자)"
      % (pr["len_p25"], pr["len_p75"], pr["len_median"], pr["len_avg"]))
    if pr["pos_dominant"] == "미포함":
        p("  키워드 위치  상위권 상당수가 키워드를 그대로 안 쓰고 변형해 씀")
        p("              (그래도 내 글엔 앞부분에 넣는 게 안전합니다)")
    else:
        p("  키워드 위치  %s 배치가 다수" % pr["pos_dominant"])
    p("  유형        다수는 %s  (%s)" % (
        pr["type_dominant"],
        " / ".join("%s %d" % (k, v)
                   for k, v in sorted(pr["types"].items(), key=lambda x: -x[1]))))
    if pr["top_hooks"]:
        p("  자주 쓰는 훅 %s" % ", ".join(pr["top_hooks"][:5]))
    p("  숫자 %d%% · 물음표 %d%% · 연도 %d%% · 영문 %d%%"
      % (pr["digit_ratio"], pr["q_ratio"], pr["year_ratio"], pr["english_ratio"]))
    p("  최근30일 글 %d%%  ·  상위 장악 %d건" % (pr["fresh30_ratio"], pr["dominance"]))

    # ── 여기부터 통합 전 [1. 블로그 키워드 분석]이 보여주던 것 ──
    if pr["separators"]:
        p("\n■ 상위권이 쓰는 구분자")
        for label, cnt in sorted(pr["separators"].items(), key=lambda x: -x[1])[:6]:
            p("    %-10s %s %d/%d" % (label, bar(cnt, pr["n"]), cnt, pr["n"]))

    if pr["unigrams"]:
        p("\n■ 상위권 제목에 자주 같이 나오는 낱말 (키워드 자체는 뺌)")
        p("    " + ", ".join("%s(%d)" % (w, c) for w, c in pr["unigrams"][:12]))
    if pr["bigrams"]:
        p("\n■ 자주 붙어 나오는 두 낱말")
        p("    " + ", ".join("%s(%d)" % (g, c) for g, c in pr["bigrams"][:8]))

    if pr["freshness"]:
        p("\n■ 상위권 글이 언제 쓰였나")
        for label in ("30일 이내", "90일 이내", "1년 이내", "1년 초과"):
            cnt = pr["freshness"].get(label, 0)
            if cnt:
                p("    %-9s %s %d/%d" % (label, bar(cnt, pr["n"]), cnt, pr["n"]))
        if pr["latest_post"]:
            p("    가장 최근 글: %s" % pr["latest_post"])

    if pr["repeat_bloggers"]:
        p("\n■ 이 키워드를 장악한 블로그 (2건 이상)")
        for b, c in pr["repeat_bloggers"]:
            p("    · %s (%d건)" % (b, c))

    if entry.get("my_title"):
        score, axes = entry["score"], entry["axes"]
        p("\n■ 내 제목 진단")
        p("  \"%s\"  (%d자)" % (entry["my_title"], len(entry["my_title"])))
        p("  ─ 제목 점수 %d / 100 · %s" % (score, grade(score)))
        p("")
        for name, full, sc, note in axes:
            p("  %-11s %s %2d/%2d" % (name, bar(sc, full), sc, full))
            p("       %s" % note)
        p("\n■ 이렇게 고쳐보세요 (표준형에 맞춘 제목안)")
        tips, _ = entry["suggest"]
    else:
        p("\n■ (제목을 안 적어서 표준형만 보여드립니다)")
        p("  이 표준형에 맞춰 제목을 지으면 됩니다. 제안 제목:")
        tips, _ = suggest(kw, pr)

    for s, ln in tips:
        mark = "  ✓" if pr["len_p25"] <= ln <= pr["len_p75"] else "   "
        p("    %s %s  (%d자)" % (mark, s, ln))

    p("\n  ─ 상위권 제목 예시 (참고)")
    for t in pr["sample_titles"][:5]:
        p("     · %s" % t)
    p("")
    p("  * 검색 API sim 정렬 기준입니다. 통합검색 VIEW 탭 순위가 아닙니다.")
    p("")
    return "\n".join(out)


def parse_lines(lines):
    """'키워드 | 제목' 또는 '키워드' 만. #/빈 줄 무시."""
    pairs = []
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if "|" in s:
            kw, title = s.split("|", 1)
            if kw.strip():
                pairs.append((kw.strip(), title.strip()))
        else:
            pairs.append((s, ""))
    return pairs


def save_csv(entries, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["키워드", "내 제목", "제목점수", "평가", "길이", "주력구간",
                    "키워드위치", "내유형", "상위권다수유형", "숫자%", "물음표%",
                    "최근30일%", "상위장악", "자주쓰는훅"])
        for e in entries:
            pr = e["profile"]
            t = e.get("my_title", "")
            w.writerow([e["keyword"], t, e.get("score", ""),
                        grade(e["score"]) if "score" in e else "",
                        len(t) if t else "",
                        "%d~%d자" % (pr["len_p25"], pr["len_p75"]),
                        keyword_position(t, e["keyword"])[0] if t else "",
                        title_type(t) if t else "", pr["type_dominant"],
                        pr["digit_ratio"], pr["q_ratio"], pr["fresh30_ratio"],
                        pr["dominance"], ", ".join(pr["top_hooks"][:5])])


def save_titles_csv(entries, path):
    """상위권 제목 원본. 통합 전 [1. 블로그 키워드 분석]의 제목목록.csv 를 대신한다."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["키워드", "순번", "상위권 제목", "글자수", "유형", "키워드위치"])
        for e in entries:
            kw = e["keyword"]
            for i, t in enumerate(e["profile"]["titles"], 1):
                w.writerow([kw, i, t, len(t), title_type(t),
                            keyword_position(t, kw)[0]])


# ---------------------------------------------------------------- 실행

def main():
    ap = argparse.ArgumentParser(description="제목 진단 — 상위권 표준형 대비 채점")
    ap.add_argument("pairs", nargs="*", help="'키워드 | 제목' 형식. 여러 개 가능")
    ap.add_argument("--입력", "--in", dest="infile", help="입력 파일")
    ap.add_argument("--out", help="결과 저장 프리픽스")
    args = ap.parse_args()

    api_url, headers, mode = naver_api.search_credentials()

    if args.infile:
        with open(args.infile, encoding="utf-8") as f:
            targets = parse_lines(f.readlines())
    elif args.pairs:
        targets = parse_lines(args.pairs)
    else:
        raise SystemExit("진단할 '키워드 | 제목'을 --입력 파일이나 인자로 주세요.")

    if not targets:
        raise SystemExit(
            "진단할 내용이 없습니다.\n"
            "3_설정 폴더의 진단할제목.txt 에 '키워드 | 제목'을 한 줄에 하나씩 적어주세요.\n"
            "제목 없이 키워드만 적으면 그 키워드의 표준형만 보여드립니다.")

    sys.stderr.write("키워드 %d개 · 상위 %d개 문서를 봅니다. (%s)\n\n"
                     % (len(targets), TOP_COUNT, mode))

    entries = []
    for i, (kw, title) in enumerate(targets, 1):
        sys.stderr.write("\r상위 문서 수집 ... %d/%d (%s)                 "
                         % (i, len(targets), kw[:18]))
        sys.stderr.flush()
        items, _ = naver_api.search(kw, TOP_COUNT, api_url, headers,
                                    since=SINCE, verbose=False)
        pr = profile(kw, items)
        if pr is None:
            print("\n[%s] 상위 문서가 없어 진단을 건너뜁니다." % kw)
            continue
        entry = {"keyword": kw, "my_title": title, "profile": pr}
        if title:
            entry["score"], entry["axes"] = diagnose(title, kw, pr)
            entry["suggest"] = suggest(kw, pr)
        entries.append(entry)
    sys.stderr.write("\r수집 완료 (%d개)                                      \n" % len(entries))

    for e in entries:
        print(render(e))

    scored = [e for e in entries if "score" in e]
    if len(scored) > 1:
        print("=" * 66)
        print("  제목 점수 요약")
        print("=" * 66)
        for e in sorted(scored, key=lambda x: -x["score"]):
            print("  %3d점  %-24s %s" % (e["score"], e["keyword"][:24],
                                         e["my_title"][:36]))
        print("")

    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump({"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                       "since": SINCE, "top_count": TOP_COUNT,
                       "entries": entries}, f, ensure_ascii=False, indent=1)
        save_csv(entries, args.out + "_진단.csv")
        save_titles_csv(entries, args.out + "_제목목록.csv")
        print("저장: %s.json , %s_진단.csv , %s_제목목록.csv\n"
              % (args.out, args.out, args.out))


if __name__ == "__main__":
    main()
