FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc

COPY requirements.txt .
RUN pip install --no-cache-dir sqlalchemy psycopg2-binary

COPY . .

CMD ["python", "main.py"]