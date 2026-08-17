#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실행기 — 도구들이 공유하는 단 하나의 실행 진입점.

통합 전에는 이 파일이 170줄짜리로 9개 폴더에 통째로 복사돼 있었다.
docstring 한 줄과 CONFIG 한 줄 빼면 diff가 완전히 비어 있었다. 실행기 버그
하나를 고치려면 9곳을 고쳐야 했다. 이제 여기 한 곳이다.

    python3 runner.py <도구이름>

도구이름은 아래 TOOLS 의 열쇠. 1_시작하기 폴더의 .bat 이 이걸 부른다.
"""

import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))       # 4_건드리지마세요/공용
PROGRAMS = os.path.dirname(HERE)                        # 4_건드리지마세요
ROOT = os.path.dirname(PROGRAMS)                        # 뮤직잇츠 도구모음
SETTINGS = os.path.join(ROOT, "3_설정")
RESULTS = os.path.join(ROOT, "2_결과")
KEYFILE = os.path.join(SETTINGS, "api_key.txt")

# 검색 키 / 트렌드 키. 예전 이름(NCP_APIGW_*)도 계속 받는다.
SEARCH_KEYS = ["SEARCH_KEY_ID", "SEARCH_KEY"]
TREND_KEYS = ["TREND_KEY_ID", "TREND_KEY"]


# ---------------------------------------------------------------- 도구 목록
#
# program : 4_건드리지마세요 폴더 안의 파일 이름
# needs   : 있어야 하는 키 (search / trend / 없으면 빈 리스트)
# inputs  : 3_설정 폴더에 있어야 하는 파일. {IN:이름} 으로 인자에 꽂힌다
# excel   : 결과 폴더를 넘겨 엑셀을 만드는 스크립트 (없으면 None)
# renames : 결과 파일 이름을 사람이 읽을 이름으로 바꾼다

TOOLS = {
    # 결과 폴더를 새로 만들지 않고 기존 결과를 읽기만 하는 도구는 simple 로 둔다.
    "전체보기": {
        "label": "0. 전체 보기",
        "program": "대시보드.py",
        "args": [],
        "needs": [],
        "inputs": [],
        "excel": None,
        "renames": [],
        "simple": True,
        "opens": "대시보드.html",     # 다 만든 뒤 이 파일 하나만 연다
    },
    "키워드발굴": {
        "label": "1. 키워드 발굴",
        "program": "키워드발굴.py",
        "args": ["--out", "{DAY}/추천"],
        "needs": ["search", "trend"],
        "inputs": [],
        "excel": "키워드발굴_엑셀.py",
        "renames": [("추천_추천.csv", "발행추천.csv"), ("추천.json", "데이터.json")],
    },
    "제목진단": {
        "label": "2. 제목 진단",
        "program": "제목진단.py",
        "args": ["--입력", "{IN:진단할제목.txt}", "--out", "{DAY}/진단"],
        "needs": ["search"],
        "inputs": ["진단할제목.txt"],
        "excel": "제목진단_엑셀.py",
        "renames": [("진단_진단.csv", "제목진단.csv"), ("진단_제목목록.csv", "상위권제목목록.csv"),
                    ("진단.json", "데이터.json")],
    },
    "성과추적": {
        "label": "3. 성과 추적",
        "program": "성과추적.py",
        "args": ["--키워드", "{IN:추적할키워드.txt}",
                 "--경쟁블로그", "{IN:경쟁블로그.txt}", "--out", "{DAY}/추적"],
        "needs": ["search"],
        "inputs": ["추적할키워드.txt", "경쟁블로그.txt"],
        "excel": "성과추적_엑셀.py",
        "renames": [("추적_순위.csv", "검색어순위.csv"), ("추적_경쟁.csv", "경쟁비교.csv"),
                    ("추적.json", "데이터.json")],
    },
    "이웃발굴": {
        "label": "4. 이웃 발굴",
        "program": "이웃발굴.py",
        "args": ["--out", "{DAY}/이웃후보"],
        "needs": ["search"],
        "inputs": [],
        "excel": "이웃발굴_엑셀.py",
        "renames": [("이웃후보_이웃후보.csv", "소통후보.csv"), ("이웃후보.json", "데이터.json")],
    },
    # '5. 뉴스 확인'은 2026-08-17에 여기서 뺐다. 옆 프로젝트 [1. IT 뉴스 모니터링]과
    # 같은 도구였다(뉴스수집.py 가 상태파일 경로 한 줄만 달랐고 보고서 프롬프트는
    # 바이트까지 같았다). 맥과 윈도우에서 각각 돌아 '확인기록'이 갈라져 같은 기사를
    # 두 번 수집하고 있었다. 기록은 합쳐서 프로젝트 1 쪽에 남겼다.
    # 뉴스는 [1. IT 뉴스 모니터링]에서만 돌린다.
}


# ---------------------------------------------------------------- 도우미

class ToolError(Exception):
    """도구 하나를 멈추는 오류. '한번에 돌리기'에서는 다음 도구로 넘어간다."""

    def __init__(self, *msgs):
        super().__init__("\n".join(msgs))
        self.msgs = msgs


def die(*msg):
    raise ToolError(*msg)


def pause():
    try:
        input("엔터를 누르면 창이 닫힙니다...")
    except EOFError:
        pass


def read_keys(path):
    """api_key.txt 에서 이름=값 을 읽어 딕셔너리로. # 로 시작하는 줄은 설명."""
    got = {}
    if not os.path.isfile(path):
        return got
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            name, _, value = line.partition("=")
            name, value = name.strip(), value.strip().strip('"').strip("'")
            if value:
                got[name] = value
    return got


