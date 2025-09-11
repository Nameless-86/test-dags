import os
import json
import pandas as pd
import uuid
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams


def load_metrics_dataframe(json_path: str) -> pd.DataFrame:
    """
    Load a metrics JSON file and convert it to a pandas DataFrame.
    Each object should have:
      - 'query' (dict): the metric query
      - 'description' (str): human-readable description
      - Any additional fields will become extra columns (optional)
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"File not found: {json_path}")

    with open(json_path) as f:
        json_data = json.load(f)

    metrics_df = pd.DataFrame(json_data)
    return metrics_df


def load_all_metrics_dataframes(folder_path: str) -> dict:
    """
    Load all JSON files from a directory as DataFrames.
    The dictionary key is the base filename (without extension).
    """
    dataframe_dict = {}
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            key = os.path.splitext(filename)[0]
            metrics_df = load_metrics_dataframe(file_path)
            dataframe_dict[key] = metrics_df
    return dataframe_dict


def create_qdrant_collection_if_needed(client: QdrantClient, collection_name: str):
    """
    Create a Qdrant collection if it does not already exist.
    Uses cosine distance and vector size 1024.
    """
    existing_collections = client.get_collections().collections
    for collection in existing_collections:
        if collection.name == collection_name:
            return collection_name

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    )
    return collection_name


def populate_qdrant_with_embeddings(
    client: QdrantClient,
    metrics_df: pd.DataFrame,
    collection_name: str,
    embedder,
    dry_run=False,
):
    """
    Embed each metric using the embedder, and upsert as vector points in Qdrant.
    The embedding context is a string with the query and description.
    Payload includes the original query, description, and any extra fields.
    """
    batch_size = 200
    batch_points = []
    num_rows = len(metrics_df)

    for row_index, (_, metric_row) in enumerate(metrics_df.iterrows()):
        # Convert the query dict to a plain string
        query_as_text = json.dumps(metric_row["query"], ensure_ascii=False)
        # Build the embedding context
        embedding_context = (
            f"query: {query_as_text}\ndescription: {metric_row['description']}"
        )

        # Generate the embedding vector
        embedding_vector = embedder.embed_batch([embedding_context])[0]

        # Build the Qdrant payload
        payload = {
            "query": metric_row["query"],
            "description": metric_row["description"],
        }
        # Add any other extra fields from the dataframe to the payload
        for column in metrics_df.columns:
            if column not in ["query", "description"]:
                payload[column] = metric_row[column]

        # Build the Qdrant point
        point = {
            "id": str(uuid.uuid4()),
            "vector": embedding_vector,
            "payload": payload,
        }
        batch_points.append(point)
        # Upsert in batches unless in dry run mode
        is_batch_full = len(batch_points) >= batch_size
        if is_batch_full and not dry_run:
            client.upsert(collection_name=collection_name, points=batch_points)
            batch_points = []

    # Upsert any remaining points
    if batch_points and not dry_run:
        client.upsert(collection_name=collection_name, points=batch_points)

    message = "Prepared" if dry_run else "Loaded"
