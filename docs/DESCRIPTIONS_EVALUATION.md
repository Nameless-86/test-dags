# DESCRIPTIONS_EVALUATION Pipeline Translation Plan

## Current Pipeline Overview

The descriptions evaluation pipeline (relevancy_eval) assesses vector search quality and relevance for telemetry and monitoring systems. It generates realistic queries, executes vector searches, and evaluates the relevance of retrieved results using LLM-based metrics.

### Current Components

1. **Dataset Preparation** (`prepare_dataset.py`)
   - Generates realistic SRE/DevOps queries from metric definitions using LLM (Ollama/Llama)
   - Extracts provider name from input file paths
   - Creates natural language questions focused on monitoring and troubleshooting
   - Outputs JSONL format with generated queries

2. **Vector Search Execution** (`run_search.py`)
   - Executes searches against vector database endpoints
   - Queries Qdrant collections with generated questions
   - Retrieves top-k results with scores and metadata
   - Outputs search results in JSONL format

3. **Relevancy Evaluation** (`run_evaluation.py`)
   - Uses DeepEval metrics for contextual relevance and recall assessment
   - Implements custom evaluation templates for DevOps/monitoring context
   - Evaluates retrieved metrics against expected results
   - Provides detailed feedback on relevance quality

4. **Results Analysis** (`reasons_analysis.py`, `compare_results.py`)
   - Analyzes evaluation results and generates insights
   - Compares different search configurations or models
   - Creates visualization and reports for performance assessment

5. **Remediation Process** (`remediation.py`)
   - Identifies and addresses poor-performing queries
   - Implements improvement strategies for vector search
   - Tracks remediation effectiveness over time

## Airflow DAG Structure Plan

### Main DAG: `descriptions_evaluation`

**Schedule**: Manual trigger only (schedule_interval=None)
**Dependencies**: Qdrant embeddings service
**Trigger**: When adding new providers or updating vector data

#### Tasks:

1. **validate_existing_datasets** (PythonOperator)
   - **Function**: Validate existing evaluation query files are present and valid
   - **Inputs**: Pre-generated query files from relevancy_eval/queries/
   - **Outputs**: Validated dataset files mapping
   - **XCom**: `dataset_files_map` (provider → file_path mapping)

2. **run_vector_searches** (TaskGroup)
   - **Description**: Parallel search execution for each provider
   - **Dynamic Tasks**: One task per provider (CloudWatch, Prometheus, Loki, etc.)
   - **Function**: Execute vector searches against Qdrant collections
   - **Dependencies**: validate_existing_datasets
   - **Outputs**: Search results JSONL per provider

3. **evaluate_search_relevancy** (TaskGroup)
   - **Description**: Parallel relevancy evaluation for each provider
   - **Dynamic Tasks**: One task per provider
   - **Function**: Assess contextual relevance and recall
   - **Dependencies**: run_vector_searches
   - **Outputs**: Evaluation results per provider

4. **analyze_results** (PythonOperator)
   - **Function**: Aggregate and analyze evaluation results
   - **Dependencies**: evaluate_search_relevancy
   - **Inputs**: All provider evaluation results
   - **Outputs**: Comprehensive analysis report

5. **identify_remediation_candidates** (PythonOperator)
   - **Function**: Identify poorly performing queries/metrics
   - **Dependencies**: analyze_results
   - **Outputs**: Remediation candidate list
   - **XCom**: `remediation_candidates`

6. **execute_remediation** (PythonOperator)
   - **Function**: Apply remediation strategies
   - **Dependencies**: identify_remediation_candidates
   - **Inputs**: Remediation candidates from XCom
   - **Outputs**: Remediation results

7. **generate_quality_report** (PythonOperator)
   - **Function**: Create comprehensive quality dashboard
   - **Dependencies**: [analyze_results, execute_remediation]
   - **Outputs**: HTML dashboard, metrics summary

