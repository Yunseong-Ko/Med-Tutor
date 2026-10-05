/**
 * AI 생성 문항 검토용 구글폼 자동 생성 (Apps Script)
 *
 * 사용법: script.google.com → 새 프로젝트 → 이 파일 전체 붙여넣기 → 저장
 *   - 폼 2개(문항별 검토 + 종합 설문) 모두: 상단 함수 buildForms 선택 → 실행
 *   - 종합 설문만: buildSurveyOnly 선택 → 실행
 *   → 권한 승인 → 실행 로그에 학생 배포용 링크 출력 (응답 시트의 '링크' 탭에도 기록)
 *
 * 폼1 (문항별 검토): 1문항 검토 = 1회 제출. 제출 후 "다른 응답 제출"로 반복.
 *   교수님 검토표(xlsx) 항목 그대로 — 3개 평가항목 1~5점, 종합판정 4단계, 의견.
 * 폼2 (종합 설문): 검토 전부 끝낸 뒤 1인 1회. 9문항 Likert + 종합 의견(개방형).
 *
 * 폼에는 문항 본문이 들어가지 않는다(번호만) — 해설집 docx를 보며 응답.
 * 집계: 응답 시트 탭별 CSV 다운로드 → scripts/aggregate_gform_csv.py
 */

var STUDENTS = [];
for (var i = 1; i <= 31; i++) STUDENTS.push('학생 ' + ('0' + i).slice(-2));

var VERDICTS = ['수정없이 사용', '소폭 수정하여 사용', '대폭 수정 필요', '사용 불가'];

var SCALE_NOTE = '1점=전혀 그렇지 않다 · 2점=그렇지 않다 · 3점=보통이다 · 4점=그렇다 · 5점=매우 그렇다';

var SURVEY_ITEMS = [
  ['안면타당도', '전체적으로 볼 때, 검토한 문항들은 임상종합평가 문항으로 적절해 보였다.'],
  ['내용 포괄성', '검토한 문항들은 의과대학생이 임상종합평가에서 알아야 할 중요한 임상 지식과 내용을 적절히 포함하고 있었다.'],
  ['임상적 관련성', '문항에서 제시된 상황과 질문은 실제 임상 상황과 관련성이 높았다.'],
  ['임상추론 평가 적절성', '문항들은 단순한 지식 암기뿐 아니라 임상 상황을 해석하고 판단하는 능력을 평가하는 데 적절했다.'],
  ['난이도 적절성', '문항의 전반적인 난이도는 의과대학생의 임상종합평가 수준에 적절했다.'],
  ['문항 완성도', '문항줄기와 선택지는 전반적으로 명확하고 완성도가 높아 질문의 의도를 이해하기 쉬웠다.'],
  ['정답·해설의 교육적 유용성', '제시된 정답과 해설은 정답의 근거를 이해하고 관련 내용을 학습하는 데 도움이 되었다.'],
  ['평가도구 활용 가능성', '검토한 문항들은 수정·보완을 거친다면 실제 임상종합평가에 활용할 수 있는 수준이라고 생각한다.'],
  ['학습도구 활용 가능성', '이러한 AI 생성 문항은 임상종합평가 준비를 위한 학습 및 자가점검에 도움이 될 것이라고 생각한다.'],
];

