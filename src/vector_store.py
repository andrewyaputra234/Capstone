"""
Vector Store Module - Semantic Search using Chroma + OpenAI Embeddings
Handles document chunking, embedding, and semantic search functionality.
Supports multi-subject database organization.
"""

import os
from pathlib import Path
import shutil
from typing import List, Tuple
from argparse import ArgumentParser
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from subject_manager import SubjectManager

# Load environment variables from .env file
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHROMA_DB_BASE_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")

if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY not found in environment variables. "
        "Please create a .env file with your OpenAI API key. "
        "See .env.example for template."
    )


class VectorStore:
    """Manages vector embeddings and semantic search using Chroma."""
    
    def __init__(self, rebuild: bool = False, subject: str | None = None):
        """
        Initialize the vector store.
        
        Args:
            rebuild: If True, rebuild the entire vector database from chunk files.
            subject: Optional subject/topic name for multi-subject organization.
        """
        self.embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
        self.subject_manager = SubjectManager()
        self.subject = subject
        self.chunks_path = self.subject_manager.get_subject_output_path(subject)
        self.chroma_path = self.subject_manager.get_subject_chroma_path(subject)
        
        # Rebuild database if requested or if it doesn't exist
        if rebuild or not self.chroma_path.exists():
            self._build_vector_db()
        
        # Load existing vector store
        self.vector_store = Chroma(
            persist_directory=str(self.chroma_path),
            embedding_function=self.embeddings
        )
    
    def _build_vector_db(self):
        """Build vector database from chunk files."""
        subject_label = f" for subject '{self.subject}'" if self.subject else ""
        print(f"Building vector database from chunks in {self.chunks_path}{subject_label}...")
        
        # Clear existing database if it exists
        if self.chroma_path.exists():
            shutil.rmtree(self.chroma_path)
        
        # Load all chunk files
        documents = self._load_chunks()
        
        if not documents:
            raise ValueError(f"No chunk files found in {self.chunks_path}")
        
        print(f"Loaded {len(documents)} chunks")
        
        # Create and persist vector store
        self.vector_store = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=str(self.chroma_path)
        )
        print(f"Vector database created at {self.chroma_path}")
    
    def _load_chunks(self) -> List[Document]:
        """Load all chunk files and convert to LangChain Documents."""
        documents = []
        
        if not self.chunks_path.exists():
            return documents
        
        for chunk_file in sorted(self.chunks_path.glob("*.txt")):
            with open(chunk_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Extract filename
            filename = chunk_file.stem
            
            # Split by chunk markers if they exist
            if "--- Chunk " in content:
                # Split content by chunk markers
                chunks = content.split("--- Chunk ")
                chunk_num = 0
                
                for chunk_text in chunks:
                    if not chunk_text.strip():
                        continue
                    
                    # Remove leading chunk number if present
                    if " ---" in chunk_text:
                        chunk_text = chunk_text.split(" ---", 1)[1]
                    
                    chunk_text = chunk_text.strip()
                    
                    if chunk_text:
                        chunk_num += 1
                        doc = Document(
                            page_content=chunk_text,
                            metadata={
                                "source": filename,
                                "file_path": str(chunk_file),
                                "chunk_index": chunk_num
                            }
                        )
                        documents.append(doc)
            else:
                # If no chunk markers, treat entire file as one document
                doc = Document(
                    page_content=content,
                    metadata={
                        "source": filename,
                        "file_path": str(chunk_file)
                    }
                )
                documents.append(doc)
        
        return documents
    
    def semantic_search(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """
        Search documents semantically using the query.
        
        Args:
            query: Search query text
            top_k: Number of top results to return
        
        Returns:
            List of tuples: (source_file, relevance_score, content_preview)
        """
        # Search using similarity with score
        results = self.vector_store.similarity_search_with_score(query, k=top_k)
        
        formatted_results = []
        for doc, score in results:
            source = doc.metadata.get("source", "Unknown")
            content_preview = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            # Lower score is better in Chroma, so we invert it
            relevance = 1 - score
            formatted_results.append((source, relevance, content_preview))
        
        return formatted_results
    
    def add_documents(self, documents: List[Document]):
        """Add new documents to the vector store."""
        self.vector_store.add_documents(documents)
        print(f"Added {len(documents)} documents to vector store")


def main():
    """Test the vector store."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Semantic search using vector embeddings.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the vector database from scratch.")
    parser.add_argument("--query", type=str, help="Run a single query instead of interactive mode.")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode (default).")
    parser.add_argument("--subject", type=str, default=None, help="Subject/topic name for multi-subject organization.")
    args = parser.parse_args()
    
    try:
        # Initialize vector store with subject support
        subject_label = f" [{args.subject}]" if args.subject else ""
        vs = VectorStore(rebuild=args.rebuild, subject=args.subject)
        
        if args.query:
            # Single query mode
            results = vs.semantic_search(args.query, top_k=5)
            
            print(f"\nResults for: '{args.query}'{subject_label}\n")
            if results:
                for i, (source, score, preview) in enumerate(results, 1):
                    print(f"{i}. [{source}] (Relevance: {score:.2%})")
                    print(f"   Preview: {preview}\n")
            else:
                print("No results found.")
        else:
            # Interactive mode
            print(f"\n=== Semantic Search (Vector-based){subject_label} ===")
            print("Enter a query to search. Type 'exit' to quit.\n")
            
            while True:
                query = input("Enter query: ").strip()
                if query.lower() == "exit":
                    break
                
                if not query:
                    continue
                
                results = vs.semantic_search(query, top_k=5)
                
                print(f"\nTop 5 results for: '{query}'\n")
                for i, (source, score, preview) in enumerate(results, 1):
                    print(f"{i}. [{source}] (Relevance: {score:.2%})")
                    print(f"   Preview: {preview}\n")
    
    except KeyboardInterrupt:
        print("\nSearch interrupted.")
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
