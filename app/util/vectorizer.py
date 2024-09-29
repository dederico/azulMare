import os
import argparse
from langchain_pinecone import PineconeVectorStore
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

def getEmbeddings(use_openai=False):
    try:
        if use_openai:
            from langchain.embeddings.openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model_name="ada")
        else:
            from langchain.embeddings import SentenceTransformerEmbeddings
            return SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    except Exception as e:
        print(f"Error loading embeddings: {e}")
        return None

def splitDocs(documents, chunk_size=500, chunk_overlap=20):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    docs = text_splitter.split_documents(documents)
    return docs

def loadDocs(directory):
    try:
        loader = DirectoryLoader(directory)
        return loader.load()
    except Exception as e:
        print(f"Error loading documents from directory '{directory}': {e}")
        return None

def main(args):
    docs_directory = args.docs_directory
    index_name = args.index
    use_openai_embeddings = args.use_openai_embeddings

    documents = loadDocs(docs_directory)
    if documents is None:
        print("No documents to process. Exiting.")
        return

    docs = splitDocs(documents)

    embeddings = getEmbeddings(use_openai=use_openai_embeddings)
    if embeddings is None:
        print("Error in loading embeddings. Exiting.")
        return

    vs = PineconeVectorStore.from_documents(
        docs,
        index_name=index_name,
        embedding=embeddings
    )
    print(f"Vector store created with index '{index_name}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Document Embedding and Pinecone Indexing Script")

    parser.add_argument(
        "--use_openai_embeddings", 
        action="store_true", 
        help="Use OpenAI embeddings for vectorization (default: False)."
    )

    parser.add_argument(
        "--docs_directory", 
        type=str, 
        default="data", 
        help="Path to the directory containing documents (default: 'data')."
    )

    parser.add_argument(
        "index", 
        type=str, 
        help="Pinecone index name (mandatory)."
    )

    main(parser.parse_args())