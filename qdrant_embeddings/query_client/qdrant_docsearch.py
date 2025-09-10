from qdrant_client import QdrantClient
from qdrant_client.http.models import ScoredPoint
from qdrant_client.http import models as qmodels


class VectorCollection:
    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding_dim: int = 1024,
        create_if_missing: bool = True,
    ):
        self.client = client
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        if create_if_missing:
            self._ensure_collection_exists()
        else:
            self._verify_exists()

    def _verify_exists(self):
        collections = [col.name for col in self.client.get_collections().collections]
        if self.collection_name not in collections:
            raise ValueError(f"Collection '{self.collection_name}' does not exist.")

    def _ensure_collection_exists(self):
        collections = [col.name for col in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=self.embedding_dim, distance=qmodels.Distance.COSINE
                ),
            )

    def get_name(self):
        return self.collection_name

    def upsert_documents(self, texts: list[str], embedder) -> list[int]:
        """Embed and upsert texts into Qdrant, returning point ids."""

        embeddings = embedder.embed_batch(texts)
        start_id = self.client.count(self.collection_name).count
        points = [
            qmodels.PointStruct(id=i, vector=emb, payload={"text": txt})
            for i, (emb, txt) in enumerate(zip(embeddings, texts), start=start_id)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)
        return [p.id for p in points]


class DocumentSearcher:
    def __init__(self, vector_collection: VectorCollection, embedding_model):
        self.vector_collection = vector_collection
        self.embedding_model = embedding_model

    def search(self, query: str, top_k: int = 3):
        collection_name = self.vector_collection.get_name()
        vector = self.embedding_model.embed_batch([query])[0]

        results: list[ScoredPoint] = self.vector_collection.client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
            with_vectors=True,
        )

        return [
            {
                "id": hit.id,
                "payload": hit.payload,
                "score": hit.score,
                "vector": hit.vector,
            }
            for hit in results
        ]
