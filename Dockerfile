FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r Requirements.txt

CMD ["python", "server_1.py"]