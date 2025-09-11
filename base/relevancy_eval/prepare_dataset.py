import argparse
import json
import time
from langchain_ollama import ChatOllama
from pathlib import Path


def extract_provider_name(input_path: str) -> str:
    """
    Extracts the provider name from the input file path.
    E.g. '../vector/cloudwatch.json' -> 'cloudwatch'
    """
    return Path(input_path).stem.lower()


def build_prompt(provider: str, metric_information: str, description: str) -> str:
    """
    Create a prompt that makes the LLM craft ONE realistic SRE / DevOps-style
    question about the metric, without injecting regions or time windows.
    The resulting question must:
      • fit in ≤ 25 words
      • focus on meaning, thresholds, spikes / drops, or actionable correlation
      • mention at most ONE extra metric if that helps surface a potential issue
      • contain no pre-/post-amble — only the question itself
    """
    return (
        "You are an on-call SRE investigating production incidents.\n"
        f"Below is a metric from {provider}. Write ONE natural-language question "
        "that would help diagnose a problem or decide an action.\n"
        "Constraints:\n"
        "  • ≤ 25 words, plain English, one sentence.\n"
        "  • Do NOT mention time ranges, regions, dashboards, or queries.\n"
        "  • You MAY reference thresholds (e.g., “exceed ten”), spikes/drops, or\n"
        "    correlate with ONE other metric only if that correlation could signal\n"
        "    a performance or availability issue.\n"
        "  • Output ONLY the question, no bullets, no explanation.\n\n"
        "Examples (follow the style, not the content):\n"
        "Metric Name: AnomalousHostCount\n"
        "Technical description: Number of hosts flagged as anomalous by built-in detection.\n"
        "Question: Does the AnomalousHostCount exceed ten, indicating a potential outbreak?\n\n"
        "Metric Name: HealthyHostCount\n"
        "Technical description: Count of targets passing health checks.\n"
        "Question: Do drops in HealthyHostCount correlate with spikes in UnHealthyHostCount?\n\n"
        f"Metric information: {metric_information}\n"
        f"Technical description: {description}\n"
        "Question:"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate natural-language evaluation queries from metric definitions using an LLM."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input JSON file (e.g., vector/cloudwatch.json)",
    )
    parser.add_argument(
        "--output",
        default="eval_queries.jsonl",
        help="Output JSONL file for generated queries",
    )
    parser.add_argument(
        "--limit", type=int, default=1000, help="Maximum number of queries to generate"
    )
    args = parser.parse_args()

    provider = extract_provider_name(args.input)

    # Load metric definitions from input JSON file
    with open(args.input, "r") as f:
        metrics = json.load(f)

    # Initialize the LLM client
    llm = ChatOllama(
        model="llama3.1:8b",
        temperature=0.1,
        base_url="https://5222377d817f.ngrok-free.app/",
    )

    generated = 0
    id_width = len(str(min(args.limit, len(metrics))))

    with open(args.output, "w") as outfile:
        for idx, metric in enumerate(metrics):
            if generated >= args.limit:
                break  # Stop if we have reached the user-defined limit

            # Extract metric name and description (handle both possible formats)
            metric_information = metric.get("query", {})
            description = metric.get("description")

            # Skip if either field is missing
            if not metric_information or not description:
                print(
                    f"[WARN] Skipping entry {idx+1}: missing MetricName or description"
                )
                continue

            # Build the LLM prompt
            prompt = build_prompt(provider, metric_information, description)

            # Call the LLM to generate the question
            try:
                response = llm.invoke(prompt)
                question = response.content.strip()
                if not question or question.lower().startswith("error"):
                    print(f"[WARN] No valid question generated for entry {idx+1}")
                    continue
            except Exception as e:
                print(f"[ERROR] LLM call failed for entry {idx+1}: {e}")
                continue

            # Build the output dictionary
            output_entry = {
                "id": f"{provider}_{str(generated + 1).zfill(id_width)}",
                "provider": provider,
                "metric_information": metric_information,
                "generated_question": question,
            }

            # Write as a JSON line
            outfile.write(json.dumps(output_entry) + "\n")
            print(f"[OK] {output_entry['id']}")

            generated += 1
            time.sleep(0.65)  # Small delay to avoid rate limiting

    print(f"\n✅ Done. {generated} queries written to {args.output}")


if __name__ == "__main__":
    main()
