#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_UIUX="/Users/goyunseong/Downloads/UIUX"
PACKAGE_ROOT="$PROJECT_ROOT/tmp/claude_design_handoff_20260715"
ZIP_PATH="$PROJECT_ROOT/tmp/Paccine_Claude_Design_Handoff_20260715.zip"

rm -rf "$PACKAGE_ROOT"
mkdir -p \
  "$PACKAGE_ROOT/00_START_HERE" \
  "$PACKAGE_ROOT/01_DESIGN_SOURCE" \
  "$PACKAGE_ROOT/02_CODE_REFERENCE/main" \
  "$PACKAGE_ROOT/02_CODE_REFERENCE/faculty_studio_v2" \
  "$PACKAGE_ROOT/02_CODE_REFERENCE/cpx_reference_only" \
  "$PACKAGE_ROOT/03_PRODUCT_CONTEXT" \
  "$PACKAGE_ROOT/04_SYNTHETIC_DATA"

copy_required() {
  local source="$1"
  local destination="$2"
  if [[ ! -f "$source" ]]; then
    printf 'Required file missing: %s\n' "$source" >&2
    exit 1
  fi
  cp "$source" "$destination"
}

copy_optional() {
  local source="$1"
  local destination="$2"
  if [[ -f "$source" ]]; then
    cp "$source" "$destination"
  fi
}

copy_required \
  "$PROJECT_ROOT/docs/Claude_Design_UIUX_Coverage_Gap_Prompt_20260715.md" \
  "$PACKAGE_ROOT/00_START_HERE/01_EXECUTION_PROMPT.md"
copy_required \
  "$PROJECT_ROOT/docs/Paccine_Current_Behavior_Inventory_20260715.md" \
  "$PACKAGE_ROOT/00_START_HERE/02_CURRENT_BEHAVIOR_INVENTORY.md"
copy_required \
  "$PROJECT_ROOT/docs/Faculty_Studio_V2_UIUX_Gap_Audit_20260716.md" \
  "$PACKAGE_ROOT/00_START_HERE/03_FACULTY_STUDIO_GAP_AUDIT.md"
copy_required \
  "$PROJECT_ROOT/docs/Claude_Design_UIUX_Upload_Manifest_20260715.md" \
  "$PACKAGE_ROOT/00_START_HERE/04_UPLOAD_MANIFEST.md"

design_files=(
  "Paccine App.dc.html"
  "Paccine Login.dc (1).html"
  "Paccine Student.dc (1).html"
  "Paccine Exam Review.dc (1).html"
  "Paccine Student Report.dc.html"
  "Student Learning Concepts.dc (1).html"
  "Paccine Faculty Studio.dc.html"
  "Faculty Studio V2 Plan.dc.html"
  "Paccine Faculty Cohort.dc.html"
  "Ontology Feedback Track Audit.dc.html"
  "CTA Hierarchy.dc (1).html"
  "Paused & Resume.dc.html"
  "Paccine Routing Map.dc.html"
  "Paccine Mobile.dc (1).html"
  "Paccine Mobile copy.dc (1).html"
  "ios-frame (1).jsx"
  "android-frame (1).jsx"
  "CPX Station Flow.dc (1).html"
)

for file in "${design_files[@]}"; do
  copy_required "$SOURCE_UIUX/$file" "$PACKAGE_ROOT/01_DESIGN_SOURCE/$file"
done

copy_required "$PROJECT_ROOT/frontend/index.html" "$PACKAGE_ROOT/02_CODE_REFERENCE/main/index.html"
copy_required "$PROJECT_ROOT/frontend/app.js" "$PACKAGE_ROOT/02_CODE_REFERENCE/main/app.js"
copy_required "$PROJECT_ROOT/frontend/styles.css" "$PACKAGE_ROOT/02_CODE_REFERENCE/main/styles.css"
copy_optional "$PROJECT_ROOT/frontend/paccine-v2.css" "$PACKAGE_ROOT/02_CODE_REFERENCE/main/DO_NOT_USE_AS_VISUAL_REFERENCE_paccine-v2.css"

copy_required "$PROJECT_ROOT/frontend/faculty-studio-v2/index.html" "$PACKAGE_ROOT/02_CODE_REFERENCE/faculty_studio_v2/index.html"
copy_required "$PROJECT_ROOT/frontend/faculty-studio-v2/faculty-studio.css" "$PACKAGE_ROOT/02_CODE_REFERENCE/faculty_studio_v2/faculty-studio.css"
copy_required "$PROJECT_ROOT/frontend/faculty-studio-v2/faculty-studio.js" "$PACKAGE_ROOT/02_CODE_REFERENCE/faculty_studio_v2/faculty-studio.js"

copy_optional "$PROJECT_ROOT/frontend/cpx-osce/index.html" "$PACKAGE_ROOT/02_CODE_REFERENCE/cpx_reference_only/index.html"
copy_optional "$PROJECT_ROOT/frontend/cpx-osce/styles.css" "$PACKAGE_ROOT/02_CODE_REFERENCE/cpx_reference_only/styles.css"
copy_optional "$PROJECT_ROOT/frontend/cpx-osce/app.js" "$PACKAGE_ROOT/02_CODE_REFERENCE/cpx_reference_only/app.js"

context_files=(
  "PACCINE_PROJECT_MASTER_STATUS_20260711.md"
  "Faculty_Studio_V2_Audit_20260712.md"
  "Claude_Ontology_Feedback_RAG_UIUX_Handoff_20260712.md"
  "Claude_Faculty_Studio_UIUX_Handoff_20260712.md"
  "Faculty_Studio_V2_UIUX_Gap_Audit_20260716.md"
)

for file in "${context_files[@]}"; do
  copy_optional "$PROJECT_ROOT/docs/$file" "$PACKAGE_ROOT/03_PRODUCT_CONTEXT/$file"
done

copy_required \
  "$PROJECT_ROOT/docs/design_samples/paccine_design_sample_data_20260715.json" \
  "$PACKAGE_ROOT/04_SYNTHETIC_DATA/paccine_design_sample_data_20260715.json"

cat > "$PACKAGE_ROOT/README_FIRST.md" <<'EOF'
# P:accine Claude Design handoff

1. Start with `00_START_HERE/01_EXECUTION_PROMPT.md`.
2. Treat `01_DESIGN_SOURCE` as the visual source of truth.
3. Treat `02_CODE_REFERENCE` as behavior reference only.
4. Do not use the file prefixed with `DO_NOT_USE_AS_VISUAL_REFERENCE` as a design reference.
5. Use only `04_SYNTHETIC_DATA` for screen content.
6. Do not redesign CPX/OSCE. Its files are present only to preserve entry and return behavior.
7. First produce the coverage matrix, then create every missing P0 screen.
EOF

rm -f "$ZIP_PATH"
(
  cd "$(dirname "$PACKAGE_ROOT")"
  zip -qr "$ZIP_PATH" "$(basename "$PACKAGE_ROOT")"
)

printf 'Created: %s\n' "$ZIP_PATH"
