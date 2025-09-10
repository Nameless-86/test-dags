from os import getenv
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from qdrant_docsearch import VectorCollection, DocumentSearcher
from e5_embedder import E5Embedder

QDRANT_URL = getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDING_DIM = 1024  # e5-large

client = QdrantClient(url=QDRANT_URL)
app = FastAPI(title="embedds API w/ Qdrant")
model = E5Embedder("/app/local_e5_model")

# --- Pydantic Schemas ---


class Texts(BaseModel):
    inputs: List[str] = Field(..., example=["Hi", "other Doc"])


class SearchRequest(BaseModel):
    query: str = Field(..., example="CPU usage high")
    top_k: int = Field(5, ge=1, le=100, example=5)
    collection: str = Field(..., example="prometheus")


# --- Endpoints ---


@app.post("/search")
async def search(req: SearchRequest):
    try:
        vector_collection = VectorCollection(
            client, req.collection, embedding_dim=EMBEDDING_DIM, create_if_missing=False
        )
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Collection '{req.collection}' not found."
        )

    document_searcher = DocumentSearcher(vector_collection, model)
    results = document_searcher.search(req.query, top_k=req.top_k)

    if not results:
        raise HTTPException(status_code=404, detail="No results found.")

    # Retorna todos los resultados:
    return {"result": results}


@app.post("/embed")
async def embed(req: Texts):
    embeddings = model.embed_batch(req.inputs)
    return {"embeddings": embeddings}
