"use strict";

/**
 * CpxAI: AI 표준화환자 실전모드 엔진 경계.
 * - 서버(/api/cpx-chat, Cloudflare Pages Function + OPENAI_API_KEY)가 있으면 실제 LLM 사용
 * - 없으면 케이스 데이터 기반 로컬 mock 환자/간이 채점으로 자동 전환
 * app.js는 이 파일의 window.CpxAI만 사용하므로, 나중에 LLM 교체 시 이 파일만 바꾸면 된다.
 */
(function () {
  const API_ENDPOINT = "./api/cpx-chat";
  const API_TIMEOUT_MS = 20000;

  let engineCache = null; // "api" | "mock"

  /* ---------------- 공통 유틸 ---------------- */

  function hashCode(text) {
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
      hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    }
    return hash;
  }

  const MALE_NAMES = ["김민수", "이준호", "박성진", "최영훈", "정우진", "한동현", "오재원", "서지훈"];
  const FEMALE_NAMES = ["김은지", "이수진", "박미영", "최혜란", "정다은", "한소영", "오유진", "서민정"];
  const CHILD_NAMES = ["김도윤", "이서준", "박하은", "최지우"];

  function personaFor(caseData) {
    const seed = hashCode(caseData.id);
    const ageText = String(caseData.patient.age || "");
    const ageNum = parseInt(ageText, 10) || 40;
    const isChild = ageNum <= 10 || ageText.includes("개월");
    const isFemale = String(caseData.patient.sex || "").includes("여");
    const pool = isChild ? CHILD_NAMES : isFemale ? FEMALE_NAMES : MALE_NAMES;
    const name = pool[seed % pool.length];
    const guardian = isChild;
    return {
      name,
      guardian,
      speaker: guardian ? "보호자" : "환자",
      age: caseData.patient.age,
      sex: caseData.patient.sex,
      worry: caseData.mustNotMiss && caseData.mustNotMiss.length
        ? `혹시 ${caseData.differentials?.[caseData.differentials.length - 1] || "심각한 병"}처럼 큰 병은 아닐까 걱정하고 있다`
        : "증상이 나빠질까 걱정하고 있다"
    };
  }

  // 조사 제거 + 2글자 이상 토큰 추출
  function tokenize(text) {
    return String(text)
      .split(/[^0-9A-Za-z가-힣]+/)
      .map((token) => token.replace(/(께서|에서|으로|이나|한테|에게|라고|하고|보다|처럼|부터|까지|은|는|이|가|을|를|의|에|와|과|도|만|로|요)$/u, ""))
      .filter((token) => token.length >= 2);
  }

  // 개념어 → 학생이 실제로 쓰는 표현들
  const SYNONYMS = {
    기간: ["언제", "며칠", "몇 주", "몇 달", "얼마나 됐", "얼마나 오래", "시작", "부터"],
    시작: ["언제", "부터", "처음"],
    빈도: ["몇 번", "몇번", "얼마나 자주", "하루에", "횟수"],
    양상: ["어떻게", "어떤 식", "느낌", "양상"],
    통증: ["아프", "아픈", "통증", "쑤시", "따가", "쥐어짜", "어디가 아프", "어떻게 아프", "어디쯤"],
    위치: ["어디", "부위", "위치"],
    방사: ["뻗치", "퍼지", "어깨", "등으로", "방사"],
    야간: ["밤에", "야간", "자다가", "새벽"],
    혈변: ["피가", "혈변", "피 섞", "빨간"],
    흑변: ["검은 변", "흑변", "까만"],
    발열: ["열이", "발열", "오한", "열나"],
    구토: ["토하", "구토", "구역", "메스껍", "울렁"],
    체중: ["체중", "몸무게", "살이", "살 빠"],
    식사: ["식사", "드시", "먹", "음식", "식욕"],
    수면: ["잠", "수면", "불면", "주무"],
    음주: ["술", "음주", "소주", "맥주", "반주"],
    흡연: ["담배", "흡연", "피우"],
    약물: ["약", "복용", "드시는 약", "진통제", "항생제", "영양제"],
    과거력: ["예전에", "과거", "앓았", "진단받", "수술", "병원 다니"],
    가족력: ["가족", "집안", "부모님", "형제", "친척"],
    여행: ["여행", "해외", "외국"],
    직업: ["직업", "무슨 일", "하시는 일"],
    스트레스: ["스트레스", "힘든 일", "고민"],
    월경: ["생리", "월경", "마지막 생리"],
    임신: ["임신", "피임", "성관계"],
    소변: ["소변", "오줌", "화장실"],
    소변량: ["소변량", "소변 양", "몇 번이나 보"],
    대변: ["변", "설사", "대변", "화장실"],
    잔변감: ["잔변", "덜 본 느낌", "시원하지"],
    어지럼: ["어지럽", "어지럼", "핑 도", "실신"],
    두통: ["머리가 아프", "두통", "머리 아픔"],
    호흡: ["숨", "호흡", "숨차", "숨이 가쁘"],
    황달: ["노랗", "황달", "눈이 노래"],
    부종: ["붓", "부종", "부어"],
    피로: ["피곤", "피로", "기운"],
    기분: ["기분", "우울", "가라앉"],
    자살사고: ["죽고 싶", "자살", "극단적인 생각", "해치고 싶"],
    불안: ["불안", "초조", "걱정"],
    기억: ["기억", "깜빡", "잊어버리"],
    발달: ["발달", "옹알이", "걸음", "말이 늦"],
    눈맞춤: ["눈맞춤", "눈을 맞추", "쳐다보"],
    호명: ["이름을 부르", "불러도", "반응"],
    예방접종: ["접종", "예방주사", "백신"],
    청력: ["청력", "듣", "귀"],
    관절: ["관절", "무릎", "붓고", "구부리"],
    분비물: ["분비물", "냉", "질"],
    가려움: ["가렵", "가려움", "간지럽"],
    감염: ["상한 음식", "주변에", "비슷한 증상", "유행"],
    동의: ["동의", "괜찮으시겠", "허락", "진행해도 될까"],
    알레르기: ["알레르기", "알러지", "부작용"],
    운동: ["운동", "움직이", "활동"],
    악화완화: ["심해지", "나아지", "악화", "완화", "좋아지"]
  };

  // 어느 카드에나 등장해 오매칭을 만드는 범용 단어는 키워드에서 제외
  const GENERIC_TOKENS = new Set([
    "증상", "관련", "여부", "정도", "동반", "이전", "최근", "때문",
    "경우", "혹시", "선생님", "환자", "확인", "말씀", "있다", "없다", "그리고"
  ]);

  function expandKeywords(topicText, answerText) {
    const keywords = new Set();
    tokenize(topicText).forEach((token) => {
      if (!GENERIC_TOKENS.has(token)) keywords.add(token);
    });
    tokenize(answerText).slice(0, 6).forEach((token) => {
      if (!GENERIC_TOKENS.has(token)) keywords.add(token);
    });
    Object.entries(SYNONYMS).forEach(([concept, terms]) => {
      if (topicText.includes(concept) || answerText.includes(concept)) {
        terms.forEach((term) => keywords.add(term));
        keywords.add(concept);
      }
    });
    return Array.from(keywords);
  }

  // 케이스 대본체("~있다.")를 환자 구어체("~있어요.")로 변환
  const SPOKEN_RULES = [
    [/나아진다(?=[.,\s]|$)/g, "나아져요"],
    [/좋아진다(?=[.,\s]|$)/g, "좋아져요"],
    [/심해진다(?=[.,\s]|$)/g, "심해져요"],
    [/피곤하다(?=[.,\s]|$)/g, "피곤해요"],
    [/아프다(?=[.,\s]|$)/g, "아파요"],
    [/힘들다(?=[.,\s]|$)/g, "힘들어요"],
    [/무섭다(?=[.,\s]|$)/g, "무서워요"],
    [/그렇다(?=[.,\s]|$)/g, "그래요"],
    [/모른다(?=[.,\s]|$)/g, "몰라요"],
    [/온다(?=[.,\s]|$)/g, "와요"],
    [/간다(?=[.,\s]|$)/g, "가요"],
    [/된다(?=[.,\s]|$)/g, "돼요"],
    [/난다(?=[.,\s]|$)/g, "나요"],
    [/든다(?=[.,\s]|$)/g, "들어요"],
    [/잔다(?=[.,\s]|$)/g, "자요"],
    [/본다(?=[.,\s]|$)/g, "봐요"],
    [/했다(?=[.,\s]|$)/g, "했어요"],
    [/([가-힣])었다(?=[.,\s]|$)/g, "$1었어요"],
    [/([가-힣])았다(?=[.,\s]|$)/g, "$1았어요"],
    [/([가-힣])였다(?=[.,\s]|$)/g, "$1였어요"],
    [/있다(?=[.,\s]|$)/g, "있어요"],
    [/없다(?=[.,\s]|$)/g, "없어요"],
    [/같다(?=[.,\s]|$)/g, "같아요"],
    [/많다(?=[.,\s]|$)/g, "많아요"],
    [/싶다(?=[.,\s]|$)/g, "싶어요"],
    [/([가-힣])하다(?=[.,\s]|$)/g, "$1해요"],
    [/이다(?=[.,\s]|$)/g, "이에요"]
  ];

  function spokenize(text) {
    return SPOKEN_RULES.reduce((acc, [pattern, replacement]) => acc.replace(pattern, replacement), String(text));
  }

  function buildReveals(caseData) {
    return (caseData.script || []).map(([topic, answer], index) => ({
      id: `reveal-${index}`,
      topic,
      answer,
      keywords: expandKeywords(topic, answer)
    }));
  }

  function countHits(text, keywords) {
    let hits = 0;
    keywords.forEach((keyword) => {
      if (keyword.length >= 2 && text.includes(keyword)) hits += 1;
    });
    return hits;
  }

  function includesAny(text, terms) {
    return terms.some((term) => text.includes(term));
  }

  /* ---------------- mock 표준화환자 ---------------- */

  function mockPatientReply(ctx, transcript, userText) {
    const caseData = ctx.caseData;
    const persona = personaFor(caseData);
    const text = userText.trim();
    const revealedIds = new Set(
      transcript.filter((m) => m.revealId).map((m) => m.revealId)
    );
    const studentTurns = transcript.filter((m) => m.role === "student").length;

    // 0) 마무리 인사
    if (includesAny(text, ["마무리했습니다", "마무리하겠습니다", "이상입니다", "진료를 마치", "들어가 보세요", "안녕히"])) {
      return { text: "네, 감사합니다 선생님. 잘 부탁드립니다." };
    }

    // 1) 인사 + 환자 확인
    if (includesAny(text, ["성함", "이름", "나이", "연세", "확인하겠"]) && studentTurns <= 2) {
      return { text: `네, 안녕하세요. 저는 ${persona.name}이고 ${persona.age}입니다.` };
    }
    if (includesAny(text, ["안녕하세요", "학생의사", "반갑습니다"]) && studentTurns <= 1) {
      return { text: `네, 안녕하세요 선생님.` };
    }

    // 2) 개방형 주호소 질문
    if (includesAny(text, ["어디가 불편", "어떻게 오셨", "무엇이 불편", "불편한 점", "불편하신", "어떤 증상", "말씀해 주세요", "말씀해주세요"])) {
      return { text: caseData.patient.opening };
    }

    // 3) 진단명 캐묻기 → 환자는 되묻기만
    if (includesAny(text, ["무슨 병", "제 병이", "진단이 뭐", "뭐가 문제", "암인가요", "큰 병인가요"])) {
      return { text: "글쎄요... 그걸 잘 몰라서 왔어요. 심각한 건가요, 선생님?" };
    }

    // 4) 케이스 스크립트 기반 점진 공개
    // 학생이 "…확인했습니다. 그런데 ~나요?"처럼 요약+질문을 함께 말하면
    // 마지막 문장(실제 질문)만으로 매칭해 요약 부분의 오염을 막는다.
    const sentenceParts = text.split(/[.!?…]/).map((part) => part.trim()).filter(Boolean);
    const focus = sentenceParts.length ? sentenceParts[sentenceParts.length - 1] : text;
    const reveals = buildReveals(caseData);
    let best = null;
    reveals.forEach((reveal) => {
      const hits = countHits(focus, reveal.keywords);
      if (hits <= 0) return;
      const unrevealedBonus = revealedIds.has(reveal.id) ? 0 : 0.5;
      const score = hits + unrevealedBonus;
      if (!best || score > best.score) best = { reveal, score };
    });
    if (best) {
      const already = revealedIds.has(best.reveal.id);
      const prefix = already ? "아까 말씀드린 대로 " : "";
      return { text: prefix + spokenize(best.reveal.answer), revealId: best.reveal.id };
    }

    // 5) 진찰/검사 선언과 동의
    if (includesAny(text, ["진찰", "청진", "촉진", "타진", "눌러보겠", "검사를 하겠", "검사하겠", "확인해 보겠", "확인해보겠", "동의", "괜찮으시겠", "진행하겠"])) {
      const consentAsk = includesAny(text, ["동의", "괜찮으시겠"]);
      return {
        text: consentAsk
          ? "네, 필요하다면 하셔야죠. 많이 아픈 검사는 아니죠?"
          : "네, 알겠습니다. 그렇게 하세요."
      };
    }

    // 6) 설명/치료계획 단계 → 짧게 수긍 + 걱정 한 번
    if (text.length > 40 && includesAny(text, ["가능성", "검사", "치료", "계획", "설명드리", "말씀드리", "필요합니다", "진행하겠습니다"])) {
      const worried = transcript.some((m) => m.role === "patient" && m.worryAsked);
      if (!worried) {
        return { text: "네... 설명 감사합니다. 그런데 많이 안 좋은 건 아닐까요? 걱정이 돼서요.", worryAsked: true };
      }
      return { text: "네, 알겠습니다. 말씀해 주신 대로 할게요." };
    }

    // 7) 질문 받기/마무리 흐름
    if (includesAny(text, ["궁금한 점", "질문 있으", "더 물어보실", "궁금하신"])) {
      const worried = transcript.some((m) => m.role === "patient" && m.worryAsked);
      if (!worried) {
        return { text: "저... 이게 시간이 지나면 저절로 낫는 건가요? 그게 제일 궁금해요.", worryAsked: true };
      }
      return { text: "아니요, 설명을 잘 해주셔서 괜찮습니다. 감사합니다." };
    }

    // 8) 스크립트에 없는 증상 질문 → 부정 답변 (표준화환자 규칙)
    if (/(나요|가요|세요|습니까|었나요|았나요|인가요|있으세요|하셨어요)\s*[?？]?$/.test(text) || text.endsWith("?")) {
      const negatives = [
        "아니요, 그런 건 없었어요.",
        "글쎄요... 그런 적은 없는 것 같아요.",
        "아니요, 특별히 그러지는 않았어요."
      ];
      return { text: negatives[hashCode(text) % negatives.length] };
    }

    // 9) 기본
    return { text: "네..." };
  }

  /* ---------------- mock 간이 채점 ---------------- */

  function checklistCoverage(ctx, transcript) {
    const caseData = ctx.caseData;
    const studentText = transcript
      .filter((m) => m.role === "student")
      .map((m) => m.text)
      .join(" ");
    const rows = [];
    (caseData.sections || []).forEach((section) => {
      section.items.forEach((entry) => {
        const keywords = expandKeywords(entry.text, "");
        const hits = countHits(studentText, keywords);
        const needed = keywords.length <= 4 ? 1 : 2;
        rows.push({
          section: section.title,
          sectionId: section.id,
          text: entry.text,
          critical: Boolean(entry.critical),
          covered: hits >= needed
        });
      });
    });
    return rows;
  }

  function liveMissing(ctx, transcript, limit = 3) {
    return checklistCoverage(ctx, transcript)
      .filter((row) => row.critical && !row.covered)
      .slice(0, limit)
      .map((row) => row.text);
  }

  function mockGrade(ctx, transcript) {
    const caseData = ctx.caseData;
    const guide = ctx.guide || {};
    const rows = checklistCoverage(ctx, transcript);
    const covered = rows.filter((row) => row.covered);
    const missedCritical = rows.filter((row) => row.critical && !row.covered);
    const studentMessages = transcript.filter((m) => m.role === "student");
    const studentText = studentMessages.map((m) => m.text).join(" ");

    const goodPoints = [];
    covered.filter((row) => row.critical).slice(0, 3).forEach((row) => {
      goodPoints.push(`핵심 항목을 직접 확인했습니다: ${row.text}`);
    });
    if (includesAny(studentText, ["정리하면", "요약하면", "제가 이해한"])) {
      goodPoints.push("환자 말을 요약하고 확인하는 문장을 사용했습니다. PPI에서 점수가 되는 습관입니다.");
    }
    if (includesAny(studentText, ["걱정", "힘드셨", "놀라셨", "불안하셨"])) {
      goodPoints.push("공감 표현을 사용해 라포를 챙겼습니다.");
    }
    if (!goodPoints.length && studentMessages.length >= 3) {
      goodPoints.push("스테이션을 끝까지 진행하며 대화 흐름을 유지했습니다.");
    }

    // 시험장에서 빠지면 위험한 항목: 필수 누락 중 안전/마무리·설명 쪽 우선
    const risky = [...missedCritical]
      .sort((a, b) => {
        const weight = (row) =>
          row.sectionId === "closing" || row.sectionId === "explain" ? 0 : 1;
        return weight(a) - weight(b);
      })
      .slice(0, 3)
      .map((row) => row.text);

    const nextScript = [
      guide.opening,
      (guide.history || [])[0],
      (guide.history || [])[1] || (guide.exam || [])[0],
      guide.explain,
      guide.closing
    ].filter(Boolean).slice(0, 5);

    return {
      engine: "mock",
      summary: `학생 발화 ${studentMessages.length}회, 체크리스트 ${covered.length}/${rows.length}개 인정(간이 채점), 필수 누락 ${missedCritical.length}개.`,
      goodPoints,
      missedCritical: missedCritical.map((row) => ({ text: row.text, section: row.section })),
      risky,
      nextScript,
      planTalk: ctx.planText || "",
      safety: caseData.safety,
      stats: {
        studentTurns: studentMessages.length,
        covered: covered.length,
        total: rows.length,
        missedCriticalCount: missedCritical.length
      }
    };
  }

  /* ---------------- 서버(API) 연동 ---------------- */

  function buildPacket(ctx) {
    const caseData = ctx.caseData;
    const persona = personaFor(caseData);
    return {
      caseId: caseData.id,
      category: caseData.category,
      presentation: caseData.presentation,
      diagnosis: caseData.diagnosis,
      patient: caseData.patient,
      persona,
      reveals: (caseData.script || []).map(([topic, answer]) => ({ topic, answer })),
      mustNotMiss: caseData.mustNotMiss,
      differentials: caseData.differentials,
      safety: caseData.safety,
      checklist: (caseData.sections || []).map((section) => ({
        title: section.title,
        id: section.id,
        items: section.items.map((entry) => ({ text: entry.text, critical: Boolean(entry.critical) }))
      })),
      guide: ctx.guide,
      planText: ctx.planText
    };
  }

  async function callApi(payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
    try {
      const response = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`api-${response.status}`);
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function probeEngine() {
    if (engineCache) return engineCache;
    try {
      const data = await callApi({ mode: "ping" });
      engineCache = data && data.ok ? "api" : "mock";
    } catch {
      engineCache = "mock";
    }
    return engineCache;
  }

  function slimTranscript(transcript) {
    return transcript
      .filter((m) => m.role === "student" || m.role === "patient")
      .slice(-40)
      .map((m) => ({ role: m.role, text: String(m.text).slice(0, 800) }));
  }

  async function patientReply(ctx, transcript, userText) {
    const engine = await probeEngine();
    if (engine === "api") {
      try {
        const data = await callApi({
          mode: "patient",
          packet: buildPacket(ctx),
          transcript: slimTranscript(transcript),
          userText: String(userText).slice(0, 800)
        });
        if (data && data.text) return { text: data.text, engine: "api" };
      } catch {
        engineCache = "mock";
      }
    }
    const mock = mockPatientReply(ctx, transcript, userText);
    return { ...mock, engine: "mock" };
  }

  async function grade(ctx, transcript) {
    const engine = await probeEngine();
    if (engine === "api") {
      try {
        const data = await callApi({
          mode: "grade",
          packet: buildPacket(ctx),
          transcript: slimTranscript(transcript)
        });
        if (data && data.result) {
          const fallback = mockGrade(ctx, transcript);
          return {
            ...fallback,
            ...data.result,
            engine: "api",
            planTalk: data.result.planTalk || fallback.planTalk,
            nextScript: (data.result.nextScript || []).length ? data.result.nextScript : fallback.nextScript
          };
        }
      } catch {
        engineCache = "mock";
      }
    }
    return mockGrade(ctx, transcript);
  }

  window.CpxAI = {
    probeEngine,
    patientReply,
    grade,
    liveMissing,
    personaFor
  };
})();
