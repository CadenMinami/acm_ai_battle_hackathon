# Start from the official slim Python 3.11 image so agents run in a small, consistent Python environment.
FROM python:3.11-slim

# Use /app as the container working directory so all later paths are stable and predictable.
WORKDIR /app

# Copy the repository's agent implementations into the image so subprocess commands can run them inside the container.
COPY agents/ /app/agents/

# Treat the container command as Python arguments so callers can pass an agent script path at runtime.
ENTRYPOINT ["python3"]
