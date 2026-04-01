from argparse import ArgumentParser
from pathlib import Path

from langchain_community.document_loaders import UnstructuredWordDocumentLoader, UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from subject_manager import SubjectManager


def load_document(file_path: Path):
    """Load DOCX or PDF files."""
    file_ext = file_path.suffix.lower()
    
    if file_ext == ".docx":
        loader = UnstructuredWordDocumentLoader(str(file_path))
    elif file_ext == ".pdf":
        loader = UnstructuredPDFLoader(str(file_path))
    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Supported: .docx, .pdf")
    
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


if __name__ == "__main__":
    main()
