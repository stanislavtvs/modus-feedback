FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -r app && useradd -r -g app app
COPY . .
RUN mkdir -p private_uploads staticfiles && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["sh", "entrypoint.sh"]
