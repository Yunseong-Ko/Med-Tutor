const FORM_TITLE = '부산대학교 의과대학 교수·조교 AI 문항개발/학습지원 수요조사';
const FORM_DESCRIPTION = [
  '안녕하세요. 본 설문은 부산대학교 RISE 사업 준비를 위해 의과대학 교수·조교의 문항 제작, 검수, 배포, 학습지원 관련 실제 페인포인트를 파악하기 위한 조사입니다.',
  '',
  '응답 시간은 약 7~10분이며, 응답 내용은 과제 기획 및 파일럿 설계에만 활용됩니다.',
  '개인 식별이 필요한 정보는 필수가 아니며, 원하실 경우 익명으로 응답하실 수 있습니다.',
].join('\n');

const CONFIRMATION_MESSAGE =
  '응답해 주셔서 감사합니다. 주신 의견은 교수용 AI 문항개발·배포 플랫폼 기획과 파일럿 설계에 반영하겠습니다.';

function createProfessorPainpointGoogleForm() {
  const form = FormApp.create(FORM_TITLE);
  form.setDescription(FORM_DESCRIPTION);
  form.setConfirmationMessage(CONFIRMATION_MESSAGE);
  form.setProgressBar(true);
  form.setShuffleQuestions(false);
  form.setCollectEmail(false);
  form.setAllowResponseEdits(true);

  addIntroSection(form);
  addCurrentWorkflowSection(form);
  addPainpointSection(form);
  addReferenceAndStyleSection(form);
  addStudentLearningSection(form);
  addAdoptionSection(form);

  Logger.log('Note: "Limit to 1 response" is not exposed by FormApp. If you need it, enable it manually in Form settings.');
  Logger.log('Edit URL: ' + form.getEditUrl());
  Logger.log('Respond URL: ' + form.getPublishedUrl());
}

