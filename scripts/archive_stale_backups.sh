#!/usr/bin/env bash
# 스테일 백업 아카이브 (삭제 아님, 이동 = 되돌리기 가능)
# 생성: 2026-07-13 · 리뷰 후 실행:  bash scripts/archive_stale_backups.sh
# 되돌리기: mv _archive/20260713/* ./  (원위치로)
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

DEST="_archive/20260713"
mkdir -p "$DEST"

# 명백히 죽은 백업/구버전만. 현행 app.py·api_server.py는 제외.
TARGETS=(
  "build_backup_20260210_185035"
  "build_backup_20260210_185610"
  "dist_backup_20260210_185035"
  "dist_backup_20260210_185610"
  "MedTutor.spec.backup_20260210_185035"
  "MedTutor.spec.backup_20260210_185610"
  "app_old.py"
  "app_old_backup.py"
  "app_backup_1770541749.py"
  "streamlit.log"
)

echo "=== 이동 대상 (존재하는 것만) ==="
for t in "${TARGETS[@]}"; do
  [ -e "$t" ] && du -sh "$t" || echo "  (없음) $t"
done

read -r -p $'\n계속 이동할까요? [y/N] ' ok
[ "$ok" = "y" ] || { echo "취소됨."; exit 0; }

for t in "${TARGETS[@]}"; do
  [ -e "$t" ] && mv "$t" "$DEST/" && echo "이동: $t -> $DEST/"
done

echo ""
echo "완료. 아카이브 위치: $DEST (회수 가능 용량 아래)"
du -sh "$DEST"
echo ""
echo "검토 후 완전 삭제하려면:  rm -rf $DEST   (되돌리기 불가)"
echo "※ .gitignore에 _archive/ 추가 권장."
