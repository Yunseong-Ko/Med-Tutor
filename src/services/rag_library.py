from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_ROOT = Path("data_private/rag")
DEFAULT_COURSE_ID = "hematology_oncology"
INDEX_FILENAME = "rag_index.json"
PARSER_VERSION = "rag-0.1.0"

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+/#.\-]*|[가-힣]{2,}")
SPACE_RE = re.compile(r"\s+")

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "are",
    "was",
    "were",
    "대한",
    "다음",
    "있는",
    "가장",
    "것은",
    "환자",
    "문항",
    "설명",
    "정답",
}

HEMATOLOGY_ONCOLOGY_SYNONYMS: dict[str, list[str]] = {
    "aml": ["acute myeloid leukemia", "급성골수성백혈병", "골수성백혈병", "blast"],
    "all": ["acute lymphoblastic leukemia", "급성림프모구백혈병", "림프모구"],
    "cml": ["chronic myeloid leukemia", "만성골수성백혈병", "bcr-abl", "philadelphia"],
    "cll": ["chronic lymphocytic leukemia", "만성림프구백혈병"],
    "dlbcl": ["diffuse large b-cell lymphoma", "미만성거대b세포림프종"],
    "hodgkin": ["reed-sternberg", "호지킨", "림프종"],
    "myeloma": ["multiple myeloma", "다발골수종", "m protein", "crab"],
    "iron": ["iron deficiency anemia", "철결핍빈혈", "ferritin", "tibc"],
    "b12": ["megaloblastic anemia", "거대적혈모구빈혈", "vitamin b12", "엽산"],
    "dic": ["disseminated intravascular coagulation", "파종혈관내응고", "fibrinogen"],
    "itp": ["immune thrombocytopenia", "면역혈소판감소증", "혈소판감소"],
    "tma": ["ttp", "hus", "thrombotic microangiopathy", "미세혈관병"],
    "febrile": ["febrile neutropenia", "호중구감소성 발열", "neutropenia"],
    "transfusion": ["수혈", "packed rbc", "platelet concentrate", "ffp"],
}

