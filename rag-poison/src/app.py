import os
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# Initialize the 'Secure-by-Design' perspective: 
# Even "legitimate" looking data can be a carrier for an attack.
model = SentenceTransformer('all-MiniLM-L6-v2')

def load_data(file_path):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def run_simulation():
    # 1. Ingesting Enterprise Reality (Internal Policy)
    kb_docs = load_data('data/internal_kb.txt')
    
    # 2. Ingesting the Attack (Simulating an indexed malicious email)
    poison_docs = load_data('data/malicious_input.txt')
    
    all_docs = kb_docs + poison_docs
    embeddings = model.encode(all_docs)

    # Setup Vector DB
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    # 3. The Query
    user_query = "How should I update my payroll information?"
    query_vector = model.encode([user_query])
    
    # Search for the most relevant context
    D, I = index.search(np.array(query_vector), k=1)
    retrieved_context = all_docs[I[0][0]]

    print(f"\n[ARCHITECT LOG] User Query: {user_query}")
    print(f"[ARCHITECT LOG] Retrieved Context: {retrieved_context}")
    print("-" * 50)
    print(f"FINAL LLM INPUT: Answer the user query using this context: {retrieved_context}")

if __name__ == "__main__":
    run_simulation()
