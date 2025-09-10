# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a test-dags repository for translating data pipelines to Airflow DAGs. The codebase contains multiple components:

- **dags/**: Airflow DAG definitions (currently contains a simple test DAG)
- **end-to-end/**: End-to-end evaluation scripts for PQL queries and analysis
- **qdrant_embeddings/**: Vector database service with embeddings using E5 model
- **relevancy_eval/**: Evaluation scripts for search relevancy and remediation
- **vector/**: JSON data files containing data for various services (CloudWatch, Loki, Prometheus, etc.)

## Development Commands

### Qdrant Embeddings Service
```bash
# Build and start Qdrant with Docker Compose
cd qdrant_embeddings
docker compose -f docker-compose-dev.yml up --build
```
# Check the embeddings are up, it may take up to 5 minutes
```bash
chmod +x qdrant_embeddings/validate_collections.sh
./qdrant_embeddings/validate_collections.sh
```

### End-to-End Evaluation
```bash
cd end-to-end
```

# Run evaluation with test cases

## Make sure the OPENAI_API_TOKEN is set

```bash
python3 run_grun.py \
  --test-cases test_cases.json \
  --runs-dir runs
```

# Evaluate PQL results
```bash
python3 eval_pql.py --input results.json
python3 eval_pql.py --input results.json --where-filter aws-cw
python3 eval_pql.py --input results.json --name-contains prometheus
```

# Analyze results
```bash
python3 eval_analysis.py --input results.json --actual-mode executive_summary
python3 eval_analysis.py --input results.json --actual-mode key_findings
python3 eval_analysis.py --input results.json --actual-mode full --where-filter loki
```

### Relevancy Evaluation
```bash
cd relevancy_eval
```

# Install dependencies
```bash
pip install -r requirements.txt
```

# Run search evaluation
```bash
python3 run_search.py
```

# Run evaluation pipeline
```bash
python3 run_evaluation.py
```

# Analyze reasons
```bash
python3 reasons_analysis.py
```

# Run remediation
```bash
python3 remediation.py
```

## Architecture

### Qdrant Vector Database Service
- Main service in `qdrant_embeddings/main.py` provides search and embedding endpoints
- Uses E5 embedder model for text embeddings (`e5_embedder.py`)
- Query client provides HTTP API for search operations
- Docker setup with separate dev/test configurations
- Collections contain embeddings for various monitoring services (CloudWatch, Loki, Prometheus, etc.)

### Airflow DAGs
- Located in `dags/` directory
- Initially contains simple test DAG with BashOperator
- Target is to translate existing pipelines to Airflow format

### Evaluation Framework  
- End-to-end evaluation tests PQL queries against various data sources
- Relevancy evaluation measures search quality and performs remediation
- Results analysis provides executive summaries and key findings
- Vector data stored as JSON files for different services

## Key Dependencies

### Python Packages
- `qdrant-client==1.8.0` for vector database operations
- `torch` and `transformers==4.52.4` for E5 embeddings model
- `pandas==2.2.3` for data processing
- `airflow` for DAG definitions (Apache Airflow)

### Docker Services
- Qdrant vector database
- Custom embedding service built with Python
