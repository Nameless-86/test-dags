max_consecutive_failures# End-to-End Evaluation Pipeline

## Overview

The end-to-end evaluation pipeline validates the complete PQL (Query Language) generation and monitoring analysis workflow. This pipeline tests the entire flow from user prompts to final analysis results, ensuring both PQL quality and analysis accuracy.

## Architecture

```
JSONL Input → Test Case Generation → WebSocket Testing → Result Processing → Quality Evaluation
     ↓              ↓                      ↓                  ↓                  ↓
Input Data    Test Cases JSON      JSONL Event Logs    Structured Results   Evaluation Reports
```

## Components

### 1. `make_test_cases.py` - Test Case Converter
**Purpose**: Converts JSONL format test cases to WebSocket-compatible test format with provider-specific configurations.

**Input**: JSONL file with test cases containing:
- `id`: Unique test case identifier
- `provider`: Data source (prometheus, aws, cloudwatch)
- `metric_information`: Metric metadata and filters
- `generated_question`: Natural language monitoring question

**Output**: JSON file with structured test cases including:
- Formatted prompts and metadata
- Provider-specific configurations (where, when, useVectorSearch)
- Metric filters and search parameters

**Key Features**:
- Provider-specific configuration mapping
- Metric filter extraction and formatting
- Descriptive test case naming
- Metadata preservation for analysis

### 2. `run_grun.py` - WebSocket Test Executor
**Purpose**: Executes test cases against WebSocket endpoints asynchronously, capturing all interaction data.

**Input**: JSON test cases from `make_test_cases.py`
**Output**: JSONL log files with timestamped WebSocket events

**Key Features**:
- Asynchronous WebSocket connection management
- Session-based request/response tracking
- Comprehensive event logging (connections, requests, responses, errors)
- Configurable timeouts and retry logic
- Structured JSONL output for downstream processing

### 3. `consume_logs.py` - Log Parser & Result Aggregator
**Purpose**: Converts raw JSONL WebSocket logs into structured test results with extracted analysis data.

**Input**: JSONL log files from `run_grun.py`
**Output**: Structured JSON with test cases, results, and summary statistics

**Key Features**:
- WebSocket event parsing and test case reconstruction
- Analysis data extraction from success frames
- Error handling and timeout detection
- Summary statistics generation (success rates, durations)
- Structured result format for evaluation tools

### 4. `eval_pql.py` - PQL Quality Evaluator
**Purpose**: Evaluates generated PQL quality using DeepEval framework with comprehensive rubric.

**Input**: Structured results from `consume_logs.py`
**Output**: PQL quality scores (1-10) with detailed feedback

**Evaluation Criteria**:
- **Time Range Fidelity (0-2)**: Correct time range interpretation
- **Metric & Source Correctness (0-3)**: Appropriate namespace/metric selection
- **Dimensions & Grouping (0-2)**: Proper dimension usage and filtering
- **Structure & Syntax Quality (0-2)**: PQL structural coherence
- **Focus & Parsimony (0-1)**: Minimal yet sufficient PQL generation

**Key Features**:
- Automated PQL detection and validation
- DeepEval integration with GPT-based scoring
- Detailed feedback and improvement suggestions
- Configurable evaluation models

### 5. `eval_analysis.py` - Analysis Quality Evaluator
**Purpose**: Evaluates monitoring analysis output quality across multiple evaluation modes.

**Input**: Structured results from `consume_logs.py`
**Output**: Analysis quality scores with specific improvement recommendations

**Evaluation Modes**:
- `executive_summary`: Evaluates executive summary only
- `key_findings`: Evaluates key findings section
- `full`: Evaluates complete analysis (concatenated sections)

**Evaluation Criteria**:
- **Data Accuracy (0-4)**: Time range fidelity, metric semantics, no fabricated data
- **Relevance to Question (0-3)**: Direct answers, clear conclusions
- **Completeness (0-3)**: Coverage of requested aspects, actionable recommendations
- **Bonus (0-1)**: Multi-source correlation when appropriate

## Data Flow

### Complete Workflow
1. **Input Preparation**: JSONL test cases with provider-specific questions
2. **Test Case Generation**: Convert to WebSocket format with configurations
3. **WebSocket Testing**: Execute against PQL generation endpoints
4. **Log Processing**: Parse WebSocket logs into structured results
5. **Quality Evaluation**: Assess both PQL and analysis quality
6. **Reporting**: Generate comprehensive evaluation reports

### File Flow
```
input.jsonl
    ↓ make_test_cases.py
test_cases.json
    ↓ run_grun.py
runs/YYYYMMDD-HHMMSS.log
    ↓ consume_logs.py
test_results.json
    ↓ [eval_pql.py + eval_analysis.py]
evaluation_reports/
```

## Usage

### Environment Setup
```bash
# Required environment variables
export OPENAI_API_TOKEN="your-openai-api-key"
# Install dependencies
uv pip install websockets deepeval pandas transformers
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### Basic Workflow
```bash
# 1. Generate test cases (if needed)
python3 make_test_cases.py input.jsonl --output test_cases.json

