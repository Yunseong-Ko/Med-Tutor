# P:accine (Axioma Learning OS) — Railway demo container
FROM python:3.12-slim

WORKDIR /app

# HWP/PDF extraction and PPTX visual preview need the command-line helpers
# below. Keeping these in the image makes the deployed Faculty Studio follow
# the same upload path as the local application.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-noto-cjk \
    libreoffice-impress \
    libreoffice-writer \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code separately so the allow-listed data bundle is stored in
# one image layer instead of being duplicated during a later rename/copy step.
COPY *.py ./
COPY frontend/ ./frontend/
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY schemas/ ./schemas/
COPY assets/ ./assets/
COPY docs/Ontology_V1_Readiness_20260711.json ./docs/Ontology_V1_Readiness_20260711.json
COPY data_private/ ./runtime_seed/

# Railway volumes are attached only at runtime and are not overlays.
# start_railway.sh copies this allow-listed bundle into an empty persistent
# /app/data_private volume on first boot.
RUN chmod +x /app/scripts/start_railway.sh

ENV PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["/app/scripts/start_railway.sh"]
