from langchain_community.document_loaders import UnstructuredWordDocumentLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pathlib import Path
from typing import List, Optional
import PyPDF2

class DocumentIngestionAgent:
    """
    Agent A1: Ingests documents (PDF, DOCX, TXT) and extracts text content.
    Supports both text-based and scanned documents.
    """
    
    def __init__(self):
        """Initialize the document ingestion agent."""
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=100
        )
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text content from a document.
        
        Args:
            file_path: Path to the document file (PDF, DOCX, or TXT)
        
        Returns:
            Extracted text content as a single string
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_ext = file_path.suffix.lower()
        
        try:
            if file_ext == ".pdf":
                return self._extract_pdf(str(file_path))
            elif file_ext == ".docx":
                return self._extract_docx(str(file_path))
            elif file_ext == ".txt":
                return self._extract_txt(str(file_path))
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
        except Exception as e:
            print(f"[ERROR] Failed to extract text from {file_path}: {e}")
            raise
    
    def _extract_pdf(self, file_path: str) -> str:
        """Extract text from PDF files."""
        try:
            text_content = []
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text.strip():
                        text_content.append(page_text)
            
            combined_text = "\n".join(text_content)
            if not combined_text.strip():
                raise ValueError("No text could be extracted from PDF")
            return combined_text
        except Exception as e:
            print(f"[WARN] PDF extraction failed: {e}. Trying alternative method...")
            # Fallback: use PyPDFLoader from LangChain
            try:
                loader = PyPDFLoader(file_path)
                documents = loader.load()
                return "\n".join([doc.page_content for doc in documents])
            except Exception as fallback_error:
                raise ValueError(f"Failed to extract PDF: {fallback_error}")
    
    def _extract_docx(self, file_path: str) -> str:
        """Extract text from DOCX files."""
        try:
            loader = UnstructuredWordDocumentLoader(file_path)
            documents = loader.load()
            return "\n".join([doc.page_content for doc in documents])
        except Exception as e:
            raise ValueError(f"Failed to extract DOCX: {e}")
    
    def _extract_txt(self, file_path: str) -> str:
        """Extract text from TXT files."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Failed to extract TXT: {e}")
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks for processing.
        
        Args:
            text: The text content to chunk
        
        Returns:
            List of text chunks
        """
        # Create simple document-like objects for the splitter
        class SimpleDoc:
            def __init__(self, content):
                self.page_content = content
        
        docs = [SimpleDoc(text)]
        chunks = self.text_splitter.split_documents(docs)
        return [chunk.page_content for chunk in chunks]


# For backward compatibility: if this file is run as a script
if __name__ == "__main__":
    # Legacy script execution
    file_path = "Capstone project Proposal Template_AndrewYaputra_2303129.docx"
    agent = DocumentIngestionAgent()
    
    print("--- Agent A1: Ingesting Document ---")
    text_content = agent.extract_text(file_path)
    
    # Chunk the text
    chunks = agent.chunk_text(text_content)
    print(f"Successfully split the document into {len(chunks)} chunks.")
    if chunks:
        print("Example Chunk:")
        print(chunks[0][:500])