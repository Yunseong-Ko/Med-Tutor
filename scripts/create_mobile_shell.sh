#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${ROOT_DIR}/mobile_shell"
TEMPLATE_MAIN="${ROOT_DIR}/mobile_shell_template/lib/main.dart"

if ! command -v flutter >/dev/null 2>&1; then
  echo "error: flutter not found. install Flutter SDK first." >&2
  exit 1
fi

if [ -d "${TARGET_DIR}" ]; then
  echo "error: ${TARGET_DIR} already exists. remove it first if you want to recreate." >&2
  exit 1
fi

flutter create \
  --platforms=android,ios \
  --org io.axiomaq.mobile \
  --project-name axiomaq_mobile_shell \
  "${TARGET_DIR}"

cp "${TEMPLATE_MAIN}" "${TARGET_DIR}/lib/main.dart"

(
  cd "${TARGET_DIR}"
  flutter pub add webview_flutter
  flutter pub get
)

cat <<EOF
done.

next:
1) android debug run
   cd "${TARGET_DIR}" && flutter run -d android

2) ios debug run (mac only)
   cd "${TARGET_DIR}" && flutter run -d ios

3) release builds
   cd "${TARGET_DIR}" && flutter build apk --release
   cd "${TARGET_DIR}" && flutter build ios --release
EOF
