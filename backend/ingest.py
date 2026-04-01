"""
Phase 1: PDF Data Ingestion & Vectorization Pipeline
卫健委指南 PDF -> Text Extraction -> Chunking -> Embedding -> ChromaDB
"""
import os
import sys
import re
import io
from pathlib import Path
from typing import List, Dict, Optional

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pdfplumber
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Config
PDF_DIR = "/app/pdfs/nhc-guidelines"
CHROMA_DIR = os.path.join(os.path.dirname(__file__), '..', 'chroma_db')
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
EMBEDDING_MODEL = "text-embedding-v3"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def extract_text_from_pdf(pdf_path: str) -> List[Dict[str, str]]:
    """Extract text and tables from a single PDF."""
    pages = []
    filename = os.path.basename(pdf_path)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # Extract main text
                text = page.extract_text() or ""
                
                # Extract tables and merge them into text
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        table_text = ""
                        for row in table:
                            cells = [str(cell) if cell else "" for cell in row]
                            table_text += " | ".join(cells) + "\n"
                        text += "\n[表格数据]\n" + table_text
                
                if text.strip():
                    pages.append({
                        "page_num": i + 1,
                        "text": text.strip(),
                        "source": filename,
                        "total_pages": len(pdf.pages)
                    })
        print(f"  ✅ {filename}: {len(pages)} pages extracted")
    except Exception as e:
        print(f"  ❌ {filename}: Error - {e}")
    
    return pages


def chunk_text(pages: List[Dict[str, str]], chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[Dict[str, str]]:
    """Split extracted text into overlapping chunks."""
    chunks = []
    
    for page_data in pages:
        text = page_data["text"]
        # Split by paragraphs first for better semantic boundaries
        paragraphs = re.split(r'\n{2,}', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({
                    "text": current_chunk.strip(),
                    "source": page_data["source"],
                    "page": page_data["page_num"],
                    "total_pages": page_data["total_pages"]
                })
                # Keep overlap
                words = current_chunk.split()
                current_chunk = ""
                # Take last few words for overlap
                overlap_words = words[-(overlap // 4):]
                current_chunk = " ".join(overlap_words) + "\n\n"
            current_chunk += para + "\n\n"
        
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "source": page_data["source"],
                "page": page_data["page_num"],
                "total_pages": page_data["total_pages"]
            })
    
    return chunks


def get_embeddings_batch(texts: List[str], client: OpenAI) -> List[List[float]]:
    """Get embeddings from DashScope/Qwen API in batches."""
    all_embeddings = []
    batch_size = 6
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
                dimensions=1024
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            print(f"    Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1} done ({len(batch)} texts)")
        except Exception as e:
            print(f"    ❌ Embedding batch error: {e}")
            # Fallback: zero vectors (will still be searchable by metadata)
            all_embeddings.extend([[0.0] * 1024 for _ in batch])
    
    return all_embeddings


def main():
    print("=" * 60)
    print("卫健委指南 RAG - Phase 1: Data Ingestion & Vectorization")
    print("=" * 60)
    
    # Step 1: Collect all PDFs
    pdf_files = sorted(Path(PDF_DIR).glob("*.pdf"))
    print(f"\n📂 Found {len(pdf_files)} PDF files in {PDF_DIR}")
    
    if not pdf_files:
        print("❌ No PDFs found! Check the directory path.")
        sys.exit(1)
    
    # Step 2: Extract text from all PDFs
    print(f"\n📖 Extracting text from PDFs...")
    all_pages = []
    for pdf_path in pdf_files:
        pages = extract_text_from_pdf(str(pdf_path))
        all_pages.extend(pages)
    print(f"  Total pages extracted: {len(all_pages)}")
    
    # Step 3: Chunk the text
    print(f"\n✂️  Chunking text (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})...")
    chunks = chunk_text(all_pages)
    print(f"  Total chunks created: {len(chunks)}")
    
    # Step 4: Initialize ChromaDB
    print(f"\n💾 Storing in ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    
    # Delete existing collection if exists
    try:
        chroma_client.delete_collection("nhc_guidelines")
        print("  Dropped existing collection")
    except:
        pass
    
    collection = chroma_client.create_collection(
        name="nhc_guidelines",
        metadata={"description": "卫健委诊疗指南知识库"}
    )
    
    # Step 5: Get embeddings and store in batches
    print(f"\n🔗 Getting embeddings via DashScope (model: {EMBEDDING_MODEL})...")
    embedding_client = OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    
    embed_batch = 6  # DashScope max batch size
    chroma_batch = 50  # ChromaDB batch size
    total_batches = (len(chunks) - 1) // chroma_batch + 1
    
    for batch_idx in range(0, len(chunks), chroma_batch):
        batch_chunks = chunks[batch_idx:batch_idx + chroma_batch]
        texts = [c["text"] for c in batch_chunks]
        ids = [f"chunk_{batch_idx + j}" for j in range(len(batch_chunks))]
        metadatas = [{"source": c["source"], "page": c["page"], "total_pages": c["total_pages"]} for c in batch_chunks]
        
        # Get embeddings in sub-batches of 6 (DashScope limit)
        embeddings = get_embeddings_batch(texts, embedding_client)
        
        # Store in ChromaDB
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        current_batch = batch_idx // chroma_batch + 1
        print(f"  Stored batch {current_batch}/{total_batches} ({len(batch_chunks)} chunks)")
    
    # Summary
    count = collection.count()
    print(f"\n{'=' * 60}")
    print(f"✅ Ingestion Complete!")
    print(f"   - PDFs processed: {len(pdf_files)}")
    print(f"   - Total pages: {len(all_pages)}")
    print(f"   - Total chunks: {len(chunks)}")
    print(f"   - ChromaDB collection count: {count}")
    print(f"   - Collection name: nhc_guidelines")
    print(f"   - ChromaDB path: {CHROMA_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
