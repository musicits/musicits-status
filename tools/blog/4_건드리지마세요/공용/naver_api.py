#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 API 두 종류 — 블로그 검색, 데이터랩 검색어트렌드.

통합 전에는 credentials()가 5곳(1·4·5·6·8번), 검색 호출이 5곳, 데이터랩 호출이
2곳(3·5번)에 복붙돼 있었다. 여기 하나로 모았다.

**앱이 두 개고 인증키가 서로 다르다. 섞으면 401이다.**
  · keyword-analyzer  → 블로그 검색     (SEARCH_KEY_ID / SEARCH_KEY)
  · trend-analyzer    → 검색어트렌드     (TREND_KEY_ID  / TREND_KEY)
설정/api_key.txt 에 두 쌍이 다 들어가는 이유다.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- 주소

SEARCH_HUB_URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"
SEARCH_LEGACY_URL = "https://openapi.naver.com/v1/search/blog.json"

# 데이터랩은 호스트가 두 벌이다. 콘솔이 개편 중이라 계정이 어느 쪽에 붙어
# 있느냐에 따라 다르다. 경로가 /search-trend/v1/... 다. /datalab/... 이 아니다
# (콘솔 표기와 URL이 안 맞는다 — 여기서 한참 헤맸다).
TREND_URLS = [
    "https://naverapihub.apigw.ntruss.com/search-trend/v1/search",  # NAVER API HUB (새 콘솔)
    "https://naveropenapi.apigw.ntruss.com/datalab/v1/search",      # AI·NAVER API (구 콘솔)
]
_resolved_trend_url = None   # 한 번 성공한 주소를 기억해 두고 이후엔 그것만 쓴다

MAX_DISPLAY = 100     # 검색 API가 한 번에 주는 최대 건수
MAX_START = 1000      # 검색 API start 파라미터 상한
MAX_GROUPS = 5        # 데이터랩 한 요청에 담을 수 있는 키워드 그룹 수
MIN_DATE = "2016-01-01"   # 데이터랩이 제공하는 가장 이른 날짜

BLOCKED = (404, 401, 403)  # '이 주소는 네 계정에 안 열려 있다'는 뜻으로 오는 응답들


# ---------------------------------------------------------------- 인증

def search_credentials():
    """블로그 검색용 (URL, 헤더, 모드이름). HUB 키가 있으면 그쪽을 우선.

    구 developers.naver.com 키(NAVER_CLIENT_ID/SECRET)도 fallback으로 받는다.
    """
    hub_id = os.environ.get("SEARCH_KEY_ID") or os.environ.get("NCP_APIGW_API_KEY_ID")
    hub_key = os.environ.get("SEARCH_KEY") or os.environ.get("NCP_APIGW_API_KEY")
    if hub_id and hub_key:
        return SEARCH_HUB_URL, {
            "X-NCP-APIGW-API-KEY-ID": hub_id,
            "X-NCP-APIGW-API-KEY": hub_key,
        }, "NAVER API HUB"

    old_id = os.environ.get("NAVER_CLIENT_ID")
    old_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if old_id and old_secret:
        return SEARCH_LEGACY_URL, {
            "X-Naver-Client-Id": old_id,
            "X-Naver-Client-Secret": old_secret,
        }, "구 Developers(openapi.naver.com)"

    raise SystemExit(
        "\n블로그 검색 API 키가 없습니다.\n"
        "3_설정 폴더의 api_key.txt 를 열어 등호(=) 뒤에 값을 넣어주세요.\n"
        "  SEARCH_KEY_ID=...     (keyword-analyzer 앱의 Client ID)\n"
        "  SEARCH_KEY=...        (같은 앱의 Client Secret)\n")


