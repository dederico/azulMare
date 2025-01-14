FROM python:3.11-slim-buster
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

EXPOSE 8010