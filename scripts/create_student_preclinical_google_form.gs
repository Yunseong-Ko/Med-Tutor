const STUDENT_FORM_TITLE = '부산대학교 의과대학 본1·본2 내신 준비 학습지원 수요조사';
const STUDENT_FORM_DESCRIPTION = [
  '안녕하세요. 본 설문은 부산대학교 RISE 사업 준비를 위해 본과 1학년, 본과 2학년 학생들의 내신 준비 경험과 학습 페인포인트를 파악하기 위한 조사입니다.',
  '',
  '이번 설문은 국가고시 준비가 아니라 본1·본2 내신 준비 경험을 기준으로 답해주시면 됩니다.',
  '응답 시간은 약 6~8분이며, 응답 내용은 학습지원 기능 기획과 파일럿 설계에만 활용됩니다.',
  '이름은 필수가 아니며, 원하실 경우 익명으로 응답하실 수 있습니다.',
].join('\n');

const STUDENT_CONFIRMATION_MESSAGE =
  '응답해 주셔서 감사합니다. 주신 의견은 의과대학 학생용 AI 학습지원 기능과 파일럿 설계에 반영하겠습니다.';

function createStudentPreclinicalGoogleForm() {
  const form = FormApp.create(STUDENT_FORM_TITLE);
  form.setDescription(STUDENT_FORM_DESCRIPTION);
  form.setConfirmationMessage(STUDENT_CONFIRMATION_MESSAGE);
  form.setProgressBar(true);
  form.setShuffleQuestions(false);
  form.setCollectEmail(false);
  form.setAllowResponseEdits(true);

  addStudentIntroSection(form);
  addStudentStudyWorkflowSection(form);
  addStudentPainpointSection(form);
  addStudentQuestionAndExplanationSection(form);
  addStudentAIAndAdoptionSection(form);
  addStudentPilotSection(form);

  Logger.log('Note: "Limit to 1 response" is not exposed by FormApp. If you need it, enable it manually in Form settings.');
  Logger.log('Edit URL: ' + form.getEditUrl());
  Logger.log('Respond URL: ' + form.getPublishedUrl());
}

