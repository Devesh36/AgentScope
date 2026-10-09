FROM python:3.12-slim
WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt
COPY apps/api apps/api
COPY packages/python-sdk packages/python-sdk
RUN pip install --no-cache-dir --no-deps ./packages/python-sdk
WORKDIR /app/apps/api
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
