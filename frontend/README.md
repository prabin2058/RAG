# RAG PDF Q&A — Frontend

React + Vite + Tailwind CSS frontend for the RAG PDF Q&A app — now with **JWT login/registration** and per-user workspaces. Connects to the FastAPI backend at `http://localhost:8000`. No API keys or paid services.

**Stack:** React 19 · Vite 7 · Tailwind 4 · TanStack Query · Zustand · React Router 7 · lucide-react · react-hot-toast

## Prerequisites

- Node 18+
- The backend running locally (see `../backend/README.md`)
- Ollama running with a model pulled

## Setup & run

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The backend and Ollama must be running first.

## Auth flow

- `/register` — create an account (email + min-8-char password, validation + toasts)
- `/login` — sign in (OAuth2 form flow, Swagger-compatible)
- Token stored in `localStorage`; validated against `/auth/me` on page load
- Any 401 from the API clears the session and redirects to `/login`
- Logout button in the sidebar header

## Configuration

Copy `.env.example` to `.env` if the backend isn't on the default address:

```bash
VITE_API_URL=http://localhost:8000
```

## Features

- Sidebar: document list with status badges, upload modal, per-document delete, user email + logout
- Drag-and-drop PDF upload with background processing status polling (every 2s)
- Chat with page-cited sources, collapsible citations, thinking indicator, auto-scroll
- Optimistic user messages (TanStack Query `setQueryData` + `invalidateQueries`, rolled back on error)
- Responsive: sidebar collapses into a slide-over drawer on mobile

## Structure

```
src/
├── main.jsx / App.jsx        # router + guards + providers
├── Layout.jsx                # two-column shell
├── api.js                    # fetch wrapper: token injection, 401 handling, /api/v1
├── auth.js                   # register / login / me calls
├── authStore.js              # zustand: token + user, localStorage persistence
├── AuthContext.jsx           # login/register/logout actions + session restore
├── store.js                  # zustand: active document
├── components/               # Sidebar, UploadModal, ChatWindow, MessageBubble,
│                             # SourceCitation, RequireAuth (guards)
└── pages/                    # Login.jsx, Register.jsx
```

## Build for production

```bash
npm run build && npm run preview
```