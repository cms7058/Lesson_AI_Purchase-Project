FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN groupadd --gid 10001 aiassist && useradd --uid 10001 --gid aiassist --create-home aiassist
WORKDIR /opt/ai-assist
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN pip install . && mkdir -p /data && chown aiassist:aiassist /data
COPY deploy/container-entrypoint.py /opt/ai-assist/container-entrypoint.py
COPY deploy/bootstrap.py /opt/ai-assist/bootstrap.py
WORKDIR /data
USER aiassist
EXPOSE 8000
ENTRYPOINT ["python", "/opt/ai-assist/container-entrypoint.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