def trend_credentials():
    """검색어트렌드용 헤더. keyword-analyzer 키를 넣으면 401이 난다."""
    kid = os.environ.get("TREND_KEY_ID")
    key = os.environ.get("TREND_KEY")
    if not kid or not key:
        # 예전 도구들은 트렌드에도 NCP_APIGW_* 를 썼다. 한 벌만 있는 경우를 위해 남겨둔다.
        kid = kid or os.environ.get("NCP_APIGW_API_KEY_ID")
        key = key or os.environ.get("NCP_APIGW_API_KEY")
    if not kid or not key:
        raise SystemExit(
            "\n검색어트렌드 API 키가 없습니다.\n"
            "3_설정 폴더의 api_key.txt 를 열어 등호(=) 뒤에 값을 넣어주세요.\n"
            "  TREND_KEY_ID=...      (trend-analyzer 앱의 Client ID)\n"
            "  TREND_KEY=...         (같은 앱의 Client Secret)\n"
            "* 검색용 키(SEARCH_KEY)와 다른 값입니다. 섞으면 401이 납니다.\n")
    return {
        "X-NCP-APIGW-API-KEY-ID": kid,
        "X-NCP-APIGW-API-KEY": key,
        "Content-Type": "application/json",
    }


NOT_SUBSCRIBED = """
────────────────────────────────────────────────────────────
 검색어트렌드가 아직 신청되어 있지 않습니다.
 (키는 맞습니다. API만 추가하면 됩니다. 무료입니다.)

 추가하는 방법 — 5분 걸립니다:

   1) https://console.ncloud.com  접속해서 로그인
   2) 위쪽 검색창에  NAVER API HUB  라고 치고 들어갑니다
   3) 왼쪽 메뉴에서  Application  클릭
   4) [+ Application 등록] 버튼 클릭
   5) 카드가 쭉 나오는데, 그중
        검색어트렌드   (Data Lab Search Trend API)
      카드 오른쪽 위 네모칸에 체크
   6) [다음] → Application 이름을 적고 → [완료]

   저장한 뒤 1~2분 기다렸다가 다시 실행하시면 됩니다.

   * 새 Application을 만들면 인증키가 새로 나옵니다.
     [인증 정보] 버튼을 눌러 나오는 값을
     3_설정 폴더의 api_key.txt 의 TREND_KEY_ID / TREND_KEY 에 넣어주세요.
────────────────────────────────────────────────────────────
"""


# ---------------------------------------------------------------- 블로그 검색

