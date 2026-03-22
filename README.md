# AI-Powered Task & Knowledge Management System

A focused MVP that demonstrates **system design**, **AI integration**, and **clean implementation** — built with FastAPI, MySQL, FAISS, and sentence-transformers.

---

## What This System Does

An organisation's admin builds a knowledge base by uploading documents. Users are assigned tasks and can semantically search those documents to complete their work. Every action is logged, every API is role-protected, and the AI search runs entirely on-device — no external API keys required.

---

## Tech Stack

| Layer | Technology | Why this choice |
|---|---|---|
| API Framework | **FastAPI** (Python 3.11) | Async support, automatic OpenAPI docs, dependency injection for clean RBAC |
| Database | **MySQL 8** + SQLAlchemy ORM | Relational integrity with FK constraints; SQLAlchemy keeps models decoupled from raw SQL |
| Auth | **JWT** (python-jose) + bcrypt (passlib) | Stateless tokens — no session storage needed; bcrypt for secure password hashing |
| AI Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` | 384-dim vectors, runs 100% locally, no OpenAI dependency, strong semantic quality |
| Vector Store | **FAISS** `IndexFlatIP` | Exact cosine similarity via inner product on L2-normalised vectors; persisted to disk |
| Validation | **Pydantic v2** | Request/response contracts enforced at the boundary; errors surface early |
| Frontend | Vanilla HTML/CSS/JS (single file) | Zero build toolchain; ships as a static file served by FastAPI |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                    │
│                                                             │
│  /auth/login      → verify credentials → issue JWT        │
│  /tasks           → CRUD + query filters (RBAC enforced)   │
│  /documents/upload → extract → chunk → embed → FAISS      │
│  /search          → embed query → FAISS → MySQL lookup     │
│  /analytics       → aggregate stats from activity_logs     │
│  /notifications   → poll assignments + deadlines           │
└────────────────┬────────────────────────┬───────────────────┘
                 │                        │
          MySQL (SQLAlchemy)       FAISS + sentence-transformers
          ├─ roles                 ├─ all-MiniLM-L6-v2 (384-dim)
          ├─ users  (FK → roles)   ├─ IndexFlatIP  (cosine sim)
          ├─ tasks  (FK → users)   └─ Persisted: faiss_index.bin
          ├─ documents (FK → users)        faiss_id_map.npy
          ├─ document_chunks (FK → documents)
          └─ activity_logs (FK → users)
```

---

## AI Integration — How It Actually Works

This is the core of the system. The implementation avoids black-box LLM calls and builds the pipeline from scratch.

### Document Indexing (on upload)

```
Raw file (.txt / .pdf)
    │
    ▼  extract text
Plain text string
    │
    ▼  chunk_text()  — 512-char windows, 64-char overlap
List[str]  (preserves context across chunk boundaries)
    │
    ▼  SentenceTransformer.encode()
float32 array  shape: (N, 384)
    │
    ▼  faiss.normalize_L2()   — converts to unit vectors
    │
    ▼  FAISS IndexFlatIP.add()
Vectors stored in memory + persisted to faiss_index.bin
Chunk text + metadata stored in MySQL (document_chunks table)
```

### Semantic Search (on query)

```
User query string
    │
    ▼  SentenceTransformer.encode()  +  normalize_L2()
Query vector  shape: (1, 384)
    │
    ▼  FAISS IndexFlatIP.search(query_vec, top_k)
    │   — inner product = cosine similarity (after normalisation)
    │   — returns indices + similarity scores
    │
    ▼  id_map[index]  →  (document_id, chunk_db_id)
    │
    ▼  MySQL lookup: SELECT chunk_text, document title
    │
Ranked results with similarity scores  →  JSON response
```

**Key design decision:** Chunk metadata lives in MySQL (queryable, relational), raw float32 vectors live in FAISS (fast nearest-neighbour). The two are linked via an in-memory `id_map` that is persisted alongside the index so it survives restarts.

---

## Database Schema

Six tables with proper primary keys, foreign keys, and indexes.

```sql
roles
  id          INT PK AUTO_INCREMENT
  name        VARCHAR(50) UNIQUE NOT NULL        -- 'admin' | 'user'
  description VARCHAR(255)

users
  id              INT PK AUTO_INCREMENT
  username        VARCHAR(100) UNIQUE NOT NULL   (indexed)
  email           VARCHAR(255) UNIQUE NOT NULL   (indexed)
  hashed_password VARCHAR(255) NOT NULL
  full_name       VARCHAR(255)
  is_active       BOOLEAN NOT NULL DEFAULT TRUE
  role_id         INT FK → roles.id

tasks
  id          INT PK AUTO_INCREMENT
  title       VARCHAR(255) NOT NULL
  description TEXT
  status      ENUM('pending','in_progress','completed')  (indexed)
  priority    ENUM('low','medium','high')
  due_date    DATETIME
  assigned_to INT FK → users.id  (indexed)
  created_by  INT FK → users.id

documents
  id              INT PK AUTO_INCREMENT
  title           VARCHAR(255) NOT NULL
  filename        VARCHAR(255) NOT NULL
  file_path       VARCHAR(512) NOT NULL
  file_type       VARCHAR(50)
  file_size       INT
  chunk_count     INT
  is_indexed      BOOLEAN
  uploaded_by     INT FK → users.id

document_chunks
  id            INT PK AUTO_INCREMENT
  document_id   INT FK → documents.id  (indexed, CASCADE DELETE)
  chunk_index   INT NOT NULL
  chunk_text    TEXT NOT NULL
  faiss_index_id INT

activity_logs
  id          INT PK AUTO_INCREMENT
  user_id     INT FK → users.id
  action      VARCHAR(100)  (indexed)   -- login | task_update | search | ...
  entity_type VARCHAR(50)
  entity_id   INT
  detail      TEXT  (JSON string)
  ip_address  VARCHAR(45)
  created_at  DATETIME  (indexed)
```

