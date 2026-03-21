# AI-Powered Task & Knowledge Management System

A production-ready MVP built with **FastAPI + MySQL + FAISS + sentence-transformers**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                      │
│                                                                 │
│  /auth  ──► AuthRouter       JWT mint / validate               │
│  /tasks ──► TasksRouter      CRUD + dynamic filtering          │
│  /documents ► DocsRouter     Upload → chunk → embed            │
│  /search ──► SearchRouter    Query → embed → FAISS → results   │
│  /analytics ► Analytics      Task stats + top queries          │
│  /users ──► UsersRouter      Admin user management             │
└────────────────────┬────────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
     MySQL (SQLAlchemy)    FAISS + sentence-transformers
     ─ users               ─ all-MiniLM-L6-v2 (384-dim)
     ─ roles               ─ IndexFlatIP (cosine similarity)
     ─ tasks               ─ Persisted to faiss_index.bin
     ─ documents
     ─ document_chunks
     ─ activity_logs
```

---

## Database Schema

```sql
roles          ← id, name, description
users          ← id, username, email, hashed_password, role_id (FK→roles)
tasks          ← id, title, status, priority, assigned_to (FK→users), created_by (FK→users)
documents      ← id, title, filename, file_path, is_indexed, uploaded_by (FK→users)
document_chunks← id, document_id (FK→documents), chunk_index, chunk_text, faiss_index_id
activity_logs  ← id, user_id (FK→users), action, entity_type, entity_id, detail, ip_address
```

---

## Quick Start

### Option A – Docker (recommended)

```bash
git clone <repo>
cd ai_task_system
docker-compose up --build
```

API available at: http://localhost:8000  
Swagger UI:       http://localhost:8000/docs

### Option B – Local (requires MySQL running)

```bash
# 1. Create virtual env
python -m venv venv && source venv/bin/activate

# 2. Install deps
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit DATABASE_URL, SECRET_KEY in .env

# 4. Seed DB (creates tables + default users)
python seed.py

# 5. Run
uvicorn app.main:app --reload
```

---

## Default Credentials

| Role  | Username | Password  |
|-------|----------|-----------|
| Admin | admin    | Admin@123 |
| User  | john     | User@123  |

---

## API Reference

### Authentication

```http
POST /auth/login
Content-Type: application/json

{ "username": "admin", "password": "Admin@123" }
```

Returns `access_token` — include in all subsequent requests:
```
Authorization: Bearer <token>
```

---

### Tasks

| Method | Endpoint        | Role        | Description                       |
|--------|-----------------|-------------|-----------------------------------|
| GET    | /tasks          | any         | List tasks (filterable)           |
| GET    | /tasks/{id}     | any         | Get single task                   |
| POST   | /tasks          | admin       | Create & assign task              |
| PATCH  | /tasks/{id}     | any         | Update task (users: status only)  |
| DELETE | /tasks/{id}     | admin       | Delete task                       |

**Dynamic Filtering Examples:**
```
GET /tasks?status=completed
GET /tasks?assigned_to=1
GET /tasks?status=pending&priority=high
GET /tasks?created_by=1&status=in_progress
```

---

### Documents

| Method | Endpoint              | Role  | Description                      |
|--------|-----------------------|-------|----------------------------------|
| POST   | /documents/upload     | admin | Upload .txt/.pdf → auto-indexed  |
| GET    | /documents            | any   | List documents                   |
| GET    | /documents/{id}       | any   | Get document metadata            |
| DELETE | /documents/{id}       | admin | Delete + remove from FAISS       |

Upload example (multipart):
```bash
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "title=Company Handbook" \
  -F "file=@handbook.txt"
```

---

### Search (Semantic / AI)

```http
POST /search
Content-Type: application/json

{ "query": "vacation policy", "top_k": 5 }
```

**How it works:**
1. Query text → 384-dim embedding (sentence-transformers, local)
2. FAISS cosine similarity search across all indexed chunks
3. Retrieve chunk text + document metadata from MySQL
4. Return ranked results with similarity scores

---

### Analytics

```http
GET /analytics
```

Returns:
- Task stats (total, pending, in_progress, completed)
- Total documents & users
- Top 10 most-searched queries
- Activity count in last 24 hours

---

## AI / Embedding Architecture

```
Document Upload
      │
      ▼
 Extract Text (.txt / .pdf)
      │
      ▼
 Chunk Text (512 chars, 64 overlap)
      │
      ▼
 sentence-transformers (all-MiniLM-L6-v2)
 → 384-dimensional float32 vectors
      │
      ▼
 L2 Normalize → FAISS IndexFlatIP
 (inner product = cosine similarity after normalisation)
      │
      ▼
 Persist: faiss_index.bin + MySQL chunks


Search Query
      │
      ▼
 Embed query → 384-dim vector
      │
      ▼
 FAISS.search(top_k)
      │
      ▼
 Lookup chunk text + doc metadata (MySQL)
      │
      ▼
 Return ranked SearchResult[]
```

**Key design choices:**
- `all-MiniLM-L6-v2` runs 100% locally — no OpenAI/API keys required
- FAISS `IndexFlatIP` gives exact nearest-neighbour (no approximation for correctness)
- Chunk metadata lives in MySQL; only raw vectors live in FAISS
- Index is persisted to disk and reloaded on startup (stateful)

---

## RBAC Summary

| Endpoint              | Admin | User |
|-----------------------|-------|------|
| Create user           | ✅    | ❌   |
| Upload document       | ✅    | ❌   |
| Delete document       | ✅    | ❌   |
| Create task           | ✅    | ❌   |
| Assign task           | ✅    | ❌   |
| View all tasks        | ✅    | ❌*  |
| View own tasks        | ✅    | ✅   |
| Update task status    | ✅    | ✅** |
| Search documents      | ✅    | ✅   |
| View analytics        | ✅    | ✅   |

\* Users see only tasks assigned to or created by them  
\*\* Users can only change `status` field on tasks assigned to them

---

## Activity Logging

All key actions are tracked in `activity_logs`:

| Action           | Trigger                        |
|------------------|--------------------------------|
| `login`          | Successful login               |
| `login_failed`   | Bad credentials                |
| `task_create`    | Admin creates task             |
| `task_update`    | Any status/field change        |
| `task_view`      | Single task fetched            |
| `document_upload`| File uploaded & indexed        |
| `document_view`  | Document metadata fetched      |
| `search`         | Semantic search performed      |

Each log record stores: `user_id`, `action`, `entity_type`, `entity_id`, `detail` (JSON), `ip_address`, `timestamp`.

---

## Project Structure

```
ai_task_system/
├── app/
│   ├── main.py                  # FastAPI app + lifespan
│   ├── core/
│   │   ├── config.py            # Pydantic settings
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   └── security.py          # JWT + RBAC helpers
│   ├── models/
│   │   └── user.py              # All ORM models (User, Task, Document…)
│   ├── schemas/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── services/
│   │   ├── search_service.py    # FAISS + sentence-transformers
│   │   └── activity_service.py  # Activity logging helper
│   └── routers/
│       ├── auth.py
│       ├── tasks.py
│       ├── documents.py
│       ├── search.py
│       ├── analytics.py
│       └── users.py
├── seed.py                      # DB init + default data
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```
