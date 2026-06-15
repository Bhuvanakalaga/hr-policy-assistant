import os

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

# Paths

BASE_DIR = os.path.dirname(__file__)

POLICY_PATH = os.path.join(
    BASE_DIR,
    "data",
    "policy.txt"
)

INDEX_PATH = os.path.join(
    BASE_DIR,
    "data",
    "faiss_index"
)

# Embeddings

def get_embeddings():

    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


# Create Vector Store

def create_vector_store():
    """Load policy.txt, split it into chunks, embed them, and save the FAISS index."""

    print("Loading policy document...")

    loader = TextLoader(
        POLICY_PATH,
        encoding="utf-8"
    )

    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chunks = splitter.split_documents(documents)

    print(f"Created {len(chunks)} chunks")

    embeddings = get_embeddings()

    vector_store = FAISS.from_documents(
        chunks,
        embeddings
    )

    os.makedirs(INDEX_PATH, exist_ok=True)

    vector_store.save_local(INDEX_PATH)

    print("FAISS Index Created Successfully")


# Load Vector Store

_vector_store = None

def load_vector_store():

    global _vector_store

    if _vector_store is None:

        if not os.path.exists(INDEX_PATH):
            raise FileNotFoundError(
                f"FAISS index not found at '{INDEX_PATH}'. "
                "Please run create_vector_db.py first."
            )

        embeddings = get_embeddings()

        _vector_store = FAISS.load_local(
            INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )

        print("FAISS loaded into memory")

    return _vector_store


# Search Policy

def search_policy_chunks(
    query: str,
    k: int = 4
) -> str:
    """
    Search the FAISS index using Max Marginal Relevance (MMR).

    MMR improves retrieval diversity by avoiding multiple nearly-identical
    chunks and returning a broader set of relevant policy sections.
    """

    vector_store = load_vector_store()

    docs = vector_store.max_marginal_relevance_search(
        query=query,
        k=k,
        fetch_k=10
    )

    if not docs:
        return "No relevant policy information found for this query."

    return "\n\n".join(
        doc.page_content
        for doc in docs
    )