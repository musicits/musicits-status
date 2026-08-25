#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""휴대폰 수집 결과로 보고서를 쓴다.

깃허브 Actions 안에서만 돌아간다(.github/workflows/collect.yml).
수집 직후, 결과 페이지를 만들기 전에 한 번 실행된다.

**키가 없으면 아무것도 하지 않고 조용히 끝난다.** 보고서는 있으면 좋은 것이고,
없다고 수집 결과까지 못 보게 되면 안 된다. 실패해도 마찬가지로 그냥 넘어간다.

두 번에 나눠 묻는다. 한 번에 다 시키면 90건짜리 회차에서 뒤쪽이 성의 없어진다.

  1단계(고르기)  제목 전부 번역 + 기기 소식만 남기기 + 주요 소식 고르기
                 → 재료는 제목과 피드 요약. 값이 싸고 전체를 훑어야 하는 일이다.
  2단계(쓰기)    고른 기사만 원문을 열어 읽고 한 꼭지씩 쓰기
                 → 5건뿐이라 원문을 다 넘겨도 무료 한도 안에서 끝난다.

**PC 보고서를 대신하지 않는다.** 저쪽은 Claude 가 기사를 읽고 쓰며 뉴스 쿼터까지
같이 본다. 이쪽은 폰에서 그 모양으로 훑어보기 위한 것이고, 원문을 못 읽은 기사는
'피드 요약만'이라고 적어 둔다 — 읽은 척하는 것보다 낫다.

■ 왜 Gemini 인가 (2026-08-18)

무료 등급이 있어서다. 하루 한 번 도는 이 용도에는 무료 한도로 충분하다.
대신 **무료 등급은 구글이 보낸 내용을 제품 개선에 쓰고 사람이 읽어볼 수 있다.**
그래서 여기로 보내는 것은 이미 공개된 기사(제목·피드 요약·본문)뿐이다.
블로그 성과 수치나 경쟁 블로그 목록은 절대 이쪽으로 보내지 않는다.
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUNS = os.path.join(REPO, "cloud", "runs")
sys.path.insert(0, HERE)
import fulltext                                                 # noqa: E402

# 쓸 모델. 바꾸려면 이 줄만 고치면 된다.
#   gemini-3.7-flash       현재 설정. 번역 품질과 중요도 판단을 우선한다
#   gemini-3.5-flash-lite  더 빠르고 싸다. 무료 한도가 모자랄 때 이쪽으로
MODEL = "gemini-3.7-flash"

PICKS = 5                 # 주요 소식으로 고를 최대 건수
FEED_SUMMARY_CHARS = 300  # 1단계에서 모델에게 넘길 피드 요약 길이
VERDICTS = ["공식 확인됨", "루머 단계", "리뷰·실측", "보도 인용"]

WHO = """당신은 블로그 '뮤직잇츠'의 IT 뉴스 담당입니다.
애플·삼성·오디오·카메라 기기 소식을 한국 독자에게 전합니다."""

SORT_SYSTEM = WHO + """

받은 기사 목록을 훑어 세 가지를 합니다.

1) 모든 기사의 제목을 자연스러운 한국어로 옮깁니다(ko).
   - 제품명·회사명은 한국에서 쓰는 표기를 씁니다 (Galaxy Z Fold 9 → 갤럭시 Z 폴드9).
   - 원문에 없는 내용을 넣지 않습니다. 과장하지 않습니다.
   - 이미 한국어인 제목은 그대로 둡니다.

2) 기기 소식만 남깁니다(keep).
   - 남길 것: 신제품, 사양, 가격, 출시 일정, 중요한 기능 변화, 실측 리뷰.
   - 거를 것: 기업 실적·주주환원·수상·B2B·생산라인, 소송과 규제, 할인·이벤트,
     사소한 앱 업데이트, 시장 점유율 전망, 사건사고와 잡담.
   - 거른 기사는 왜 걸렀는지 drop 에 두세 단어로 적습니다("기업/B2B", "할인" 처럼).

3) 남긴 기사에는 한 줄 문장을 씁니다(line).
   - "무엇이 어떻게 됐다" 한 문장. 제목을 그대로 되풀이하지 않습니다.
   - 루머면 루머라고 밝힙니다.

그리고 남긴 것 중 뮤직잇츠 독자에게 가장 중요한 기사를 중요한 순으로 picks 에 담습니다.
   - 기기 자체의 소식(신제품, 사양, 가격, 출시)을 앞에 둡니다.
   - 확인된 발표와 루머를 섞지 않습니다.
   - why 에는 그 소식이 무엇을 뜻하는지 한 줄로 씁니다. 제목을 되풀이하지 않습니다."""

