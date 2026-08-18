FROM python:3.11-slim

WORKDIR /app

# Copy everything first (source is needed for editable install)
COPY pyproject.toml alembic.ini ./
COPY src/ src/
COPY migrations/ migrations/
COPY examples/ examples/
COPY tests/ tests/

# Install package + dependencies
RUN pip install --no-cache-dir ".[dev]"

# Run migrations then start the API
CMD alembic upgrade head && uvicorn datapulse.api.app:app --host 0.0.0.0 --port 8000
