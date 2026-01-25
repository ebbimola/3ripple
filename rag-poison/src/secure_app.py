import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

model = SentenceTransformer('all-MiniLM-L6-v2')


def load_data(file_path):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def run_secure_simulation():
    # 1. Structured Ingestion (The Architect's Way)
    # We maintain a mapping of index IDs to metadata
    metadata_map = {}
    all_docs = []

    # Ingest Trusted Data
    internal_docs = load_data('data/internal_kb.txt')
    for d in internal_docs:
        metadata_map[len(all_docs)] = {"source": "INTERNAL"}
        all_docs.append(d)

    # Ingest Untrusted Data (The Poison)
    external_docs = load_data('data/malicious_input.txt')
    for d in external_docs:
        metadata_map[len(all_docs)] = {"source": "EXTERNAL_INGEST"}
        all_docs.append(d)

    # 2. Vectorization
    embeddings = model.encode(all_docs)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(np.array(embeddings))

    # 3. Secure Retrieval Logic
    user_query = "How should I update my payroll information?"
    query_vector = model.encode([user_query])

    # We ask for the top 5 matches to ensure we find an internal one
    D, I = index.search(np.array(query_vector), k=5)

    print(f"\n[ARCHITECT LOG] Security Layer Active: Applying Metadata Filter...")

    filtered_context = None
    for hit_idx in I[0]:
        if metadata_map[hit_idx]["source"] == "INTERNAL":
            filtered_context = all_docs[hit_idx]
            break  # We found the most relevant TRUSTED document

    if filtered_context:
        print(f"[ARCHITECT LOG] Validation Passed. Source: INTERNAL")
        print(f"SECURE OUTPUT: {filtered_context}")
    else:
        print(f"[ALERT] No trusted context found. Blocking LLM generation to prevent hallucination/poisoning.")


if __name__ == "__main__":
    run_secure_simulation()