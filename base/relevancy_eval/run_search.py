import json
import argparse
import requests
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input eval_queries.jsonl file")
    parser.add_argument(
        "--output",
        default="search_results.jsonl",
        help="Output JSONL file for search results",
    )
    parser.add_argument(
        "--search-url", required=True, help="URL of your /search endpoint"
    )
    parser.add_argument("--collection", required=True, help="Qdrant collection name")
    parser.add_argument(
        "--top_k", type=int, default=5, help="Number of results to retrieve per query"
    )
    args = parser.parse_args()

    provider = args.collection

    with open(args.input) as fin, open(args.output, "w") as fout:
        for line in fin:
            entry = json.loads(line)
            payload = {
                "collection": provider,
                "query": entry["generated_question"],
                "top_k": args.top_k,
            }
            try:
                resp = requests.post(args.search_url, json=payload, timeout=20)
                resp.raise_for_status()
                results = resp.json().get("result", [])
                if not results:
                    print(f"[WARN] No results for {entry['id']}")
                    continue

                if isinstance(results, dict):
                    results = [results]

                output_results = []
                for res in results:
                    description = res["payload"].get("description", "")
                    metric_information = res["payload"].get("query", "")
                    output_results.append(
                        {
                            "Metric information": metric_information,
                            "Description": description,
                            "score": res.get("score"),
                            "id": res.get("id"),
                        }
                    )

                out_entry = {
                    "id": entry["id"],
                    "query": entry["generated_question"],
                    "Metric Information": entry.get("metric_information"),
                    "results": output_results,
                }
                fout.write(json.dumps(out_entry) + "\n")
                print(f"[OK] {entry['id']}")

            except Exception as e:
                print(f"[ERROR] Query failed for {entry['id']}: {e}")


if __name__ == "__main__":
    main()