WRITE_SYSTEM = WHO + """

고른 기사의 원문을 읽고 보고서 한 꼭지씩 씁니다. 기사마다 네 가지입니다.

1) verdict — 이 소식의 성격. """ + " / ".join(VERDICTS) + """ 중 하나.
   회사가 직접 발표한 것만 '공식 확인됨' 입니다. 팁스터·유출·전망은 '루머 단계',
   직접 써보고 측정한 글은 '리뷰·실측', 다른 매체를 받아 적은 것은 '보도 인용'.

2) body — 기사 내용을 4~6문장으로 정리합니다.
   - 숫자(가격, 용량, 시간, 무게, 화소)는 원문에 있는 그대로 옮깁니다.
   - 원문에 없는 배경 설명이나 추측을 보태지 않습니다.
   - **'원문: 읽지 못했습니다' 라고 적힌 기사는 피드 요약에 있는 만큼만 쓰고 짧게
     끝냅니다. 빈 자리를 지어내지 마세요.** 두 문장뿐이어도 괜찮습니다.

3) blog_line — 이 소식이 뮤직잇츠 독자에게 무엇을 뜻하는지 한 문장.

4) title_ideas — 블로그 제목 후보 3개.
   - 원문이 말하지 않은 것을 제목에 넣지 않습니다. 낚시성 제목을 쓰지 않습니다.
   - 셋을 서로 다른 각도로 잡습니다(무엇이 나왔나 / 왜 그런가 / 뭘 따져봐야 하나)."""

SORT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "ko": {"type": "string"},
                    "keep": {"type": "boolean"},
                    "drop": {"type": "string"},
                    "line": {"type": "string"},
                },
                "required": ["no", "ko", "keep"],
            },
        },
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "why": {"type": "string"},
                },
                "required": ["no", "why"],
            },
        },
    },
    "required": ["items", "picks"],
}

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "reports": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "verdict": {"type": "string", "enum": VERDICTS},
                    "body": {"type": "string"},
                    "blog_line": {"type": "string"},
                    "title_ideas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["no", "verdict", "body", "blog_line", "title_ideas"],
            },
        },
    },
    "required": ["reports"],
}


def latest_run():
    """가장 최근 수집 폴더. 없으면 None."""
    if not os.path.isdir(RUNS):
        return None
    for name in sorted((n for n in os.listdir(RUNS)
                        if re.match(r"\d{4}-\d{2}-\d{2}_\d{4}$", n)), reverse=True):
        if os.path.isfile(os.path.join(RUNS, name, "새소식.json")):
            return os.path.join(RUNS, name)
    return None


def ask(system, prompt, schema):
    """한 번 묻고 답을 받는다."""
    from google import genai

    client = genai.Client()          # GEMINI_API_KEY 환경변수를 읽는다
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=system,
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": schema},
        # 구글 쪽에 대화를 남겨둘 이유가 없다. 한 번 묻고 끝이다.
        store=False,
    )
    return json.loads(interaction.output_text)


def sort_prompt(items):
    lines = []
    for i, it in enumerate(items):
        lines.append("%d. [%s] %s (%s)"
                     % (i, it.get("category"), it.get("title"), it.get("source")))
        summary = (it.get("summary") or "")[:FEED_SUMMARY_CHARS]
        if summary:
            lines.append("   피드 요약: %s" % summary)
    return ("아래 기사 %d건입니다. 번호를 그대로 써서 답해주세요.\n"
            "items 에는 %d건 전부를 담고, picks 에는 최대 %d건을 담습니다.\n\n%s"
            % (len(items), len(items), PICKS, "\n".join(lines)))


def write_prompt(picked):
    """picked: [(번호, 기사, 본문, 못읽은 사유)]"""
    blocks = []
    for no, it, body, reason in picked:
        block = ["[%d] %s · %s · %s"
                 % (no, it.get("category"), it.get("source"), it.get("date_kst")),
                 "제목: %s" % it.get("title")]
        summary = it.get("summary") or ""
        if summary:
            block.append("피드 요약: %s" % summary)
        if body:
            block.append("원문:\n%s" % body)
        else:
            block.append("원문: 읽지 못했습니다(%s). "
                         "위 피드 요약에 있는 것만 쓰세요." % reason)
        blocks.append("\n".join(block))
    return ("아래 %d건입니다. 대괄호 안의 번호를 그대로 써서 답해주세요.\n\n%s"
            % (len(picked), "\n\n----\n\n".join(blocks)))


