# Architecture Overview

The engineering-copilot is a retrieval-augmented generation (RAG) system hosted on AWS.
It answers questions about engineering documentation by retrieving relevant context and
generating grounded responses using Amazon Bedrock.

## Components

### Ingestion Pipeline

The ingestion pipeline loads markdown documents, splits them into chunks, generates
vector embeddings using Amazon Bedrock, and stores them in Amazon OpenSearch Serverless.

Each chunk preserves metadata including the source file name and chunk index, which
allows the query pipeline to return citations alongside generated answers.

### Query API

The query API accepts a natural language question, retrieves the most relevant chunks
from OpenSearch, and passes them as context to a Bedrock language model.

The response includes a grounded answer and the list of source chunks used, enabling
full source attribution in the final output.

### Infrastructure

All infrastructure is managed with Terraform and deployed via GitHub Actions.
State is stored remotely in an S3 bucket with DynamoDB locking to prevent concurrent
apply conflicts.

## Design Principles

- Retrieval quality is prioritised over model complexity.
- Every chunk carries source metadata so answers can always be traced back to a document.
- The ingestion and query logic is kept independent from AWS services to remain testable.