def ensure_openpyxl():
    """엑셀을 만들려면 openpyxl 이 필요하다. 새 PC에는 없으므로 한 번만 자동으로 깐다."""
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        pass
    print("")
    print("엑셀 만드는 부품(openpyxl)을 설치합니다. 처음 한 번만 하고 1분쯤 걸립니다...")
    rc = subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl"])
    if rc != 0:
        print("")
        print("[알림] 부품 설치에 실패했습니다. 인터넷 연결을 확인해 주세요.")
        print("직접 설치하려면 명령 프롬프트에서:  pip install openpyxl")
        print("분석 결과(리포트.txt, 데이터.json)는 그대로 저장돼 있습니다.")
        return False
    return True


def check_keys(cfg, env):
    """필요한 키가 다 있는지. 없으면 어느 앱 키인지까지 짚어준다."""
    got = read_keys(KEYFILE)
    if not got:
        die("[오류] 3_설정 폴더에 api_key.txt 가 없거나 비어 있습니다.",
            "위치: %s" % KEYFILE)

    # 예전 이름 한 벌만 넣어둔 경우를 받아준다
    if got.get("NCP_APIGW_API_KEY_ID") and not got.get("SEARCH_KEY_ID"):
        got["SEARCH_KEY_ID"] = got["NCP_APIGW_API_KEY_ID"]
        got["SEARCH_KEY"] = got.get("NCP_APIGW_API_KEY", "")

    missing = []
    if "search" in cfg["needs"]:
        missing += [k for k in SEARCH_KEYS if not got.get(k)]
    if "trend" in cfg["needs"]:
        missing += [k for k in TREND_KEYS if not got.get(k)]
    if missing:
        die("[오류] api_key.txt 안에 키가 비어 있습니다.",
            "채워야 할 것: " + ", ".join(missing),
            "",
            "SEARCH_* 는 keyword-analyzer 앱, TREND_* 는 trend-analyzer 앱 키입니다.",
            "두 앱은 인증키가 서로 다릅니다. 섞으면 401 오류가 납니다.",
            "",
            "파일 위치: %s" % KEYFILE)
    env.update(got)


# ---------------------------------------------------------------- 실행

RUN_ALL = "전부돌리기"
RUN_ALL_ORDER = ["키워드발굴", "제목진단", "성과추적", "이웃발굴"]

