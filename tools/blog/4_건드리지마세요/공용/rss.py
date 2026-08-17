#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RSS 읽기 — 네이버 블로그 RSS와 일반 뉴스 RSS(2.0/Atom).

통합 전에는 파서가 네 벌이었다: [4.블로그추적기] fetch_posts(ElementTree),
[7.경쟁벤치마킹] fetch_rss(정규식), [8.이웃소통] rss_activity(정규식),
[9.IT뉴스] 뉴스수집(자체 2.0+Atom). 하나로 합쳤다.

못 가져오는 값 (묻기 전에 답):
  조회수 · 방문자수 · 유입 검색어 · 댓글수 · 이웃수 · AI 브리핑 인용수는
  **어떤 방법으로도 안 된다.** blog.naver.com/robots.txt 가 방문자 카운터
  (NVisitor4Ajax.naver), comment.naver, /post/ 를 전부 Disallow 했고
  Yeti·ClaudeBot 포함 전면 차단이다. 2026-08-07 확인. 크롤러를 붙이지 말 것.
  본문 전체·유저 태그·이미지 수도 RSS에 안 온다(요약만 옴).
"""

import html
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

BLOG_RSS = "https://rss.blog.naver.com/%s.xml"
RSS_MAX = 50          # 네이버 블로그 RSS가 주는 최대 글 수. 늘릴 방법이 없다.
UA = "musicits-tools/2.0"

DATE_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
)


def strip_tags(t):
    """CDATA와 태그, HTML 엔티티를 벗긴다."""
    t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t or "", flags=re.S)
    t = re.sub(r"<.*?>", "", t)
    return html.unescape(t).strip()


def clean(text):
    """검색 API 응답의 <b> 강조 태그와 HTML 엔티티 제거."""
    text = re.sub(r"</?b>", "", text or "")
    return html.unescape(text).strip()


def parse_date(text, as_string=False):
    """RSS 날짜 문자열 → datetime (또는 as_string이면 'YYYY-MM-DD'). 실패하면 None/''."""
    raw = strip_tags(text)
    if not raw:
        return "" if as_string else None
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(raw, fmt)
            return d.strftime("%Y-%m-%d") if as_string else d
        except ValueError:
            continue
    return "" if as_string else None


def fetch(url, timeout=15):
    """URL을 읽어 본문 문자열을 준다. 실패하면 (None, 사유)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return None, "RSS 없음 (HTTP %s)" % e.code
    except urllib.error.URLError as e:
        return None, "네트워크 오류 (%s)" % e.reason
    except Exception as e:
        return None, "읽기 실패 (%s)" % e


def post_key(url):
    """프로토콜(http/https)과 물음표 뒤 꼬리표를 떼서 글 하나를 가리키는 열쇠로.

    RSS의 guid와 검색 API의 link가 같은 글인데 형식이 다르다(?fromRss=true 등).
    이걸 안 맞추면 '실제로 순위에 잡힌 검색어'가 항상 빈다.
    """
    url = (url or "").split("?")[0].split("#")[0]
    url = re.sub(r"^https?://", "", url).rstrip("/")
    return url


def blog_id_from_link(link):
    """bloggerlink(blog.naver.com/xxxx)에서 아이디를 뽑는다."""
    if not link:
        return None
    m = re.search(r"blog\.naver\.com/([A-Za-z0-9_\-]+)", link)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 네이버 블로그

