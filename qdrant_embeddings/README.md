# Qdrant DB Image – Rebuild & Push Guide

This guide describes how to rebuild the Docker image of Qdrant **with your loaded collections** and push it to DockerHub.

## 1. Prepare Compose File

* **Remove or comment out the volume** for Qdrant’s storage in your `docker-compose-test.yml`:

  ```yaml
  #volumes:
  #  - qdrant_data:/qdrant/storage
  ```

  > This ensures the database files remain *inside* the container.

## 2. Build and Start Qdrant

```bash
docker compose -f docker-compose-test.yml up --build
```

* Wait for Qdrant to start.
* Load/import all collections and data you want to persist.

## 3. Commit the Container

* List containers and find the Qdrant container ID:

  ```bash
  docker ps
  ```
* Commit the container **with the data** to a new image:

  ```bash
  docker commit [container_id] autoptic/metrics:[tag]
  docker commit [container_id] autoptic/metrics:latest
  ```

## 4. Push the Image to DockerHub

```bash
docker push autoptic/metrics:[tag]
docker push autoptic/metrics:latest
```

* Authenticate first with `docker login` if needed.
## (Optional) Test the New Image

* Use `docker-compose-dev.yml` that references the image directly (without build).
* Start Qdrant and verify that collections are present.
---

## **Notes**

* If you make changes to the data, repeat steps 3–5.
* If you change the Dockerfile or code, rebuild using:

  ```bash
  docker compose build --no-cache
  docker compose up --force-recreate
  ```
* Make sure no volumes are mounted for `/qdrant/storage` while building the image.
* Test search endpoint
```bash
curl -X POST http://localhost:8000/search   -H "Content-Type: application/json"   -d '{
    "query": "CPU usage high",
    "top_k": 1,
    "collection": "cloudwatch"
  }'
```

```bash
curl -X POST http://localhost:8000/embed \
  -H "Content-Type: application/json" \
  -d '{"inputs": ["CPU usage high"]}'
```