/** 폼1: 문항별 검토 (1문항 = 1회 제출) */
function makeReviewForm(ss) {
  var f = FormApp.create('AI 생성 필기문항 검토 (문항별)');
  f.setDescription(
    '배정받은 문항 1개를 검토할 때마다 1회 제출합니다.\n' +
    '해설집(문항해설 docx)을 보면서 응답해 주세요. 제출 후 "다른 응답 제출"을 눌러 다음 문항을 이어서 검토합니다.\n' +
    '의학적 검수 전 AI 생성물 · 외부 배포 금지'
  );
  f.setCollectEmail(false);
  f.setLimitOneResponsePerUser(false);
  f.setConfirmationMessage('저장되었습니다. 다음 문항은 "다른 응답 제출"을 눌러 계속해 주세요.');

  f.addListItem().setTitle('검토자 번호').setChoiceValues(STUDENTS).setRequired(true);
  f.addTextItem().setTitle('문항 번호')
    .setHelpText('해설집에 표시된 전역 번호(1~320)')
    .setValidation(FormApp.createTextValidation().requireNumberBetween(1, 320).build())
    .setRequired(true);

  var scales = ['의학적 정확성·타당성', '문항·선택지의 명확성과 완성도', '정답·해설의 적절성'];
  for (var s = 0; s < scales.length; s++) {
    f.addScaleItem().setTitle(scales[s]).setBounds(1, 5)
      .setLabels('매우 미흡', '매우 우수').setRequired(true);
  }
  f.addMultipleChoiceItem().setTitle('종합판정').setChoiceValues(VERDICTS).setRequired(true);
  f.addParagraphTextItem().setTitle('의견 / 수정 제안')
    .setHelpText('오류·모호한 부분·수정 제안을 자유롭게 (선택)');

  f.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  return f;
}

/** 폼2: 종합 설문 (교수님 확정 문안 그대로) */
function makeSurveyForm(ss) {
  var f = FormApp.create('AI 생성 임상종합평가 문항 검토 후 설문');
  f.setDescription(
    '다음 문항은 검토한 AI 생성 필기시험 문항 전체에 대한 의견을 묻는 질문입니다.\n' +
    '각 문항에 대해 가장 적절한 응답을 선택해 주십시오.\n\n' +
    '응답척도\n' + SCALE_NOTE
  );
  f.setCollectEmail(false);
  f.setLimitOneResponsePerUser(false);
  f.setConfirmationMessage('설문이 제출되었습니다. 참여해 주셔서 감사합니다.');

  f.addListItem().setTitle('검토자 번호').setChoiceValues(STUDENTS).setRequired(true);
  for (var q = 0; q < SURVEY_ITEMS.length; q++) {
    f.addScaleItem().setTitle((q + 1) + '. ' + SURVEY_ITEMS[q][0])
      .setHelpText(SURVEY_ITEMS[q][1])
      .setBounds(1, 5).setLabels('전혀 그렇지 않다', '매우 그렇다')
      .setRequired(true);
  }
  f.addParagraphTextItem().setTitle('10. 종합 의견')
    .setHelpText('검토한 AI 생성 문항에서 가장 개선이 필요하다고 생각한 점 또는 향후 문항 생성 시 반영하면 좋을 점을 자유롭게 작성해 주십시오.');

  f.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  return f;
}

function writeLinks(ss, rows) {
  var sh = ss.insertSheet('링크', 0);
  sh.appendRow(['구분', '학생 배포용 URL', '편집용 URL']);
  for (var i = 0; i < rows.length; i++) sh.appendRow(rows[i]);
  sh.appendRow(['응답 스프레드시트', ss.getUrl(), '']);
}

/** 실행 1: 폼 2개 + 응답 시트 */
function buildForms() {
  var ss = SpreadsheetApp.create('AI문항검토_응답');
  var f1 = makeReviewForm(ss);
  var f2 = makeSurveyForm(ss);
  writeLinks(ss, [
    ['폼1 문항별 검토', f1.getPublishedUrl(), f1.getEditUrl()],
    ['폼2 종합 설문', f2.getPublishedUrl(), f2.getEditUrl()],
  ]);
  Logger.log('폼1(문항별 검토) 배포용: ' + f1.getPublishedUrl());
  Logger.log('폼2(종합 설문)   배포용: ' + f2.getPublishedUrl());
  Logger.log('응답 스프레드시트: ' + ss.getUrl());
}

/** 실행 2: 종합 설문만 */
function buildSurveyOnly() {
  var ss = SpreadsheetApp.create('AI문항검토_설문응답');
  var f = makeSurveyForm(ss);
  writeLinks(ss, [['종합 설문', f.getPublishedUrl(), f.getEditUrl()]]);
  Logger.log('종합 설문 배포용: ' + f.getPublishedUrl());
  Logger.log('응답 스프레드시트: ' + ss.getUrl());
}
