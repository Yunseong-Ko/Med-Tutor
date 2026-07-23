# PMA 70문항 보강 API 계약

적용 세트: `임상종합평가 · 2025 B군 1교시` 70문항

목적은 향후 학생 UIUX를 교체하더라도 문항·해설·Ontology·Anki·제시자료 연결을 다시 만들지 않고 동일 API 응답을 그대로 재사용하는 것이다.

## 제출 전

`GET /api/student/qbank`

- 제공: `id`, 시험/과목/주제 메타데이터, `stem`, `stimulus`, 공개 선지의 `n`·`text`, `imgs`, `practice_ready`, `media_requirement`
- 금지: `answer`, `explanation`, `choice_explanations`, `points`, `concept_id`, `target_axis_type`, `anki_cards`, `evidence`
- `imgs`는 실제 연결이 확인된 자료만 제공한다.
- 원본 이미지가 없지만 필요한 시각 소견이 지문에 완전히 기술된 문항은 `media_requirement=described_in_stem`으로 표시한다.

## 답안 제출 후

`POST /api/student/questions/{question_id}/answer`

기본 응답에 다음 보강 필드를 제공한다.

- 해설: `explanation`, `choice_explanations`, `points`
- Ontology: `concept_id`, `concept_label`, `concept_registry_status`
- 10-Axis: `target_axis_type`, `target_axis_label`, `target_axis_ids`, `target_axis_resolution`
- 복습: `anki_cards`
- 자료: `connected_media`, `media_requirement_satisfied_by_text`
- 출처: `evidence`
- 검수 상태: `enrichment_release`, `enrichment_needs_review`, `ontology_analytics_approved`

`evidence`의 Harrison 항목은 원문 인용이 아니라 위치 안내다. `support_scope=chapter_pointer_not_claim_entailment`이면 UI에 “Harrison 위치 안내 · 문장 단위 인용 검증 전”으로 표시한다. `segment_text`는 API와 Overlay 어디에도 포함하지 않는다.

## UI 재연결 기준

- Reader의 해설·출제 포인트·검사자료·개념노트·Anki 탭은 위 필드만 소비한다.
- UI는 Overlay 파일을 직접 읽지 않고 API만 호출한다.
- `release_mode=owner_curated_demo`인 경우 “시연용 검수 콘텐츠 · 실제 교수 의학 검수 대기”를 표시한다.
- 실제 교수 승인 후에도 필드 구조는 그대로 유지되고 `release_mode=faculty_approved`, `medical_approval=true`로 상태만 바뀐다.
- 새 UIUX는 `/student/reader.html`을 대체할 수 있지만 위 제출 전/후 노출 경계는 변경하지 않는다.

## 현재 완성도

- 해설·선지풀이·10-Axis·개념·Anki: 70/70
- 실제 제시자료: 40개
- 지문 기술로 충족된 시각 문항: 2개
- 학생 풀이 가능: 70/70
- 실제 교수 의학 승인: 별도 대기(시연 콘텐츠와 구분)
