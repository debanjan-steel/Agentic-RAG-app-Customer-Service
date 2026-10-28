import os
import glob
from pathlib import Path
from dotenv import load_dotenv
from google import genai
import chromadb

# Load environment variables (.env)
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file. Please ensure it is set.")

# Initialize the official Gemini Client
client = genai.Client(api_key=API_KEY)

# Initialize ChromaDB persistent storage in ./chroma_db
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Reset or create collection
collection_name = "amazon_shipping_docs"
try:
    chroma_client.delete_collection(name=collection_name)
    print(f"Cleared existing collection '{collection_name}'.")
except Exception:
    pass

collection = chroma_client.create_collection(
    name=collection_name,
    metadata={"hnsw:space": "cosine"}
)

def chunk_markdown(file_path: str):
    """
    Chunks a markdown file by sections (split by markdown headers ##).
    Preserves document title and context in each chunk.
    """
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")
    title = path.stem.replace("_", " ").title()
    
    # Split by section headers
    raw_sections = content.split("\n## ")
    chunks = []
    
    for i, section in enumerate(raw_sections):
        if not section.strip():
            continue
        
        if i == 0:
            section_text = section.strip()
            section_title = "Overview"
        else:
            lines = section.split("\n", 1)
            section_title = lines[0].strip()
            section_text = section.strip()
        
        full_chunk = f"Document: {title}\nSection: {section_title}\n\n{section_text}"
        chunks.append({
            "id": f"{path.stem}_sec_{i}",
            "text": full_chunk,
            "metadata": {
                "source": path.name,
                "title": title,
                "section": section_title
            }
        })
    return chunks

def run_ingestion():
    data_files = glob.glob("./data/*.md")
    if not data_files:
        print("No markdown files found in ./data directory.")
        return

    all_chunks = []
    for file_path in data_files:
        chunks = chunk_markdown(file_path)
        all_chunks.extend(chunks)
        print(f"Loaded {len(chunks)} chunks from {file_path}")

    print(f"\nTotal chunks to index: {len(all_chunks)}")
    print("Generating embeddings using Gemini embedding model (gemini-embedding-001)...")

    ids = [c["id"] for c in all_chunks]
    documents = [c["text"] for c in all_chunks]
    metadatas = [c["metadata"] for c in all_chunks]
    embeddings = []

    # Generate embeddings in a single batch request
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=documents
    )
    embeddings = [e.values for e in response.embeddings]

    # Store in ChromaDB
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    print(f"Successfully stored {len(documents)} chunks in ChromaDB ('{collection_name}')!\n")

if __name__ == "__main__":
    run_ingestion()
