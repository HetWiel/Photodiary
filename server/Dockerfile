# Het dagboek: neemt foto's aan, en zet er één keer per dag één online met een plaat uit de krat.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Eigen gebruiker; de mappen bestaan vooraf, zodat de Docker-volumes dezelfde eigenaar krijgen
RUN useradd --system --uid 10001 dagboek \
 && mkdir -p /data /publiek \
 && chown dagboek:dagboek /data /publiek
COPY *.py *.onnx ./
USER dagboek

EXPOSE 8080
CMD ["python", "dagboek.py"]
