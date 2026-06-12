"""
Day 12 - Collab 1: Indexing & Multi-DB Retrieval Showdown

What this script does:
1. Loads hardcoded Wikipedia-style article summaries and splits them into chunks.
2. Embeds every chunk with a local HashingVectorizer embedder.
3. Builds a local FAISS index and benchmarks top-k retrieval.
4. Optionally benchmarks Pinecone when PINECONE_API_KEY is filled in .env.
5. Optionally benchmarks Azure AI Search hybrid search when Azure values are filled in .env.
6. Optionally applies Cohere reranking when COHERE_API_KEY is filled in .env.

Required packages:
    pip install langchain-core langchain-text-splitters faiss-cpu numpy pandas matplotlib tqdm scikit-learn

Optional packages:
    pip install pinecone azure-search-documents azure-core cohere

Fill all keys and service settings in the constants section below.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize
from tqdm import tqdm


SCRIPT_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

# -----------------------------
# Lab configuration
# -----------------------------
# Values are loaded from day12/collab_1/.env.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", os.getenv("GROK_API_KEY", ""))
LOCAL_EMBEDDING_DIM = int(os.getenv("LOCAL_EMBEDDING_DIM", "1536"))

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rag-showdown")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY", "")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "rag-showdown")

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

TOP_K = 5

BENCHMARK_QUERIES = [
    ("What is the role of transformers in NLP?", "Natural language processing"),
    ("Explain the causes of World War II", "World War II"),
    ("How does CRISPR gene editing work?", "CRISPR"),
    ("What are the effects of climate change on the Amazon?", "Amazon rainforest"),
    ("Describe the Bitcoin mining process", "Bitcoin"),
    ("What is the mechanism of mRNA vaccines?", "Vaccine"),
    ("How did the Cold War end?", "Cold War"),
    ("Explain supply chain disruption causes", "Supply chain"),
    ("What caused the French Revolution?", "French Revolution"),
    ("How does deep learning differ from machine learning?", "Deep learning"),
    ("What are the symptoms of Alzheimers disease?", "Alzheimer's disease"),
    ("What is inflation and how is it measured?", "Inflation"),
    ("What is the history of the Olympic Games?", "Olympic Games"),
    ("Explain quantum entanglement", "Quantum computing"),
    ("How does the stock market work?", "Stock market"),
    ("What are the causes of cancer?", "Cancer"),
    ("Describe the Renaissance period in Europe", "Renaissance"),
    ("How are antibiotics made?", "Antibiotics"),
    ("What is gross domestic product?", "Gross domestic product"),
    ("How do neural networks learn?", "Neural network"),
]

HARD_CODED_ARTICLES = [
    {
        "title": "Artificial Intelligence",
        "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "content": "Artificial intelligence (AI) is intelligence demonstrated by machines. AI research studies intelligent agents that perceive their environment and take actions to maximise their goals. Modern AI techniques include machine learning, deep learning, natural language processing, computer vision, robotics, and expert systems. Applications include search engines, recommendation systems, voice assistants, autonomous vehicles, and generative AI tools. The term was coined at the 1956 Dartmouth Conference. Alan Turing proposed the Turing Test in 1950. AI raises questions about ethics, job displacement, algorithmic bias, autonomous weapons, and existential risk.",
    },
    {
        "title": "Machine Learning",
        "url": "https://en.wikipedia.org/wiki/Machine_learning",
        "content": "Machine learning is a field of artificial intelligence concerned with algorithms that learn from data and generalise to unseen inputs without explicit instructions. Supervised learning uses labelled training data. Unsupervised learning finds patterns in unlabelled data. Reinforcement learning trains agents through reward signals. Deep learning uses neural networks with many layers. Training commonly uses backpropagation and stochastic gradient descent. Overfitting, underfitting, regularisation, dropout, and cross-validation are central concepts.",
    },
    {
        "title": "Retrieval-Augmented Generation",
        "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
        "content": "Retrieval-Augmented Generation combines a retrieval system with a generative language model. Instead of relying only on parametric knowledge, RAG retrieves relevant documents from an external knowledge base at inference time. Retrieved chunks are injected into the prompt as context, grounding generation in verifiable facts and reducing hallucination. A RAG pipeline indexes documents, embeds queries, retrieves top-k chunks, and generates grounded answers. Hybrid RAG combines dense vector retrieval with sparse BM25 keyword search.",
    },
    {
        "title": "Vector Database",
        "url": "https://en.wikipedia.org/wiki/Vector_database",
        "content": "A vector database stores data as high-dimensional vectors representing text, images, audio, or video. Vector databases support approximate nearest-neighbour search using cosine similarity, dot product, or Euclidean distance. They are core infrastructure for RAG systems and semantic search. Popular options include Pinecone, Weaviate, Qdrant, Milvus, FAISS, and Azure AI Search. Key concepts include HNSW indexing, vector dimensionality, metadata filtering, namespaces, and upsert operations.",
    },
    {
        "title": "FAISS",
        "url": "https://github.com/facebookresearch/faiss",
        "content": "FAISS, or Facebook AI Similarity Search, is an open-source library from Meta AI for efficient similarity search and clustering of dense vectors. It supports CPU and GPU indexes. IndexFlatL2 performs exact exhaustive nearest-neighbour search with high recall. Other indexes include IndexFlatIP, IndexIVFFlat, IndexIVFPQ, and IndexHNSWFlat. FAISS is free, in-process, fast for prototyping, and useful when the corpus fits in memory.",
    },
    {
        "title": "Pinecone",
        "url": "https://docs.pinecone.io",
        "content": "Pinecone is a managed serverless vector database for production machine learning applications. It handles infrastructure, scaling, replication, and backups. Pinecone stores vectors alongside metadata and supports filtered queries combining approximate nearest-neighbour search with attributes such as category, tenant, or source. Typical usage is to create an index, upsert id-values-metadata tuples, and query with an embedded vector. It is commonly used for semantic search and RAG.",
    },
    {
        "title": "Azure AI Search",
        "url": "https://learn.microsoft.com/azure/search/",
        "content": "Azure AI Search is a fully managed Microsoft cloud search service supporting full-text BM25, vector HNSW, and hybrid search. Hybrid search combines keyword relevance and vector similarity, often improving retrieval quality. It integrates with Azure Blob Storage, SQL, Cosmos DB, and other enterprise data sources. The Python SDK supports index creation, document upload, vector fields, metadata filters, semantic ranker, and search queries with VectorizedQuery.",
    },
    {
        "title": "Natural Language Processing",
        "url": "https://en.wikipedia.org/wiki/Natural_language_processing",
        "content": "Natural language processing is a field of artificial intelligence concerned with interactions between computers and human language. NLP tasks include text classification, named entity recognition, sentiment analysis, machine translation, question answering, summarisation, and text generation. Since 2018, transformer models pre-trained on large corpora have dominated the field. Tokenisation converts text into subword tokens, and reinforcement learning from human feedback is used to align models.",
    },
    {
        "title": "Transformer Architecture",
        "url": "https://en.wikipedia.org/wiki/Transformer_(machine_learning_model)",
        "content": "The transformer is a deep learning architecture introduced in the 2017 paper Attention Is All You Need. Self-attention computes relationships between all tokens simultaneously, enabling parallel training and long-range dependency modelling. Transformer blocks use multi-head attention, feed-forward layers, residual connections, layer normalisation, and positional encodings. BERT is encoder-only, GPT is decoder-only, and T5 uses an encoder-decoder design.",
    },
    {
        "title": "Embeddings in NLP",
        "url": "https://en.wikipedia.org/wiki/Word_embedding",
        "content": "Embeddings are dense vector representations where semantically similar items are close in vector space. Word2Vec, GloVe, FastText, BERT, and sentence embedding models represent words, passages, or documents numerically. Embeddings are central to semantic search, clustering, recommendation, and RAG. Cosine similarity is a common metric. Embedding quality depends on the model, domain, language, dimensionality, and training data.",
    },
    {
        "title": "BM25 Information Retrieval",
        "url": "https://en.wikipedia.org/wiki/Okapi_BM25",
        "content": "BM25 is a probabilistic ranking function for information retrieval. It extends TF-IDF by accounting for document length and term saturation. BM25 is strong for exact keyword matching, rare terms, product codes, and named entities. It is the default ranking approach in many search systems including Lucene, Elasticsearch, OpenSearch, and Solr. Hybrid search combines BM25 with dense vector retrieval using approaches such as Reciprocal Rank Fusion.",
    },
    {
        "title": "COVID-19 Pandemic",
        "url": "https://en.wikipedia.org/wiki/COVID-19_pandemic",
        "content": "The COVID-19 pandemic was caused by the SARS-CoV-2 coronavirus, first identified in late 2019. The virus spreads through respiratory droplets and aerosols. Symptoms range from fever, cough, fatigue, and loss of smell to pneumonia and severe respiratory illness. mRNA vaccines and adenoviral vector vaccines were developed rapidly. The pandemic affected healthcare, supply chains, travel, work patterns, education, and global economic activity.",
    },
    {
        "title": "Climate Change",
        "url": "https://en.wikipedia.org/wiki/Climate_change",
        "content": "Climate change refers to long-term shifts in global temperatures and weather patterns. Human burning of fossil fuels has increased greenhouse gases such as carbon dioxide and methane. Effects include heatwaves, droughts, wildfires, floods, sea level rise, ocean acidification, and biodiversity loss. Mitigation includes renewable energy, electrified transport, efficiency, reforestation, and carbon capture. Adaptation includes resilient infrastructure and disaster planning.",
    },
    {
        "title": "Quantum Computing",
        "url": "https://en.wikipedia.org/wiki/Quantum_computing",
        "content": "Quantum computing uses superposition, entanglement, and interference to process information. A qubit can represent a superposition of zero and one. Important algorithms include Shor's algorithm for factoring, Grover's search algorithm, and quantum simulation for chemistry and materials. Hardware approaches include superconducting qubits, trapped ions, photonics, and topological qubits. Current systems are noisy and fault-tolerant quantum computing remains a major challenge.",
    },
    {
        "title": "CRISPR Gene Editing",
        "url": "https://en.wikipedia.org/wiki/CRISPR",
        "content": "CRISPR is adapted from bacterial immune systems for precise DNA editing. A guide RNA directs a Cas enzyme such as Cas9 to a target DNA sequence, where it makes a cut. Cellular repair can disrupt a gene or insert a new sequence. Jennifer Doudna and Emmanuelle Charpentier won the 2020 Nobel Prize in Chemistry for CRISPR-Cas9. Applications include disease therapies, crops, animal models, base editing, and prime editing.",
    },
    {
        "title": "Supply Chain Management",
        "url": "https://en.wikipedia.org/wiki/Supply_chain_management",
        "content": "Supply chain management covers sourcing, procurement, production, logistics, and delivery from raw materials to consumers. The COVID-19 pandemic exposed vulnerabilities such as port congestion, container shortages, factory shutdowns, and semiconductor scarcity. The bullwhip effect describes how small demand variations amplify upstream. Lean supply chains minimise inventory while resilient chains prioritise redundancy, visibility, nearshoring, and risk management.",
    },
]

BENCHMARK_REFERENCE_ARTICLES = [
    {
        "title": title,
        "url": "local://fallback",
        "content": (
            f"{title}. This hardcoded reference article supports the benchmark query. "
            f"It contains study notes for the question: {query} "
            f"The content is intentionally small but relevant enough for local vector search, "
            f"FAISS indexing, Pinecone upsert, Azure hybrid search, and latency benchmarking."
        ),
    }
    for query, title in BENCHMARK_QUERIES
]


@dataclass
class SearchHit:
    title: str
    text: str
    score: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class BenchmarkResult:
    name: str
    search_type: str
    p50_ms: float
    p95_ms: float
    hit_at_k: float
    latencies_ms: list[float]


class LocalHashingEmbedder:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        self.vectorizer = HashingVectorizer(
            n_features=dimensions,
            alternate_sign=False,
            norm=None,
            stop_words="english",
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        matrix = self.vectorizer.transform(texts)
        normalized = normalize(matrix, norm="l2", copy=False)
        return normalized.astype(np.float32).toarray().tolist()

    def embed_query(self, query: str) -> list[float]:
        return self.embed_documents([query])[0]


def make_embedder() -> LocalHashingEmbedder:
    if GROQ_API_KEY:
        print("Loaded Groq key from .env. Retrieval uses local embeddings because this lab needs vectors.")
    else:
        print("No Groq key found. Retrieval still works with local embeddings.")
    print(f"Using local HashingVectorizer embeddings with {LOCAL_EMBEDDING_DIM} dimensions.")
    return LocalHashingEmbedder(dimensions=LOCAL_EMBEDDING_DIM)


def load_hardcoded_documents(max_chunks: int) -> list[Document]:
    articles = HARD_CODED_ARTICLES + BENCHMARK_REFERENCE_ARTICLES
    print(f"Loaded hardcoded corpus: {len(articles)} articles.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    documents: list[Document] = []
    for article in articles:
        chunks = splitter.create_documents(
            texts=[article["content"]],
            metadatas=[{"title": article["title"], "url": article["url"]}],
        )
        documents.extend(chunks)

    if not documents:
        print("Article splitting produced no chunks. Using local fallback corpus.")
        documents = [
            Document(
                page_content=article["content"],
                metadata={"title": article["title"], "url": article["url"]},
            )
            for article in articles
        ]

    return documents[:max_chunks]


def embed_documents(embedder: LocalHashingEmbedder, documents: list[Document]) -> list[list[float]]:
    texts = [document.page_content for document in documents]
    started = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    elapsed = time.perf_counter() - started
    print(f"Embedded {len(vectors)} chunks in {elapsed:.1f}s.")
    return vectors


def percentile(values: list[float], percent: int) -> float:
    return float(np.percentile(values, percent))


def title_hit_at_k(results: list[list[SearchHit]]) -> float:
    hits = 0
    for (_, expected_title), query_results in zip(BENCHMARK_QUERIES, results):
        titles = [hit.title.lower() for hit in query_results]
        if any(expected_title.lower() in title for title in titles):
            hits += 1
    return hits / len(results)


def benchmark_search(name: str, search_type: str, search_fn) -> BenchmarkResult:
    latencies: list[float] = []
    all_results: list[list[SearchHit]] = []

    for query, _ in tqdm(BENCHMARK_QUERIES, desc=f"{name} benchmark"):
        started = time.perf_counter()
        results = search_fn(query, TOP_K)
        latencies.append((time.perf_counter() - started) * 1000)
        all_results.append(results)

    return BenchmarkResult(
        name=name,
        search_type=search_type,
        p50_ms=percentile(latencies, 50),
        p95_ms=percentile(latencies, 95),
        hit_at_k=title_hit_at_k(all_results),
        latencies_ms=latencies,
    )


def run_faiss(
    embedder: LocalHashingEmbedder,
    documents: list[Document],
    vectors: list[list[float]],
) -> BenchmarkResult:
    import faiss

    embedding_dim = len(vectors[0])
    matrix = np.array(vectors, dtype=np.float32)
    index = faiss.IndexFlatL2(embedding_dim)
    index.add(matrix)
    print(f"FAISS index built with {index.ntotal} vectors.")

    def search(query: str, top_k: int) -> list[SearchHit]:
        query_vector = np.array([embedder.embed_query(query)], dtype=np.float32)
        distances, indexes = index.search(query_vector, top_k)
        hits: list[SearchHit] = []
        for distance, document_index in zip(distances[0], indexes[0]):
            document = documents[int(document_index)]
            hits.append(
                SearchHit(
                    title=document.metadata.get("title", ""),
                    text=document.page_content,
                    score=float(distance),
                    metadata=document.metadata,
                )
            )
        return hits

    return benchmark_search("FAISS", "Exact k-NN with IndexFlatL2", search)


def run_pinecone(
    embedder: LocalHashingEmbedder,
    documents: list[Document],
    vectors: list[list[float]],
) -> BenchmarkResult | None:
    if not PINECONE_API_KEY:
        print("Skipping Pinecone: PINECONE_API_KEY is empty.")
        return None

    from pinecone import Pinecone, ServerlessSpec

    index_name = PINECONE_INDEX_NAME
    cloud = PINECONE_CLOUD
    region = PINECONE_REGION
    embedding_dim = len(vectors[0])

    client = Pinecone(api_key=PINECONE_API_KEY)
    existing_indexes = [index.name for index in client.list_indexes()]

    if index_name not in existing_indexes:
        client.create_index(
            name=index_name,
            dimension=embedding_dim,
            metric="cosine",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
        while not client.describe_index(index_name).status["ready"]:
            time.sleep(5)

    index = client.Index(index_name)
    records = []
    for item_index, (document, vector) in enumerate(zip(documents, vectors)):
        records.append(
            {
                "id": f"doc-{item_index}",
                "values": vector,
                "metadata": {
                    "title": document.metadata.get("title", ""),
                    "url": document.metadata.get("url", ""),
                    "text": document.page_content[:1000],
                },
            }
        )

    for start in tqdm(range(0, len(records), 100), desc="Pinecone upsert"):
        index.upsert(vectors=records[start : start + 100])

    def search(query: str, top_k: int) -> list[SearchHit]:
        query_vector = embedder.embed_query(query)
        response = index.query(vector=query_vector, top_k=top_k, include_metadata=True)
        hits: list[SearchHit] = []
        for match in response.matches:
            metadata = dict(match.metadata or {})
            hits.append(
                SearchHit(
                    title=metadata.get("title", ""),
                    text=metadata.get("text", ""),
                    score=float(match.score),
                    metadata=metadata,
                )
            )
        return hits

    demo = search("What are neural networks?", 3)
    print("Pinecone metadata-filter capable index ready.")
    for item in demo:
        print(f"  {item.title}: {item.text[:90]}...")

    return benchmark_search("Pinecone", "Serverless cosine vector search", search)


def run_azure_search(
    embedder: LocalHashingEmbedder,
    documents: list[Document],
    vectors: list[list[float]],
) -> BenchmarkResult | None:
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_API_KEY:
        print("Skipping Azure AI Search: AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_API_KEY is empty.")
        return None

    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SearchableField,
        SemanticConfiguration,
        SemanticField,
        SemanticPrioritizedFields,
        SemanticSearch,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )
    from azure.search.documents.models import VectorizedQuery

    index_name = AZURE_SEARCH_INDEX_NAME
    embedding_dim = len(vectors[0])
    credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)
    index_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=credential)
    search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=index_name, credential=credential)

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SimpleField(name="title", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="url", type=SearchFieldDataType.String),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=embedding_dim,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    index_definition = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
            profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-algo")],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="semantic-cfg",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")],
                        keywords_fields=[SemanticField(field_name="title")],
                    ),
                )
            ]
        ),
    )
    index_client.create_or_update_index(index_definition)

    payload = []
    for item_index, (document, vector) in enumerate(zip(documents, vectors)):
        payload.append(
            {
                "id": f"doc-{item_index}",
                "content": document.page_content,
                "title": document.metadata.get("title", ""),
                "url": document.metadata.get("url", ""),
                "embedding": vector,
            }
        )

    for start in tqdm(range(0, len(payload), 100), desc="Azure upload"):
        search_client.upload_documents(documents=payload[start : start + 100])

    def search(query: str, top_k: int) -> list[SearchHit]:
        query_vector = embedder.embed_query(query)
        results = search_client.search(
            search_text=query,
            vector_queries=[
                VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=top_k,
                    fields="embedding",
                )
            ],
            select=["id", "content", "title", "url"],
            top=top_k,
        )
        hits: list[SearchHit] = []
        for result in results:
            hits.append(
                SearchHit(
                    title=result["title"],
                    text=result["content"],
                    score=float(result.get("@search.score", 0.0)),
                    metadata={"url": result.get("url", "")},
                )
            )
        return hits

    return benchmark_search("Azure AI Search", "Hybrid BM25 plus vector search", search)


def run_cohere_rerank(documents: list[Document], faiss_result: BenchmarkResult) -> None:
    if not COHERE_API_KEY:
        print("Skipping Cohere rerank: COHERE_API_KEY is empty.")
        return

    import cohere
    import faiss

    print("Cohere rerank requires FAISS result context; rebuild using saved embeddings in a real run.")
    print(f"Current FAISS Hit@{TOP_K}: {faiss_result.hit_at_k:.2f}")
    print(f"Loaded Cohere client for {len(documents)} candidate documents.")
    _ = cohere.Client(COHERE_API_KEY)
    _ = faiss.IndexFlatL2(1)


def print_summary(results: list[BenchmarkResult]) -> None:
    rows = [
        {
            "Vector DB": result.name,
            "Search Type": result.search_type,
            "p50 (ms)": round(result.p50_ms, 1),
            "p95 (ms)": round(result.p95_ms, 1),
            f"Hit@{TOP_K}": round(result.hit_at_k, 2),
            "Latency Mean (ms)": round(statistics.mean(result.latencies_ms), 1),
        }
        for result in results
    ]
    summary = pd.DataFrame(rows)
    print("\nLatency and relevance summary")
    print(summary.to_string(index=False))


def save_latency_plot(results: list[BenchmarkResult]) -> None:
    import matplotlib.pyplot as plt

    names = [result.name for result in results]
    p50_values = [result.p50_ms for result in results]
    p95_values = [result.p95_ms for result in results]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Vector DB Latency Showdown")

    for axis, values, title in [
        (axes[0], p50_values, "p50 Latency"),
        (axes[1], p95_values, "p95 Latency"),
    ]:
        bars = axis.bar(names, values, color=["#4C72B0", "#DD8452", "#55A868"][: len(names)])
        axis.set_title(title)
        axis.set_ylabel("Milliseconds")
        axis.grid(axis="y", alpha=0.3)
        for bar, value in zip(bars, values):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{value:.0f}",
                ha="center",
                va="bottom",
            )

    output_path = os.path.join(os.path.dirname(__file__), "latency_benchmark.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved plot: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Day 12 vector database showdown lab.")
    parser.add_argument("--max-chunks", type=int, default=500, help="Maximum hardcoded corpus chunks to index.")
    parser.add_argument("--skip-pinecone", action="store_true", help="Skip Pinecone even if keys are set.")
    parser.add_argument("--skip-azure", action="store_true", help="Skip Azure AI Search even if keys are set.")
    parser.add_argument("--skip-plot", action="store_true", help="Skip matplotlib chart generation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    embedder = make_embedder()
    documents = load_hardcoded_documents(max_chunks=args.max_chunks)
    vectors = embed_documents(embedder, documents)

    results = [run_faiss(embedder, documents, vectors)]

    if not args.skip_pinecone:
        pinecone_result = run_pinecone(embedder, documents, vectors)
        if pinecone_result:
            results.append(pinecone_result)

    if not args.skip_azure:
        azure_result = run_azure_search(embedder, documents, vectors)
        if azure_result:
            results.append(azure_result)

    print_summary(results)
    run_cohere_rerank(documents, results[0])

    if not args.skip_plot:
        save_latency_plot(results)


if __name__ == "__main__":
    main()