# .bat 은 순수 영문(ASCII)으로만 쓴다는 규칙 때문에 한글 도구이름을 인자로 넘길 수
# 없다. 그래서 영문 별명을 둔다. 한글 이름도 그대로 받는다(직접 돌릴 때 편하라고).
ALIASES = {
    "dashboard": "전체보기",
    "keywords": "키워드발굴",
    "titles": "제목진단",
    "track": "성과추적",
    "neighbors": "이웃발굴",
    "all": RUN_ALL,
}


def find_opener():
    """맨 위 폴더의 .claude/scripts/open_on_monitor.ps1 을 찾는다. 없으면 None.

    모니터를 고르고 창을 배치하는 로직은 그 .ps1 한 곳에만 있다. 여기서 하는 건
    '찾아서 부르기' 뿐이다. 도구모음을 다른 데로 통째로 옮기면 못 찾을 텐데,
    그때는 예전처럼 기본 브라우저로 열린다 — 결과가 안 열리는 것보다는 낫다.
    """
    here = ROOT
    for _ in range(4):
        cand = os.path.join(here, ".claude", "scripts", "open_on_monitor.ps1")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def open_path(target, place=False):
    """결과를 연다.

    place=True 면 보조 모니터에 앱 창으로 띄운다(대시보드처럼 '완성본'인 경우).
    폴더를 열 때는 place=False — 탐색기 창까지 옮기지는 않는다.
    """
    if place and sys.platform == "win32":
        ps1 = find_opener()
        if ps1:
            try:
                rc = subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy",
                                      "Bypass", "-File", ps1, "-File", target])
                if rc == 0:
                    return
            except OSError:
                pass
    try:
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.call(["open", target])
    except Exception:
        pass


def run_tool(name, open_files=True):
    """도구 하나를 돌린다. open_files=False 면(한번에 돌리기) 폴더 창을 열지 않는다."""
    cfg = TOOLS[name]

    program = os.path.join(PROGRAMS, cfg["program"])
    if not os.path.isfile(program):
        die("[오류] 프로그램을 찾을 수 없습니다.",
            "4_건드리지마세요 폴더의 %s 가 사라졌거나 옮겨졌습니다." % cfg["program"])

    for f in cfg["inputs"]:
        path = os.path.join(SETTINGS, f)
        if not os.path.isfile(path):
            die("[오류] %s 파일이 없습니다." % f,
                "3_설정 폴더 안에 있어야 합니다: %s" % path)

    env = dict(os.environ)
    env["PYTHONPATH"] = PROGRAMS + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"      # 윈도우 콘솔에서 한글이 깨지지 않게
    if cfg["needs"]:
        check_keys(cfg, env)

    # 결과 폴더도 리포트도 만들지 않는 도구(대시보드). 그냥 돌리고 결과만 연다.
    if cfg.get("simple"):
        print("")
        print("%s 을(를) 시작합니다..." % cfg["label"])
        rc = subprocess.call([sys.executable, program], env=env, cwd=PROGRAMS)
        # 파일을 여는 건 여기 한 곳에서만 한다. 프로그램 쪽에서도 열면 두 번 뜬다.
        target = os.path.join(RESULTS, cfg.get("opens", ""))
        if rc == 0 and cfg.get("opens") and os.path.isfile(target):
            open_path(target, place=True)      # 대시보드는 보조 모니터로
        return

    now = datetime.now()
    day_dir = os.path.join(RESULTS, cfg["label"],
                           now.strftime("%Y-%m-%d"), now.strftime("%H시%M분"))
    os.makedirs(day_dir, exist_ok=True)

    args = []
    for a in cfg["args"]:
        if a.startswith("{IN:"):
            args.append(os.path.join(SETTINGS, a[4:-1]))
        else:
            args.append(a.replace("{DAY}", day_dir))

    print("")
    print("%s 을(를) 시작합니다. 잠시 걸립니다..." % cfg["label"])
    print("저장 위치: %s" % os.path.relpath(day_dir, ROOT))
    print("")

    report = os.path.join(day_dir, "리포트.txt")
    # 진행 표시는 stderr 로 나온다. 합치면 리포트.txt 맨 앞이 '1/19 묶음...'
    # 으로 도배된다. stderr 는 화면에만 흐르게 둔다.
    proc = subprocess.Popen([sys.executable, program] + args, env=env,
                            cwd=PROGRAMS, stdout=subprocess.PIPE)
    with open(report, "w", encoding="utf-8") as out:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace")
            sys.stdout.write(line)
            sys.stdout.flush()
            out.write(line)
    status = proc.wait()

    if status != 0:
        die("[오류] 실행 중 문제가 생겼습니다.",
            "위에 찍힌 메시지를 그대로 복사해서 물어보시면 됩니다.")

    for src, dst in cfg["renames"]:
        s = os.path.join(day_dir, src)
        if os.path.isfile(s):
            os.replace(s, os.path.join(day_dir, dst))

    if cfg["excel"]:
        excel = os.path.join(PROGRAMS, cfg["excel"])
        if os.path.isfile(excel) and ensure_openpyxl():
            print("")
            print("엑셀 리포트를 만드는 중...")
            subprocess.call([sys.executable, excel, day_dir], env=env, cwd=PROGRAMS)

    print("")
    print("=" * 46)
    print(" 끝났습니다.")
    print(" %s 폴더에 저장됐습니다." % os.path.relpath(day_dir, ROOT))
    for line in cfg.get("after", ()):
        print(" " + line)
    print("=" * 46)
    print("")

    if open_files:
        open_path(day_dir)


