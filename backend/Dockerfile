FROM python:3.11-slim

# Номер релиза передаётся сборкой (docker-build.yml) для обоих образов; backend
# его не использует — заявляем, чтобы build-arg не считался лишним.
ARG APP_VERSION=dev
# fonts-dejavu-core: необходимы для генерации PDF-квитанций (DejaVuSans / -Bold)
RUN apt-get update && apt-get install -y libpq-dev gcc fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Важно: Убедись, что нет лишних строк USER
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
