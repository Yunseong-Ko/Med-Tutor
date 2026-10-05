#!/usr/bin/env python3
"""PTB-XL(CC BY 4.0)에서 진단별 12유도 심전도를 받아 이미지로 렌더.

출처: Wagner et al., PTB-XL a large publicly available ECG dataset (PhysioNet, CC BY 4.0).
상업 사용 가능(저작자 표시). 렌더 이미지에 출처 캡션 포함.
"""

import csv
import ast
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import wfdb

SCRATCH = Path("/private/tmp/claude-501/-Users-goyunseong-Documents-AI-Projects-Med-Tutor/4d0b9548-fa36-4402-857c-78430b4164b9/scratchpad")
CSV = SCRATCH / "ptbxl_database.csv"
WORK = SCRATCH / "ptbxl_records"
OUT = Path("data_private/exam_sets/synth_media")
BASE = "https://physionet.org/files/ptb-xl/1.0.3/"

# 진단코드 -> (이미지 제목=영어, 한글캡션은 부착 시 별도)
TARGETS = {
    "AFIB": "Atrial fibrillation (irregularly irregular, no P waves)",
    "3AVB": "Complete (third-degree) AV block",
    "SVTAC": "Supraventricular tachycardia",
}
MAX_CODES = {"AFIB": 2, "3AVB": 3, "SVTAC": 4}  # 희귀 코드는 동반코드 허용

LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def pick_records():
    rows = list(csv.DictReader(open(CSV)))
    chosen = {}
    for code in TARGETS:
        best = None
        for r in rows:
            try:
                sc = ast.literal_eval(r["scp_codes"])
            except Exception:
                continue
            # 타깃 코드가 100 확신 + 동반코드 최소 + 성인
            if sc.get(code) == 100.0 and len(sc) <= MAX_CODES.get(code, 2):
                age = r.get("age") or "0"
                try:
                    if float(age) < 18:
                        continue
                except Exception:
                    pass
                best = r
                break
        if best:
            chosen[code] = best
    return chosen


def download_record(relpath):
    """records100/<sub>/<id>_lr .hea/.dat 다운로드"""
    for ext in (".hea", ".dat"):
        url = BASE + relpath + ext
        dst = WORK / (relpath + ext)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            urllib.request.urlretrieve(url, dst)
    return WORK / relpath


def render(rec_path, code, desc, ecg_id):
    sig, meta = wfdb.rdsamp(str(rec_path))
    fs = meta["fs"]
    n = sig.shape[0]
    t = np.arange(n) / fs
    fig, axes = plt.subplots(6, 2, figsize=(11, 8.5), sharex=True)
    fig.patch.set_facecolor("white")
    order = [0, 6, 1, 7, 2, 8, 3, 9, 4, 10, 5, 11]  # I,V1,II,V2,...
    for ax_i, lead_i in enumerate(order):
        ax = axes[ax_i // 2, ax_i % 2]
        ax.plot(t, sig[:, lead_i], color="#111", lw=0.7)
        ax.set_facecolor("#fff5f5")
        ax.grid(True, which="both", color="#f4b6b6", lw=0.4)
        ax.set_xticks(np.arange(0, t[-1] + 0.2, 0.2))
        ax.set_xticklabels([])
        ax.set_yticks([])
        ax.tick_params(length=0)
        ax.text(0.01, 0.78, LEADS[lead_i], transform=ax.transAxes,
                fontsize=10, fontweight="bold", color="#0F766E")
        for s in ax.spines.values():
            s.set_color("#f4b6b6")
    fig.suptitle(f"12-lead ECG · {desc}", fontsize=12, y=0.995, color="#0B1F3A")
    fig.text(0.5, 0.005,
             f"Source: PTB-XL (PhysioNet, CC BY 4.0) record {ecg_id} — Wagner et al. 2020",
             ha="center", fontsize=7, color="#64748b")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"ptbxl_{code}_{ecg_id}.png"
    fig.savefig(dst, dpi=110)
    plt.close(fig)
    return dst


def main():
    chosen = pick_records()
    manifest = []
    for code, row in chosen.items():
        rel = row["filename_lr"]  # e.g. records100/00000/00001_lr
        rec = download_record(rel)
        dst = render(rec, code, TARGETS[code], row["ecg_id"])
        manifest.append((code, row["ecg_id"], str(dst)))
        print(f"[render] {code} (ecg_id {row['ecg_id']}) → {dst.name}")
    print("완료:", len(manifest), "개 심전도 렌더")


if __name__ == "__main__":
    raise SystemExit(main())
