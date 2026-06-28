"""Legacy optional Qdrant uploader.

The v1 pipeline uses ``legal_lm.rag.LocalVectorStore`` by default. This module
is kept only for older experiments and intentionally performs no cloud
connection on import.
"""

from __future__ import annotations

import os
import hashlib
import uuid

from bs4 import BeautifulSoup
from cleantext import clean
from dotenv import load_dotenv


QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "web_content")


class LocalHashEmbedding:
    def embed_query(self, text: str, size: int = 64):
        digest = hashlib.sha256(text.lower().encode("utf-8", errors="ignore")).digest()
        return [((digest[index % len(digest)] / 127.5) - 1.0) for index in range(size)]


def _get_clients():
    load_dotenv()
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url or not qdrant_api_key:
        raise RuntimeError(
            "Qdrant uploader is a legacy optional utility. Set QDRANT_URL, "
            "and QDRANT_API_KEY to use it, or use legal_lm.rag for the "
            "default local retrieval path."
        )

    from qdrant_client import QdrantClient

    qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    embedding_model = LocalHashEmbedding()
    return qdrant_client, embedding_model


def ensure_collection():
    qdrant_client, _ = _get_clients()
    from qdrant_client.models import VectorParams

    existing = qdrant_client.get_collections().collections
    if QDRANT_COLLECTION in [col.name for col in existing]:
        qdrant_client.delete_collection(collection_name=QDRANT_COLLECTION)

    qdrant_client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=64, distance="Cosine"),
    )


def extract_text_from_html(html_path: str) -> str:
    with open(html_path, "r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    return " ".join(text.split())


def chunk_text(text: str, chunk_size: int = 1000):
    words = text.split()
    return [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]


def upload_html_to_cloud_qdrant(html_path: str, title_prefix: str = "Legal HTML Document"):
    qdrant_client, embedding_model = _get_clients()
    ensure_collection()

    raw_text = extract_text_from_html(html_path)
    cleaned_text = clean(
        raw_text,
        fix_unicode=True,
        to_ascii=True,
        lower=True,
        no_line_breaks=True,
        lang="en",
    )

    chunks = chunk_text(cleaned_text)
    for idx, chunk in enumerate(chunks):
        point_id = str(uuid.uuid4())
        qdrant_client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[
                {
                    "id": point_id,
                    "vector": embedding_model.embed_query(text=chunk),
                    "payload": {
                        "title": f"{title_prefix} - Part {idx + 1}",
                        "content": chunk,
                        "url": "local_html_doc",
                        "source": "html_legal",
                    },
                }
            ],
        )

    print(f"[INFO] Uploaded {len(chunks)} chunks from {html_path} to Qdrant.")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "National Survey of State Laws - HeinOnline.org.html")
    upload_html_to_cloud_qdrant(html_path)
