from argparse import ArgumentParser
from pathlib import Path
import re


def load_chunk_files(path: Path):
    if path.is_file():
        return [path]
    return sorted(path.glob("*.txt"))


def parse_chunks(chunk_file: Path):
    text = chunk_file.read_text(encoding="utf-8")
    raw_chunks = re.split(r"^--- Chunk \d+ ---\s*$", text, flags=re.MULTILINE)
    return [chunk.strip() for chunk in raw_chunks if chunk.strip()]


def score_chunk(chunk: str, query: str):
    query_lower = query.casefold()
    chunk_lower = chunk.casefold()
    if query_lower not in chunk_lower:
        return 0
    return chunk_lower.count(query_lower)


def search_chunks(chunk_files, query: str, top_k: int = 5):
    results = []
    for chunk_file in chunk_files:
        chunks = parse_chunks(chunk_file)
        for index, chunk in enumerate(chunks, start=1):
            score = score_chunk(chunk, query)
            if score > 0:
                snippet = " ".join(chunk.split())
                results.append((score, chunk_file, index, snippet[:300]))

    results.sort(key=lambda item: item[0], reverse=True)
    return results[:top_k]


def print_results(results, query: str):
    if not results:
        print(f"No matches found for '{query}'.")
        return

    print(f"Top results for '{query}':")
    for score, chunk_file, index, snippet in results:
        print(f"\n- File: {chunk_file.name}")
        print(f"  Chunk: {index}")
        print(f"  Score: {score}")
        print(f"  Snippet: {snippet}")


def interactive_mode(search_path: Path):
    chunk_files = load_chunk_files(search_path)
    if not chunk_files:
        print(f"No .txt chunk files found in: {search_path}")
        return

    print("Loaded chunk files:")
    for chunk_file in chunk_files:
        print(f"- {chunk_file.name}")

    while True:
        query = input("\nAsk a question (or press Enter to exit): ").strip()
        if not query:
            print("Exiting assistant.")
            break
        results = search_chunks(chunk_files, query)
        print_results(results, query)


def main():
    parser = ArgumentParser(description="Simple assistant for searching chunk text files.")
    parser.add_argument(
        "path",
        help="Path to a chunk text file or a directory containing chunk text files.",
    )
    parser.add_argument("--query", default=None, help="Question or keyword to search for.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive assistant mode.",
    )
    args = parser.parse_args()

    search_path = Path(args.path)
    if not search_path.exists():
        print(f"Error: path not found: {search_path}")
        return

    if args.interactive:
        interactive_mode(search_path)
    elif args.query:
        chunk_files = load_chunk_files(search_path)
        if not chunk_files:
            print(f"No .txt chunk files found in: {search_path}")
            return
        results = search_chunks(chunk_files, args.query)
        print_results(results, args.query)
    else:
        print("Please provide --query or --interactive.")


if __name__ == "__main__":
    main()
