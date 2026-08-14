

# Governed Memory Hub - Complete Enterprise Governed Memory Platform (Phases 1–11)

This project implements the **Governed Memory Hub**, establishing an enterprise-grade, privacy-preserving, governance-first AI memory platform spanning Phases 1 through 11: Foundation, Compliance Controls, Synthetic Corpus, Ingestion Tollgate, Policy Engine, Retrieval & Filtering, Graph Lineage, Agent Orchestration, Evidence Package Verification, Section 14 Control Cockpit Dashboard, and Section 12 Erasure & Retention Governance.

## 🏗 Directory Structure

```
.
├── apps/
│   ├── api/             # FastAPI backend service (GET /health endpoint & dependency monitoring)
│   └── cockpit/         # Next.js 14 control cockpit UI dashboard
├── services/            # Placeholder for future phase core services
├── agents/              # Placeholder for future phase agent implementations
├── db/
│   ├── migrations/      # Database migrations placeholder
│   └── seeds/           # Database seeds placeholder
├── security/            # Security & policy placeholder
├── tests/               # Automated test suite (pytest)
├── infra/               # Infrastructure configurations placeholder
├── docs/                # Project documentation
├── scripts/             # Developer & operational automation scripts
├── .env.example         # Environment variables template
├── docker-compose.yml   # Multi-container orchestration (PostgreSQL 16, Redis, API, Cockpit)
├── Makefile             # Developer control commands (up, down, logs, test)
└── README.md            # Project guide and documentation
```

---

## 🚀 Quick Start Instructions

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- `make` (optional, for convenience)

### 1. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 2. Start all services using Makefile
```bash
make up
```
Or directly with Docker Compose:
```bash
docker compose up -d --build
```

### 3. Verify System Health
Once started, check the status of running containers:
```bash
docker compose ps
```

Access the components:
- **Cockpit UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI /health Endpoint**: [http://localhost:8000/health](http://localhost:8000/health)
- **FastAPI Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Running Automated Tests

Run the full pytest suite inside the API container:
```bash
make test
```
Or directly via Docker Compose:
```bash
docker compose exec api pytest -v /app/tests
```

---

## 🛠 Useful Makefile Commands

- `make up`: Build and start all container services in detached mode
- `make down`: Stop and remove all containers and networks
- `make logs`: View live streaming logs from all services
- `make test`: Execute automated unit and integration tests

---

## 📡 API Health Endpoint (`GET /health`)

Returns real-time status and health checks for external dependencies (PostgreSQL 16 and Redis):

```json
{
  "status": "healthy",
  "service": "Governed Memory Hub API",
  "phase": "Phase 1: Foundation",
  "timestamp": "2026-08-13T12:00:00.000Z",
  "dependencies": {
    "postgres": {
      "status": "healthy",
      "latency_ms": 1.25,
      "message": "PostgreSQL 16 connection successful"
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 0.82,
      "message": "Redis connection successful"
    }
  }
}
```

---

## 🔒 Scope & Non-Goals (Phase 1)
As mandated by project requirements:
- **Phase 1 Only**: Focuses strictly on infrastructure foundation, container health monitoring, FastAPI backend, and Next.js status dashboard.
- **Phase 2+ Non-Goals**: No agents, RAG, pgvector, Apache AGE graph store, OPA policy engine, authentication, or business logic in this phase.
