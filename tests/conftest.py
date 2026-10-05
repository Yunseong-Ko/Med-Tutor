"""테스트 공통 격리 — 로컬에만 있는 과별 교과서(data_private/textbooks)를 테스트가 읽지 않게 한다(T-TBX-01).

기본값으로 존재하지 않는 경로를 가리키므로 개발 PC와 CI/배포 환경의 결과가 같다.
과별 교과서 발췌를 검사하는 테스트는 합성 픽스처 디렉터리로 환경변수를 다시 지정한다.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_local_textbooks(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PACCINE_TEXTBOOKS_DIR", str(tmp_path_factory.getbasetemp() / "_no_textbooks"))
    yield
