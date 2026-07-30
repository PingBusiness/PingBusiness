FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY realm-bootstrap/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser

COPY realm-bootstrap/bootstrap_realm.py realm-bootstrap/reconcile_realm.py realm-bootstrap/verify_realm.py ./
COPY ESTORE-realm-template.json ./ESTORE-realm-template.json

USER 10001
CMD ["python", "/app/bootstrap_realm.py"]
