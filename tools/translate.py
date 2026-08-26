#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""휴대폰 수집 결과의 제목을 한국어로 옮기고 주요 이슈를 골라낸다.

깃허브 Actions 안에서만 돌아간다(.github/workflows/collect.yml).
수집 직후, 결과 페이지를 만들기 전에 한 번 실행된다.

**키가 없으면 아무것도 하지 않고 조용히 끝난다.** 번역은 있으면 좋은 것이고,
없다고 수집 결과까지 못 보게 되면 안 된다. 실패해도 마찬가지로 그냥 넘어간다.

**PC 보고서를 대신하지 않는다.** 저쪽은 Claude 가 기사 원문을 직접 열어 읽고
쓰는 것이고, 여기는 수집된 제목과 피드 요약만 보고 옮기는 것이다.

■ 왜 Gemini 인가 (2026-08-18)

무료 등급이 있어서다. 하루 한 번 도는 이 용도에는 무료 한도로 충분하다.
대신 **무료 등급은 구글이 보낸 내용을 제품 개선에 쓰고 사람이 읽어볼 수 있다.**
그래서 여기로 보내는 것은 이미 공개된 기사 제목과 피드 요약뿐이다.
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

# 쓸 모델. 바꾸려면 이 줄만 고치면 된다.
#   gemini-3.7-flash       현재 설정. 번역 품질과 중요도 판단을 우선한다
#   gemini-3.5-flash-lite  더 빠르고 싸다. 무료 한도가 모자랄 때 이쪽으로
MODEL = "gemini-3.7-flash"

HIGHLIGHTS = 8            # 주요 이슈로 고를 개수
FEED_SUMMARY_CHARS = 300  # 모델에게 넘길 피드 요약 길이

SYSTEM = """당신은 블로그 '뮤직잇츠'의 IT 뉴스 담당입니다.
애플·삼성·오디오·카메라 기기 소식을 한국 독자에게 전합니다.

받은 기사 목록에 대해 두 가지를 합니다.

1) 모든 기사의 제목을 자연스러운 한국어로 옮깁니다.
   - 제품명·회사명은 한국에서 쓰는 표기를 씁니다 (Galaxy Z Fold 9 → 갤럭시 Z 폴드9).
   - 원문에 없는 내용을 넣지 않습니다. 과장하지 않습니다.
   - 이미 한국어인 제목은 그대로 둡니다.

2) 그중 뮤직잇츠 독자에게 중요한 기사를 고르고, 왜 중요한지 한 줄로 씁니다.
   - 기기 자체의 소식(신제품, 사양, 가격, 출시, 중요한 기능 변화)을 우선합니다.
   - 할인·이벤트·앱 업데이트·시장 점유율 같은 주변 소식은 뒤로 미룹니다.
   - 확인된 발표와 루머를 섞지 말고, 루머면 루머라고 밝힙니다.
   - 한 줄 요약은 제목을 되풀이하지 말고, 그 소식이 무엇을 뜻하는지 씁니다."""

# 답을 정해진 모양으로 받는다. 자유 형식으로 받아 파싱하면 형식이 흔들린다.
SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "ko": {"type": "string"},
                },
                "required": ["no", "ko"],
            },
        },
        "highlights": {
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
    "required": ["titles", "highlights"],
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


def build_prompt(items):
    lines = []
    for i, it in enumerate(items):
        lines.append("%d. [%s] %s (%s)"
                     % (i, it.get("category"), it.get("title"), it.get("source")))
        summary = (it.get("summary") or "")[:FEED_SUMMARY_CHARS]
        if summary:
            lines.append("   피드 요약: %s" % summary)
    return ("아래 기사 %d건입니다. 번호를 그대로 써서 답해주세요.\n"
            "titles 에는 %d건 전부, highlights 에는 중요한 순으로 %d건을 담습니다.\n\n%s"
            % (len(items), len(items), min(HIGHLIGHTS, len(items)), "\n".join(lines)))


def api_key():
    """번역에 쓸 키. 없으면 보고서 키라도 쓴다.

    한도를 나누려고 키를 둘로 두는 것이 원래 설계지만(README 6·7번), 하나만
    넣어둔 상태에서 번역이 통째로 빠지는 편이 더 나쁘다. 둘 다 있으면 지금처럼
    갈라 쓰고, 하나뿐이면 그 하나로 둘 다 돈다.
    """
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_REPORT_KEY")


def ask(items):
    """기사 목록을 넘겨 번역과 주요 이슈를 받는다."""
    from google import genai

    client = genai.Client(api_key=api_key())
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=SYSTEM,
        input=build_prompt(items),
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": SCHEMA},
        # 구글 쪽에 대화를 남겨둘 이유가 없다. 한 번 묻고 끝이다.
        store=False,
    )
    return json.loads(interaction.output_text)


def main():
    if not api_key():
        print("GEMINI_API_KEY 도 GEMINI_REPORT_KEY 도 없어 번역을 건너뜁니다.")
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY 가 없어 보고서 키를 같이 씁니다(한도를 나눠 쓰게 됩니다).")

    run_dir = latest_run()
    if not run_dir:
        print("번역할 수집 결과가 없습니다.")
        return 0

    with open(os.path.join(run_dir, "새소식.json"), encoding="utf-8") as f:
        items = json.load(f)
    if not items:
        print("새 기사가 없어 번역할 것이 없습니다.")
        return 0

    try:
        got = ask(items)
    except Exception as exc:                                    # noqa: BLE001
        # 번역이 실패해도 수집 결과는 그대로 볼 수 있어야 한다.
        print("[건너뜀] 번역하지 못했습니다: %s: %s" % (type(exc).__name__, exc))
        return 0

    def valid(entry, field):
        return (isinstance(entry, dict) and isinstance(entry.get("no"), int)
                and 0 <= entry["no"] < len(items) and entry.get(field))

    out = {
        "model": MODEL,
        "titles": {str(t["no"]): t["ko"] for t in got.get("titles") or []
                   if valid(t, "ko")},
        "highlights": [{"no": h["no"], "why": h["why"]}
                       for h in got.get("highlights") or [] if valid(h, "why")],
    }
    with open(os.path.join(run_dir, "요약.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("번역 %d/%d건, 주요 이슈 %d건 (%s)"
          % (len(out["titles"]), len(items), len(out["highlights"]), MODEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
