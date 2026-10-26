FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as a normal user, not root.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8501 8502

# The command is chosen per service in docker-compose.yml (provider site or admin site).
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]