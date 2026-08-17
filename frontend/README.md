# RAG PDF Q&A — Frontend

React + Vite + Tailwind CSS frontend for the RAG PDF Q&A app. Connects to the FastAPI backend at `http://localhost:8000`. No API keys or paid services — everything routes through the local backend.

**Stack:** React 19 · Vite 7 · Tailwind CSS 4 · TanStack Query · Zustand · lucide-react · react-hot-toast

## Prerequisites

- Node 18+
- The backend running locally (see `../backend/README.md`)
- Ollama running with a model pulled

## Setup

```bash
cd frontend
npm install
```

## Run

```bash
npm run dev
```

Open http://localhost:5173. Both the backend and Ollama must be running first.

## Configuration

Copy `.env.example` to `.env` if the backend isn't on the default address:

```bash
VITE_API_URL=http://localhost:8000
```

## Build for production

```bash
npm run build && npm run preview
```

## Features

- Sidebar document list with status badges (processing / ready / failed), upload modal, and per-document delete
- Drag-and-drop PDF upload with background processing status polling (every 2s)
- Chat with page-cited sources, collapsible per-answer citations, thinking indicator, and auto-scroll
- Responsive: sidebar collapses into a slide-over drawer on mobile