def blog_posts(blog_id, soft=True, limit=RSS_MAX):
    """네이버 블로그 RSS에서 최근 글을 읽는다. 최대 50개.

    soft=True면 실패해도 멈추지 않고 빈 목록을 준다 — 비교 대상 블로그가 하나
    사라졌다고 내 블로그 추적까지 중단시킬 이유는 없다.

    각 글: guid(열쇠) / url / title / category / tags / summary / pubdate('YYYY-MM-DD')
           / date(datetime, 정렬용)
    """
    raw, err = fetch(BLOG_RSS % blog_id)

    def give_up(msg):
        if soft:
            sys.stderr.write("\r    %s — 건너뜁니다 (%s)%s\n" % (blog_id, msg, " " * 20))
            return []
        raise SystemExit("[RSS 오류] %s — %s" % (blog_id, msg))

    if raw is None:
        return give_up(err)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return give_up("글 목록 형식을 읽을 수 없습니다 (%s)" % e)

    channel = root.find("channel")
    if channel is None:
        return give_up("글 목록이 비어 있습니다")

    posts = []
    for item in channel.findall("item")[:limit]:
        def get(tag):
            node = item.find(tag)
            return clean(node.text) if node is not None and node.text else ""

        raw_link = get("guid") or get("link")
        title = get("title")
        if not raw_link or not title:
            continue
        node = item.find("pubDate")
        pub_raw = node.text if node is not None else ""
        posts.append({
            "guid": post_key(raw_link),
            "url": raw_link.split("?")[0],
            "title": title,
            "category": get("category"),
            "tags": [t.strip() for t in get("tag").split(",") if t.strip()],
            "summary": get("description")[:200],
            "pubdate": parse_date(pub_raw, as_string=True),
            "date": parse_date(pub_raw),
        })
    if not posts and soft:
        return give_up("글이 없음 (비공개이거나 RSS 미제공)")
    return posts


def publish_rhythm(posts, window_days=28):
    """(주당발행, 최근발행 며칠전). 글이 없으면 (None, None).

    '최근 window_days일에 몇 개'를 4로 나눈다. RSS가 50개까지만 줘서, 아주
    활발한 블로그는 50개가 하루이틀에 몰려 '50÷기간'이 주 300개처럼 폭발한다
    (실제로 겪음). 28일 창으로 고정하면 최근 리듬이 안정적으로 나오고,
    뜸한 블로그는 자연히 낮게 잡힌다.
    """
    dates = sorted([p["date"] for p in posts if p.get("date")])
    if not dates:
        return None, None
    now = datetime.now(dates[-1].tzinfo)
    last_days = (now - dates[-1]).days
    recent = sum(1 for d in dates if (now - d).days <= window_days)
    per_week = round(recent / (window_days / 7.0), 1)
    # 최근 창에 글이 하나도 없으면(뜸한 블로그) 전체 범위로 대략치를 낸다
    if recent == 0 and len(dates) >= 2:
        span = (dates[-1] - dates[0]).days or 1
        per_week = round(len(dates) / span * 7, 1)
    return per_week, last_days


# ---------------------------------------------------------------- 일반 RSS (뉴스)

def news_items(url, cap=8, timeout=12):
    """RSS 2.0 / Atom 양쪽을 읽어 [{title, link, date, summary}]. 실패하면 (None, 사유).

    feedparser 없이 표준 라이브러리만 쓴다(윈도우 새 PC에 패키지를 안 깔려고).
    날짜가 없는 항목(일부 Apple Newsroom)은 date=None으로 둔다 — 버리지 않는다.
    """
    raw, err = fetch(url, timeout=timeout)
    if raw is None:
        return None, err
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return None, "형식 오류 (%s)" % e

    ns = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(".//%sentry" % ns)
    out = []
    for node in nodes[:cap]:
        def text(*tags):
            for t in tags:
                el = node.find(t)
                if el is not None and el.text:
                    return strip_tags(el.text)
            return ""

        title = text("title", "%stitle" % ns)
        if not title:
            continue
        link = text("link", "guid")
        if not link:                       # Atom은 link가 href 속성이다
            el = node.find("%slink" % ns)
            if el is not None:
                link = el.get("href", "")
        out.append({
            "title": title,
            "link": link,
            "date": parse_date(text("pubDate", "%supdated" % ns,
                                    "%spublished" % ns, "dc:date")),
            "summary": text("description", "%ssummary" % ns)[:300],
        })
    if not out:
        return None, "항목이 없음"
    return out, None
