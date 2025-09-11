# END-TO-END Pipeline Translation Plan

## Current Pipeline Overview

The end-to-end pipeline evaluates PQL (Query Language) generation and analysis quality through a comprehensive testing workflow. This pipeline tests the complete flow from user prompts to analysis results.

### Current Components

1. **Test Case Generation** (`make_test_cases.py`)
   - Converts JSONL test cases to WebSocket test case format
   - Handles provider-specific configurations (Prometheus, AWS CloudWatch, etc.)
   - Extracts metric filters and generates descriptive test case names

2. **WebSocket Test Runner** (`run_grun.py`)
   - Executes test cases against WebSocket endpoints
   - Manages session lifecycle and response logging
   - Handles connection management and timeouts
   - Logs all frames to JSONL format for analysis

3. **PQL Quality Evaluation** (`eval_pql.py`)
   - Uses DeepEval with GPT models to assess PQL quality
   - Evaluates time range fidelity, metric correctness, dimensions, structure, and focus
   - Scores from 1-10 with detailed rubric
   - Detects valid PQL structure and syntax

4. **Analysis Quality Evaluation** (`eval_analysis.py`)
   - Evaluates the quality of monitoring analysis output
   - Assesses data accuracy, relevance, completeness, and actionability
   - Supports multiple evaluation modes (executive_summary, key_findings, full)
   - Provides structured feedback and improvement suggestions

## Airflow DAG Structure Plan

### Main DAG: `end_to_end_evaluation`

**Schedule**: Manual trigger only (schedule_interval=None)
**Dependencies**: Qdrant embeddings service must be running
**Trigger**: When running evaluation with existing test cases

#### Tasks:

1. **validate_test_cases** (PythonOperator)
   - **Function**: Validate existing test case file format and content
   - **Inputs**: Pre-generated test cases JSON file from end-to-end/
   - **Outputs**: Validated test cases file path
   - **XCom**: `test_cases_file_path`

2. **run_websocket_tests** (PythonOperator)
   - **Function**: Execute WebSocket test cases
   - **Dependencies**: validate_test_cases
   - **Inputs**: Test cases from XCom, API token from Airflow Variable
   - **Outputs**: Raw test results JSONL
   - **XCom**: `test_results_file_path`

3. **evaluate_pql_quality** (PythonOperator)
   - **Function**: Assess PQL generation quality
   - **Dependencies**: run_websocket_tests
   - **Inputs**: Test results from XCom
   - **Outputs**: PQL evaluation results
   - **XCom**: `pql_evaluation_results`

4. **evaluate_analysis_quality** (PythonOperator)
   - **Function**: Assess analysis output quality
   - **Dependencies**: run_websocket_tests
   - **Inputs**: Test results from XCom
   - **Outputs**: Analysis evaluation results
   - **XCom**: `analysis_evaluation_results`

5. **generate_evaluation_report** (PythonOperator)
   - **Function**: Combine all evaluation results into comprehensive report
   - **Dependencies**: [evaluate_pql_quality, evaluate_analysis_quality]
   - **Inputs**: All evaluation results from XCom
   - **Outputs**: Final evaluation report (JSON/HTML)

6. **notify_results** (EmailOperator)
   - **Function**: Send evaluation summary to stakeholders
   - **Dependencies**: generate_evaluation_report
   - **Content**: Key metrics, pass/fail status, report links

### Task Implementation Details

#### 1. validate_test_cases
- **Logic**: Validate existing test case JSON files in `end-to-end/` directory
- **Implementation**: Check file format, required fields, and test case structure
- **Output**: Validated test cases file path for WebSocket execution

#### 2. run_websocket_tests
- **Implementation**: Use `end-to-end/run_grun.py` logic
- **Function**: Execute WebSocket test cases against PQL generation endpoints
- **Output**: Raw test results JSONL with session data and responses

#### 3. evaluate_pql_quality
- **Implementation**: Use `end-to-end/eval_pql.py` functionality
- **Function**: Assess PQL generation quality using DeepEval metrics
- **Output**: PQL evaluation scores and detailed feedback

#### 4. evaluate_analysis_quality
- **Implementation**: Use `end-to-end/eval_analysis.py` functionality
- **Function**: Assess analysis output quality across multiple modes
- **Output**: Analysis evaluation scores and improvement suggestions

### Configuration Requirements

#### Airflow Variables:
- `end_to_end_test_cases_file`: Path to existing test cases JSON file
- `api_token`: WebSocket API authentication token
- `websocket_host`: WebSocket server host (default: localhost)
- `websocket_port`: WebSocket server port (default: 9999)
- `evaluation_model`: LLM model for evaluations (default: gpt-4.1-mini)

#### Connections:
- `openai_default`: OpenAI API connection for DeepEval

### Data Flow
```
Existing Test Cases → Validation → WebSocket Results → [PQL Eval, Analysis Eval] → Combined Report → Notification
```

### Monitoring & Alerting

- **Success Criteria**: 
  - All test cases execute successfully
  - PQL quality score > 7.0 average
  - Analysis quality score > 7.0 average

- **Failure Conditions**:
  - WebSocket connection failures
  - Evaluation model API errors
  - Score degradation > 1.0 from baseline

### Extensions

1. **Parallel Provider Testing**: Split by provider (AWS, Prometheus, etc.)
2. **Historical Tracking**: Store results in database for trend analysis
3. **Automated Remediation**: Trigger improvement workflows on poor scores
4. **A/B Testing**: Compare different model versions or configurations