NEURO_SPECIAL_SENSES_SYNONYMS: dict[str, list[str]] = {
    "autonomic dysreflexia": ["자율신경 이상반사증", "척수손상", "방광팽창", "대변매복"],
    "orthostatic hypotension": ["기립성 저혈압", "supine", "standing blood pressure", "수축기혈압 감소"],
    "bulbocavernosus": ["구해면체반사", "anal reflex", "lowest sacral segment", "sacral reflex arc"],
    "craniosynostosis": ["두개유합증", "cranial suture", "sagittal suture", "metopic suture"],
    "myelomeningocele": ["척수수막류", "neural tube defect", "spina bifida", "alpha fetoprotein", "엽산"],
    "icf": ["international classification of functioning", "activities", "disability", "impairment"],
    "peripheral neuropathy": ["말초신경병증", "demyelinating neuropathy", "axonal neuropathy", "nerve conduction velocity", "amplitude"],
    "corticospinal": ["피질척수로", "corticobulbar tract", "motor neuron", "pyramidal tract"],
    "ulnar": ["척골신경", "ulnar nerve", "cubital tunnel", "guyon canal", "hypothenar"],
    "median": ["정중신경", "median nerve", "carpal tunnel", "thenar"],
    "radial": ["요골신경", "radial nerve", "wrist drop", "posterior interosseous"],
    "musculocutaneous": ["근육피부신경", "musculocutaneous nerve", "biceps reflex"],
    "axillary": ["겨드랑신경", "axillary nerve", "deltoid", "regimental badge"],
    "myasthenia gravis": ["중증근무력증", "acetylcholine receptor", "anti-cholinesterase", "thymectomy", "가슴샘절제술"],
    "duchenne muscular dystrophy": ["듀센 근육이영양증", "DMD", "dystrophin", "x-linked", "antisense oligonucleotide"],
    "herpes zoster": ["대상포진", "varicella zoster", "dorsal root ganglion", "감각신경절"],
    "olfactory disorder": ["후각장애", "olfactory training", "KVSS", "상기도감염", "비부비동질환"],
    "optic neuropathy": ["시신경병증", "optic neuritis", "ischemic optic neuropathy", "relative afferent pupillary defect", "RAPD"],
    "lhon": ["Leber hereditary optic neuropathy", "레버유전시신경병증", "mitochondrial DNA", "중심시력저하"],
    "oculomotor palsy": ["눈돌림신경마비", "third nerve palsy", "posterior communicating artery aneurysm", "동공확대", "안검하수"],
    "abducens palsy": ["가돌림신경마비", "sixth nerve palsy", "수평복시", "외전장애"],
    "trochlear palsy": ["도르래신경마비", "fourth nerve palsy", "head tilt", "vertical diplopia"],
    "spinal muscular atrophy": ["척수성근위축증", "SMA", "SMN1", "전각세포", "hypotonia"],
    "developmental delay": ["발달지연", "언어발달", "소근육", "대근육", "전반적 발달지연"],
    "aphasia": ["실어증", "Broca", "Wernicke", "conduction aphasia", "arcuate fasciculus", "inferior frontal gyrus"],
    "neglect": ["무시증후군", "hemispatial neglect", "우반구", "parietal lobe"],
    "frontal lobe": ["전두엽", "orbitofrontal", "medial frontal", "dorsolateral prefrontal", "집행기능"],
    "alzheimer": ["알츠하이머", "노인반", "신경섬유다발", "amyloid", "tau", "기억장애"],
    "vascular dementia": ["혈관성 치매", "stepwise deterioration", "lacunar infarct", "territorial infarction"],
    "mild cognitive impairment": ["경도인지장애", "MCI", "activities of daily living", "일상생활수행"],
    "epilepsy": ["뇌전증", "seizure", "발작", "hyperexcitability", "hypersynchrony"],
    "absence seizure": ["소발작", "absence seizure", "ethosuximide", "3Hz spike and wave"],
    "rolandic epilepsy": ["양성롤란딕뇌전증", "benign rolandic epilepsy", "oxcarbazepine", "centrotemporal spikes"],
    "febrile seizure": ["열발작", "complex febrile seizure", "simple febrile seizure", "전신강직간대발작"],
    "status epilepticus": ["경련지속상태", "status epilepticus", "lorazepam", "diazepam", "phenytoin", "phenobarbital"],
    "tetany": ["테타니", "hypocalcemia", "alkalosis", "HCO3", "calcium"],
    "uveitis scleritis": ["포도막염", "공막염", "상공막염", "세극등", "결막충혈"],
    "spinal tract": ["척수로", "dorsal column", "spinothalamic tract", "lateral corticospinal tract", "fasciculus gracilis", "fasciculus cuneatus"],
    "spinal cord syndrome": ["척수증후군", "anterior cord syndrome", "posterior cord syndrome", "Brown-Sequard", "central cord syndrome"],
    "multiple sclerosis": ["다발경화증", "MS", "dissemination in time", "dissemination in space", "interferon beta"],
    "neuromyelitis optica": ["시신경척수염", "NMOSD", "AQP4", "longitudinally extensive transverse myelitis"],
    "subacute combined degeneration": ["아급성연합변성", "vitamin B12", "posterior column", "lateral corticospinal tract"],
    "spinal cord infarction": ["척수경색", "anterior spinal artery", "DWI", "ADC", "급성 하지위약"],
    "facet joint pain": ["후관절 통증", "medial branch block", "dorsal ramus", "내측지 신경"],
    "sagittal balance": ["골반입사각", "pelvic incidence", "sacral slope", "pelvic tilt", "pelvic anteversion", "pelvic retroversion"],
    "fine needle aspiration": ["세침흡인세포검사", "FNA", "경부 종물", "neck mass", "cytology"],
    "primitive reflex": ["원시반사", "Moro reflex", "Galant reflex", "traction reflex", "ATNR", "tonic labyrinthine reflex"],
    "cerebral palsy": ["뇌성마비", "spastic bilateral type", "periventricular leukomalacia", "PVL", "미숙아"],
    "mrc scale": ["MRC 도수근력평가", "manual muscle testing", "근력평가", "grade 0", "grade 1", "grade 2", "grade 3"],
    "thyroid eye disease": ["갑상샘눈병증", "Graves ophthalmopathy", "안구돌출", "고용량 스테로이드", "orbital decompression"],
    "orbital blowout fracture": ["안와골절", "blowout fracture", "oculocardiac reflex", "하직근 감돈", "오심", "구토", "서맥"],
    "outer hair cell": ["외유모세포", "outer hair cell", "cochlear amplifier", "otoacoustic emission", "cochlear microphonic"],
    "middle ear impedance": ["중이 음전달", "고막", "등골판", "ossicular lever", "catenary lever"],
    "vestibular nuclei": ["전정핵", "VOR", "VCR", "VSR", "superior vestibular nucleus", "lateral vestibular nucleus"],
    "otolith": ["이석기관", "utricle", "saccule", "otoconia", "striola", "linear acceleration"],
    "referred otalgia": ["연관통", "referred otalgia", "Arnold nerve", "auricular branch", "CN IX", "CN X"],
    "tinnitus": ["이명", "Jastreboff", "neurophysiological model", "limbic system", "conditioned fear"],
    "auricle": ["이개", "perichondritis", "auricular hematoma", "cauliflower ear", "lobule"],
    "malignant otitis externa": ["악성 외이도염", "Pseudomonas aeruginosa", "skull base osteomyelitis", "Tc-99m"],
    "temporal bone fracture": ["측두골 골절", "otic capsule sparing", "otic capsule violating", "CSF leak", "hemotympanum", "facial nerve palsy"],
    "audiometry": ["청력검사", "순음청력검사", "pure tone audiometry", "AAO-HNS", "4분법", "speech audiometry"],
    "tuning fork test": ["음차검사", "Weber test", "Rinne test", "Schwabach test", "Gelle test"],
    "tympanometry": ["고막운동성계측", "tympanogram", "임피던스 청력검사", "type A", "type B"],
    "oae": ["이음향방사", "otoacoustic emission", "Auto-OAE", "newborn hearing screening"],
    "otitis media": ["급성중이염", "삼출성 중이염", "otitis media with effusion", "tympanogram B"],
    "cholesteatoma": ["진주종", "cholesteatoma", "만성중이염", "후천성 진주종", "선천성 진주종"],
    "meningitis": ["뇌수막염", "meningitis", "CSF", "lumbar puncture contraindication", "3세대 cephalosporin", "vancomycin"],
    "vertigo": ["어지럼", "현훈", "nystagmus", "HINTS", "head impulse test"],
    "bppv": ["양성돌발체위현훈", "BPPV", "Dix-Hallpike", "canalith repositioning"],
    "meniere": ["메니에르병", "Meniere disease", "저염식", "이뇨제", "intratympanic gentamicin"],
    "vestibular neuritis": ["전정신경염", "vestibular neuritis", "acute unilateral vestibulopathy", "vestibular rehabilitation"],
    "vestibular migraine": ["전정편두통", "vestibular migraine", "migraine-associated vertigo"],
    "ramsay hunt": ["람세이헌트증후군", "Ramsay Hunt", "Varicella-zoster virus", "안면신경마비", "이통"],
    "facial nerve test": ["안면신경검사", "electroneuronography", "ENoG", "Schirmer test", "stapedial reflex"],
    "sudden hearing loss": ["돌발성 난청", "sudden sensorineural hearing loss", "steroid", "어음명료도"],
    "presbycusis": ["노인성 난청", "presbycusis", "sensorineural hearing loss", "보청기"],
    "gjb2": ["GJB2", "connexin 26", "비증후군성 난청", "상염색체 열성"],
    "aqueous humor": ["방수유출", "aqueous humor", "trabecular meshwork", "Schlemm canal", "juxtacanalicular meshwork"],
    "retina layers": ["망막층", "retinal pigment epithelium", "photoreceptor layer", "outer nuclear layer", "inner nuclear layer", "ganglion cell layer", "nerve fiber layer"],
    "basilar membrane": ["바닥막", "basilar membrane", "cochlea", "organ of Corti"],
    "cataract": ["백내장", "cataract", "posterior capsule opacification", "aphakia", "intraocular lens"],
    "endophthalmitis": ["안내염", "endophthalmitis", "백내장수술 후", "안통", "시력저하"],
    "herpetic keratitis": ["헤르페스 각막염", "disciform keratitis", "steroid", "HSV"],
    "glaucoma": ["녹내장", "neovascular glaucoma", "open angle glaucoma", "angle recession", "fibrovascular membrane"],
    "viral conjunctivitis": ["바이러스성 결막염", "pseudomembrane", "subconjunctival hemorrhage", "enterovirus 70", "coxsackievirus A24"],
    "pterygium": ["익상편", "pterygium", "pinguecula", "검열반"],
    "vernal keratoconjunctivitis": ["봄철각결막염", "vernal keratoconjunctivitis", "giant papillae", "mast cell stabilizer"],
    "nasolacrimal duct obstruction": ["선천코눈물관폐쇄", "nasolacrimal duct obstruction", "digital massage", "dacryocystitis"],
    "phlyctenular keratoconjunctivitis": ["플릭텐각결막염", "phlyctenular keratoconjunctivitis", "결절", "각막신생혈관"],
    "tremor": ["떨림", "essential tremor", "action tremor", "resting tremor", "propranolol", "thyrotoxicosis"],
    "hemifacial spasm": ["반측안면경련", "hemifacial spasm", "botulinum toxin", "microvascular decompression"],
    "parkinson": ["파킨슨", "basal ganglia", "dopamine", "bradykinesia", "levodopa", "deep brain stimulation", "DBS"],
    "coma localization": ["혼수 병소", "Cheyne-Stokes respiration", "cluster respiration", "apneustic respiration", "pinpoint pupil", "decerebrate"],
    "cortical malformation": ["피질발달기형", "hemimegalencephaly", "heterotopia", "lissencephaly", "polymicrogyria", "schizencephaly"],
    "headache red flag": ["두통 경고징후", "복시", "유두부종", "red flag", "secondary headache"],
    "intracranial pressure": ["두개내압상승", "ICP", "mannitol", "head elevation", "papilledema"],
    "cauda equina": ["마미총", "cauda equina", "saddle anesthesia", "urinary retention", "emergency surgery"],
    "cranial nerve": ["뇌신경", "optic nerve", "trigeminal nerve", "facial nerve", "glossopharyngeal nerve", "accessory nerve"],
    "hypoglossal": ["설하신경", "hypoglossal nerve", "tongue deviation"],
    "mlf": ["안쪽세로다발", "medial longitudinal fasciculus", "internuclear ophthalmoplegia", "PPRF", "abducens nucleus"],
    "visual pathway": ["시각경로", "optic chiasm", "optic tract", "lateral geniculate body", "optic radiation", "calcarine cortex"],
    "strabismus": ["사시", "paralytic strabismus", "Herring law", "Sherrington law", "diplopia", "confusion", "suppression"],
    "pediatric eye exam": ["신생아 안과검사", "oculo-digital reflex", "fixation", "visual development"],
    "epiblepharon": ["덧눈꺼풀", "epiblepharon", "속눈썹", "각막자극"],
    "lumbar radiculopathy": ["요추신경근병증", "lumbar disc herniation", "femoral stretch test", "patellar reflex", "L3-4"],
    "spinal stenosis": ["척추관협착증", "neurogenic claudication", "허리 굴곡", "보행 시 하지통증"],
    "spinal tumor": ["척추종양", "schwannoma", "meningioma", "chordoma", "metastatic spinal tumor", "hemangioma"],
    "neurogenic shock": ["신경인성 쇼크", "neurogenic shock", "cervical spinal cord injury", "bradycardia", "hypotension", "quadriplegia"],
    "age related macular degeneration": ["나이관련황반변성", "AMD", "drusen", "geographic atrophy", "anti-VEGF"],
    "diabetic retinopathy": ["당뇨망막병증", "proliferative diabetic retinopathy", "retinal neovascularization", "macular edema", "VEGF"],
    "retinopathy of prematurity": ["미숙아망막병증", "ROP", "prematurity", "low birth weight", "retinal neovascularization"],
    "brainstem": ["뇌간", "midbrain", "pons", "medulla", "cranial nerve nucleus"],
    "spinal cord": ["척수", "anterior horn cell", "posterior column", "spinothalamic tract"],
    "stroke": ["뇌졸중", "ischemic stroke", "hemorrhage", "thrombolysis", "NIHSS"],
    "seizure": ["경련", "epilepsy", "status epilepticus", "antiepileptic"],
    "parkinson": ["파킨슨", "basal ganglia", "dopamine", "bradykinesia"],
    "demyelination": ["탈수초", "multiple sclerosis", "optic neuritis", "myelin"],
    "vision": ["시각경로", "optic nerve", "optic chiasm", "visual field"],
    "hearing": ["청각", "vestibular", "cochlea", "sensorineural hearing loss"],
    # --- high-yield additions for neuro/special senses 2차 exam topics ---
    "acoustic neuroma": ["청신경종양", "vestibular schwannoma", "CPA tumor", "cerebellopontine angle", "unilateral tinnitus"],
    "cochlear implant": ["인공와우", "cochlear implant", "전극", "electrode array", "청성뇌간반응", "ABR"],
    "eustachian tube": ["이관", "eustachian tube dysfunction", "adenoid hypertrophy", "valsalva"],
    "cerebellar ataxia": ["소뇌실조", "gait ataxia", "dysmetria", "intention tremor", "tandem gait", "nystagmus"],
    "nystagmus": ["안진", "horizontal nystagmus", "gaze-evoked nystagmus", "downbeat nystagmus", "HINTS"],
    "retinal detachment": ["망막박리", "retinal detachment", "lattice degeneration", "horseshoe tear", "photocoagulation"],
    "optic disc": ["시신경유두", "papilledema", "optic disc swelling", "cup-to-disc ratio", "glaucomatous cupping"],
    "anosmia": ["무후각증", "anosmia", "COVID-19", "olfactory epithelium", "zinc"],
    "aied": ["자가면역내이질환", "AIED", "autoimmune inner ear disease", "fluctuating sensorineural hearing loss", "steroid responsive"],
    "hearing aid": ["보청기", "hearing aid fitting", "gain", "output", "open fitting", "RIC"],
}

