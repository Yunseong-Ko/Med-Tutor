from pathlib import Path

from src.services.medlegal_emr_importer import deidentify_emr_text, import_emr_text_to_case, parse_emr_records


def test_deidentify_emr_text_removes_core_identifiers():
    raw = """
123456789
등록번호 : 123456789
환자성명 : 홍길동
주치의:김의사
최초작성 : 박작성  2026-04-21 13:47
집도의
1 : 최집도
영양사성명 : 이영양
Ahrong Kim MD
외과 옥선호 올림
씨젠의료재단, DS2026-22708
010-1234-5678
주안이레평안 고모
"""

    cleaned = deidentify_emr_text(raw)

    assert "123456789" not in cleaned
    assert "홍길동" not in cleaned
    assert "김의사" not in cleaned
    assert "박작성" not in cleaned
    assert "최집도" not in cleaned
    assert "이영양" not in cleaned
    assert "Ahrong Kim MD" not in cleaned
    assert "옥선호" not in cleaned
    assert "DS2026-22708" not in cleaned
    assert "010-1234-5678" not in cleaned
    assert "주안이레평안" not in cleaned
    assert "[REDACTED_NAME]" in cleaned


def test_parse_emr_records_splits_tab_timestamp_headers():
    raw = """
외래초진기록-Freetext\t2026-03-17 10:11
[외래]진료일:2026-03-17 진료과:외과 주치의:김의사 [신환]
주호소
수술 전 평가

협진기록\t2026-03-17 11:48
[외래]진료일:2026-03-17 진료과:외과 주치의:김의사 [신환]
의뢰내용
협진 의뢰
"""

    records = parse_emr_records(raw)

    assert len(records) == 2
    assert records[0]["note_type"] == "outpatient_initial"
    assert records[0]["care_setting"] == "외래"
    assert records[1]["note_type"] == "consult"
    assert records[1]["relative_day"] == "D+0"
    assert "김의사" not in records[0]["deidentified_text"]


def test_import_emr_text_to_case_creates_deidentified_case():
    raw = """
입원기록(pnuh)-외과(기본)\t2026-04-21 16:00
[입원]2026/04/21~재원중 진료과:외과 주치의:김의사
계획
질환상태, 치료계획, 치료에 따른 예상효과 및 위험에 대해 교육함

수술기록-외과\t2026-04-22 15:30 수술:2026-04-22
[입원]2026/04/21~재원중 진료과:외과 주치의:김의사
수술요약
Complications : N

입퇴원요약기록(pnuh)-외과(기본)\t2026-04-27 09:22
[입원]2026/04/21 ~ 2026/04/28 진료과:외과 주치의:김의사
추후계획
opd f.u
"""

    result = {}
    try:
        result = import_emr_text_to_case(
            raw,
            source_name="synthetic.txt",
            case_id="unit_surgical_case",
            title="합성 수술 기록 케이스",
        )

        assert result["record_count"] == 3
        assert result["case"]["deidentified"] is True
        assert result["case"]["track"] == "surgical_medlegal"
        assert "operative_note" in result["note_types"]
        assert "discharge_summary" in result["note_types"]
    finally:
        for path in (result.get("paths") or {}).values():
            Path(path).unlink(missing_ok=True)
