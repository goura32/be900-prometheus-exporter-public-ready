FROM python:3.12-alpine
WORKDIR /app
COPY be900_exporter.py /app/be900_exporter.py
RUN adduser -D -H -u 10001 exporter
USER exporter
EXPOSE 9119
CMD ["python", "-u", "be900_exporter.py", "--listen", "0.0.0.0", "--port", "9119"]
