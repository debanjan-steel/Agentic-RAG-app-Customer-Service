import os
import sys
from dotenv import load_dotenv
from google import genai
import chromadb

# Load environment variables (.env)
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file. Please ensure it is set.")

# Initialize Gemini Client
client = genai.Client(api_key=API_KEY)

# Connect to existing ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection_name = "amazon_shipping_docs"

try:
    collection = chroma_client.get_collection(name=collection_name)
except Exception as e:
    print(f"Error loading collection '{collection_name}'. Did you run 'ingest.py' first?")
    sys.exit(1)

SYSTEM_INSTRUCTION = """You are a helpful and polite Amazon Customer Support Assistant specializing in Shipping and Delivery.

Answer the customer's question strictly using ONLY the provided Context sections below.
Follow these rules:
1. If the provided context contains the answer, explain it clearly, accurately, and politely.
2. Mention the specific policy or section where relevant (e.g., "According to our Guaranteed Delivery Policy...").
3. If the customer's question is NOT covered by the context (for example, inquiries about returning products, account passwords, refunds on damaged items, or other non-shipping topics), politely state that you only have information regarding Shipping & Delivery, and direct them to the appropriate Customer Service department. Do NOT guess or make up policies.
"""

def answer_customer_query(query: str, top_k: int = 3):
    print(f"\n{'='*60}")
    print(f"Customer Question: {query}")
    print(f"{'='*60}")

    # 1. Embed query
    query_emb_resp = client.models.embed_content(
        model="gemini-embedding-001",
        contents=query
    )
    query_embedding = query_emb_resp.embeddings[0].values

    # 2. Retrieve top-k chunks from ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )

    retrieved_docs = results["documents"][0]
    retrieved_metas = results["metadatas"][0]
    distances = results["distances"][0] if "distances" in results and results["distances"] else []

    print("\n[Retrieved Context from Knowledge Base]:")
    context_blocks = []
    for i, (doc, meta) in enumerate(zip(retrieved_docs, retrieved_metas)):
        dist_str = f"(distance: {distances[i]:.4f})" if i < len(distances) else ""
        print(f"  [{i+1}] {meta.get('source')} - {meta.get('section')} {dist_str}")
        context_blocks.append(f"--- Context Source {i+1}: {meta.get('title')} ({meta.get('section')}) ---\n{doc}")

    full_context = "\n\n".join(context_blocks)

    # 3. Construct prompt
    user_prompt = f"""Context:
{full_context}

Customer Question:
{query}

Please provide a helpful, grounded customer support response:"""

    # 4. Generate answer using Gemini 3.5 Flash Lite
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"{SYSTEM_INSTRUCTION}\n\n{user_prompt}"
    )

    print(f"\n[Support Assistant Response]:\n")
    print(response.text)
    print(f"{'='*60}\n")
    return response.text

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single query from command line arguments
        user_question = " ".join(sys.argv[1:])
        answer_customer_query(user_question)
    else:
        # Interactive Chat Mode in Terminal
        print("\n" + "="*60)
        print("🤖 Amazon Customer Support Assistant (Shipping & Delivery)")
        print("Type your question and press Enter. Type 'exit' or 'quit' to leave.")
        print("="*60 + "\n")
        
        while True:
            try:
                user_question = input("Customer: ").strip()
                if not user_question:
                    continue
                if user_question.lower() in ["exit", "quit", "q"]:
                    print("\nThank you for contacting Amazon Support. Goodbye!")
                    break
                answer_customer_query(user_question)
            except (KeyboardInterrupt, EOFError):
                print("\n\nThank you for contacting Amazon Support. Goodbye!")
                break