COURSE_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "hematology_oncology": HEMATOLOGY_ONCOLOGY_SYNONYMS,
    "neuro_special_senses": NEURO_SPECIAL_SENSES_SYNONYMS,
}

ANKI_TEMPLATE_CARDS: list[dict[str, Any]] = [
    {
        "patterns": ["myeloma", "multiple myeloma", "다발골수종", "crab"],
        "plain_text": "Multiple myeloma is associated with CRAB findings, monoclonal protein, and lytic bone lesions.",
        "anki_text": "Multiple myeloma is associated with {{c1::CRAB findings}}, {{c2::monoclonal protein}}, and {{c3::lytic bone lesions}}.",
    },
    {
        "patterns": ["iron deficiency", "철결핍", "ferritin", "tibc"],
        "plain_text": "Iron deficiency anemia typically shows low ferritin, increased TIBC, and microcytic hypochromic anemia.",
        "anki_text": "Iron deficiency anemia typically shows {{c1::low ferritin}}, {{c2::increased TIBC}}, and {{c3::microcytic hypochromic anemia}}.",
    },
    {
        "patterns": ["aml", "acute myeloid", "급성골수성", "auer", "blast"],
        "plain_text": "Acute myeloid leukemia often presents with blasts, Auer rods, anemia, and thrombocytopenia.",
        "anki_text": "Acute myeloid leukemia often presents with {{c1::blasts}}, {{c2::Auer rods}}, {{c3::anemia}}, and {{c4::thrombocytopenia}}.",
    },
    {
        "patterns": ["febrile neutropenia", "호중구감소성 발열", "neutropenia", "chemotherapy"],
        "plain_text": "Febrile neutropenia after chemotherapy requires prompt broad-spectrum antibiotic therapy.",
        "anki_text": "{{c1::Febrile neutropenia}} after chemotherapy requires prompt {{c2::broad-spectrum antibiotic therapy}}.",
    },
    {
        "patterns": ["hypertriglyceridemia", "triglyceride", "fenofibrate", "eruptive xanthoma", "pancreatitis"],
        "plain_text": "Severe hypertriglyceridemia can cause acute pancreatitis and may present with eruptive xanthomas.",
        "anki_text": "Severe {{c1::hypertriglyceridemia}} can cause {{c2::acute pancreatitis}} and may present with {{c3::eruptive xanthomas}}.",
    },
    {
        "patterns": ["fibrate", "fenofibrate", "triglyceride", "vldl", "chylomicron"],
        "plain_text": "Fibrates decrease serum triglycerides by increasing hydrolysis of VLDLs and chylomicrons.",
        "anki_text": "{{c1::Fibrates}} decrease serum {{c2::triglycerides}} by increasing {{c3::hydrolysis}} of VLDLs and chylomicrons.",
    },
]


