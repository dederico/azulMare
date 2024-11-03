import os
import argparse
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

def initialize_pinecone(api_key, environment):
    return Pinecone(api_key=api_key)

def index_exists(pinecone_client, index_name):
    return index_name in pinecone_client.list_indexes().names()

def get_index_info(pinecone_client, index_name):
    return pinecone_client.describe_index(index_name)

def create_pinecone_index(pinecone_client, index_name, dimension, metric='cosine', region='us-east-1'):
    pinecone_client.create_index(
        name=index_name,
        dimension=dimension,
        metric=metric,
        spec=ServerlessSpec(
            cloud='aws',
            region=region
        )
    )

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
    pinecone_api_key = args.pinecone_api_key
    pinecone_env = args.pinecone_env

    pinecone_client = initialize_pinecone(pinecone_api_key, pinecone_env)

    embeddings = getEmbeddings(use_openai=use_openai_embeddings)
    if embeddings is None:
        print("Error in loading embeddings. Exiting.")
        return

    if index_exists(pinecone_client, index_name):
        index_info = get_index_info(pinecone_client, index_name)
        if index_info.dimension != 384:
            print(f"Error: Existing index '{index_name}' has dimension {index_info.dimension}, but embeddings have dimension {embedding_dimension}.")
            return
        else:
            print(f"Index '{index_name}' already exists with matching dimension.")
    else:
        create_pinecone_index(pinecone_client, index_name, dimension=384)
        print(f"Index '{index_name}' created.")

    documents = loadDocs(docs_directory)
    if documents is None:
        print("No documents to process. Exiting.")
        return

    docs = splitDocs(documents)

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

    parser.add_argument(
        "--pinecone_api_key", 
        type=str, 
        required=True, 
        help="Your Pinecone API key."
    )

    parser.add_argument(
        "--pinecone_env", 
        type=str, 
        required=True, 
        help="Pinecone environment (e.g., 'us-west1-gcp')."
    )

    main(parser.parse_args())