function addStudentIntroSection(form) {
  form.addSectionHeaderItem()
    .setTitle('1. 기본 정보')
    .setHelpText('본1·본2 내신 준비 맥락을 파악하기 위한 기본 문항입니다.');

  form.addMultipleChoiceItem()
    .setTitle('현재 학년을 선택해 주세요.')
    .setRequired(true)
    .setChoiceValues([
      '본과 1학년',
      '본과 2학년',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('현재 기준으로 내신 준비 부담은 어느 정도인가요?')
    .setRequired(true)
    .setChoiceValues([
      '매우 높다',
      '높다',
      '보통이다',
      '낮다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('체감상 시험 또는 평가가 어느 정도 간격으로 있다고 느끼나요?')
    .setRequired(true)
    .setChoiceValues([
      '거의 매주 있다',
      '대체로 2주 간격이다',
      '3~4주 간격이다',
      '시기마다 크게 다르다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('ChatGPT, Claude, Gemini 같은 AI 도구를 공부에 사용해 본 적이 있나요?')
    .setRequired(true)
    .setChoiceValues([
      '자주 사용한다',
      '가끔 사용한다',
      '들어봤지만 거의 사용하지 않는다',
      '사용해본 적 없다',
    ]);

  form.addTextItem()
    .setTitle('후속 인터뷰가 가능하다면 연락받을 이름/이메일을 적어주세요. (선택)')
    .setRequired(false);
}

function addStudentStudyWorkflowSection(form) {
  form.addPageBreakItem()
    .setTitle('2. 현재 내신 준비 방식')
    .setHelpText('학생들이 실제로 어떤 자료와 방식으로 공부하는지 확인합니다.');

  form.addCheckboxItem()
    .setTitle('시험 준비 시 주로 보는 자료를 선택해 주세요. (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '강의 PPT',
      '강의 녹화/수업자료',
      '개인 필기',
      '동기/선배 정리노트',
      '교과서',
      '기출문항/복원문항',
      '문제집 또는 외부 자료',
      'AI 요약/질문 도구',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('시험 준비에서 가장 시간이 많이 드는 단계는 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '강의자료 정리',
      '암기 포인트 추리기',
      '개념 간 연결 이해',
      '기출문항 정리',
      '오답 정리',
      '시험 범위 우선순위 정하기',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('시험 직전 가장 불안한 지점은 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '범위가 너무 많아서 무엇을 봐야 할지 모르겠다',
      '교수님이 어디를 중요하게 보는지 모르겠다',
      '암기는 했는데 응용 문제가 어렵다',
      '오답을 왜 틀렸는지 정리되지 않는다',
      '시간이 부족해 반복 복습이 안 된다',
      '기타',
    ]);

  form.addScaleItem()
    .setTitle('강의자료, 필기, 기출문항, 개념정리가 여러 곳에 흩어져 있어 불편한 정도는 어느 정도인가요?')
    .setBounds(1, 5)
    .setLabels('거의 불편하지 않다', '매우 불편하다')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('현재 본인만의 내신 공부 루틴이 있다면 간단히 적어주세요. (선택)')
    .setRequired(false);
}

function addStudentPainpointSection(form) {
  form.addPageBreakItem()
    .setTitle('3. 학생 페인포인트')
    .setHelpText('내신 준비에서 어떤 어려움이 가장 큰지 확인합니다.');

  form.addGridItem()
    .setTitle('아래 항목이 얼마나 큰 부담인지 선택해 주세요.')
    .setRequired(true)
    .setRows([
      '시험 범위가 너무 넓다',
      '교수별 출제 스타일 파악이 어렵다',
      '기출문항 정리가 어렵다',
      '강의자료 핵심 포인트 추리기가 어렵다',
      '오답 이유를 이해하기 어렵다',
      '모르는 용어를 찾는 데 시간이 많이 든다',
      '비슷한 개념끼리 헷갈린다',
      '반복 복습 시간이 부족하다',
      '이미지/표/도식 문제 해석이 어렵다',
    ])
    .setColumns([
      '1 거의 아니다',
      '2',
      '3 보통',
      '4',
      '5 매우 그렇다',
    ]);

  form.addCheckboxItem()
    .setTitle('AI가 가장 먼저 도와주면 좋겠는 기능을 선택해 주세요. (최대 3개 권장)')
    .setRequired(true)
    .setChoiceValues([
      '시험 범위 핵심 요약',
      '교수 스타일 기반 예상문항',
      '기출문항 정리 및 묶기',
      '정답/오답 해설 강화',
      '모르는 용어 즉시 설명',
      '관련 개념/노트 자동 연결',
      '비슷한 문제 추천',
      '취약 단원 자동 정리',
      '복습 스케줄 추천',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('지금 가장 아쉬운 것은 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '문항 수는 있는데 해설이 약하다',
      '자료는 많은데 정리가 안 된다',
      '기출은 있는데 유형 분석이 안 된다',
      '개념은 아는데 시험형 문제로 연결이 안 된다',
      '공부 시간이 절대적으로 부족하다',
      '기타',
    ]);

  form.addParagraphTextItem()
    .setTitle('시험 준비 중 "이것만 바로 해결되면 좋겠다" 싶은 불편을 적어주세요. (선택)')
    .setRequired(false);
}

function addStudentQuestionAndExplanationSection(form) {
  form.addPageBreakItem()
    .setTitle('4. 문항·해설·개념 연결')
    .setHelpText('문항 생성보다 어떤 학습지원이 더 중요한지 확인합니다.');

  form.addMultipleChoiceItem()
    .setTitle('학생 입장에서 더 중요한 것은 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '더 많은 예상문항',
      '더 좋은 해설',
      '관련 개념으로 바로 이어지는 기능',
      '기출문항 정리와 분류',
      '취약점 분석과 복습 추천',
    ]);

  form.addCheckboxItem()
    .setTitle('좋은 해설에는 어떤 요소가 꼭 필요하다고 생각하나요? (복수 선택 가능)')
    .setRequired(true)
    .setChoiceValues([
      '정답 근거를 명확히 설명',
      '오답 선지가 왜 틀렸는지 비교',
      '관련 개념을 함께 정리',
      '강의 슬라이드/노트 위치 연결',
      '비슷한 문제 추천',
      '암기 포인트 한 줄 요약',
      '기타',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('문제를 풀다가 모르는 용어를 누르면 바로 개념 설명이 뜨는 기능이 있다면 어떨 것 같나요?')
    .setRequired(true)
    .setChoiceValues([
      '매우 유용할 것 같다',
      '어느 정도 유용할 것 같다',
      '있으면 좋지만 필수는 아니다',
      '오히려 집중을 방해할 수 있다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('가장 써보고 싶은 기능 하나를 고른다면 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '교수 스타일 기반 예상문항 생성',
      '오답 개념 자동 정리',
      '비슷한 문제 추천',
      '개념/용어 즉시 설명 패널',
      '강의노트와 문제 연결 그래프',
      '시험 전 핵심 포인트 요약',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('Obsidian처럼 개념과 노트를 연결해 주는 기능이 있다면 사용할 것 같나요?')
    .setRequired(true)
    .setChoiceValues([
      '매우 사용할 것 같다',
      '어느 정도 사용할 것 같다',
      '상황에 따라 다를 것 같다',
      '거의 사용하지 않을 것 같다',
    ]);
}

function addStudentAIAndAdoptionSection(form) {
  form.addPageBreakItem()
    .setTitle('5. AI 활용 수용성')
    .setHelpText('학생이 실제로 안심하고 쓸 수 있는 조건을 확인합니다.');

  form.addGridItem()
    .setTitle('아래 조건이 얼마나 중요한지 선택해 주세요.')
    .setRequired(true)
    .setRows([
      '해설 정확도',
      '교수 수업자료 반영 정도',
      '기출문항 스타일 반영',
      '빠른 검색/즉시 설명',
      '사용 편의성',
      '개인정보/학습기록 보호',
    ])
    .setColumns([
      '1 낮음',
      '2',
      '3 보통',
      '4',
      '5 매우 중요',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('AI가 만든 예상문항을 사용할 때 가장 걱정되는 점은 무엇인가요?')
    .setRequired(true)
    .setChoiceValues([
      '실제 시험과 동떨어질까 봐 걱정된다',
      '해설이 부정확할까 봐 걱정된다',
      '오히려 공부 범위가 더 넓어질까 봐 걱정된다',
      '시간만 쓰고 효율이 낮을까 봐 걱정된다',
      '개인정보나 학습기록이 걱정된다',
      '특별한 걱정은 없다',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('학교 단위 학습지원 도구가 생긴다면 어느 방식이 가장 좋을 것 같나요?')
    .setRequired(true)
    .setChoiceValues([
      '웹에서 바로 문제 풀이와 해설 보기',
      '강의자료 기반 요약과 예상문항 보기',
      '오답노트와 취약 단원 추천 중심',
      '개념 검색과 노트 연결 중심',
      '상황에 따라 조합해서 쓰고 싶다',
    ]);

  form.addParagraphTextItem()
    .setTitle('AI 학습도구를 쓸 때 꼭 지켜졌으면 하는 조건이 있다면 적어주세요. (선택)')
    .setRequired(false);
}

function addStudentPilotSection(form) {
  form.addPageBreakItem()
    .setTitle('6. 파일럿 제안')
    .setHelpText('실제 파일럿 설계에 참고하기 위한 마지막 문항입니다.');

  form.addParagraphTextItem()
    .setTitle('파일럿 과목으로 잘 맞을 것 같은 과목이나 상황이 있다면 적어주세요. (선택)')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('이 도구에 꼭 들어가야 할 기능 1가지를 적어주세요.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('있으면 좋아 보여도 실제로는 잘 안 쓸 것 같은 기능이 있다면 적어주세요. (선택)')
    .setRequired(false);
}
