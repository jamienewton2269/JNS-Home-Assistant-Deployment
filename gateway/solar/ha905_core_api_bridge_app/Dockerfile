FROM ghcr.io/home-assistant/base:latest
RUN apk --no-cache add python3
COPY probe.py /opt/jns/probe.py
CMD ["python3", "/opt/jns/probe.py"]
