from argparse import ArgumentParser
from pathlib import Path
import re


def load_chunk_file(chunk_file: Path):
    text = chunk_file.read_text(encoding="utf-8")
    raw_chunks = re.split(r"^--- Chunk \d+ ---\s*$", text, flags=re.MULTILINE)
    return [chunk.strip() for chunk in raw_chunks if chunk.strip()]


def get_text_files(path: Path):
    if path.is_file():
        return [path]
    return sorted(path.glob("*.txt"))


def search_chunks(chunks, query: str):
    query_lower = query.casefold()
    results = []
    for index, chunk in enumerate(chunks, start=1):
        if query_lower in chunk.casefold():
            snippet = chunk.replace("\n", " ").strip()
            results.append((index, snippet[:250]))
    return results


def print_results(file_path: Path, chunks, query: str):
    print(f"\nSearching {file_path} for '{query}'")
    results = search_chunks(chunks, query)
    if not results:
        print("No matches found.")
        return

    print(f"Found {len(results)} matches:")
    for index, snippet in results:
        print(f"- Chunk {index}: {snippet}")


def run_query(path: Path, query: str):
    chunk_files = get_text_files(path)
    if not chunk_files:
        print(f"No .txt chunk files found in: {path}")
        return

    for chunk_file in chunk_files:
        chunks = load_chunk_file(chunk_file)
        print_results(chunk_file, chunks, query)


def interactive_mode(path: Path):
    chunk_files = get_text_files(path)
    if not chunk_files:
        print(f"No .txt chunk files found in: {path}")
        return

    print("Loaded chunk files:")
    for chunk_file in chunk_files:
        print(f"- {chunk_file}")

    while True:
        query = input("\nEnter a search keyword (or press Enter to exit): ").strip()
        if not query:
            print("Goodbye.")
            break
        run_query(path, query)


def main():
    parser = ArgumentParser(description="Search saved chunk text files for keywords.")
    parser.add_argument(
        "path",
        help="Path to a chunk text file or a directory containing chunk text files.",
    )
    parser.add_argument("--query", default=None, help="Keyword or phrase to search for.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enter interactive search mode.",
    )
    args = parser.parse_args()

    search_path = Path(args.path)
    if not search_path.exists():
        print(f"Error: path not found: {search_path}")
        return

    if args.interactive:
        interactive_mode(search_path)
    elif args.query:
        run_query(search_path, args.query)
    else:
        print("Please provide --query or --interactive.")


if __name__ == "__main__":
    main()
