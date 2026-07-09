import json
import requests
import math
from config import Config
from db import db

def dot_product(v1, v2):
    return sum(x * y for x, y in zip(v1, v2))

def magnitude(v):
    return math.sqrt(sum(x * x for x in v))

def cosine_similarity(v1, v2):
    m1 = magnitude(v1)
    m2 = magnitude(v2)
    if m1 == 0 or m2 == 0:
        return 0.0
    return dot_product(v1, v2) / (m1 * m2)

class RAGManager:
    def __init__(self):
        self.ollama_url = Config.OLLAMA_HOST
        self.model = Config.EMBEDDINGS_MODEL

    def get_embedding(self, text):
        """Calls local Ollama instance to generate vector embedding for a block of text."""
        try:
            res = requests.post(f"{self.ollama_url}/api/embeddings", json={
                "model": self.model,
                "prompt": text
            }, timeout=3)
            if res.status_code == 200:
                return res.json().get("embedding")
        except Exception as e:
            print(f"RAG: Ollama embedding generation failed ({e})")
        return None

    def index_document(self, title, content, category):
        """Generates embedding and indexes the document into the KB database."""
        embedding = self.get_embedding(content)
        
        if db.engine_type == 'postgres':
            db.execute_query(
                "INSERT INTO kb_documents (title, content, category, embedding) VALUES (%s, %s, %s, %s);",
                (title, content, category, embedding)
            )
        else:
            emb_str = json.dumps(embedding) if embedding else None
            db.execute_query(
                "INSERT INTO kb_documents (title, content, category, embedding) VALUES (%s, %s, %s, %s);",
                (title, content, category, emb_str)
            )
        print(f"RAG: Indexed guide '{title}' into knowledge base.")

    def search_kb(self, query_text, limit=3):
        """Performs semantic vector search or falls back to text search if offline."""
        embedding = self.get_embedding(query_text)

        if not embedding:
            print("RAG: Falling back to keyword-based query search.")
            like_pat = f"%{query_text}%"
            rows = db.fetch_all(
                "SELECT title, content, category FROM kb_documents WHERE title LIKE %s OR content LIKE %s LIMIT %s;",
                (like_pat, like_pat, limit)
            )
            return rows

        if db.engine_type == 'postgres':
            # Execute pgvector cosine similarity query
            rows = db.fetch_all("""
                SELECT title, content, category, (embedding <=> %s::vector) as distance
                FROM kb_documents
                ORDER BY distance ASC
                LIMIT %s;
            """, (embedding, limit))
            return rows
        else:
            # SQLite fallback: calculate similarity manually in Python
            rows = db.fetch_all("SELECT title, content, category, embedding FROM kb_documents;")
            scored_docs = []
            
            for r in rows:
                if not r['embedding']:
                    continue
                try:
                    doc_vec = json.loads(r['embedding'])
                    similarity = cosine_similarity(embedding, doc_vec)
                    
                    scored_docs.append({
                        "title": r['title'],
                        "content": r['content'],
                        "category": r['category'],
                        "score": float(similarity)
                    })
                except Exception as ex:
                    print(f"RAG SQLite Search: Parse error on doc - {ex}")
            
            scored_docs.sort(key=lambda x: x['score'], reverse=True)
            return scored_docs[:limit]

# Export default manager
rag_manager = RAGManager()