---

## RBAC Design

Role enforcement is implemented as **FastAPI dependency functions**, not middleware. Each route explicitly declares which dependency it requires.

```python
# Protects a route to admins only
@router.post("/tasks")
def create_task(current_user = Depends(require_admin), ...):
    ...

# Any authenticated user
@router.post("/search")
def search(current_user = Depends(get_current_user), ...):
    ...

# Additional row-level check inside handler
if current_user.role.name != "admin":
    if task.assigned_to != current_user.id:
        raise HTTPException(403, "Access denied")
```

| Endpoint | Admin | User |
|---|:---:|:---:|
| Upload / delete document | ✅ | ❌ |
| Create / assign task | ✅ | ❌ |
| View all tasks | ✅ | ❌ |
| View own assigned tasks | ✅ | ✅ |
| Update task status | ✅ | ✅ (own only) |
| Semantic search | ✅ | ✅ |
| Analytics | ✅ | ✅ |

---

## Project Structure

```
ai_task_system/
├── app/
│   ├── main.py                     # App factory, CORS, lifespan, static file serving
│   ├── core/
│   │   ├── config.py               # Pydantic Settings — reads .env, type-safe
│   │   ├── database.py             # SQLAlchemy engine, SessionLocal, get_db()
│   │   └── security.py             # JWT encode/decode, password hashing, RBAC deps
│   ├── models/
│   │   └── user.py                 # All 6 ORM models — single file, clear relationships
│   ├── schemas/
│   │   └── schemas.py              # Pydantic request + response models
│   ├── services/
│   │   ├── search_service.py       # VectorSearchService — FAISS + sentence-transformers
│   │   └── activity_service.py     # log_activity() — single function, called everywhere
│   └── routers/
│       ├── auth.py                 # POST /auth/login, GET /auth/me
│       ├── tasks.py                # Full CRUD + dynamic query filters
│       ├── documents.py            # Upload, list, download, delete
│       ├── search.py               # POST /search — semantic pipeline
│       ├── analytics.py            # GET /analytics — task stats + top queries
│       ├── notes.py                # Task notes (stored in activity_logs)
│       ├── notifications.py        # Server-side polling + deadline alerts
│       └── users.py                # User management (admin only)
├── static/
│   └── index.html                  # Full SaaS frontend — single file, no build step
├── seed.py                         # Creates tables + seeds default roles and users
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

---

## Setup Instructions

### Prerequisites
- Python 3.11
- MySQL 8.0

### Local Setup

```bash
# 1. Clone / unzip the project
cd ai_task_system

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and set DATABASE_URL with your MySQL root password:
# DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/ai_task_db

# 5. Create the database
# In MySQL CLI:
CREATE DATABASE ai_task_db;

# 6. Seed — creates all 6 tables + default accounts
python seed.py

# 7. Run
uvicorn app.main:app --reload
```

| URL | Purpose |
|---|---|
| http://localhost:8000 | Frontend UI |
| http://localhost:8000/docs | Swagger API docs |

### Docker (no local MySQL needed)

```bash
docker-compose up --build
```

### Default Accounts

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin@123` |
| User | `john` | `User@123` |

---

## API Reference

### Authentication
```http
POST /auth/login
{"username": "admin", "password": "Admin@123"}

→ {"access_token": "eyJ...", "role": "admin", ...}
```
All protected endpoints require: `Authorization: Bearer <token>`

### Tasks — dynamic filtering
```
GET /tasks                              all tasks (admin) / own tasks (user)
GET /tasks?status=pending
GET /tasks?assigned_to=2
GET /tasks?status=completed&priority=high
POST   /tasks          (admin)  create + assign
PATCH  /tasks/{id}              update status
DELETE /tasks/{id}     (admin)  delete
```

### Documents
```
POST /documents/upload      (admin)  multipart: title + file (.txt / .pdf)
GET  /documents                      list all
GET  /documents/{id}/download        view / download file
DELETE /documents/{id}     (admin)
```

### Search
```http
POST /search
{"query": "what is the leave policy", "top_k": 5}

→ ranked results with similarity scores
```

### Analytics
```
GET /analytics
→ task counts by status, document count, top 10 search queries, 24h activity
```

---

## Activity Logging

Every key action is persisted to `activity_logs` with user, timestamp, IP, and a JSON detail blob.

| Action | Trigger |
|---|---|
| `login` | Successful sign-in |
| `login_failed` | Bad credentials |
| `task_create` | Admin creates task |
| `task_update` | Status or field change |
| `document_upload` | File indexed into FAISS |
| `document_view` | Document metadata fetched |
| `search` | Semantic query executed — query text stored for analytics |
| `task_note` | Note added to a task |
