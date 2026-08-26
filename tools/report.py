#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""휴대폰 수집 결과로 IT 뉴스 보고서를 쓴다 (클라우드용).

깃허브 Actions 안에서만 돌아간다(.github/workflows/collect.yml).
수집 → 번역 다음, 결과 페이지를 만들기 전에 한 번 실행된다.

■ 집 / 밖 두 갈래

같은 보고서를 두 곳에서 만든다. 쓰는 모델이 다를 뿐 양식은 하나다.

    집(PC)   run_all.py → Claude Code CLI → 2_확인결과/날짜/시각/보고서.md
    밖(폰)   이 파일    → Gemini          → cloud/runs/YYYY-MM-DD_HHMM/보고서.md

서로 덮어쓰지 않는다. 확인 기록도 따로라 아침에 폰에서 본 기사가 PC 보고서에
다시 나올 수 있다 — 겹칠 뿐 빠지지는 않는다(collect.yml 주석과 같은 이야기).

■ 양식의 원본은 한 곳이다

`tools/보고서_작성_프롬프트.md` 는 PC 쪽 원본
(`1. IT 뉴스 모니터링/3_건드리지마세요/보고서_작성_프롬프트.md`)의 사본이다.
web.py 가 사이트를 만들 때마다 덮어쓰므로 **이 사본을 직접 고치지 말 것.**
양식을 바꾸려면 PC 원본을 고치고 `★_웹에 올리기.bat` 을 누르면 된다.

■ 키

`GEMINI_REPORT_KEY` 를 쓴다. 번역이 쓰는 `GEMINI_API_KEY` 와 **일부러 다른
키다.** 보고서는 기사 본문까지 넘기느라 번역보다 훨씬 크고, 한도가 한 열쇠에
묶여 있으면 보고서가 번역을 잡아먹는다. 키가 없으면 아무것도 하지 않고 조용히
끝난다 — 보고서가 없다고 수집 결과까지 못 보게 되면 안 된다.

무료 등급은 구글이 보낸 내용을 제품 개선에 쓰고 사람이 읽어볼 수 있다.
그래서 여기로 가는 것은 **이미 공개된 기사의 제목과 본문뿐이다.** 블로그 성과
수치나 경쟁 블로그 목록은 절대 이쪽으로 보내지 않는다(translate.py 와 같은 규칙).
"""
import html
import json
import os
import re
import sys
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUNS = os.path.join(REPO, "cloud", "runs")
SPEC = os.path.join(HERE, "보고서_작성_프롬프트.md")

# 쓸 모델. 바꾸려면 이 줄만 고치면 된다.
#   gemini-3.7-flash  현재 설정. 본문을 읽고 요약하는 일이라 lite 는 권하지 않는다
MODEL = "gemini-3.7-flash"

MAIN_PICKS = 5            # 원문을 열어 정식 양식으로 쓰는 건수
CANDIDATES = 12           # 그 5건을 채우려고 미리 받아 두는 후보 수
PER_SOURCE_CAP = 2        # 같은 소스에서 주요 소식으로 고를 최대 건수
MIN_BODY_CHARS = 400      # 이보다 짧으면 껍데기만 받은 것으로 본다
BODY_CHARS = 6000         # 기사 하나에서 모델에게 넘길 본문 길이
LIST_SUMMARY_CHARS = 300  # 한줄 목록용 피드 요약 길이
FETCH_TIMEOUT = 20

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

CATEGORY_ORDER = ["IT 공식발표", "IT 루머", "오디오", "카메라"]

SYSTEM = """당신은 IT 블로그 '뮤직잇츠(music ITs)'의 뉴스 모니터링 담당자입니다.
애플·삼성 등 해외 IT 소식, 음향기기, 카메라를 다룹니다.
결과물은 블로그 원고 재료로 그대로 복사해서 쓰입니다.

작성 지침을 함께 받습니다. **그 지침의 양식을 글자 하나도 바꾸지 마세요.**
지침과 이 문장이 어긋나면 지침을 따릅니다.