def search(keyword, count, api_url, headers, sort="sim", since=None, verbose=True):
    """검색 API를 페이지네이션하며 count개까지 모은다. (글목록, 전체문서수)를 준다.

    since('YYYYMMDD' 또는 'YYYY-MM-DD')를 주면 그 날짜 이후 글만 남긴다. 검색
    API에는 기간 필터가 없으므로 넉넉히 긁어와서 여기서 걸러낸다. postdate가
    YYYYMMDD 문자열이라 사전순 비교가 곧 날짜 비교다.

    각 글에 _rawrank(네이버가 매긴 원래 순위)를 박아둔다. 기간 필터로 걸러낸
    뒤의 순번을 쓰면 실제보다 앞선 순위로 보여 오해를 부른다.
    """
    if since:
        since = since.replace("-", "")
    items, skipped, total, start = [], 0, 0, 1

    while len(items) < count and start <= MAX_START:
        # 걸러낼 예정이면 매번 최대치로 긁어온다
        display = MAX_DISPLAY if since else min(MAX_DISPLAY, count - len(items))
        params = urllib.parse.urlencode({
            "query": keyword, "display": display, "start": start,
            "sort": sort, "format": "json",
        })
        req = urllib.request.Request(api_url + "?" + params, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                body = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise SystemExit("[API 오류 %s] %s\n%s" % (e.code, e.reason, detail))
        except urllib.error.URLError as e:
            raise SystemExit("[네트워크 오류] %s" % e.reason)

        if not total:
            total = body.get("total", 0)
        got = body.get("items", [])
        if not got:
            break
        for idx, it in enumerate(got):
            if since and (it.get("postdate") or "") < since:
                skipped += 1
                continue
            it["_rawrank"] = start + idx
            items.append(it)
        if verbose:
            sys.stderr.write("\r  %s ... %d건 (기간 밖 %d건 제외)"
                             % (keyword, len(items), skipped))
            sys.stderr.flush()
        start += display
        time.sleep(0.1)   # 매너 딜레이

    if verbose:
        sys.stderr.write("\r  %s ... %d건 확보 (기간 밖 %d건 제외, 전체 %s건)     \n"
                         % (keyword, len(items), skipped, format(total, ",")))
    return items[:count], total


def search_once(keyword, api_url, headers, depth=100, sort="sim"):
    """한 번만 호출한다(페이지네이션 없음). 순위 추적용.

    각 글에 _rank(1부터)를 박는다. depth를 100 넘게 올려도 검색 API display
    상한이 100이라 의미가 없다 — 100위 밖 순위는 실질적으로 뜻이 없기도 하다.
    """
    params = urllib.parse.urlencode({
        "query": keyword, "display": min(depth, MAX_DISPLAY), "start": 1,
        "sort": sort, "format": "json",
    })
    req = urllib.request.Request(api_url + "?" + params, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            body = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit("[API 오류 %s] %s\n%s" % (e.code, e.reason, detail))
    except urllib.error.URLError as e:
        raise SystemExit("[네트워크 오류] %s" % e.reason)

    items = body.get("items", [])
    for idx, it in enumerate(items):
        it["_rank"] = idx + 1
    return items, body.get("total", 0)


# ---------------------------------------------------------------- 데이터랩

def trend_call(headers, start, end, time_unit, groups, retries=2):
    """데이터랩에 한 번 요청. groups는 [(표시이름, [검색어들]), ...].

    주소가 두 벌이라 처음 한 번은 순서대로 찔러본다. 막힌 주소는 계정에 따라
    404로도 오고 401로도 와서, 둘 다 '다음 주소 시도'로 넘긴다.

    진단에 쓸 것 — 응답으로 원인이 갈린다:
      404 errorCode 300 URL not found     → 경로가 틀렸다
      401 errorCode 210 subscription      → 경로는 맞고 신청이 안 됐다
      401 "이 Application에서 활성화 안 됨" → 다른 앱의 키를 쓰고 있다
    """
    global _resolved_trend_url
    payload = json.dumps({
        "startDate": start,
        "endDate": end,
        "timeUnit": time_unit,
        "keywordGroups": [{"groupName": n, "keywords": k} for n, k in groups],
    }).encode("utf-8")

    candidates = [_resolved_trend_url] if _resolved_trend_url else list(TREND_URLS)
    last = None

    for url in candidates:
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=payload, headers=headers,
                                         method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as res:
                    _resolved_trend_url = url
                    return json.loads(res.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")
                if e.code == 429:
                    raise SystemExit("\n[한도 초과] 오늘 사용량 50,000회를 다 썼습니다. "
                                     "내일 다시 실행해주세요.\n")
                # 데이터랩은 서버 쪽 일시 오류를 HTTP 400 + 본문 errorCode 500
                # ("검색 트렌드 API 호출 오류")으로 돌려준다. 같은 요청이 조금 뒤엔
                # 그냥 되므로 5xx와 같이 재시도한다. 2026-08-12 실측:
                # 키워드 203개를 돌릴 때 일별 51묶음은 다 되고 주별 38묶음째에서 났다.
                transient = e.code >= 500 or (
                    e.code == 400 and ('"errorCode":500' in detail
                                       or "호출 오류" in detail))
                if transient and attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if e.code in BLOCKED:
                    last = (url, e.code, detail)
                    break            # 다음 주소로
                raise SystemExit("\n[API 오류 %s] %s\n%s\n"
                                 % (e.code, e.reason, detail[:400]))
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise SystemExit("\n[네트워크 오류] %s\n" % e.reason)

    # 두 주소 모두 막혔다 = 아직 신청이 안 된 것이다.
    if _resolved_trend_url:
        # 되던 주소가 갑자기 막힌 경우라 안내문보다 원문이 도움이 된다.
        raise SystemExit("\n[API 오류] %s\n%s\n" % (last[1], last[2][:400]))
    raise SystemExit(NOT_SUBSCRIBED)


def trend_collect(headers, targets, start, end, time_unit, label, anchor):
    """키워드를 4개씩 끊어 요청하고, 기준 키워드로 눈금을 맞춰 하나로 합친다.

    데이터랩의 ratio는 '그 요청 안에서' 가장 큰 값을 100으로 놓은 상대값이다.
    요청을 나눠 보내면 요청마다 기준이 달라져 숫자를 그대로 비교할 수 없다.
    그래서 모든 요청에 anchor를 한 자리 끼워 넣고, anchor 평균이 100이 되도록
    배율을 걸어 요청끼리 눈금을 맞춘다.

    targets는 [(표시이름, [검색어들], 분류), ...].
    돌려주는 값: (기간라벨 리스트, {표시이름: [값, ...]}, 조회 실패한 이름 집합)

    한 묶음이 재시도 뒤에도 실패하면 그 묶음만 건너뛰고 계속 간다. 키워드가
    200개 넘어가면 5분짜리 작업인데 묶음 하나 때문에 통째로 날릴 이유가 없다.
    실패한 키워드는 '조회 실패'로 표시하지, 지어낸 0으로 채우지 않는다.
    """
    per_call = MAX_GROUPS - 1          # 한 자리는 기준 키워드가 쓴다
    batches = [targets[i:i + per_call] for i in range(0, len(targets), per_call)]
    periods, series, failed = [], {}, set()

    for i, batch in enumerate(batches, 1):
        groups = [(anchor, [anchor])] + [(n, k) for n, k, _ in batch]
        try:
            body = trend_call(headers, start, end, time_unit, groups)
        except SystemExit as e:
            # 신청 안 됨·한도 초과처럼 다음 묶음도 똑같이 실패할 오류는 그대로 멈춘다.
            msg = str(e)
            if "신청" in msg or "한도 초과" in msg:
                raise
            for n, _, _ in batch:
                failed.add(n)
            sys.stderr.write("\r  %s ... %d/%d 묶음 건너뜀 (일시 오류)        \n"
                             % (label, i, len(batches)))
            continue

        raw = {}
        for r in body.get("results", []):
            raw[r.get("title")] = [(d.get("period"), float(d.get("ratio", 0)))
                                   for d in r.get("data", [])]

        # 값이 0인 구간은 응답에서 아예 빠져서 온다. 전체 기간 라벨을 먼저 모아둔다.
        for name, pairs in raw.items():
            for p, _ in pairs:
                if p not in periods:
                    periods.append(p)

        anchor_pairs = raw.get(anchor, [])
        anchor_mean = (sum(v for _, v in anchor_pairs) / len(anchor_pairs)
                       if anchor_pairs else 0)
        scale = (100.0 / anchor_mean) if anchor_mean > 0 else 1.0

        for name, _, _ in batch:
            pairs = raw.get(name, [])
            series[name] = {p: v * scale for p, v in pairs}

        sys.stderr.write("\r  %s ... %d/%d 묶음" % (label, i, len(batches)))
        sys.stderr.flush()
        time.sleep(0.2)   # 매너 딜레이

    periods.sort()
    filled = {name: [vals.get(p, 0.0) for p in periods]
              for name, vals in series.items()}
    note = ("  (%d개 조회 실패)" % len(failed)) if failed else ""
    sys.stderr.write("\r  %s ... 완료 (%d개 구간)%s          \n"
                     % (label, len(periods), note))
    return periods, filled, failed


def rescale(units):
    """앵커 기준(에어팟=100)을 '이번에 가장 많이 검색된 키워드=100'으로 바꾼다.

    앵커는 요청끼리 눈금을 맞추는 용도라 이미 제 역할을 끝냈다. 그대로 두면
    앵커보다 훨씬 작은 키워드(LP 입문 등)가 0.0으로 뭉개져 읽을 수가 없다.
    비율만 바꾸는 것이라 상승률·최고치대비 같은 지표는 영향을 받지 않는다.

    units는 [{키워드: [값,...]}, ...]. 세 단위(일/주/월)에 같은 배율을 걸어야
    'level ÷ year_max' 처럼 단위를 넘나드는 계산이 깨지지 않는다.
    """
    peak = 0.0
    for u in units[:2]:   # 일별·주별에서만 최고점을 찾는다 (월별은 평균이라 낮게 나옴)
        for vals in u.values():
            if vals:
                peak = max(peak, max(vals))
    if peak <= 0:
        return
    factor = 100.0 / peak
    for u in units:
        for name, vals in u.items():
            u[name] = [v * factor for v in vals]
