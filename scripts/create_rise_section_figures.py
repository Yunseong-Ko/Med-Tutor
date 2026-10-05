from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path("docs/rise_figures")
W, H = 1920, 1080

FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/NanumGothic.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


F_TITLE = load_font(58)
F_SUBTITLE = load_font(30)
F_H = load_font(34)
F_BODY = load_font(25)
F_SMALL = load_font(22)
F_KPI = load_font(42)
F_STEP = load_font(30)

BLUE = "#005BAC"
NAVY = "#18324A"
TEAL = "#00A6A6"
MINT = "#EAF8F6"
SKY = "#EAF4FF"
LAVENDER = "#F1F3FF"
AMBER = "#FFF6DF"
GREEN = "#EAF7E8"
RED_TINT = "#FFF0EF"
GRAY = "#667085"
LIGHT_GRAY = "#E6EAF0"
CARD_BORDER = "#D5DEE8"
TEXT = "#17212B"


def bbox(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)


def text_size(draw, text, font):
    b = bbox(draw, text, font)
    return b[2] - b[0], b[3] - b[1]


def wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = word
        else:
            buf = ""
            for ch in word:
                cand = buf + ch
                if text_size(draw, cand, font)[0] <= max_width:
                    buf = cand
                else:
                    if buf:
                        lines.append(buf)
                    buf = ch
            current = buf
    if current:
        lines.append(current)
    return lines


def draw_text(draw, text, xy, font, fill=TEXT, anchor=None):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def draw_wrapped(draw, text, x, y, max_width, font, fill=TEXT, line_gap=8):
    yy = y
    for line in wrap_text(draw, text, font, max_width):
        draw.text((x, yy), line, font=font, fill=fill)
        yy += text_size(draw, line, font)[1] + line_gap
    return yy


def draw_card(draw, xy, fill="#FFFFFF", outline=CARD_BORDER, radius=30, shadow=True, width=2):
    x1, y1, x2, y2 = xy
    if shadow:
        draw.rounded_rectangle((x1 + 10, y1 + 12, x2 + 10, y2 + 12), radius=radius, fill="#E8EDF4")
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_pill(draw, xy, text, fill, fg="#FFFFFF", font=F_SMALL):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=(y2 - y1) // 2, fill=fill)
    draw.text(((x1 + x2) / 2, (y1 + y2) / 2 - 1), text, font=font, fill=fg, anchor="mm")


def draw_arrow(draw, start, end, color=BLUE, width=6):
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    import math

    angle = math.atan2(y2 - y1, x2 - x1)
    head_len = 22
    head_ang = 0.55
    p1 = (x2 - head_len * math.cos(angle - head_ang), y2 - head_len * math.sin(angle - head_ang))
    p2 = (x2 - head_len * math.cos(angle + head_ang), y2 - head_len * math.sin(angle + head_ang))
    draw.polygon([end, p1, p2], fill=color)


def draw_header(draw, title, subtitle):
    draw.rectangle((0, 0, W, H), fill="#FFFFFF")
    draw.rounded_rectangle((72, 64, 186, 98), radius=17, fill=BLUE)
    draw.text((129, 80), "P:accine", font=F_SMALL, fill="#FFFFFF", anchor="mm")
    draw.text((96, 128), title, font=F_TITLE, fill=NAVY)
    draw.text((100, 205), subtitle, font=F_SUBTITLE, fill=GRAY)
    draw.line((96, 255, W - 96, 255), fill=LIGHT_GRAY, width=2)


def icon_search(draw, cx, cy, color=BLUE):
    draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), outline=color, width=7)
    draw.line((cx + 23, cy + 23, cx + 54, cy + 54), fill=color, width=7)


def icon_blueprint(draw, cx, cy, color=TEAL):
    draw.rounded_rectangle((cx - 42, cy - 42, cx + 42, cy + 42), radius=12, outline=color, width=6)
    for dx in [-16, 16]:
        draw.line((cx + dx, cy - 32, cx + dx, cy + 32), fill=color, width=3)
    for dy in [-12, 16]:
        draw.line((cx - 32, cy + dy, cx + 32, cy + dy), fill=color, width=3)
    draw.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill=color)


def icon_pilot(draw, cx, cy, color="#7A5AF8"):
    draw.rounded_rectangle((cx - 55, cy - 28, cx + 55, cy + 35), radius=12, outline=color, width=6)
    draw.line((cx - 30, cy + 52, cx + 30, cy + 52), fill=color, width=6)
    draw.line((cx, cy + 35, cx, cy + 52), fill=color, width=6)
    draw.ellipse((cx - 28, cy - 5, cx - 4, cy + 19), fill=color)
    draw.ellipse((cx + 8, cy - 5, cx + 32, cy + 19), fill=color)


