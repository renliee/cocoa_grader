FROM python:3.11-slim

WORKDIR /app

#OpenCV needs "libglib2.0-0" and "libgl1" because ultralytics pulls in opencv python (not headless).
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*

#torch and torchvision come from the CPU index because we don't need a GPU to run.
RUN pip install --no-cache-dir torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu

#check requirements if it is the same with previous requirements or not, if not, it will reinstall the requirements, else then it will use the cached requirements from previous build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#copy the source code below to the backend container
COPY core/ ./core/
COPY main.py .
COPY db.py domain.py presentation.py reports.py security.py schemas.py storage.py workflow.py ./
COPY migrations/ ./migrations/
COPY assets/ ./assets/
COPY weights/ ./weights/

RUN mkdir -p /tmp/ultralytics && chmod 777 /tmp/ultralytics
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