지침에 나오는 도구 이야기(WebFetch, curl, 파일 저장, 채팅 출력)는 무시하세요.
기사 본문은 이미 아래에 붙여 드렸고, 당신은 보고서 본문만 쓰면 됩니다.
설명이나 머리말 없이 보고서 그 자체로 시작하세요."""


# ------------------------------------------------------------------ 수집 결과

def latest_run():
    """가장 최근 수집 폴더. 없으면 None. (translate.py 와 같은 규칙)"""
    if not os.path.isdir(RUNS):
        return None
    for name in sorted((n for n in os.listdir(RUNS)
                        if re.match(r"\d{4}-\d{2}-\d{2}_\d{4}$", n)), reverse=True):
        if os.path.isfile(os.path.join(RUNS, name, "새소식.json")):
            return os.path.join(RUNS, name)
    return None


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["picks"],
}


def ask_picks(items, key, want):
    """어느 기사를 정식 양식으로 쓸지 지침대로 고르게 한다. 실패하면 빈 목록.

    제목과 피드 요약만 넘기는 짧은 호출이다. 본문을 받아오기 **전에** 골라야
    엉뚱한 기사의 원문을 열댓 개나 긁는 헛일을 안 한다.
    """
    lines = []
    for i, it in enumerate(items):
        lines.append("%d. [%s] %s (%s%s)"
                     % (i, it.get("category"), it.get("title"), it.get("source"),
                        " · 중요 소식만" if it.get("major_only") else ""))
        summary = (it.get("summary") or "")[:LIST_SUMMARY_CHARS]
        if summary:
            lines.append("   %s" % summary)
    prompt = ("아래 기사 %d건 중 [선별 규칙]에 따라 주요 소식 %d건을 고르세요.\n"
              "중요한 순서로 번호만 담아 답하세요. 거를 것(마케팅성·전시회·"
              "콘텐츠 사건 등)은 빼고, 같은 사건을 여러 소스가 다뤘으면 가장 "
              "상세한 것 하나만 고릅니다.\n\n%s"
              % (len(items), min(MAIN_PICKS, len(items)), "\n".join(lines)))
    try:
        from google import genai
        client = genai.Client(api_key=key)
        got = client.interactions.create(
            model=MODEL, system_instruction=SYSTEM, input=prompt,
            response_format={"type": "text", "mime_type": "application/json",
                             "schema": PICK_SCHEMA},
            store=False,
        )
        return json.loads(got.output_text).get("picks") or []
    except Exception as exc:                              # noqa: BLE001
        print("   [건너뜀] 고르기 실패, 번역 순서로 갑니다: %s: %s"
              % (type(exc).__name__, exc))
        return []


def pick_main(items, digest, key=None, want=MAIN_PICKS):
    """정식 양식으로 쓸 **후보** 번호들. 중요한 순서다.

    실제로 쓸 5건은 이 중에서 원문이 열리는 것으로 채운다(main 참고). 그래서
    필요한 수보다 넉넉히 돌려준다.

    순서는 이렇다.

      1. 번역 단계(translate.py)가 골라 둔 '독자에게 중요한 순서'
      2. 그게 없으면(번역 키가 없었거나 한도를 넘긴 날) 모델에게 직접 고르게 한다
      3. 그것도 안 되면 카테고리 순서

    3번까지 내려가면 선별 규칙이 전혀 안 걸린다 — 실제로 그렇게 골라 보니
    같은 발표의 미국판·한국판이 나란히 뽑히고 전시회 초대장까지 올라왔다.
    그래서 2번을 사이에 뒀다.

    어느 경로로 왔든 지침의 '같은 소스에서 최대 2건' 은 여기서 지킨다.
    """
    picked, per_source = [], {}

    def take(i):
        src = items[i].get("source") or ""
        if i in picked or per_source.get(src, 0) >= PER_SOURCE_CAP:
            return False
        picked.append(i)
        per_source[src] = per_source.get(src, 0) + 1
        return True

    def fill(nos):
        for no in nos:
            if isinstance(no, int) and 0 <= no < len(items):
                take(no)
            if len(picked) >= want:
                return True
        return False

    if fill([h.get("no") for h in (digest.get("highlights") or [])]):
        return picked
    if key and fill(ask_picks(items, key, want)):
        return picked

    for cat in CATEGORY_ORDER:
        for i, it in enumerate(items):
            if it.get("category") == cat and take(i) and len(picked) >= want:
                return picked
    for i in range(len(items)):                    # 그래도 모자라면 순서대로
        if take(i) and len(picked) >= want:
            break
    return picked


# ------------------------------------------------------------------ 본문 읽기

DROP_TAGS = re.compile(r"(?is)<(script|style|noscript|template|svg)\b.*?</\1>")
ARTICLE = re.compile(r"(?is)<article\b[^>]*>(.*?)</article>")
BLOCK_END = re.compile(r"(?i)</(p|div|section|li|h[1-6]|br)\s*>|<br\s*/?>")
TAG = re.compile(r"(?s)<[^>]+>")


def readable_url(url):
    """받아올 주소로 손본다.

    네이버 블로그(란즈크)는 PC 주소로 받으면 본문이 iframe 안에 있어 껍데기만
    온다. 모바일 주소로 바꾸면 본문이 그대로 들어 있다.
    """
    return url.replace("//blog.naver.com/", "//m.blog.naver.com/")


def fetch_body(url):
    """기사 본문을 글자로 뽑는다. 못 읽으면 None.

    모델에게 URL 을 던져 대신 읽게 하지 않는다. 그 능력은 모델·버전마다 다르고,
    막힌 사이트에서 조용히 지어낼 위험이 있다. 여기서 직접 받아서 넘긴다.
    """
    url = readable_url(url)
    try:
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept-Language": "ko,en;q=0.8"})
        with urlopen(req, timeout=FETCH_TIMEOUT) as r:
            raw = r.read(1_500_000)
            charset = (r.headers.get_content_charset() or "utf-8")
    except Exception as exc:                              # noqa: BLE001
        print("     본문 실패: %s: %s" % (type(exc).__name__, exc))
        return None

    try:
        text = raw.decode(charset, "replace")
    except (LookupError, ValueError):
        text = raw.decode("utf-8", "replace")

    text = DROP_TAGS.sub(" ", text)
    bodies = ARTICLE.findall(text)                        # 본문 태그가 있으면 그쪽만
    if bodies:
        text = max(bodies, key=len)
    text = BLOCK_END.sub("\n", text)
    text = TAG.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text).strip()
    return text or None


# ------------------------------------------------------------------ 프롬프트

def build_prompt(items, digest, mains, bodies):
    titles = digest.get("titles") or {}
    out = ["수집된 새 기사 %d건입니다." % len(items), ""]

    out.append("## 주요 소식으로 다룰 %d건 (원문 본문 포함)" % len(mains))
    out.append("")
    for n, i in enumerate(mains, 1):
        it = items[i]
        out.append("### %d. %s" % (n, it.get("title")))
        ko = titles.get(str(i))
        if ko:
            out.append("제목 한국어 초벌: %s" % ko)
        out.append("카테고리: %s" % it.get("category"))
        out.append("소스: %s%s" % (it.get("source"),
                                 " (공식 뉴스룸)" if it.get("official") else ""))
        out.append("게시: %s" % it.get("date_kst"))
        out.append("URL: %s" % it.get("link"))
        body = bodies.get(i)
        if body:
            out.append("원문 본문:")
            out.append(body[:BODY_CHARS])
        else:
            out.append("원문 본문: (접속 불가 — 피드 요약만 있습니다. 요약 끝에 "
                       "'(원문 접속 불가, 피드 기준)' 을 붙이세요.)")
            out.append("피드 요약: %s" % (it.get("summary") or "")[:LIST_SUMMARY_CHARS])
        out.append("")

    rest = [i for i in range(len(items)) if i not in mains]
    out.append("## 나머지 소식 %d건 (한줄 목록용)" % len(rest))
    out.append("")
    if not rest:
        out.append("(없음)")
    for n, i in enumerate(rest, len(mains) + 1):
        it = items[i]
        out.append("%d. [%s] %s (%s)" % (n, it.get("category"),
                                         titles.get(str(i)) or it.get("title"),
                                         it.get("source")))
        out.append("   %s" % it.get("link"))
        summary = (it.get("summary") or "")[:LIST_SUMMARY_CHARS]
        if summary:
            out.append("   피드 요약: %s" % summary)
    return "\n".join(out)


def ask(spec, prompt, key):
    from google import genai

    client = genai.Client(api_key=key)
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=SYSTEM + "\n\n---- 작성 지침 ----\n" + spec,
        input=prompt,
        # 구글 쪽에 대화를 남겨둘 이유가 없다. 한 번 묻고 끝이다.
        store=False,
    )
    return (interaction.output_text or "").strip()


# ------------------------------------------------------------------ 진행

def main():
    key = os.environ.get("GEMINI_REPORT_KEY")
    if not key:
        print("GEMINI_REPORT_KEY 가 없어 보고서를 건너뜁니다.")
        return 0

    run_dir = latest_run()
    if not run_dir:
        print("보고서를 쓸 수집 결과가 없습니다.")
        return 0

    items = read_json(os.path.join(run_dir, "새소식.json")) or []
    if not items:
        print("새 기사가 없어 보고서를 만들지 않습니다.")
        return 0

    if not os.path.isfile(SPEC):
        print("[건너뜀] 작성 지침(%s)이 없습니다." % os.path.basename(SPEC))
        return 0
    with open(SPEC, encoding="utf-8") as f:
        spec = f.read()

    digest = read_json(os.path.join(run_dir, "요약.json")) or {}
    cands = pick_main(items, digest, key, CANDIDATES)

    # 원문이 열리는 것으로 5건을 채운다. 열리는 소스를 골라 두면 헛걸음이 없다 —
    # TechRadar·What Hi-Fi 는 가입 유도 화면으로 잘리고, 소니·후지 루머는 403 이
    # 잦다. 후보를 다 봐도 모자라면 못 읽은 것으로 채우고, 그 항목은 피드 요약
    # 기준이라고 보고서에 밝히게 한다.
    mains, bodies = [], {}
    for i in cands:
        if len(mains) >= MAIN_PICKS:
            break
        print("   원문 읽는 중: %s" % (items[i].get("title") or "")[:60])
        body = fetch_body(items[i].get("link") or "")
        if body:
            bodies[i] = body
            mains.append(i)
    for i in cands:                                # 열린 것만으로 모자랄 때
        if len(mains) >= MAIN_PICKS:
            break
        if i not in mains:
            mains.append(i)
    mains.sort(key=cands.index)                    # 중요한 순서를 되돌린다
    print("주요 소식 %d건(본문 %d건), 나머지 %d건"
          % (len(mains), len(bodies), len(items) - len(mains)))

    try:
        text = ask(spec, build_prompt(items, digest, mains, bodies), key)
    except Exception as exc:                              # noqa: BLE001
        # 보고서가 실패해도 수집 결과와 번역은 그대로 볼 수 있어야 한다.
        print("[건너뜀] 보고서를 쓰지 못했습니다: %s: %s" % (type(exc).__name__, exc))
        return 0
    if not text:
        print("[건너뜀] 빈 답이 왔습니다.")
        return 0

    with open(os.path.join(run_dir, "보고서.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("보고서 %d글자 (%s · 본문 %d/%d건 읽음)"
          % (len(text), MODEL, len(bodies), len(mains)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
