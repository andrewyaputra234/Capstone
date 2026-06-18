from argparse import ArgumentParser
from pathlib import Path
import shutil
import os

from langchain_community.document_loaders import UnstructuredWordDocumentLoader, UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from subject_manager import SubjectManager
from vector_store import VectorStore
from agent_image_extractor import (
    extract_docx_images,
    extract_pdf_pages_as_images,
    extract_single_image_as_page,
    is_supported_image_file,
    docx_to_pdf_images,
)


def load_document(file_path: Path):
    """Load DOCX, PDF, or TXT files."""
    file_ext = file_path.suffix.lower()
    
    if is_supported_image_file(str(file_path)):
        from langchain_core.documents import Document
        return [
            Document(
                page_content=(
                    "Visual stimulus image for PSLE English oral practice. "
                    "Use the associated page image to extract prompts and conduct "
                    "stimulus-based conversation."
                ),
                metadata={"source": file_path.name, "content_type": "image_stimulus"},
            )
        ]
    
    if file_ext == ".docx":
        loader = UnstructuredWordDocumentLoader(str(file_path))
    elif file_ext == ".pdf":
        try:
            loader = UnstructuredPDFLoader(str(file_path))
            return loader.load()
        except Exception as e:
            print(f"[WARNING] PDF loader failed: {e}")
            print("[INFO] Falling back to PyMuPDF text extraction; page images will still be attempted separately.")
            return _load_pdf_with_pymupdf(file_path)
    elif file_ext == ".txt":
        # Load plain text file
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        from langchain_core.documents import Document
        return [Document(page_content=content, metadata={"source": file_path.name})]
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .docx, .pdf, .txt, .png, .jpg, .jpeg, .webp")
    
    return loader.load()


def _load_pdf_with_pymupdf(file_path: Path):
    """Load PDF text without Poppler so ingestion can continue on Windows."""
    try:
        import fitz
        from langchain_core.documents import Document
    except ImportError as e:
        raise RuntimeError("PyMuPDF is required for PDF fallback loading. Install with: pip install PyMuPDF") from e

    documents = []
    with fitz.open(str(file_path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                documents.append(
                    Document(
                        page_content=text,
                        metadata={"source": file_path.name, "page": page_index},
                    )
                )

    if documents:
        return documents

    return [
        Document(
            page_content=(
                "This PDF did not contain extractable text. Use extracted page images "
                "as visual stimulus context for PSLE oral English practice."
            ),
            metadata={"source": file_path.name, "page": 1, "text_extraction": "empty"},
        )
    ]


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


def get_document_files(input_path: Path) -> list[Path]:
    """Get all supported document files from input path."""
    if input_path.is_file():
        return [input_path]
    files = (
        sorted(input_path.glob("*.docx"))
        + sorted(input_path.glob("*.pdf"))
        + sorted(input_path.glob("*.txt"))
        + sorted(input_path.glob("*.png"))
        + sorted(input_path.glob("*.jpg"))
        + sorted(input_path.glob("*.jpeg"))
        + sorted(input_path.glob("*.webp"))
    )
    return files


def get_docx_files(input_path: Path):
    """Backward-compatible alias for get_document_files."""
    return get_document_files(input_path)


def _extract_document_images(doc_file: str, doc_type: str, subject: str) -> int:
    """Extract page/embedded images for a subject document. Returns image count."""
    images_dir = Path("data") / f"{subject}_images"
    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    output_dir = str(images_dir)
    count = 0
    if is_supported_image_file(doc_file):
        page_images = extract_single_image_as_page(doc_file, output_dir)
        count = len(page_images)
    elif doc_type == "pdf":
        page_images = extract_pdf_pages_as_images(doc_file, output_dir, dpi=150)
        count = len(page_images)
    elif doc_type == "docx":
        page_images = docx_to_pdf_images(doc_file, output_dir, dpi=150)
        if page_images:
            count = len(page_images)
        else:
            embedded_images = extract_docx_images(doc_file, output_dir)
            count = len(embedded_images) if embedded_images else 0
    return count


def ingest_document(
    file_path: str | Path,
    subject: str,
    rubric: str | None = None,
    material_type: str | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 100,
) -> dict:
    """
    Full ingestion pipeline: copy to subject input, chunk, embed, extract images.

    Returns a summary dict used by CLI, Streamlit, and CrewAI workflows.
    """
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"Document not found: {src}")

    subject_manager = SubjectManager()
    input_dir = subject_manager.get_subject_input_path(subject)
    dest = input_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)

    output_dir = subject_manager.get_subject_output_path(subject)
    process_file(dest, chunk_size, chunk_overlap, output_dir)

    vector_rebuilt = False
    if material_type != "reading":
        VectorStore(rebuild=True, subject=subject)
        vector_rebuilt = True
    if rubric:
        subject_manager.set_subject_rubric(subject, rubric)

    doc_type = dest.suffix.lower().lstrip(".")
    image_count = 0
    if material_type != "reading" and (
        doc_type in ("pdf", "docx", "png", "jpg", "jpeg", "webp")
        or is_supported_image_file(str(dest))
    ):
        image_count = _extract_document_images(str(dest), doc_type, subject)

    if material_type != "reading":
        subject_manager.set_subject_pdf(subject, str(dest))
    if material_type in {"visual", "reading"}:
        subject_manager.set_subject_material_path(subject, material_type, str(dest))

    chunk_files = list(output_dir.glob("*.txt"))
    return {
        "subject": subject,
        "file_path": str(dest),
        "chunk_count": len(chunk_files),
        "db_path": str(subject_manager.get_subject_chroma_path(subject, create=vector_rebuilt)),
        "image_count": image_count,
        "rubric": rubric,
        "material_type": material_type,
        "vector_rebuilt": vector_rebuilt,
    }


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

    doc_files = get_document_files(input_path)
    if not doc_files:
        print(f"No supported documents found in: {input_path}")
        return

    if args.subject:
        for file_path in doc_files:
            try:
                result = ingest_document(
                    file_path,
                    subject=args.subject,
                    rubric=args.rubric,
                    chunk_size=args.chunk_size,
                    chunk_overlap=args.chunk_overlap,
                )
                print(f"SUCCESS: Ingested '{file_path.name}' for subject '{args.subject}'")
                print(f"  Chunks: {result['chunk_count']}, Images: {result['image_count']}")
                if args.search:
                    documents = load_document(result["file_path"])
                    chunks = split_document(documents, args.chunk_size, args.chunk_overlap)
                    results = search_chunks(chunks, args.search)
                    print(f"Search results for '{args.search}':")
                    if results:
                        for index, snippet in results:
                            print(f"- Chunk {index}: {snippet}")
                    else:
                        print("No matches found.")
            except Exception as e:
                print(f"ERROR: Failed to ingest {file_path}: {e}")
    else:
        for file_path in doc_files:
            process_file(file_path, args.chunk_size, args.chunk_overlap, output_dir, args.search)


if __name__ == "__main__":
    main()