def rag_index_path(course_id: str = DEFAULT_COURSE_ID) -> Path:
    return DATA_ROOT / safe_slug(course_id) / INDEX_FILENAME


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9가-힣._-]+", "_", str(value or "").strip())
    slug = slug.strip("._-")
    return slug or "rag"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha1("::".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return digest[:length]


def clean_text(text: str) -> str:
    text = str(text or "").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    tokens = [match.group(0).lower() for match in TOKEN_RE.finditer(str(text or ""))]
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def expand_query_terms(query: str, *, course_id: str | None = None) -> list[str]:
    base_terms = tokenize(query)
    expanded = list(base_terms)
    query_lower = str(query or "").lower()
    synonym_sources: list[dict[str, list[str]]] = []
    if course_id and course_id in COURSE_SYNONYMS:
        synonym_sources.append(COURSE_SYNONYMS[course_id])
    elif course_id:
        synonym_sources.extend(COURSE_SYNONYMS.values())
    else:
        synonym_sources.extend(COURSE_SYNONYMS.values())
    for synonyms in synonym_sources:
        for key, values in synonyms.items():
            candidates = [key, *values]
            if any(candidate.lower() in query_lower for candidate in candidates):
                expanded.extend(tokenize(" ".join(candidates)))
    return sorted(set(expanded))


def expand_course_query_terms(query: str, course_id: str) -> list[str]:
    return expand_query_terms(query, course_id=course_id)


def _legacy_expand_hematology_terms(query: str) -> list[str]:
    query_lower = str(query or "").lower()
    expanded = list(tokenize(query))
    for key, values in HEMATOLOGY_ONCOLOGY_SYNONYMS.items():
        candidates = [key, *values]
        if any(candidate.lower() in query_lower for candidate in candidates):
            expanded.extend(tokenize(" ".join(candidates)))
    return sorted(set(expanded))


def infer_source_type(path: Path) -> str:
    name = path.name.lower()
    if "harrison" in name or "part 4 oncology" in name or "oncology and hematology" in name:
        return "textbook"
    if "정리족" in path.name:
        return "student_summary"
    if "출족" in path.name:
        return "past_exam_notes"
    if "guideline" in name or "지침" in path.name:
        return "guideline"
    return "reference"


def infer_title(path: Path) -> str:
    return path.stem.replace("_", " ").strip()


def extract_pdf_pages(path: Path) -> list[dict[str, Any]]:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - environment issue
        raise RuntimeError("PyMuPDF가 설치되어 있어야 PDF 근거 DB를 만들 수 있습니다.") from exc

    pages: list[dict[str, Any]] = []
    with fitz.open(str(path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = clean_text(page.get_text("text"))
            if text:
                pages.append({"page": page_index, "text": text})
    return pages


def extract_text_pages(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_pages(path)
    if suffix in {".txt", ".md"}:
        text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))
        return [{"page": 1, "text": text}] if text else []
    raise ValueError(f"지원하지 않는 근거자료 형식입니다: {path.name}")


def chunk_pages(
    pages: list[dict[str, Any]],
    *,
    chunk_size: int = 1800,
    overlap: int = 180,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        page_no = int(page["page"])
        paragraphs = [clean_text(part) for part in re.split(r"\n\s*\n", page["text"]) if clean_text(part)]
        buffer = ""
        for paragraph in paragraphs:
            if not buffer:
                buffer = paragraph
                continue
            if len(buffer) + len(paragraph) + 2 <= chunk_size:
                buffer = f"{buffer}\n\n{paragraph}"
                continue
            chunks.append({"page_start": page_no, "page_end": page_no, "text": buffer})
            tail = buffer[-overlap:] if overlap and len(buffer) > overlap else ""
            buffer = clean_text(f"{tail}\n\n{paragraph}")
        if buffer:
            chunks.append({"page_start": page_no, "page_end": page_no, "text": buffer})
    return chunks


def _document_record(path: Path, *, course_id: str, title: str | None = None) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    source_type = infer_source_type(resolved)
    document_id = stable_id(course_id, str(resolved), length=12)
    return {
        "document_id": document_id,
        "course_id": course_id,
        "title": title or infer_title(resolved),
        "source_type": source_type,
        "source_path": str(resolved),
        "source_name": resolved.name,
    }


def build_rag_index(
    source_paths: list[Path],
    *,
    course_id: str = DEFAULT_COURSE_ID,
    output_path: Path | None = None,
    chunk_size: int = 1800,
    overlap: int = 180,
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    document_frequency: dict[str, int] = defaultdict(int)

    for raw_path in source_paths:
        path = raw_path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"근거자료를 찾을 수 없습니다: {path}")
        document = _document_record(path, course_id=course_id)
        pages = extract_text_pages(path)
        page_chunks = chunk_pages(pages, chunk_size=chunk_size, overlap=overlap)
        document["page_count"] = len(pages)
        document["chunk_count"] = len(page_chunks)
        documents.append(document)

        for chunk_index, chunk in enumerate(page_chunks, start=1):
            text = chunk["text"]
            terms = sorted(set(tokenize(text)))
            for term in terms:
                document_frequency[term] += 1
            chunk_id = stable_id(document["document_id"], str(chunk_index), text[:80], length=16)
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document["document_id"],
                    "course_id": course_id,
                    "title": document["title"],
                    "source_type": document["source_type"],
                    "source_name": document["source_name"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "text": text,
                    "terms": terms,
                    "char_count": len(text),
                }
            )

    index = {
        "schema_version": PARSER_VERSION,
        "course_id": course_id,
        "created_at": utc_now(),
        "documents": documents,
        "chunks": chunks,
        "stats": {
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "term_count": len(document_frequency),
        },
        "document_frequency": dict(sorted(document_frequency.items())),
    }

    save_rag_index(index, output_path or rag_index_path(course_id))
    return index


def save_rag_index(index: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(index, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as temp_file:
        temp_file.write(content)
        temp_name = temp_file.name
    Path(temp_name).replace(path)
    _load_rag_index_from_path.cache_clear()


@lru_cache(maxsize=16)
def _load_rag_index_from_path(path_text: str, mtime_ns: int, size: int) -> dict[str, Any]:
    # mtime/size are part of the cache key so rebuilt indexes are picked up automatically.
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


def load_rag_index(course_id: str = DEFAULT_COURSE_ID, index_path: Path | None = None) -> dict[str, Any]:
    path = index_path or rag_index_path(course_id)
    if not path.exists():
        raise FileNotFoundError(f"RAG 인덱스가 아직 없습니다: {path}")
    stat = path.stat()
    return _load_rag_index_from_path(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def get_rag_index_status(course_id: str = DEFAULT_COURSE_ID) -> dict[str, Any]:
    path = rag_index_path(course_id)
    if not path.exists():
        return {
            "course_id": course_id,
            "ready": False,
            "index_path": str(path),
            "message": "아직 로컬 근거 DB 인덱스가 생성되지 않았습니다.",
        }
    index = load_rag_index(course_id)
    return {
        "course_id": course_id,
        "ready": True,
        "index_path": str(path),
        "created_at": index.get("created_at"),
        "schema_version": index.get("schema_version"),
        **index.get("stats", {}),
        "documents": [
            {
                "document_id": doc.get("document_id"),
                "title": doc.get("title"),
                "source_type": doc.get("source_type"),
                "page_count": doc.get("page_count"),
                "chunk_count": doc.get("chunk_count"),
            }
            for doc in index.get("documents", [])
        ],
    }


def _idf(term: str, *, chunk_count: int, document_frequency: dict[str, int]) -> float:
    df = max(1, int(document_frequency.get(term, 0)))
    return math.log((chunk_count + 1) / df) + 1


def _score_chunk(
    chunk: dict[str, Any],
    *,
    query: str,
    query_terms: list[str],
    chunk_count: int,
    document_frequency: dict[str, int],
) -> float:
    title_lower = str(chunk.get("title") or "").lower()
    term_set = chunk.get("_term_set")
    if not isinstance(term_set, set):
        indexed_terms = chunk.get("terms")
        term_set = set(indexed_terms) if isinstance(indexed_terms, list) else set()
        if term_set:
            chunk["_term_set"] = term_set
    text_lower = ""
    term_counts = Counter()
    if not term_set:
        text_lower = str(chunk.get("text") or "").lower()
        term_counts = Counter(tokenize(text_lower))
    score = 0.0
    query_lower = query.lower().strip()
    if 4 <= len(query_lower) <= 120:
        if not text_lower:
            text_lower = str(chunk.get("text") or "").lower()
        if query_lower in text_lower:
            score += 6.0
    for term in query_terms:
        count = 1 if term in term_set else term_counts.get(term, 0)
        if count:
            score += (1.0 + min(count, 4) * 0.35) * _idf(
                term,
                chunk_count=chunk_count,
                document_frequency=document_frequency,
            )
        if term in title_lower:
            score += 0.75
    if chunk.get("source_type") in {"student_summary", "guideline"}:
        score += 0.25
    return round(score, 4)


def make_snippet(text: str, query_terms: list[str], *, max_chars: int = 700) -> str:
    cleaned = clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    lower = cleaned.lower()
    preferred_terms = [
        term
        for term in sorted(set(query_terms), key=len, reverse=True)
        if len(term) >= 4 and term.lower() not in STOPWORDS
    ]
    positions = [lower.find(term.lower()) for term in preferred_terms if lower.find(term.lower()) >= 0]
    if not positions:
        positions = [lower.find(term.lower()) for term in query_terms if lower.find(term.lower()) >= 0]
    start = positions[0] if positions else 0
    start = max(0, start - max_chars // 4)
    end = min(len(cleaned), start + max_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(cleaned) else ""
    return f"{prefix}{cleaned[start:end].strip()}{suffix}"


def first_sentence(text: str, *, max_chars: int = 220) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    sentence = re.split(r"(?<=[.!?。！？다])\s+", cleaned)[0].strip()
    if len(sentence) > max_chars:
        sentence = sentence[:max_chars].rsplit(" ", 1)[0].strip() + "..."
    return sentence


def make_cloze_sentence(sentence: str, query_terms: list[str]) -> str:
    text = first_sentence(sentence, max_chars=260)
    if not text:
        return ""
    candidates = [
        term
        for term in sorted(set(query_terms), key=len, reverse=True)
        if len(term) >= 4 and re.search(re.escape(term), text, flags=re.IGNORECASE)
    ][:3]
    cloze_text = text
    for index, term in enumerate(candidates, start=1):
        cloze_text = re.sub(
            re.escape(term),
            lambda match: f"{{{{c{index}::{match.group(0)}}}}}",
            cloze_text,
            count=1,
            flags=re.IGNORECASE,
        )
    return cloze_text


def template_anki_cards(query: str, *, course_id: str, limit: int) -> list[dict[str, Any]]:
    query_lower = str(query or "").lower()
    cards: list[dict[str, Any]] = []
    for template in ANKI_TEMPLATE_CARDS:
        patterns = [str(pattern).lower() for pattern in template["patterns"]]
        if not any(pattern in query_lower for pattern in patterns):
            continue
        card_id = stable_id(query, template["plain_text"], length=12)
        cards.append(
            {
                "card_id": card_id,
                "front": template["plain_text"],
                "back": template["anki_text"],
                "plain_text": template["plain_text"],
                "anki_text": template["anki_text"],
                "source": "P:accine concept template",
                "tags": [course_id, "concept_template", "cloze_draft"],
                "needs_review": True,
            }
        )
        if len(cards) >= limit:
            break
    return cards


def search_rag_evidence(
    query: str,
    *,
    course_id: str = DEFAULT_COURSE_ID,
    limit: int = 8,
    index_path: Path | None = None,
) -> dict[str, Any]:
    query = clean_text(query)
    if not query:
        raise ValueError("검색어가 비어 있습니다.")
    index = load_rag_index(course_id, index_path=index_path)
    query_terms = expand_query_terms(query, course_id=course_id)
    chunks = index.get("chunks", [])
    document_frequency = index.get("document_frequency", {})
    scored: list[dict[str, Any]] = []
    for chunk in chunks:
        score = _score_chunk(
            chunk,
            query=query,
            query_terms=query_terms,
            chunk_count=max(1, len(chunks)),
            document_frequency=document_frequency,
        )
        if score <= 0:
            continue
        scored.append({"score": score, "chunk": chunk})
    scored.sort(key=lambda item: item["score"], reverse=True)
    top_scored = scored[: max(1, min(limit, 20))]
    results: list[dict[str, Any]] = []
    for item in top_scored:
        chunk = item["chunk"]
        chunk_text = str(chunk.get("text") or "")
        results.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "title": chunk.get("title"),
                "source_type": chunk.get("source_type"),
                "source_name": chunk.get("source_name"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "score": item["score"],
                "snippet": make_snippet(chunk_text, query_terms),
                "text": make_snippet(chunk_text, query_terms, max_chars=1200),
            }
        )
    return {
        "query": query,
        "course_id": course_id,
        "query_terms": query_terms,
        "result_count": len(results),
        "results": results,
        "note": "로컬 인덱스에서 관련 근거 조각만 반환합니다. AI 해설 생성 시 이 결과만 컨텍스트로 전달하면 토큰 사용을 줄일 수 있습니다.",
    }


def draft_anki_cards_from_evidence(
    query: str,
    *,
    course_id: str = DEFAULT_COURSE_ID,
    limit: int = 5,
    index_path: Path | None = None,
) -> dict[str, Any]:
    evidence = search_rag_evidence(query, course_id=course_id, limit=limit, index_path=index_path)
    cards: list[dict[str, Any]] = template_anki_cards(query, course_id=course_id, limit=limit)
    remaining = max(0, limit - len(cards))
    query_terms = evidence.get("query_terms") or expand_query_terms(query, course_id=course_id)
    for rank, result in enumerate(evidence["results"][:remaining], start=1):
        source_label = f"{result['title']} p.{result['page_start']}"
        plain_text = first_sentence(result["snippet"]) or result["snippet"]
        anki_text = make_cloze_sentence(plain_text, query_terms) or plain_text
        cards.append(
            {
                "card_id": stable_id(query, result["chunk_id"], length=12),
                "front": plain_text,
                "back": anki_text,
                "plain_text": plain_text,
                "anki_text": anki_text,
                "source": source_label,
                "tags": [course_id, result["source_type"], "rag_draft"],
                "needs_review": True,
            }
        )
    return {
        "query": evidence["query"],
        "course_id": course_id,
        "cards": cards,
        "source_result_count": evidence["result_count"],
        "note": "초안 카드입니다. 학생 배포 전 의학적 정확성과 저작권/인용 범위를 검토해야 합니다.",
    }
