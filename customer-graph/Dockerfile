FROM python:3.13-slim

# build-essential covers any packages that need to compile native extensions
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: build the whole graph. The agent is run via a separate compose service.
CMD ["python", "pipeline.py"]
