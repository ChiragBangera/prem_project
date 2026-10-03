FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PREM_DATA_DIR=/data

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir /data && chown app:app /data

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health', timeout=3)"

# Inside the container the app listens on every interface, which is how a published port reaches it. It has NO LOGIN: publish the port only where
# you want it reachable, e.g. `docker run -p 127.0.0.1:8000:8000 ...` keeps it to this computer; `-p 8000:8000` opens it to the whole network.
CMD ["sh", "-c", "uvicorn app.api:app --host 0.0.0.0 --port ${PORT}"]
