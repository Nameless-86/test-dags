# Relevancy Evaluation Framework

A comprehensive evaluation framework for assessing the quality and relevance of vector search results in telemetry and monitoring systems. This framework uses LLM-generated queries and DeepEval metrics to evaluate how well your vector database retrieves relevant metric descriptions.

## 🎯 Overview

This framework evaluates vector search performance through a multi-step pipeline:

1. **Dataset Preparation**: Generate realistic evaluation queries from metric definitions
2. **Search Execution**: Query your vector database with generated questions
3. **Evaluation**: Assess relevance and recall using DeepEval metrics
4. **Visualization**: Analyze results with interactive charts

## 📋 Prerequisites

- Python 3.8+
- Access to an LLM service (Ollama, OpenAI, etc.)
- A running vector database (Qdrant, etc.) with populated metric data
- Vector search API endpoint

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Prepare Evaluation Dataset
Generate realistic queries from your metric definitions:
```bash
python prepare_dataset.py \
    --input ../../utils/vector/cloudwatch.json \
    --output queries/eval_queries.jsonl \
```

### 3. Run Vector Search
Execute searches against your vector database:
```bash
python run_search.py \
    --input queries/cloudwatch_queries.jsonl \
    --output search_results/cloudwatch_search_results.jsonl \
    --search-url http://localhost:8000/search \
    --top_k 5
    --collection cloudwatch
```

### 4. Evaluate Results
Assess the quality of retrieved results:
```bash
python descriptions_eval.py \
    --input search_results.jsonl
```

### 5. Analyze Results
Generate interactive charts from evaluation results:
```bash
python reasons_analysis.py
```

### 6. Remediation Process
Generate interactive charts from evaluation results:
```bash
python remediation.py
```
