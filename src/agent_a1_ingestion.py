from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Path to your specific file
file_path = "Capstone project Proposal Template_AndrewYaputra_2303129.docx"

# 2. Agent A1: Load the document
print("--- Agent A1: Ingesting Document ---")
loader = UnstructuredWordDocumentLoader(file_path)
data = loader.load()

# 3. Agent A2: Chunking (Retrieval Preparation)
# Academic papers are too long for AI to read at once. 
# We split them into smaller "chunks."
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
chunks = text_splitter.split_documents(data)

print(f"Successfully split the document into {len(chunks)} chunks.")
print("Example Chunk:")
print(chunks[0].page_content)