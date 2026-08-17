#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제목 유형 판정 · 토큰화 — 모든 도구가 이 파일 하나만 본다.

통합 전에는 이 표지어 목록이 [3.검색어트렌드] [5.발행최적화] [6.상위노출진단]
[7.경쟁벤치마킹] 네 곳에 따로 있었고 내용이 서로 달랐다. 그래서 같은 제목이
도구마다 다른 유형으로 판정됐다. 예: "LP 입문"이 5번에선 상업형(0점),
6·7번에선 정보형. 이 파일이 그 유일한 기준이다.

**표지어를 고칠 일이 있으면 반드시 여기서만 고칠 것.** 도구 쪽에 복사해두면
통합 전 상태로 되돌아간다.
"""

# ---------------------------------------------------------------- 표지어
#
# 네 도구의 목록을 합집합으로 합쳤다. 아래 두 개만 예외이고, 이유가 있다.

# 정보형 — 이 블로그의 노림수. 원인·이유·방법을 묻는 형태라 AI 브리핑이 가장 잘 인용한다.
INFO_MARK = [
    "원리", "이유", "차이", "뜻", "이란", "원인", "방법", "부작용", "줄이기",
    "종류", "닳음", "아픈", "아픔", "느린", "느려지", "부족", "저하", "청소",
    "초기화", "건강", "수명", "설정", "보는 법", "하는 법", "쓰는 법", "관리",
    "교체", "맞추기", "보관", "세척", "안될", "안날", "안 나올 때", "오래 끼면",
    "해결", "예방", "고르는", "고치는",
]

# 상업형 — '추천·후기'는 AI 브리핑 노출 자체가 제한된다.
SHOP_MARK = [
    "추천", "후기", "리뷰", "가성비", "비교", "최저가", "내돈내산", "언박싱",
    "구매",
    # [예외 1] "입문"은 5.발행최적화에만 있던 단어다. 합집합 방침대로 넣었지만
    # 6·7번에선 정보형으로 잡히던 말이라("바이닐 입문 방법" 등) 판정이 바뀐다.
    # 정보형으로 되돌리고 싶으면 이 줄을 지우고 INFO_MARK로 옮기면 된다.
    "입문",
]

# 뉴스형 — 속보성은 뉴스 기사가 인용되고 블로그는 밀린다.
NEWS_MARK = [
    "루머", "유출", "출시", "출시일", "언팩", "신제품", "이벤트", "발표",
    "업데이트", "폴더블", "공개", "스펙", "예약",
    # [예외 2] 3·5번은 "가격", 6·7번은 "가격 인상"이었다. 합집합이면 "가격"이
    # 이겨야 하지만, 그러면 "이어폰 가격 비교" 같은 평범한 상업형 제목이
    # 전부 뉴스형으로 넘어간다(뉴스형 우선순위가 가장 높아서). 좁은 쪽을 택했다.
    "가격 인상",
]

HOOK_WORDS = [
    "추천", "후기", "총정리", "정리", "방법", "비교", "순위", "TOP", "베스트",
    "best", "꿀팁", "팁", "가격", "무료", "다운로드", "사용법", "차이", "장단점",
    "리뷰", "내돈내산", "솔직", "리얼", "실사용", "체험", "가이드", "모음",
    "인기", "최신", "초보", "완벽", "한방에", "총평", "정보", "핵심", "필수",
    "이유", "고민", "원리", "뜻", "해결",
]

JOSA = [
    "으로써", "으로서", "이라고", "라고", "에서는", "에서도", "까지", "부터", "에게",
    "에서", "으로", "로써", "로서", "이나", "라도", "마저", "조차", "처럼", "보다",
    "만큼", "하고", "이랑", "에는", "에도", "은", "는", "이", "가", "을", "를",
    "의", "에", "와", "과", "도", "로", "만", "랑",
]

STOPWORDS = set([
    "그리고", "하지만", "그래서", "위한", "위해", "있는", "없는", "하는", "되는",
    "것", "수", "등", "및", "더", "좀", "정말", "진짜", "너무", "가장", "제일",
])

# 데이터랩/프리셋의 분류(category)로도 유형을 못 박을 수 있다.
# 표지어보다 이쪽이 우선이다 — 사람이 직접 붙인 꼬리표라서.
INFO_CATEGORIES = set([
    "코덱", "음질", "원리", "문제해결", "배터리", "연결", "저장공간", "건강",
    "화면", "성능", "바이닐", "LP관리", "LP문제해결", "카메라", "AI인용",
])
NEWS_CATEGORIES = set(["뉴스", "루머", "공식뉴스"])
SHOP_CATEGORIES = set(["추천", "리뷰", "구매검토"])


import re  # noqa: E402


# ---------------------------------------------------------------- 판정

def title_type(title):
    """제목 하나의 유형. 우선순위 뉴스형 > 상업형 > 정보형 > 기타.

    속보성이 가장 강한 신호라 뉴스형이 먼저다. 네 도구가 쓰던 순서와 같다.
    """
    if any(m in title for m in NEWS_MARK):
        return "뉴스형"
    if any(m in title for m in SHOP_MARK):
        return "상업형"
    if any(m in title for m in INFO_MARK):
        return "정보형"
    return "기타"


def ai_fit(name, category=None):
    """이 검색어가 AI 브리핑 인용을 노릴 만한가. (등급, 점수, 이유)를 준다.

    점수는 [1.키워드발굴]의 기회점수 중 'AI적합' 30점 배점에 그대로 쓰인다.
    category(사람이 붙인 분류)가 있으면 표지어보다 먼저 본다.
    """
    if category in INFO_CATEGORIES or any(m in name for m in INFO_MARK):
        return "높음", 30.0, "원인·이유·방법을 묻는 정보형 — AI 브리핑이 가장 잘 인용"
    if category in NEWS_CATEGORIES or any(m in name for m in NEWS_MARK):
        return "낮음(뉴스형)", 0.0, "속보성은 뉴스 기사가 인용되고 블로그는 밀림"
    if category in SHOP_CATEGORIES or any(m in name for m in SHOP_MARK):
        return "낮음(상업형)", 0.0, "'추천·후기'는 AI 브리핑 노출 자체가 제한됨"
    return "중간", 15.0, "정보형으로 각도를 틀면 인용을 노려볼 만함"


# ---------------------------------------------------------------- 문자열

def tokenize(title):
    """한글/영문/숫자 토큰으로 쪼개고 조사를 벗긴다."""
    raw = re.findall(r"[가-힣]+|[A-Za-z]+|\d+", title)
    out = []
    for tok in raw:
        if re.match(r"^[가-힣]+$", tok) and len(tok) > 2:
            for j in sorted(JOSA, key=len, reverse=True):
                if tok.endswith(j) and len(tok) - len(j) >= 2:
                    tok = tok[: -len(j)]
                    break
        low = tok.lower()
        if len(tok) < 2 and not tok.isdigit():
            continue
        if low in STOPWORDS or tok in STOPWORDS:
            continue
        out.append(low)
    return out


def words(text):
    """검색어를 낱말로만 쪼갠다(조사 처리 없음). '이어폰 청소 방법' → 3개."""
    return [t for t in re.split(r"[^0-9A-Za-z가-힣]+", (text or "").lower()) if t]


def normalize(text):
    """비교용: 공백/특수문자 제거 + 소문자."""
    return re.sub(r"[^0-9a-z가-힣]", "", (text or "").lower())


def keyword_position(title, keyword):
    """제목 내 키워드 위치를 앞부분/중간/뒷부분/미포함으로 분류. (위치, 비율)"""
    nt, nk = normalize(title), normalize(keyword)
    if not nk or nk not in nt:
        # 키워드가 통으로 안 들어간 경우, 구성 어절이 전부 들어있는지로 완화 판정
        parts = [normalize(p) for p in keyword.split() if normalize(p)]
        if parts and all(p in nt for p in parts):
            idx = min(nt.index(p) for p in parts)
        else:
            return "미포함", None
    else:
        idx = nt.index(nk)
    ratio = idx / max(len(nt), 1)
    if ratio <= 0.25:
        return "앞부분", ratio
    if ratio <= 0.6:
        return "중간", ratio
    return "뒷부분", ratio


def josa(word, pair):
    """josa("에어팟", "이/가") → "가". 받침 유무로 조사를 고른다.

    이게 없으면 "미포함가" 같은 말이 리포트에 찍힌다.
    """
    a, _, b = pair.partition("/")
    if not word:
        return b or a
    last = word[-1]
    if "가" <= last <= "힣":
        return a if (ord(last) - 0xAC00) % 28 else b
    if last.isdigit():
        return a if last in "0136780" else b
    return b


def hook_counts(titles):
    """제목 목록에서 훅 단어 등장 횟수. Counter를 돌려준다."""
    from collections import Counter
    hooks = Counter()
    for t in titles:
        low = t.lower()
        for w in HOOK_WORDS:
            if w.lower() in low:
                hooks[w] += 1
    return hooks