8. **alert_on_degradation** (BranchPythonOperator)
   - **Function**: Check for quality degradation
   - **Dependencies**: generate_quality_report
   - **Logic**: Compare current scores with historical baseline

9. **send_quality_alert** (EmailOperator)
   - **Function**: Alert on quality issues
   - **Dependencies**: alert_on_degradation
   - **Trigger**: When quality scores drop below threshold

10. **send_daily_summary** (EmailOperator)
    - **Function**: Send daily quality summary
    - **Dependencies**: generate_quality_report
    - **Content**: Key metrics, trends, recommendations

### Task Implementation Details

#### 1. validate_existing_datasets
- **Logic**: Scan `relevancy_eval/queries/` for existing `*_queries.jsonl` files
- **Output**: Map of provider → query file path for available datasets
- **Validation**: Check file existence and non-zero size

#### 2. run_vector_searches (Dynamic Task Group)
- **Implementation**: Use `relevancy_eval/run_search.py` logic
- **Dynamic Tasks**: One task per provider found in validation step
- **Function**: Execute vector searches against Qdrant collections
- **Output**: Search results JSONL per provider

#### 3. evaluate_search_relevancy (Dynamic Task Group)
- **Implementation**: Use `relevancy_eval/run_evaluation.py` logic  
- **Dynamic Tasks**: One task per provider with search results
- **Function**: Assess contextual relevance and recall using DeepEval
- **Output**: Evaluation metrics per provider

#### 4. analyze_results
- **Implementation**: Use `relevancy_eval/reasons_analysis.py` functionality
- **Function**: Aggregate evaluation results across all providers
- **Output**: Overall scores, provider breakdown, improvement areas, trends

#### 5. identify_remediation_candidates
- **Logic**: Compare relevancy scores against configurable threshold
- **Function**: Identify poorly performing queries/metrics
- **Output**: List of candidates requiring remediation

#### 6. execute_remediation
- **Implementation**: Use `relevancy_eval/remediation.py` strategies
- **Function**: Apply improvement strategies to identified candidates
- **Output**: Remediation results and effectiveness metrics

### Configuration Requirements

#### Airflow Variables:
- `qdrant_search_url`: Qdrant search endpoint URL
- `relevancy_threshold`: Minimum relevancy score threshold (default: 0.7)
- `evaluation_model`: LLM model for evaluation (default: gpt-3.5-turbo-0125)
- `top_k_results`: Number of results to retrieve per query (default: 5)

#### Connections:
- `qdrant_default`: Qdrant database connection
- `openai_default`: OpenAI API for evaluation metrics

### Data Flow
```
Pre-generated Queries → Vector Search → Relevancy Evaluation → Analysis → Remediation → Reporting
         ↓                    ↓               ↓                   ↓           ↓            ↓
    Existing JSONL         Search          Evaluation        Insights    Improvements   Dashboard
    Query Files           Results         Scores           & Trends     Applied       & Alerts
```

### Monitoring & Success Criteria

- **Success Metrics**:
  - Average relevancy score > 0.8
  - Recall score > 0.75
  - Query generation success rate > 95%
  - Search execution success rate > 98%

- **Alert Conditions**:
  - Relevancy score drops > 0.1 from baseline
  - Search failures > 5% of queries
  - OpenAI API unavailable
  - Qdrant collection empty or corrupted

### Quality Assurance

1. **Query File Validation**: Verify pre-generated query files exist and are valid
2. **Search Validation**: Test search endpoints before evaluation
3. **Model Validation**: Ensure OpenAI API is responsive
4. **Results Validation**: Check evaluation output format and completeness

### Extensions & Future Enhancements

1. **Multi-Model Comparison**: Test different embedding models
2. **Cross-Provider Analysis**: Compare relevancy across data sources
3. **Real-Time Monitoring**: Stream evaluation for production queries
4. **Automated Tuning**: Optimize search parameters based on results
5. **Federated Search**: Evaluate cross-collection search strategies