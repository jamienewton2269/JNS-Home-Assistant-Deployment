FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24
COPY probe.py /opt/jns/probe.py
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
