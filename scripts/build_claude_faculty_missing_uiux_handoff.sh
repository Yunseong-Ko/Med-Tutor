#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_UIUX="/Users/goyunseong/Downloads/UIUX"
PACKAGE_ROOT="$PROJECT_ROOT/tmp/claude_faculty_missing_uiux_20260716"
ZIP_PATH="$PROJECT_ROOT/tmp/Paccine_Claude_Faculty_Missing_UIUX_20260716.zip"

rm -rf "$PACKAGE_ROOT"
mkdir -p \
  "$PACKAGE_ROOT/00_START_HERE" \
  "$PACKAGE_ROOT/01_VISUAL_SOURCE" \
  "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/faculty_studio_v2" \
  "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/legacy_function_reference" \
  "$PACKAGE_ROOT/03_SYNTHETIC_DATA"

copy_required() {
  local source="$1"
  local destination="$2"
  if [[ ! -f "$source" ]]; then
    printf 'Required file missing: %s\n' "$source" >&2
    exit 1
  fi
  cp "$source" "$destination"
}

copy_required "$PROJECT_ROOT/docs/Claude_Faculty_Missing_UIUX_Prompt_20260716.md" "$PACKAGE_ROOT/00_START_HERE/01_EXECUTION_PROMPT.md"
copy_required "$PROJECT_ROOT/docs/Faculty_Missing_UIUX_Function_Contract_20260716.md" "$PACKAGE_ROOT/00_START_HERE/02_FUNCTION_CONTRACT.md"
copy_required "$PROJECT_ROOT/docs/Faculty_Studio_V2_UIUX_Gap_Audit_20260716.md" "$PACKAGE_ROOT/00_START_HERE/03_GAP_AUDIT.md"
copy_required "$PROJECT_ROOT/docs/Claude_Faculty_Missing_UIUX_Upload_Manifest_20260716.md" "$PACKAGE_ROOT/00_START_HERE/04_UPLOAD_MANIFEST.md"

visual_files=(
  "Paccine Faculty Studio.dc.html"
  "Faculty Studio V2 Plan.dc.html"
  "CTA Hierarchy.dc (1).html"
  "Paccine Mobile.dc (1).html"
  "Paccine Routing Map.dc.html"
  "Ontology Feedback Track Audit.dc.html"
  "Paccine Exam Review.dc (1).html"
)

for file in "${visual_files[@]}"; do
  copy_required "$SOURCE_UIUX/$file" "$PACKAGE_ROOT/01_VISUAL_SOURCE/$file"
done

copy_required "$PROJECT_ROOT/frontend/faculty-studio-v2/index.html" "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/faculty_studio_v2/index.html"
copy_required "$PROJECT_ROOT/frontend/faculty-studio-v2/faculty-studio.css" "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/faculty_studio_v2/faculty-studio.css"
copy_required "$PROJECT_ROOT/frontend/faculty-studio-v2/faculty-studio.js" "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/faculty_studio_v2/faculty-studio.js"
copy_required "$PROJECT_ROOT/frontend/index.html" "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/legacy_function_reference/index.html"
copy_required "$PROJECT_ROOT/frontend/app.js" "$PACKAGE_ROOT/02_CURRENT_IMPLEMENTATION/legacy_function_reference/app.js"

copy_required "$PROJECT_ROOT/docs/design_samples/paccine_design_sample_data_20260715.json" "$PACKAGE_ROOT/03_SYNTHETIC_DATA/paccine_design_sample_data_20260715.json"

rm -f "$ZIP_PATH"
(
  cd "$(dirname "$PACKAGE_ROOT")"
  zip -qr "$ZIP_PATH" "$(basename "$PACKAGE_ROOT")"
)

printf 'Created: %s\n' "$ZIP_PATH"

