# -*- coding: utf-8 -*-
"""
Semantic Search + Hybrid Search + Evaluation

Extension Task:
Implement formal information retrieval evaluation.
We introduce a small ground truth testing set and calculate:
1. MRR  - Mean Reciprocal Rank
2. nDCG - Normalized Discounted Cumulative Gain

This mathematically proves how well our hybrid search engine performs.
"""

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, util


# -----------------------------
# 1. Sample Dataset
# -----------------------------

corpus = [
    "How to hard-reset your iPhone 13 if the touch screen is completely frozen or unresponsive.",
    "Troubleshooting guide for iOS updates failing on newer Apple mobile devices.",
    "The new Samsung Galaxy S26 Ultra features an advanced generative AI camera system.",
    "Steps to recover a lost Google Pixel account recovery phrase or authentication token.",
    "Fixing Wi-Fi connectivity drops and network configuration errors on Apple Macbook laptops.",
    "Why is my smartphone battery draining so quickly? Top power optimization tips.",
]

print(f"Loaded database with {len(corpus)} technical documents.")


# -----------------------------
# 2. Sparse Search - BM25
# -----------------------------

tokenized_corpus = [doc.lower().split() for doc in corpus]
bm25 = BM25Okapi(tokenized_corpus)

def sparse_search(query, top_n=5):
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    top_indices = np.argsort(scores)[::-1][:top_n]

    return [(int(idx), float(scores[idx])) for idx in top_indices if scores[idx] > 0]


print("Sparse test search for 'iPhone 13':", sparse_search("iPhone 13"))


# -----------------------------
# 3. Dense Search - Sentence Transformer
# -----------------------------

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

corpus_embeddings = embedding_model.encode(
    corpus,
    convert_to_tensor=True
)

def dense_search(query, top_n=5):
    query_embedding = embedding_model.encode(query, convert_to_tensor=True)

    cos_scores = util.cos_sim(query_embedding, corpus_embeddings)[0]

    top_indices = np.argsort(cos_scores.cpu().numpy())[::-1][:top_n]

    return [(int(idx), float(cos_scores[idx])) for idx in top_indices]


print("Dense test search for 'pixels in camera':", dense_search("pixels in camera"))


# -----------------------------
# 4. Reciprocal Rank Fusion
# -----------------------------

def reciprocal_rank_fusion(sparse_results, dense_results, k=60, top_n=3):
    rrf_scores = {}

    for rank, (doc_id, _) in enumerate(sparse_results):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, (doc_id, _) in enumerate(dense_results):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    fused_rankings = sorted(
        rrf_scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    return fused_rankings[:top_n]


# -----------------------------
# 5. Hybrid Search Engine
# -----------------------------

def hybrid_search_engine(query, top_n=3, show_output=True):
    sparse_res = sparse_search(query, top_n=10)
    dense_res = dense_search(query, top_n=10)

    hybrid_res = reciprocal_rank_fusion(
        sparse_res,
        dense_res,
        k=60,
        top_n=top_n
    )

    if show_output:
        print(f"\n==== TARGET QUERY: '{query}' ====")

        for rank, (doc_id, rrf_score) in enumerate(hybrid_res):
            print(f"\n[Rank {rank + 1}] (RRF Score: {rrf_score:.4f})")
            print(f"Document #{doc_id}: {corpus[doc_id]}")

    return hybrid_res


# -----------------------------
# 6. Search Tests
# -----------------------------

hybrid_search_engine("Apple mobile device issues")

hybrid_search_engine("Macbook laptop battery optimization")


# -----------------------------------------------------
# 7. Extension Task: Formal IR Evaluation
# -----------------------------------------------------
# We now create a small ground truth dataset.
# Each query has relevant documents with relevance scores.
#
# Relevance score meaning:
# 3 = highly relevant
# 2 = relevant
# 1 = slightly relevant
# 0 = not relevant

ground_truth = {
    "iPhone frozen screen reset": {
        0: 3,
        1: 1
    },
    "Apple mobile device update issue": {
        1: 3,
        0: 2
    },
    "Samsung AI camera": {
        2: 3
    },
    "Google Pixel account recovery": {
        3: 3
    },
    "Macbook Wi-Fi network problem": {
        4: 3
    },
    "smartphone battery saving tips": {
        5: 3
    },
    "Macbook laptop battery optimization": {
        5: 3,
        4: 2
    }
}


# -----------------------------
# 8. MRR Calculation
# -----------------------------

def calculate_mrr(results, relevant_docs):
    """
    MRR = Mean Reciprocal Rank

    For one query:
    Reciprocal Rank = 1 / rank of first relevant document

    Example:
    If first relevant doc appears at rank 1, score = 1/1 = 1.0
    If first relevant doc appears at rank 3, score = 1/3 = 0.333
    """

    for rank, (doc_id, _) in enumerate(results, start=1):
        if doc_id in relevant_docs:
            return 1.0 / rank

    return 0.0


# -----------------------------
# 9. nDCG Calculation
# -----------------------------

def calculate_dcg(relevance_scores):
    """
    DCG = Discounted Cumulative Gain

    Higher relevance at top rank gets more reward.
    Lower rank results are discounted.
    """

    dcg = 0.0

    for i, relevance in enumerate(relevance_scores):
        rank = i + 1
        dcg += relevance / np.log2(rank + 1)

    return dcg


def calculate_ndcg(results, relevant_docs, top_n=3):
    """
    nDCG = Normalized Discounted Cumulative Gain

    nDCG = DCG / Ideal DCG

    Value range:
    1.0 = perfect ranking
    0.0 = poor ranking
    """

    actual_relevances = []

    for doc_id, _ in results[:top_n]:
        actual_relevances.append(relevant_docs.get(doc_id, 0))

    dcg = calculate_dcg(actual_relevances)

    ideal_relevances = sorted(
        relevant_docs.values(),
        reverse=True
    )[:top_n]

    idcg = calculate_dcg(ideal_relevances)

    if idcg == 0:
        return 0.0

    return dcg / idcg


# -----------------------------
# 10. Run Full Evaluation
# -----------------------------

def evaluate_search_engine(ground_truth, top_n=3):
    mrr_scores = []
    ndcg_scores = []

    print("\n\n========== FORMAL SEARCH EVALUATION ==========")

    for query, relevant_docs in ground_truth.items():
        results = hybrid_search_engine(
            query,
            top_n=top_n,
            show_output=False
        )

        mrr = calculate_mrr(results, relevant_docs)
        ndcg = calculate_ndcg(results, relevant_docs, top_n=top_n)

        mrr_scores.append(mrr)
        ndcg_scores.append(ndcg)

        print(f"\nQuery: {query}")
        print("Returned Docs:", [doc_id for doc_id, _ in results])
        print("Relevant Docs:", list(relevant_docs.keys()))
        print(f"MRR: {mrr:.4f}")
        print(f"nDCG@{top_n}: {ndcg:.4f}")

    mean_mrr = np.mean(mrr_scores)
    mean_ndcg = np.mean(ndcg_scores)

    print("\n========== FINAL EVALUATION RESULT ==========")
    print(f"Mean Reciprocal Rank: {mean_mrr:.4f}")
    print(f"Mean nDCG@{top_n}: {mean_ndcg:.4f}")


evaluate_search_engine(ground_truth, top_n=3)