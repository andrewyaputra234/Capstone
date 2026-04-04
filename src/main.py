from argparse import ArgumentParser
from pathlib import Path
import shutil
import os

from langchain_community.document_loaders import UnstructuredWordDocumentLoader, UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from subject_manager import SubjectManager
from vector_store import VectorStore
from agent_image_extractor import extract_pdf_pages_as_images, extract_docx_images, docx_to_pdf_images


def load_document(file_path: Path):
    """Load DOCX, PDF, or TXT files."""
    file_ext = file_path.suffix.lower()
    
    if file_ext == ".docx":
        loader = UnstructuredWordDocumentLoader(str(file_path))
    elif file_ext == ".pdf":
        loader = UnstructuredPDFLoader(str(file_path))
    elif file_ext == ".txt":
        # Load plain text file
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        from langchain_core.documents import Document
        return [Document(page_content=content, metadata={"source": file_path.name})]
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .docx, .pdf, .txt")
    
    return loader.load()


def split_document(documents, chunk_size: int = 1000, chunk_overlap: int = 100):
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_documents(documents)


def save_chunks(chunks, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for index, chunk in enumerate(chunks, start=1):
            output_file.write(f"--- Chunk {index} ---\n")
            output_file.write(chunk.page_content)
            output_file.write("\n\n")


def search_chunks(chunks, query: str):
    query_lower = query.casefold()
    results = []
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.page_content
        if query_lower in text.casefold():
            snippet = text.strip().replace("\n", " ")
            results.append((index, snippet[:250]))
    return results


def get_docx_files(input_path: Path):
    """Get all DOCX and PDF files from input path."""
    if input_path.is_file():
        return [input_path]
    
    # Get both DOCX and PDF files
    files = sorted(input_path.glob("*.docx")) + sorted(input_path.glob("*.pdf"))
    return files


def process_file(file_path: Path, chunk_size: int, chunk_overlap: int, output_dir: Path | None, search_query: str | None = None):
    print(f"Loading document: {file_path}")
    documents = load_document(file_path)
    print(f"Loaded {len(documents)} document object(s).")

    chunks = split_document(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    print(f"Successfully split the document into {len(chunks)} chunks.")

    if output_dir:
        output_path = output_dir / f"{file_path.stem}_chunks.txt"
    else:
        output_path = file_path.with_name(file_path.stem + "_chunks.txt")

    save_chunks(chunks, output_path)
    print(f"Saved chunk output to: {output_path}\n")

    if search_query:
        results = search_chunks(chunks, search_query)
        print(f"Search results for '{search_query}':")
        if results:
            for index, snippet in results:
                print(f"- Chunk {index}: {snippet}")
        else:
            print("No matches found.")
        print()


def main():
    parser = ArgumentParser(description="Load DOCX or PDF file(s) and split them into text chunks.")
    parser.add_argument(
        "path",
        help="Path to a DOCX/PDF file or a directory containing DOCX/PDF files.",
    )
    parser.add_argument("--chunk-size", type=int, default=1000, help="Maximum characters per chunk.")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Overlap characters between chunks.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional directory where chunk files are saved. Defaults to the same folder as each input file.",
    )
    parser.add_argument(
        "--search",
        default=None,
        help="Optional keyword to search for inside generated chunks.",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Subject/topic name for multi-subject organization.",
    )
    parser.add_argument(
        "--rubric",
        default=None,
        help="Rubric name to associate with this subject (e.g., primary1_math, essay_assignment).",
    )
    args = parser.parse_args()

    input_path = Path(args.path)
    if not input_path.exists():
        print(f"Error: path not found: {input_path}")
        return

    # Use SubjectManager if subject is specified, otherwise use provided output-dir
    if args.subject:
        subject_manager = SubjectManager()
        output_dir = subject_manager.get_subject_output_path(args.subject)
        subject_label = f" [{args.subject}]"
        print(f"Ingesting documents{subject_label}...")
    else:
        output_dir = Path(args.output_dir) if args.output_dir else None
        subject_label = ""
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

    docx_files = get_docx_files(input_path)
    if not docx_files:
        print(f"No .docx files found in: {input_path}")
        return

    for file_path in docx_files:
        process_file(file_path, args.chunk_size, args.chunk_overlap, output_dir, args.search)
    
    # Add chunks to ChromaDB vector store if subject is specified
    if args.subject:
        print(f"Adding chunks to vector store for subject '{args.subject}'...")
        try:
            vector_store = VectorStore(rebuild=True, subject=args.subject)
            print(f"SUCCESS: Vector database updated for subject '{args.subject}'")
            
            # Map rubric to subject if specified
            if args.rubric:
                subject_manager = SubjectManager()
                subject_manager.set_subject_rubric(args.subject, args.rubric)
            
            # ============================================================================
            # EXTRACT IMAGES FROM PDF OR DOCX (NEW FOR THIS INGESTION)
            # ============================================================================
            # Get the document file that was just ingested (PDF or DOCX)
            pdf_files = list(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path] if input_path.suffix.lower() == ".pdf" else []
            docx_files = list(input_path.glob("*.docx")) if input_path.is_dir() else [input_path] if input_path.suffix.lower() == ".docx" else []
            
            doc_file = None
            doc_type = None
            
            if pdf_files:
                doc_file = str(pdf_files[0])
                doc_type = "pdf"
            elif docx_files:
                doc_file = str(docx_files[0])
                doc_type = "docx"
            
            if doc_file:
                subject_manager = SubjectManager()
                
                # 1. CLEAR OLD IMAGES for this subject
                images_dir = Path("data") / f"{args.subject}_images"
                if images_dir.exists():
                    print(f"[INFO] Clearing old images for subject '{args.subject}'...")
                    shutil.rmtree(images_dir)
                    print(f"[OK] Old images deleted")
                
                # 2. EXTRACT IMAGES based on document type
                print(f"[INFO] Extracting images from {doc_type.upper()} document...")
                output_dir = str(images_dir)
                
                if doc_type == "pdf":
                    page_images = extract_pdf_pages_as_images(doc_file, output_dir, dpi=150)
                    print(f"[OK] Extracted {len(page_images)} pages as images from PDF")
                elif doc_type == "docx":
                    # Try to convert DOCX to images (requires LibreOffice)
                    page_images = docx_to_pdf_images(doc_file, output_dir, dpi=150)
                    if not page_images:
                        # Fallback: extract embedded images from DOCX
                        print(f"[INFO] Page-level images not available, extracting embedded images...")
                        embedded_images = extract_docx_images(doc_file, output_dir)
                        if embedded_images:
                            print(f"[OK] Extracted {len(embedded_images)} embedded images from DOCX")
                        else:
                            print(f"[INFO] No embedded images found in DOCX (text-based questions will work)")
                    else:
                        print(f"[OK] Successfully converted DOCX pages to images")
                
                # 3. STORE DOCUMENT PATH in subject config for future reference
                print(f"[INFO] Storing document path in subject config...")
                subject_manager.set_subject_pdf(args.subject, doc_file)  # Using set_subject_pdf for both PDF and DOCX
                print(f"[OK] Document path stored for subject '{args.subject}'")
            
            
        except Exception as e:
            print(f"ERROR: Failed to update vector store: {e}")


if __name__ == "__main__":
    main()