function addIntroSection(form) {
  form.addSectionHeaderItem()
    .setTitle('1. 기본 정보')
    .setHelpText('응답자 기본 맥락을 파악하기 위한 문항입니다.');

  form.addMultipleChoiceItem()
    .setTitle('현재 역할을 선택해 주세요.')
    .setRequired(true)
    .setChoiceValues([
      '교수',
      '임상교수',
      '조교',
      '교육담당/행정 지원',
      '기타',
    ]);

  form.addCheckboxItem()
    .setTitle('주로 담당하시는 영역을 선택해 주세요. (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '기초의학',
      '임상의학',
      '통합교육',
      '실습/실기 교육',
      '평가/교육과정 운영',
      '기타',
    ]);

  form.addTextItem()
    .setTitle('담당 과목 또는 블록명을 적어주세요. (선택)')
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('체감상 평가나 시험 준비 주기는 어느 정도인가요?')
    .setRequired(true)
    .setChoiceValues([
      '거의 매주 있다',
      '대체로 2주 간격이다',
      '3~4주 간격이다',
      '월 1회 이하이다',
      '과목/시기마다 크게 다르다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('Claude Code, Codex, ChatGPT 같은 AI 도구를 업무에 써보신 적이 있나요?')
    .setRequired(true)
    .setChoiceValues([
      '자주 사용한다',
      '가끔 사용한다',
      '들어봤지만 거의 사용하지 않는다',
      '사용해본 적 없다',
    ]);

  form.addTextItem()
    .setTitle('후속 인터뷰가 가능하다면 연락받으실 성함/이메일을 적어주세요. (선택)')
    .setRequired(false);
}

function addCurrentWorkflowSection(form) {
  form.addPageBreakItem()
    .setTitle('2. 현재 문항 제작 워크플로우')
    .setHelpText('현재 어떤 자료와 과정으로 문항을 만들고 있는지 확인합니다.');

  form.addCheckboxItem()
    .setTitle('문항 제작 시 주로 사용하는 자료를 선택해 주세요. (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '강의 PPT',
      '강의 PDF/유인물',
      '한글(HWP) 문서',
      '기존 기출문항',
      '기초의학종합평가/임상의학종합평가',
      'USMLE/NBME 스타일 자료',
      '교과서/가이드라인',
      '조교 메모 또는 개인 노트',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('문항은 주로 어떤 방식으로 만드시나요?')
    .setRequired(true)
    .setChoiceValues([
      '대부분 새로 만든다',
      '새 문항과 기존 문항 수정을 반반 정도 한다',
      '기존 기출문항을 수정하는 비중이 더 크다',
      '과목/상황에 따라 크게 다르다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('시험 직전 가장 시간이 오래 걸리는 단계는 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '문항 초안 작성',
      '정답 및 해설 정리',
      '선지 다듬기',
      '이미지/표/도식 문항 구성',
      '검수 및 최종 수정',
      '문항 배포/시험지 정리',
      '기타',
    ]);

  form.addScaleItem()
    .setTitle('이미지, 표, 병리 슬라이드, 방사선 사진 등이 포함된 문항은 얼마나 부담되시나요?')
    .setBounds(1, 5)
    .setLabels('부담이 거의 없다', '매우 부담된다')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('현재 문항 제작 워크플로우를 간단히 적어주세요. (예: 강의자료 정리 -> 기출 참고 -> 문항 작성 -> 조교 검토)')
    .setRequired(false);
}

function addPainpointSection(form) {
  form.addPageBreakItem()
    .setTitle('3. 교수·조교 페인포인트')
    .setHelpText('무엇이 가장 큰 병목인지 확인합니다.');

  form.addGridItem()
    .setTitle('아래 항목이 얼마나 큰 부담인지 선택해 주세요.')
    .setRequired(true)
    .setRows([
      '문항 초안 작성',
      '정답/해설 작성',
      '이미지 문항 만들기',
      '문항 검수',
      '공동출제 조율',
      '학생 배포/시험 세팅',
      '학생 오답/피드백 분석',
    ])
    .setColumns([
      '1 거의 부담 없음',
      '2',
      '3 보통',
      '4',
      '5 매우 부담',
    ]);

  form.addCheckboxItem()
    .setTitle('AI가 가장 먼저 도와주면 좋겠는 작업을 선택해 주세요. (최대 3개 권장)')
    .setRequired(true)
    .setChoiceValues([
      '강의자료에서 출제 포인트 추출',
      '문항 초안 생성',
      '선지 다듬기',
      '정답 및 해설 작성',
      '이미지 자료 정리 및 연결',
      '교수 스타일 반영',
      '검수 대기 큐 정리',
      '학생 배포 세트 만들기',
      '오답 분석 리포트 생성',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('AI가 만든 문항을 바로 쓰기 어려운 가장 큰 이유는 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '정확도가 걱정된다',
      '교수 스타일이 반영되지 않을 것 같다',
      '검수 책임이 부담된다',
      '자료 보안/데이터 통제가 걱정된다',
      '사용법이 번거로울 것 같다',
      '현재 방식으로도 충분하다',
      '기타',
    ]);

  form.addParagraphTextItem()
    .setTitle('업무 중 짧은 빈 시간 5분 안에 해결되면 좋겠는 작업이 있다면 적어주세요.')
    .setRequired(false);
}

function addReferenceAndStyleSection(form) {
  form.addPageBreakItem()
    .setTitle('4. 기출문항과 참고자료 활용')
    .setHelpText('기출과 강의자료를 어떤 옵션으로 활용하는 것이 현실적인지 확인합니다.');

  form.addMultipleChoiceItem()
    .setTitle('문항 생성 시 가장 선호할 참고 근거 조합은 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '강의자료만',
      '강의자료 + 기존 기출문항',
      '강의자료 + 기초/임상의학종합평가 스타일',
      '강의자료 + USMLE 스타일',
      '강의자료 + 교수 개인 스타일',
      '상황에 따라 다르게 선택하고 싶다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('현재 보유한 기출문항은 주로 어떻게 활용하시나요?')
    .setRequired(true)
    .setChoiceValues([
      '그대로 수정해서 사용한다',
      '선지나 표현만 일부 바꾼다',
      '개념만 유지하고 새로 만든다',
      '케이스나 수치만 바꿔 재구성한다',
      '체계적으로 활용하지 못하고 있다',
    ]);

  form.addCheckboxItem()
    .setTitle('교수별 문항 스타일을 분류한다면 어떤 구분이 실제로 유의미할까요? (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '교과서 문장 직인용형',
      '임상 케이스형',
      '짧은 선지형',
      '긴 장문 선지형',
      '약물 선택형',
      '금기증/예외 강조형',
      '함정 선지형',
      '개념 구분형',
      '치료 선택형',
      '검사 선택형',
      '기타',
    ]);

  form.addCheckboxItem()
    .setTitle('생성 옵션으로 꼭 필요할 항목을 선택해 주세요. (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '증례형 vs 개념형',
      '짧은 선지 vs 긴 선지',
      '형성평가형 vs 변별형',
      '한글 우선 vs 영문 우선',
      '약물 선택형 vs 기전 설명형',
      '교수 스타일 강도',
      '난이도',
      '이미지 포함 여부',
      '기타',
    ]);

  form.addParagraphTextItem()
    .setTitle('기출문항을 AI 입력자료로 활용할 때 우려되는 점이 있다면 적어주세요.')
    .setRequired(false);
}

function addStudentLearningSection(form) {
  form.addPageBreakItem()
    .setTitle('5. 학생 학습지원 기능')
    .setHelpText('학생에게 실제로 도움이 되는 기능의 우선순위를 파악합니다.');

  form.addMultipleChoiceItem()
    .setTitle('학생에게 더 중요한 것은 무엇이라고 생각하시나요?')
    .setRequired(true)
    .setChoiceValues([
      '더 많은 문제 수',
      '더 좋은 해설 품질',
      '관련 개념으로 바로 이어지는 기능',
      '비슷한 문제 추천',
      '오답 기반 취약 단원 정리',
    ]);

  form.addCheckboxItem()
    .setTitle('해설에 꼭 포함되어야 할 요소를 선택해 주세요. (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '정답 근거',
      '오답 선지 비교',
      '관련 개념 링크',
      '강의 슬라이드 또는 노트 연결',
      '추가 참고 문제 추천',
      '시험 포인트 요약',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('문제 풀이 중 모르는 용어나 개념을 바로 확인할 수 있는 패널이 있다면 도움이 될까요?')
    .setRequired(true)
    .setChoiceValues([
      '매우 도움이 될 것 같다',
      '어느 정도 도움이 될 것 같다',
      '있으면 좋지만 필수는 아니다',
      '오히려 방해될 수 있다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('학생용 기능 중 가장 우선순위가 높은 것은 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '오답 개념 재학습',
      '비슷한 문제 자동 추천',
      '관련 슬라이드/노트 바로 열기',
      '단원별 취약점 리포트',
      '개념 그래프/노트 연결',
    ]);

  form.addParagraphTextItem()
    .setTitle('학생용 기능 중 있으면 좋아 보여도 실제로는 잘 안 쓸 것 같은 기능이 있다면 적어주세요.')
    .setRequired(false);
}

function addAdoptionSection(form) {
  form.addPageBreakItem()
    .setTitle('6. 도입 조건과 파일럿 제안')
    .setHelpText('도입 가능성과 파일럿 운영 조건을 확인합니다.');

  form.addGridItem()
    .setTitle('학교 단위 도입 시 아래 조건이 얼마나 중요한지 선택해 주세요.')
    .setRequired(true)
    .setRows([
      '정확도',
      '보안/데이터 통제',
      '검수 가능성',
      '시간 절감',
      '비용',
      '사용 편의성',
    ])
    .setColumns([
      '1 낮음',
      '2',
      '3 보통',
      '4',
      '5 매우 중요',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('교수 검수를 전제로 할 때, AI 활용은 어디까지 가능하다고 보시나요?')
    .setRequired(true)
    .setChoiceValues([
      '형성평가용 연습문제까지만',
      '비공식 학습자료까지',
      '교수 검수 후 정규 시험 일부까지',
      '아직 판단이 어렵다',
    ]);

  form.addParagraphTextItem()
    .setTitle('파일럿 과목으로 적합하다고 생각하는 과목 또는 운영 상황을 적어주세요.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('이 플랫폼에 꼭 들어가야 할 기능 1가지를 적어주세요.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('실제 도입 시 가장 걱정되는 점을 적어주세요.')
    .setRequired(false);
}