def run_all():
    """1~4번을 차례로 전부 돌리고, 맨 끝에 대시보드를 새로 그려서 연다.

    중간에 하나가 실패해도 멈추지 않고 다음 도구로 넘어간다. 결과는 도구별로
    평소처럼 저장되지만, 폴더 창을 네 번 열지 않고 대시보드 하나만 연다.
    """
    print("")
    print("도구 네 개를 차례로 전부 돌립니다. 다 하면 10~20분쯤 걸립니다.")
    print("켜 두고 다른 일을 하셔도 됩니다.")

    failed = []
    for i, name in enumerate(RUN_ALL_ORDER, 1):
        label = TOOLS[name]["label"]
        print("")
        print("━" * 46)
        print(" (%d/%d) %s" % (i, len(RUN_ALL_ORDER), label))
        print("━" * 46)
        try:
            run_tool(name, open_files=False)
        except ToolError as e:
            print("")
            for m in e.msgs:
                print(m)
            failed.append(label)

    print("")
    print("━" * 46)
    print(" 마지막으로 대시보드를 새로 그립니다...")
    print("━" * 46)
    try:
        run_tool("전체보기", open_files=True)
    except ToolError as e:
        print("")
        for m in e.msgs:
            print(m)
        failed.append(TOOLS["전체보기"]["label"])

    print("")
    print("=" * 46)
    if failed:
        print(" 끝났습니다. 다만 이것들은 실패했습니다:")
        for label in failed:
            print("   · " + label)
        print(" 위로 올려 실패한 곳의 메시지를 복사해서")
        print(" Claude 에게 물어보시면 됩니다.")
    else:
        print(" 네 개 전부 끝났습니다. 대시보드를 열었습니다.")
    print("=" * 46)
    print("")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    arg = ALIASES.get(arg, arg)
    try:
        if arg == RUN_ALL:
            run_all()
        elif arg in TOOLS:
            run_tool(arg)
        else:
            die("[오류] 실행할 도구를 알 수 없습니다.",
                "쓸 수 있는 이름: " + ", ".join(list(ALIASES)),
                "또는 한글 이름: " + ", ".join(list(TOOLS) + [RUN_ALL]))
    except ToolError as e:
        print("")
        for m in e.msgs:
            print(m)
        print("")
        pause()
        sys.exit(1)
    pause()


if __name__ == "__main__":
    main()
