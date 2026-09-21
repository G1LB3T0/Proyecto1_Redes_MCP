FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/requirements.txt /app/server-requirements.txt
RUN pip install --no-cache-dir -r server-requirements.txt \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY src /app/src
COPY data /app/data
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "30", "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "src.custom_mcp.http_server:create_app()"]
