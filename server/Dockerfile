# Photodiary: accepts photos, and once a day publishes one with a record from the crate.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Own user; the folders exist beforehand so the Docker volumes get the same owner
RUN useradd --system --uid 10001 photodiary \
 && mkdir -p /data /public \
 && chown photodiary:photodiary /data /public
COPY *.py *.onnx ./
USER photodiary

EXPOSE 8080
CMD ["python", "diary.py"]
