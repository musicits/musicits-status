#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뮤직잇츠 IT 뉴스 수집기

지정된 소스(애플/삼성 공식, 루머 사이트, 오디오, 카메라)의 RSS를 읽어
"지난 확인 시점 이후" 새로 올라온 기사만 골라 저장한다.

- 지난 확인 시점은 3_건드리지마세요/확인기록.json 에 자동 기록된다.
  (기록이 없으면 최근 24시간을 기준으로 한다)
- 이미 본 기사 URL도 기록해서 중복으로 다시 뽑지 않는다.
- 요약·제목 후보 작성은 이 프로그램이 하지 않는다.
  (보고서_작성_프롬프트.md 를 따라 Claude가 작성)
"""
import argparse
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

# 윈도우 명령 프롬프트(cp949)에서 한글이 깨지지 않도록
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = Path(__file__).resolve().parent
STATE_FILE = BASE / "확인기록.json"

# 소스당 이 개수까지만 수집(최신순). 넘치면 "외 n건"으로 표기.
PER_SOURCE_CAP = 8
# 본 기사 URL 기록 보관 기간(일)
SEEN_KEEP_DAYS = 30

# category: 기본 분류 라벨. major_only: 사소한 루머 제외 대상(캐논/니콘/후지).
SOURCES = [
    # A(공식)
    {"name": "Apple Newsroom US", "url": "https://www.apple.com/newsroom/rss-feed.rss",
     "category": "IT 공식발표", "official": True},
    {"name": "Apple Newsroom KR", "url": "https://www.apple.com/kr/newsroom/rss-feed.rss",
     "category": "IT 공식발표", "official": True},
    {"name": "Samsung Newsroom Korea", "url": "https://news.samsung.com/kr/feed",
     "category": "IT 공식발표", "official": True},
    # B(루머)
    {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All",
     "category": "IT 루머"},
    {"name": "SamMobile", "url": "https://www.sammobile.com/feed/",
     "category": "IT 루머"},
    {"name": "AppleInsider", "url": "https://appleinsider.com/rss/news/",
     "category": "IT 루머"},
    {"name": "9to5Mac", "url": "https://9to5mac.com/feed/",
     "category": "IT 루머"},
    {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/",
     "category": "IT 루머"},
    {"name": "란즈크 블로그", "url": "https://rss.blog.naver.com/yeux1122.xml",
     "category": "IT 루머"},
    # C(오디오)
    {"name": "What Hi-Fi?", "url": "https://www.whathifi.com/feeds/all",
     "category": "오디오"},
    {"name": "SoundGuys", "url": "https://www.soundguys.com/feed/",
     "category": "오디오"},
    {"name": "The Audiophile Man", "url": "https://theaudiophileman.com/feed/",
     "category": "오디오"},
    {"name": "TechRadar 오디오", "url": "https://www.techradar.com/feeds/tag/audio",
     "category": "오디오"},
    # D(카메라)
    {"name": "Sony Alpha Rumors", "url": "https://www.sonyalpharumors.com/feed/",
     "category": "카메라"},
    {"name": "Canon Rumors", "url": "https://www.canonrumors.com/feed/",
     "category": "카메라", "major_only": True},
    {"name": "Nikon Rumors", "url": "https://nikonrumors.com/feed/",
     "category": "카메라", "major_only": True},
    {"name": "Fuji Rumors", "url": "https://www.fujirumors.com/feed/",
     "category": "카메라", "major_only": True},
]

CATEGORY_ORDER = ["IT 공식발표", "IT 루머", "오디오", "카메라"]


def fetch(url, timeout=25):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def localname(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(data):
    """RSS 2.0 / Atom 둘 다 처리. [{title, link, date, summary}] 반환."""
    # 일부 피드의 잘못된 제어문자 제거
    data = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b"", data)
    root = ET.fromstring(data)
    items = []
    if localname(root.tag) == "feed":  # Atom
        for entry in root.iter():
            if localname(entry.tag) != "entry":
                continue
            title = link = date_raw = summary = ""
            for child in entry:
                name = localname(child.tag)
                if name == "title":
                    title = child.text or ""
                elif name == "link":
                    href = child.get("href") or ""
                    rel = child.get("rel") or "alternate"
                    if href and (rel == "alternate" or not link):
                        link = href
                elif name in ("published", "updated") and not date_raw:
                    date_raw = child.text or ""
                elif name in ("summary", "content") and not summary:
                    summary = "".join(child.itertext())
            items.append({"title": strip_html(title), "link": link.strip(),
                          "date": parse_date(date_raw), "summary": strip_html(summary)})
    else:  # RSS 2.0
        for item in root.iter():
            if localname(item.tag) != "item":
                continue
            title = link = date_raw = summary = ""
            for child in item:
                name = localname(child.tag)
                if name == "title":
                    title = "".join(child.itertext())
                elif name == "link":
                    link = ("".join(child.itertext())).strip() or (child.tail or "").strip()
                elif name in ("pubDate", "date") and not date_raw:
                    date_raw = "".join(child.itertext())
                elif name == "description" and not summary:
                    summary = "".join(child.itertext())
                elif name == "encoded" and not summary:
                    summary = "".join(child.itertext())
            items.append({"title": strip_html(title), "link": link,
                          "date": parse_date(date_raw), "summary": strip_html(summary)})
    return items


def url_key(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_run": None, "seen": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="결과 저장 폴더")
    ap.add_argument("--hours", type=int, default=24,
                    help="확인 기록이 없을 때 거슬러 올라갈 시간(기본 24)")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    state = load_state()
    if state.get("last_run"):
        cutoff = datetime.fromisoformat(state["last_run"])
        cutoff_label = "지난 확인 시점"
    else:
        cutoff = now - timedelta(hours=args.hours)
        cutoff_label = f"최근 {args.hours}시간(첫 실행)"
    seen = state.get("seen", {})

    collected = []   # 이번에 뽑힌 새 기사
    errors = []      # 접속 실패한 소스
    overflow = {}    # 소스별 잘린 개수

    for src in SOURCES:
        print(f"  확인 중: {src['name']} ...", flush=True)
        try:
            feed_items = parse_feed(fetch(src["url"]))
        except Exception as e:
            errors.append(f"{src['name']}: {type(e).__name__}")
            continue

        fresh = []
        for it in feed_items:
            if not it["link"] or not it["title"]:
                continue
            key = url_key(it["link"])
            if key in seen:
                continue
            if it["date"] is not None and it["date"] <= cutoff:
                continue
            if it["date"] is None:
                # 날짜를 모르는 항목(예: 일부 애플 뉴스룸)은 첫 화면 상위 3개까지만 후보로
                if len([f for f in fresh if f["date"] is None]) >= 3:
                    continue
            fresh.append(it)

        fresh.sort(key=lambda x: x["date"] or now, reverse=True)
        if len(fresh) > PER_SOURCE_CAP:
            overflow[src["name"]] = len(fresh) - PER_SOURCE_CAP
            fresh = fresh[:PER_SOURCE_CAP]

        for it in fresh:
            seen[url_key(it["link"])] = now.isoformat()
            collected.append({
                "category": src["category"],
                "source": src["name"],
                "official": bool(src.get("official")),
                "major_only": bool(src.get("major_only")),
                "title": it["title"],
                "link": it["link"],
                "date_kst": (it["date"].astimezone(KST).strftime("%Y-%m-%d %H:%M")
                             if it["date"] else "날짜 미상"),
                "summary": it["summary"][:600],
            })

    # 오래된 seen 기록 정리
    keep_after = now - timedelta(days=SEEN_KEEP_DAYS)
    seen = {k: v for k, v in seen.items()
            if datetime.fromisoformat(v) > keep_after}
    state = {"last_run": now.isoformat(), "seen": seen}
    save_state(state)

    # 저장 — JSON(보고서 작성용) + 텍스트(사람이 보는 용)
    (out_dir / "새소식.json").write_text(
        json.dumps(collected, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = []
    lines.append("뮤직잇츠 IT 뉴스 수집 결과")
    lines.append("=" * 40)
    lines.append(f"확인 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M')} (KST)")
    lines.append(f"확인 범위: {cutoff_label} 이후 → "
                 f"{cutoff.astimezone(KST).strftime('%Y-%m-%d %H:%M')} (KST) 이후 기사")
    lines.append(f"새 기사: {len(collected)}건")
    if errors:
        lines.append(f"접속 실패: {', '.join(errors)}")
    for name, n in overflow.items():
        lines.append(f"※ {name}: 새 글이 많아 최신 {PER_SOURCE_CAP}건만 수집 (외 {n}건 생략)")
    lines.append("")

    if not collected:
        lines.append("이번 실행에서는 새 소식이 없습니다.")
    else:
        for cat in CATEGORY_ORDER:
            cat_items = [c for c in collected if c["category"] == cat]
            if not cat_items:
                continue
            lines.append(f"■ [{cat}] {len(cat_items)}건")
            lines.append("-" * 40)
            for c in cat_items:
                flag = " (중요 소식만 선별)" if c["major_only"] else ""
                lines.append(f"· {c['title']}")
                lines.append(f"  출처: {c['source']}{flag} / {c['date_kst']}")
                lines.append(f"  링크: {c['link']}")
                if c["summary"]:
                    lines.append(f"  피드 요약: {c['summary'][:300]}")
                lines.append("")
    (out_dir / "새소식.txt").write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"새 기사 {len(collected)}건을 찾았습니다.")
    if errors:
        print(f"접속 실패한 소스: {', '.join(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