def icon_chart(draw, cx, cy, color="#F79009"):
    draw.line((cx - 45, cy + 40, cx + 50, cy + 40), fill=color, width=6)
    draw.line((cx - 40, cy + 40, cx - 40, cy - 42), fill=color, width=6)
    bars = [(-22, 12), (4, -12), (30, -34)]
    for x, top in bars:
        draw.rounded_rectangle((cx + x - 8, cy + top, cx + x + 8, cy + 38), radius=5, fill=color)


def section5():
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw_header(
        draw,
        "5. 연구방법",
        "교수·학생 요구분석에서 파일럿 검증까지 이어지는 4단계 연구 설계",
    )

    steps = [
        ("1", "요구분석", "교수 설문·인터뷰\n학생 내신 준비 불편 조사\n공통 요구와 차이 도출", SKY, icon_search, BLUE),
        ("2", "설계 및 개발", "문항 메타데이터 설계\n기출 유형화·프롬프트 설계\n생성·검수·배포 기능 구현", MINT, icon_blueprint, TEAL),
        ("3", "시범 적용", "파일럿 과목 1개 선정\n실제 자료 기반 초안 생성\n승인 문항 학습/시험 세트 배포", LAVENDER, icon_pilot, "#7A5AF8"),
        ("4", "평가 및 개선", "제작 시간·채택률 측정\n해설/개념 연결 만족도 분석\n개선안 및 확산 기준 도출", AMBER, icon_chart, "#F79009"),
    ]

    card_w, card_h = 382, 430
    gap = 48
    x0, y0 = 96, 325

    centers = []
    for i, (num, head, body, fill, icon, color) in enumerate(steps):
        x = x0 + i * (card_w + gap)
        y = y0
        draw_card(draw, (x, y, x + card_w, y + card_h), fill=fill, outline=CARD_BORDER, radius=34)
        draw.ellipse((x + 28, y + 30, x + 84, y + 86), fill=color)
        draw.text((x + 56, y + 57), num, font=F_STEP, fill="#FFFFFF", anchor="mm")
        icon(draw, x + card_w - 76, y + 67, color)
        draw.text((x + 32, y + 122), head, font=F_H, fill=NAVY)
        yy = y + 192
        for line in body.split("\n"):
            draw.ellipse((x + 34, yy + 8, x + 44, yy + 18), fill=color)
            yy = draw_wrapped(draw, line, x + 60, yy - 2, card_w - 95, F_BODY, TEXT, line_gap=4) + 16
        centers.append((x + card_w, y + card_h / 2))
        if i < 3:
            draw_arrow(draw, (x + card_w + 10, y + card_h / 2), (x + card_w + gap - 14, y + card_h / 2), color="#8AA3BD", width=5)

    # Bottom synthesis band
    band = (136, 825, W - 136, 985)
    draw_card(draw, band, fill="#FBFCFE", outline=LIGHT_GRAY, radius=32, shadow=False)
    draw_pill(draw, (172, 855, 352, 904), "검증 지표", BLUE, font=F_SMALL)
    draw.text((390, 872), "교수 관점", font=F_BODY, fill=NAVY)
    draw_wrapped(draw, "초안 제작 시간, 교수 수정량, 문항 채택률, 이미지 문항 처리 편의성", 390, 912, 560, F_SMALL, GRAY, line_gap=5)
    draw.line((982, 852, 982, 958), fill=LIGHT_GRAY, width=2)
    draw.text((1028, 872), "학생 관점", font=F_BODY, fill=NAVY)
    draw_wrapped(draw, "해설 유용성, 관련 개념 연결의 도움 정도, 시험 대비 효율성 체감", 1028, 912, 610, F_SMALL, GRAY, line_gap=5)
    draw.text((W - 160, 985), "정성 피드백 + 정량 지표로 최종 개선안 도출", font=F_SMALL, fill=BLUE, anchor="rs")

    return img


def icon_clock(draw, cx, cy, color=BLUE):
    draw.ellipse((cx - 42, cy - 42, cx + 42, cy + 42), outline=color, width=6)
    draw.line((cx, cy, cx, cy - 25), fill=color, width=6)
    draw.line((cx, cy, cx + 22, cy + 12), fill=color, width=6)


def icon_book(draw, cx, cy, color=TEAL):
    draw.rounded_rectangle((cx - 60, cy - 36, cx - 2, cy + 42), radius=10, outline=color, width=6)
    draw.rounded_rectangle((cx + 2, cy - 36, cx + 60, cy + 42), radius=10, outline=color, width=6)
    draw.line((cx, cy - 32, cx, cy + 45), fill=color, width=5)
    for off in [-16, 8]:
        draw.line((cx - 45, cy + off, cx - 16, cy + off), fill=color, width=3)
        draw.line((cx + 16, cy + off, cx + 45, cy + off), fill=color, width=3)


