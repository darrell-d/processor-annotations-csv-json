FROM python:3.12-slim

WORKDIR /processor

COPY processor/requirements.txt /processor/requirements.txt
RUN pip install --no-cache-dir -r /processor/requirements.txt

COPY processor/ /processor

ENV PYTHONPATH="/"

CMD ["python3.12", "-m", "processor.main"]
