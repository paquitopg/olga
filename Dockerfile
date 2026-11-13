FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates nodejs npm \
 && npm install -g @anthropic-ai/claude-code@2.1.323 \
 && rm -rf /var/lib/apt/lists/* /root/.npm

RUN useradd --uid 10001 --create-home --home-dir /home/app app
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# HOME doit etre inscriptible pour la CLI Claude ; le volume est monte sous /data.
ENV PYTHONPATH=/srv/app HOME=/home/app LIBRARY_DIR=/data/library
USER 10001
CMD ["python", "-m", "ideadesk.main"]
