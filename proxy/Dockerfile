FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 9874
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9874"]
