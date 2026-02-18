FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -U pip && pip install -r requirements.txt

COPY app.py db.py llm.py ./

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
