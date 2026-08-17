// Two-column layout: collapsible sidebar + main chat panel.
// On mobile the sidebar becomes a slide-over drawer.
import { useState } from 'react'
import { PanelLeft } from 'lucide-react'
import Sidebar from './components/Sidebar.jsx'
import ChatWindow from './components/ChatWindow.jsx'

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const closeSidebar = () => setSidebarOpen(false)

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      {/* Desktop sidebar */}
      <aside className="hidden w-80 shrink-0 border-r border-zinc-800 md:block">
        <Sidebar onDocSelected={closeSidebar} />
      </aside>

      {/* Mobile slide-over drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={closeSidebar} />
          <aside className="absolute inset-y-0 left-0 w-80 max-w-[85vw] border-r border-zinc-800 bg-zinc-950 shadow-2xl">
            <Sidebar onDocSelected={closeSidebar} />
          </aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        {/* Mobile header with hamburger */}
        <header className="flex items-center gap-3 border-b border-zinc-800 px-4 py-3 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 hover:bg-zinc-800"
            aria-label="Open document list"
          >
            <PanelLeft size={20} />
          </button>
          <h1 className="text-sm font-semibold">RAG PDF Q&amp;A</h1>
        </header>

        <ChatWindow />
      </main>
    </div>
  )
}