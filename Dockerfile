# 1. Use an official Python base image
FROM python:3.9-slim

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_VERSION=1.7.1
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VIRTUALENVS_CREATE=false
# This ensures poetry installs dependencies into the system site-packages,
# which is common for Docker images to keep them slim.

# 3. Install Poetry
# Using apt-get install -y --no-install-recommends to reduce image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry && \
    apt-get remove -y curl ca-certificates && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# 4. Set up working directory
WORKDIR /app

# 5. Copy project files and install dependencies
# Copy only files necessary for dependency installation first to leverage Docker cache
COPY pyproject.toml poetry.lock* ./
# Install dependencies (excluding dev)
# Using --no-root because the project itself will be copied in the next step.
# This avoids installing the project package itself here, only its dependencies.
RUN poetry install --no-dev --no-interaction --no-ansi --no-root

# 6. Copy the application code
# This includes the 'web' directory and the 'youtube_transcript_api' library directory
COPY ./web ./web
COPY ./youtube_transcript_api ./youtube_transcript_api
# If there are other necessary local packages or files, copy them as well.
# COPY . . # Alternative: copy everything, but less cache-friendly

# 7. Expose the port the app runs on
EXPOSE 8000

# 8. Define the command to run the app
# The command should be `uvicorn web.main:app --host 0.0.0.0 --port 8000`
# Using 0.0.0.0 makes the app accessible from outside the container.
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
