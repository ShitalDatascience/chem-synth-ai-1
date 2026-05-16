# Project architecture (discovery-agent)

This document explains the repository’s runtime architecture and how each major backend “service” connects to **Postgres (ChEMBL)**, the **vector DB (Milvus Lite)**, and the **LLM (Ollama)**.

## High-level architecture (what runs where)

- **Frontend (`frontend/`)**: Next.js UI. Calls the backend using `NEXT_PUBLIC_API_BASE_URL` from `frontend/.env.local` (currently `http://127.0.0.1:8000`).
- **Backend (`backend/`)**: FastAPI app (`backend/app/main.py`) that exposes REST endpoints and orchestrates retrieval + similarity + prediction + report generation.
- **Postgres (ChEMBL DB)**: The backend queries ChEMBL tables via SQL files loaded by `app/db/sql_loader.py` and executed through `app/db/pg.py` (psycopg v3) or (legacy) `psycopg2`.
- **Vector DB**: **Milvus Lite** (embedded, file-based) accessed via `pymilvus.MilvusClient(uri=<path>)`, configured by `MILVUS_DB_PATH` (default `./data/milvus_lite.db`).
- **LLM**: Called through **Ollama** at `http://localhost:11434` from `RAGLLM.generate()` (`backend/app/services/llm/rag_llm.py`), using model `llama3.2:latest` (currently hardcoded there).

## Backend entrypoint and routing

- **FastAPI app**: `backend/app/main.py` loads env, sets CORS, and mounts the API router.
- **API router**: `backend/app/api/router.py` includes:
  - `GET /healthz` (`backend/app/api/routes/health.py`)
  - Molecule endpoints (`backend/app/api/routes/molecule.py`)
  - RAG bundle endpoint (`backend/app/api/routes/rag.py`)
  - Report endpoints (`backend/app/api/routes/report.py`)
  - Chat endpoint (`backend/app/api/routes/chat.py`)
  - Phase 4 agent endpoint `POST /chem/predict` (delegates to `app.agents.chem_langchain_agent.run_chem_agent`)

## Core backend “services” (responsibilities + integrations)

### Postgres / ChEMBL access

- **`backend/app/db/pg.py`**
  - Builds DSN from `DATABASE_URL` or `DB_*` / `PG*` env vars.
  - Provides `pg_conn()` context manager (psycopg v3) and sets `statement_timeout`.

- **`backend/app/services/chembl_service.py`** (main ChEMBL data access)
  - Executes SQL queries loaded from `backend/app/db/sql_loader.py`.
  - Uses **psycopg v3** by default (`pg_conn()`), and also supports a **legacy psycopg2** connection mode when initialized with a config containing `host`.
  - Key methods used by the pipeline:
    - `get_by_chembl_id()`, `get_molecule_by_inchi_key()`, `get_molecule_by_canonical_smiles()`
    - `fetch_evidence_by_chembl_id()` (bioactivity rows)
    - `get_molecules_bulk()` (used after similarity search to fetch structures)

### Molecule resolution

- **`backend/app/services/resolution/molecule_resolver.py`**
  - Convenience wrapper over `ChemblService` to resolve by name/ID/InChIKey.
  - Note: it currently creates a **global legacy** `ChemblService(config)` and calls `_svc.connect()` at import time.

### Similarity / vector search

- **Milvus Lite implementation**: `backend/app/services/milvus_service.py`
  - Creates/uses a local Milvus Lite DB file at `MILVUS_DB_PATH`.
  - Maintains collection `MILVUS_COLLECTION` (default `chembl_morgan_2048`) with a schema including `fp` (2048-d float vector).
  - Provides `search(fp_vector, top_k=...)` returning coarse COSINE hits.

- **RDKit utilities**: `backend/app/services/rdkit_service.py`
  - Produces **Morgan fingerprint** (radius=2, nBits=2048) for both ingestion and query (`morgan_fp()`).
  - Reranks Milvus candidates with exact **Tanimoto** on RDKit bit vectors.
  - Also does SMILES validation, canonicalization, and molecule depiction (PNG/SVG).

- **Older/unused alternatives (present in repo)**
  - `backend/app/services/similarity/faiss_store.py` and `similarity_service.py` implement an in-memory FAISS index path, but the orchestrated pipeline is using Milvus Lite + RDKit rerank.
  - `backend/app/services/similarity/milvus_store.py` is a placeholder in-memory cosine search and is not the Milvus Lite path used by the orchestrator.

