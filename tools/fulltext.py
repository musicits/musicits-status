#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기사 주소를 열어 본문 글자만 뽑아낸다. (휴대폰 수집 전용)

깃허브 Actions 안에서 translate.py 가 불러 쓴다. PC 보고서 쪽과는 상관이 없다 —
저쪽은 Claude 가 원문을 직접 읽는다.

**막힌 곳은 막힌 대로 둔다.** 403 이 오거나 본문을 못 찾으면 그 기사는 '피드 요약만'
으로 표시하고 넘어간다. 우회를 시도하지 않는다. 읽은 척하는 것보다 못 읽었다고
적어두는 편이 낫다.

바깥 라이브러리를 쓰지 않는다. 워크플로가 pip 로 까는 것은 google-genai 하나뿐이고,
본문 추출 하나 때문에 그 목록을 늘릴 이유가 없다.
"""
import html as H
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# collect.py 와 같은 것을 쓴다. RSS 를 주는 곳과 기사를 주는 곳이 같기 때문이다.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

MAX_BYTES = 3_000_000   # 이보다 큰 문서는 기사가 아니다
MAX_CHARS = 6000        # 모델에게 넘길 본문 길이. 기사 하나로 충분하다
MIN_CHARS = 400         # 이보다 짧으면 본문을 못 찾은 것으로 본다
MIN_PARA = 25           # 이보다 짧은 문단은 메뉴·버튼 글자로 본다

# 본문이 아닌 것들. 통째로 들어낸다.
JUNK = re.compile(
    r"<(script|style|noscript|svg|iframe|form|aside|nav|header|footer|figcaption)"
    r"\b[^>]*>.*?</\1>", re.S | re.I)
ARTICLE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.S | re.I)
PARA = re.compile(r"<(p|li|h2|h3)\b[^>]*>(.*?)</\1>", re.S | re.I)
BR = re.compile(r"<br\s*/?>", re.I)
TAG = re.compile(r"<[^>]+>")
META_CHARSET = re.compile(rb'charset=["\']?([\w-]+)', re.I)

# 네이버 블로그는 주소 그대로 열면 액자(frameset)만 온다. 안쪽 주소로 바꿔 연다.
NAVER = re.compile(r"^https?://(?:m\.)?blog\.naver\.com/([^/?#]+)/(\d+)")


def real_url(url):
    m = NAVER.match(url or "")
    if m:
        return ("https://blog.naver.com/PostView.naver"
                "?blogId=%s&logNo=%s&redirect=Dlog" % m.groups())
    return url


def decode(raw, headers):
    charset = headers.get_content_charset()
    if not charset:
        m = META_CHARSET.search(raw[:4000])
        charset = m.group(1).decode("ascii", "replace") if m else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def to_text(doc):
    """문서에서 문단만 순서대로 모은다. 못 찾으면 빈 문자열."""
    doc = JUNK.sub(" ", doc)
    inside = ARTICLE.search(doc)
    if inside and len(inside.group(1)) > 600:
        doc = inside.group(1)

    out, seen = [], set()
    for _, chunk in PARA.findall(doc):
        line = H.unescape(TAG.sub(" ", BR.sub(" ", chunk)))
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < MIN_PARA or line in seen:
            continue
        seen.add(line)
        out.append(line)
        if sum(len(x) for x in out) > MAX_CHARS:
            break
    return "\n".join(out)[:MAX_CHARS]


def read(url, timeout=20):
    """(본문, 사유) 를 돌려준다. 성공하면 사유는 None.

    실패해도 예외를 올리지 않는다. 기사 하나 못 읽었다고 수집 전체가 멈추면 안 된다.
    """
    if not url:
        return "", "주소 없음"
    try:
        req = Request(real_url(url),
                      headers={"User-Agent": UA,
                               "Accept": "text/html,application/xhtml+xml"})
        with urlopen(req, timeout=timeout) as resp:
            kind = (resp.headers.get_content_type() or "").lower()
            if "html" not in kind:
                return "", "문서가 아님(%s)" % kind
            text = to_text(decode(resp.read(MAX_BYTES), resp.headers))
    except HTTPError as exc:
        return "", "HTTP %s" % exc.code
    except URLError as exc:
        return "", "접속 실패(%s)" % (getattr(exc, "reason", "") or "URLError")
    except Exception as exc:                                    # noqa: BLE001
        return "", type(exc).__name__

    if len(text) < MIN_CHARS:
        return "", "본문을 찾지 못함"
    return text, None