def sort_out(items):
    """1단계. 실패하면 (None, None)."""
    try:
        got = ask(SORT_SYSTEM, sort_prompt(items), SORT_SCHEMA)
    except Exception as exc:                                    # noqa: BLE001
        print("[건너뜀] 고르지 못했습니다: %s: %s" % (type(exc).__name__, exc))
        return None, None

    def ok(entry):
        return (isinstance(entry, dict) and isinstance(entry.get("no"), int)
                and 0 <= entry["no"] < len(items))

    by_no = {}
    for entry in got.get("items") or []:
        if ok(entry) and entry.get("ko"):
            by_no[entry["no"]] = entry
    picks, seen = [], set()
    for entry in got.get("picks") or []:
        if ok(entry) and entry.get("why") and entry["no"] not in seen:
            seen.add(entry["no"])
            picks.append(entry)
    return by_no, picks[:PICKS]


def write_out(items, picks):
    """2단계. 고른 기사의 원문을 읽고 한 꼭지씩 받는다."""
    picked = []
    for p in picks:
        it = items[p["no"]]
        body, reason = fulltext.read(it.get("link"))
        print("  원문 %s — %s"
              % ("읽음 %d자" % len(body) if body else "못 읽음(%s)" % reason,
                 (it.get("title") or "")[:50]))
        picked.append((p["no"], it, body, reason))

    try:
        got = ask(WRITE_SYSTEM, write_prompt(picked), WRITE_SCHEMA)
    except Exception as exc:                                    # noqa: BLE001
        print("[건너뜀] 보고서를 쓰지 못했습니다: %s: %s" % (type(exc).__name__, exc))
        got = {}

    written = {}
    for r in got.get("reports") or []:
        if isinstance(r, dict) and isinstance(r.get("no"), int) and r.get("body"):
            written[r["no"]] = r

    out = []
    for no, _it, body, reason in picked:
        r = written.get(no) or {}
        out.append({
            "no": no,
            "why": next(p["why"] for p in picks if p["no"] == no),
            "verdict": r.get("verdict") or "",
            "body": r.get("body") or "",
            "blog_line": r.get("blog_line") or "",
            "title_ideas": [t for t in (r.get("title_ideas") or []) if t][:3],
            "read": "원문" if body else "피드 요약 (%s)" % reason,
        })
    return out


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY 가 없어 보고서를 건너뜁니다.")
        return 0

    run_dir = latest_run()
    if not run_dir:
        print("보고서를 쓸 수집 결과가 없습니다.")
        return 0

    with open(os.path.join(run_dir, "새소식.json"), encoding="utf-8") as f:
        items = json.load(f)
    if not items:
        print("새 기사가 없어 쓸 것이 없습니다.")
        return 0

    by_no, picks = sort_out(items)
    if by_no is None:
        return 0                       # 목록만이라도 원문 제목으로 나온다

    kept = [n for n, e in by_no.items() if e.get("keep")]
    picked_nos = {p["no"] for p in picks}
    reports = write_out(items, picks) if picks else []

    dropped = {}
    for n, e in by_no.items():
        if not e.get("keep"):
            dropped[e.get("drop") or "기기 소식 아님"] = \
                dropped.get(e.get("drop") or "기기 소식 아님", 0) + 1

    out = {
        "model": MODEL,
        # 목록에 쓰는 한국어 제목. 페이지는 이것만 있어도 그려진다.
        "titles": {str(n): e["ko"] for n, e in by_no.items()},
        # 예전 페이지가 읽던 자리. 모양을 바꾸지 않고 그대로 둔다.
        "highlights": [{"no": r["no"], "why": r["why"]} for r in reports],
        "report": {
            "counts": {"collected": len(items), "kept": len(kept),
                       "picked": len(reports)},
            "picks": reports,
            "rest": [{"no": n, "line": by_no[n].get("line") or by_no[n]["ko"]}
                     for n in sorted(kept) if n not in picked_nos],
            "dropped": sorted(dropped.items(), key=lambda kv: -kv[1]),
        },
    }
    with open(os.path.join(run_dir, "요약.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("번역 %d/%d건 · 기기 소식 %d건 · 보고서 %d꼭지 (%s)"
          % (len(out["titles"]), len(items), len(kept), len(reports), MODEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
