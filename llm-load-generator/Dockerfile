FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY llm-load-generator.py .

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "llm-load-generator.py"]
