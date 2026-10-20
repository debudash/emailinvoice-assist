FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scoring.py refapi.py server.py ./

ENV PYTHONUNBUFFERED=1 \
    REFERENCE_API_URL=http://api:8000 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8200
EXPOSE 8200

# Streamable HTTP MCP endpoint: http://<host>:8200/mcp
CMD ["python", "server.py"]
