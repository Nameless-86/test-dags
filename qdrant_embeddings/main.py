from qdrant_utils import (
    load_all_metrics_dataframes,
    create_qdrant_collection_if_needed,
    populate_qdrant_with_embeddings,
)
from qdrant_client import QdrantClient
from e5_embedder import E5Embedder
import os
import time
from qdrant_client.http.exceptions import ResponseHandlingException


def wait_for_qdrant_ready(qdrant_client, max_retries=10, retry_delay=5):
    """
    Wait for the Qdrant instance to become available.
    Retries several times before raising an exception.
    """
    for attempt in range(max_retries):
        try:
            qdrant_client.get_collections()
            print("Successfully connected to Qdrant")
            return True
        except ResponseHandlingException as e:
            if attempt < max_retries - 1:
                print(
                    f"Waiting for Qdrant to be ready (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(retry_delay)
            else:
                print("Failed to connect to Qdrant after maximum retries")
                raise e


if __name__ == "__main__":
    # Get Qdrant connection URL from environment or use default
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    print(f"Connecting to Qdrant at {qdrant_url}")
    qdrant_client = QdrantClient(url=qdrant_url)

    # Wait until Qdrant is ready to receive requests
    wait_for_qdrant_ready(qdrant_client)

    # Initialize the embedding model
    embedder = E5Embedder("intfloat/e5-large-v2")

    # Load all metrics DataFrames from the target directory
    metrics_folder = "vector/"
    metrics_dataframes = load_all_metrics_dataframes(metrics_folder)

    # For each metrics DataFrame, create/use a separate Qdrant collection and insert embeddings
    for source_name, metrics_df in metrics_dataframes.items():
        collection_name = f"{source_name}"
        create_qdrant_collection_if_needed(qdrant_client, collection_name)
        print(
            f"Populating collection '{collection_name}' with data from '{source_name}', {len(metrics_df)} records."
        )
        populate_qdrant_with_embeddings(
            qdrant_client, metrics_df, collection_name, embedder
        )

    print("All embeddings loaded successfully.")
