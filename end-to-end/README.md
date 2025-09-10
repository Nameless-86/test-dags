python3 run_grun.py \
  --api-token your-api-token-here \
  --test-cases test_cases.json \
  --runs-dir runs

python3 eval_pql.py --input results.json
python3 eval_pql.py --input results.json --where-filter aws-cw
python3 eval_pql.py --input results.json --name-contains prometheus

python3 eval_analysis.py --input results.json --actual-mode executive_summary
python3 eval_analysis.py --input results.json --actual-mode key_findings
python3 eval_analysis.py --input results.json --actual-mode full --where-filter loki