def icon_bridge(draw, cx, cy, color="#7A5AF8"):
    draw.ellipse((cx - 70, cy - 22, cx - 26, cy + 22), fill=color)
    draw.ellipse((cx + 26, cy - 22, cx + 70, cy + 22), fill=color)
    draw.line((cx - 25, cy, cx + 25, cy), fill=color, width=8)
    draw.arc((cx - 52, cy - 62, cx + 52, cy + 62), start=200, end=340, fill=color, width=8)


def icon_expand(draw, cx, cy, color="#F79009"):
    draw.line((cx - 54, cy + 40, cx + 45, cy - 38), fill=color, width=8)
    draw.polygon([(cx + 45, cy - 38), (cx + 18, cy - 34), (cx + 38, cy - 12)], fill=color)
    for r in [18, 34, 50]:
        draw.arc((cx - r, cy - r, cx + r, cy + r), start=220, end=325, fill=color, width=4)


def section6():
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw_header(
        draw,
        "6. 기대효과 및 결과 활용 방안",
        "교수 업무 절감, 학생 학습효율 향상, 융합교육 경험, 확산 가능성을 정량 지표로 검증",
    )

    center = (760, 345, 1160, 575)
    draw_card(draw, center, fill="#FFFFFF", outline=BLUE, radius=42, shadow=True, width=4)
    draw_pill(draw, (812, 390, 1108, 442), "AI 교육도구 MVP", BLUE, font=F_BODY)
    draw.text((960, 488), "P:accine", font=F_TITLE, fill=NAVY, anchor="mm")
    draw.text((960, 536), "문항개발·검수·학습지원 통합 흐름", font=F_SMALL, fill=GRAY, anchor="mm")

    benefits = [
        ((104, 318, 608, 548), "교수 업무부담 감소", "강의자료·기출문항 기반 초안 생성으로 교수는 검토와 수정에 집중", SKY, icon_clock, BLUE),
        ((1312, 318, 1816, 548), "학생 내신 대비 효율 향상", "해설, 오답 비교, 개념 연결, 유사 문항 추천으로 취약 개념 보완", MINT, icon_book, TEAL),
        ((104, 610, 608, 840), "의학-공학 융합 교육", "의대생의 현장 문제 정의와 공학 계열 학생의 AI 구현 경험 결합", LAVENDER, icon_bridge, "#7A5AF8"),
        ((1312, 610, 1816, 840), "확산·고도화 가능성", "파일럿 이후 과목 확대, 타 의과대학 적용, 교육 AI 솔루션으로 발전", AMBER, icon_expand, "#F79009"),
    ]

    for xy, head, body, fill, icon, color in benefits:
        x1, y1, x2, y2 = xy
        draw_card(draw, xy, fill=fill, outline=CARD_BORDER, radius=34)
        icon(draw, x1 + 84, y1 + 82, color)
        draw.text((x1 + 160, y1 + 52), head, font=F_H, fill=NAVY)
        draw_wrapped(draw, body, x1 + 160, y1 + 112, x2 - x1 - 205, F_BODY, TEXT, line_gap=8)
        # arrows to or from center
        if x2 < center[0]:
            draw_arrow(draw, (x2 + 18, (y1 + y2) / 2), (center[0] - 18, (y1 + y2) / 2), color="#9AAFC4", width=5)
        else:
            draw_arrow(draw, (center[2] + 18, (y1 + y2) / 2), (x1 - 18, (y1 + y2) / 2), color="#9AAFC4", width=5)

    # KPI strip
    strip = (104, 895, 1816, 1010)
    draw_card(draw, strip, fill="#FBFCFE", outline=LIGHT_GRAY, radius=34, shadow=False)
    kpis = [
        ("30%+", "초안 제작 시간 절감"),
        ("70%+", "경미 수정 후 채택률"),
        ("80%+", "해설 유용성 만족도"),
        ("1개+", "파일럿 과목 실제 적용"),
        ("20명+", "설문·시범운영 참여"),
    ]
    cell_w = (strip[2] - strip[0]) / len(kpis)
    for i, (num, label) in enumerate(kpis):
        cx = strip[0] + cell_w * i + cell_w / 2
        if i > 0:
            draw.line((strip[0] + cell_w * i, strip[1] + 24, strip[0] + cell_w * i, strip[3] - 24), fill=LIGHT_GRAY, width=2)
        draw.text((cx, 936), num, font=F_KPI, fill=BLUE, anchor="mm")
        draw.text((cx, 982), label, font=F_SMALL, fill=GRAY, anchor="mm")

    draw.text((W - 110, 1040), "결과 활용: PNU 파일럿 -> 과목 확대 -> 타 의과대학 확산 -> 교육 AI 고도화", font=F_SMALL, fill=BLUE, anchor="rs")
    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        "rise_section5_research_method.png": section5(),
        "rise_section6_expected_impact.png": section6(),
    }
    for filename, img in outputs.items():
        path = OUT_DIR / filename
        img.save(path, "PNG", optimize=True)
        print(path)


if __name__ == "__main__":
    main()