# 2. Run WebSocket tests
python3 run_grun.py \
  --test-cases test_cases.json \
  --host localhost \
  --port 9999 \
  --endpoint-id default \
  --runs-dir runs

# 3. Parse logs to structured results
python3 consume_logs.py runs/20250101-120000.log --output test_results.json

# 4. Evaluate PQL quality
python3 eval_pql.py --input test_results.json --model gpt-4.1-mini

# 5. Evaluate analysis quality
python3 eval_analysis.py \
  --input test_results.json \
  --actual-mode executive_summary \
  --model gpt-4.1-mini
```

### Advanced Usage Examples
```bash
# Filter evaluation by provider
python3 eval_pql.py --input test_results.json --where-filter aws-cw
python3 eval_pql.py --input test_results.json --name-contains prometheus

# Different analysis evaluation modes
python3 eval_analysis.py --input test_results.json --actual-mode key_findings
python3 eval_analysis.py --input test_results.json --actual-mode full --where-filter loki
```

## Configuration

### Provider Configurations
- **prometheus**: `where: prometheus, when: 1h, useVectorSearch: true`
- **aws/cloudwatch**: `where: aws-cw, when: 24h, useVectorSearch: true`
- **default**: `where: <provider>, when: 1h, useVectorSearch: true`

### WebSocket Configuration
- **Default Host**: `localhost:9999`
- **Endpoint Pattern**: `ws://{host}:{port}/story/ep/{endpoint_id}/grun/ws`
- **Timeout**: 300 seconds per test case
- **Retry Logic**: Built-in connection retry with exponential backoff

### Evaluation Configuration
- **Default Model**: `gpt-4.1-mini`
- **Scoring Range**: 1-10 (10 being highest quality)
- **Threshold**: 0.8 (for pass/fail determination)
- **Output Format**: JSON with scores, reasons, and suggestions

## Dependencies

### Python Packages
- `websockets`: WebSocket client implementation
- `deepeval`: LLM evaluation framework
- `pandas`: Data processing and analysis
- `transformers`: For model integrations
- `torch`: Deep learning framework dependency

### External Services
- **WebSocket Endpoints**: PQL generation service
- **OpenAI API**: For evaluation models (GPT-4, GPT-3.5-turbo)
- **Autoptic API**: For authenticated access to PQL services

## Error Handling

### Common Issues
1. **WebSocket Connection Failures**
   - Check endpoint availability and API tokens
   - Verify network connectivity and firewall settings
   - Review timeout configurations

2. **OpenAI API Errors**
   - Validate API token and quota limits
   - Check model availability and rate limits
   - Verify evaluation request format

3. **Test Case Format Issues**
   - Ensure JSONL input format is valid
   - Check required fields are present
   - Validate provider-specific configurations

### Troubleshooting
```bash
# Validate test cases before execution
python3 make_test_cases.py --quiet input.jsonl --output /tmp/test_validation.json

# Check WebSocket connectivity
curl -H "x-api-token: $AUTOPTIC_API_TOKEN" http://localhost:9999/health

# Validate log parsing
python3 consume_logs.py --help
```

## Integration Notes

### Airflow Translation Considerations
- **File Paths**: Adapt for GitSync mounted paths (`/opt/airflow/dags/repo/`)
- **Async Operations**: WebSocket operations need Airflow-compatible execution
- **XCom Integration**: Results need to be passed between Airflow tasks
- **Error Handling**: Airflow-specific retry and failure handling
- **Environment Variables**: Use Airflow Variables and Connections

### Performance Considerations
- **Batch Processing**: Large test suites may need batching
- **Memory Management**: Monitor memory usage during evaluation
- **Timeout Configuration**: Adjust for production environments
- **Parallel Execution**: Consider parallel test execution for scale

## Output Formats

### Test Results Structure
```json
{
  "run_info": {
    "timestamp": "2025-01-01T12:00:00Z",
    "endpoint_id": "default",
    "websocket_url": "ws://localhost:9999/..."
  },
  "test_cases": [
    {
      "name": "Test Case Name",
      "session_id": "uuid",
      "status": "success|error|incomplete",
      "duration": 45.2,
      "request": { "prompt": "...", "where": "aws-cw" },
      "responses": [...],
      "final_result": {
        "executive_summary": "...",
        "key_findings": "...",
        "recommendations": "..."
      }
    }
  ],
  "summary": {
    "total_tests": 10,
    "successful_tests": 8,
    "failed_tests": 1,
    "incomplete_tests": 1,
    "success_rate": 0.8,
    "average_duration": 42.5
  }
}
```

### Evaluation Output Structure
```json
{
  "test_case": "Test Name",
  "score": 8,
  "reason": "High quality PQL with proper structure and metrics",
  "suggestion": null,
  "evaluation_details": {
    "time_range_fidelity": 2,
    "metric_correctness": 3,
    "dimensions_grouping": 2,
    "structure_quality": 1,
    "focus_parsimony": 0
  }
}
```