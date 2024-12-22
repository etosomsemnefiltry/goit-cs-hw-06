FROM python:3.12

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir pymongo

CMD ["python", "-u", "main.py"]