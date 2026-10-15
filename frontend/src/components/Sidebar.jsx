import { Link } from "react-router-dom";
import { Brain, Menu, Plus, Search, Sparkles, Upload } from "lucide-react";
import { useConversations } from "@/context/ConversationsContext";
import { ConversationItem } from "@/components/ConversationItem";

const IconButton = ({ children, ...props }) => (
  <button
    {...props}
    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-200/70"
  >
    {children}
  </button>
);

export const Sidebar = ({ open, onToggle, activeId, onNew, onNavigate }) => {
  const { items, query, setQuery, loaded } = useConversations();

  return (
    <>
      {open && <div onClick={onToggle} className="fixed inset-0 z-40 bg-slate-900/20 md:hidden" />}
      <aside
        data-testid="sidebar"
        data-state={open ? "open" : "collapsed"}
        className={`fixed inset-y-0 left-0 z-50 flex shrink-0 flex-col bg-[#f0f4f9] transition-[width,transform] duration-200 md:static md:translate-x-0 ${
          open ? "w-[280px] translate-x-0" : "w-[280px] -translate-x-full md:w-[68px]"
        }`}
      >
        <div className="flex items-center gap-1 px-3 pt-3">
          <IconButton data-testid="sidebar-toggle-button" onClick={onToggle} aria-label="Réduire ou développer le menu">
            <Menu className="h-5 w-5" />
          </IconButton>
          {open && (
            <span className="ml-1 flex items-center gap-1.5 font-display text-base font-semibold text-slate-800">
              <Sparkles className="h-4 w-4 text-[#4285f4]" /> Gemini Perso
            </span>
          )}
        </div>

        <div className="px-3 pt-6">
          <button
            data-testid="new-chat-button"
            onClick={onNew}
            title="Nouvelle discussion"
            className={`flex h-10 items-center gap-3 rounded-full text-sm font-medium text-slate-700 transition-colors hover:bg-slate-200/70 ${
              open ? "w-full bg-white/70 px-4 shadow-sm" : "w-10 justify-center"
            }`}
          >
            <Plus className="h-5 w-5 shrink-0" />
            {open && "Nouvelle discussion"}
          </button>
        </div>

        {open && (
          <>
            <div className="px-3 pt-4">
              <div className="flex h-10 items-center gap-2 rounded-full bg-white/70 px-4 focus-within:ring-2 focus-within:ring-blue-200">
                <Search className="h-4 w-4 text-slate-400" />
                <input
                  data-testid="conversation-search-input"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Rechercher des discussions"
                  className="w-full bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
                />
              </div>
            </div>
            <p className="px-6 pb-2 pt-6 text-xs font-semibold text-slate-500">Récent</p>
            <nav data-testid="conversation-list" className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
              {items.map((c) => (
                <ConversationItem key={c.id} conv={c} active={c.id === activeId} onNavigate={onNavigate} />
              ))}
              {loaded && items.length === 0 && (
                <p data-testid="conversation-list-empty" className="px-3 py-2 text-sm text-slate-400">
                  {query ? "Aucune discussion trouvée." : "Aucune discussion pour l'instant."}
                </p>
              )}
            </nav>
          </>
        )}
        <div className={`space-y-0.5 border-t border-slate-200/70 px-3 py-3 ${open ? "" : "mt-auto"}`}>
          <Link
            to="/importer"
            data-testid="sidebar-import-link"
            title="Importer depuis Gemini"
            className={`flex h-10 items-center gap-3 rounded-full text-sm text-slate-700 transition-colors hover:bg-slate-200/70 ${open ? "px-4" : "w-10 justify-center"}`}
          >
            <Upload className="h-5 w-5 shrink-0" />
            {open && "Importer depuis Gemini"}
          </Link>
          <Link
            to="/memoire"
            data-testid="sidebar-memory-link"
            title="Mémoire"
            className={`flex h-10 items-center gap-3 rounded-full text-sm text-slate-700 transition-colors hover:bg-slate-200/70 ${open ? "px-4" : "w-10 justify-center"}`}
          >
            <Brain className="h-5 w-5 shrink-0" />
            {open && "Mémoire"}
          </Link>
        </div>
      </aside>
    </>
  );
};