### Evidence aggregation (RAG “bundle”)

- **`GET /rag/molecule`** (`backend/app/api/routes/rag.py`)
  - Flow: name → `MoleculeResolver.resolve_by_name()` → `ChemblEvidenceFetcher.fetch_by_chembl_id()` → `EvidenceBundleBuilder.build()`.

- **Chat/report pipeline path** (`backend/app/services/rag_orchestrator.py`)
  - Evidence is fetched via `ChemblService.fetch_evidence_by_chembl_id()` and filtered (confidence score, target validity).
  - A summary bundle is built with `EvidenceBundleBuilder.build()` and adapted for reporting.

### Predictions

- **`backend/app/services/ml/deepchem_predictor.py`** (called from orchestrator)
  - Produces prediction outputs from canonical SMILES (the orchestrator normalizes it into `list[dict]` for reports).

### LLM + report generation

- **`backend/app/llm/chemllm_client.py`**
  - **ChemLLM** path: **LangChain** **`ChatOllama`** against **`OLLAMA_BASE_URL`** / **`CHEMLLM_MODEL`** (requires **`llm`** optional deps + local **Ollama**).

- **`backend/app/services/llm/rag_llm.py`**
  - Builds a strict JSON-only prompt embedding the evidence bundle (molecule + similar hits + evidence summary + predictions).
  - Calls **Ollama** `POST /api/generate` at `http://localhost:11434` with model `llama3.2:latest`.
  - Parses the response as JSON and normalizes into structured fields for report sections.

- **`backend/app/services/report_service.py`**
  - Converts the orchestrator result into a `ReportJSON` object.
  - Stores reports **in-memory** (`_report_store` dict). (No Postgres persistence for reports yet.)

## How everything connects (end-to-end request flow)

### UI → backend

- Frontend calls endpoints on the FastAPI server (`NEXT_PUBLIC_API_BASE_URL`).

### `POST /chat` (main “agentic RAG” flow)

Implemented in `backend/app/api/routes/chat.py`:

1. **Normalize & plan** (`backend/app/services/rag_orchestrator.py`)
   - Detects whether input is a ChEMBL ID, InChIKey, InChI, SMILES, or a name.
   - Builds a tool plan (resolve → optional similarity → evidence → optional prediction → aggregate → report → verify).

2. **Resolve molecule (Postgres)**
   - Uses `ChemblService` / `MoleculeResolver` to query ChEMBL in **Postgres** using SQL files.

3. **Similarity search (Vector DB + RDKit rerank)**
   - If there is canonical SMILES:
     - RDKit computes Morgan FP (2048).
     - **Milvus Lite** searches COSINE over stored vectors (`milvus_lite.db`).
     - The hit set is reranked using RDKit **Tanimoto** to produce final `similar_hits`.

4. **Evidence retrieval (Postgres)**
   - Fetches activity/assay/target evidence rows from ChEMBL in Postgres.

5. **Predictions (DeepChem)**
   - Uses canonical SMILES to run prediction tasks (if intent includes it / if available).

6. **Report sections (LLM)**
   - Creates an evidence bundle and calls **Ollama** via `RAGLLM.generate()`.
   - If LLM fails, it falls back to deterministic template sections.

7. **Report assembly**
   - `assemble_report()` builds `ReportJSON` and stores it in-memory.
   - Response includes `reply` + counts + `report_id`.

### `GET /rag/molecule` (bundle-only)

A simpler flow: resolve name → fetch evidence from Postgres → build an evidence bundle (no Milvus, no LLM).

## Configuration locations

- **Backend**: `backend/.env` (example in `backend/.env.example`)
  - Postgres: `DATABASE_URL` or `DB_*` / `PG*`
  - Milvus Lite: `MILVUS_DB_PATH`, `MILVUS_COLLECTION`, etc.
  - LLM: `OLLAMA_BASE_URL`, `CHEMLLM_MODEL`, `CHEMLLM_TEMPERATURE` (note: `rag_llm.py` currently hardcodes its URL/model)

- **Frontend**: `frontend/.env.local`
  - `NEXT_PUBLIC_API_BASE_URL`

