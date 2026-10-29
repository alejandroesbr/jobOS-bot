FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=true

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY cli.py ./
COPY config/filters.yaml config/profile.example.yaml config/cv_base.example.md ./config/

RUN mkdir -p data interviews followups exports

ENTRYPOINT ["python", "cli.py"]
CMD ["stats"]
