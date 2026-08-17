#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""영문 이름 진입점 — .bat 이 부르는 파일.

.bat 은 순수 영문(ASCII)으로만 쓴다는 규칙이 있다(0_문서색인.md 참고).
한글이 든 배치 파일을 cmd 가 잘못 읽어 엉뚱한 줄을 실행하는 일이 있었기 때문이다.
그래서 .bat 안에는 '공용' 같은 한글 폴더 이름을 적을 수 없다.

이 파일이 그 사이를 메운다. 이름이 영문이라 .bat 에서 부를 수 있고,
여기서 한글 경로를 파이썬으로 이어붙여 진짜 실행기(공용/runner.py)를 부른다.

    python run.py keywords      1. 키워드 발굴
    python run.py titles        2. 제목 진단
    python run.py track         3. 성과 추적
    python run.py neighbors     4. 이웃 발굴
    python run.py dashboard     0. 전체 보기
    python run.py all           5. 한번에 돌리기
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "공용"))

import runner  # noqa: E402

if __name__ == "__main__":
    runner.main()
