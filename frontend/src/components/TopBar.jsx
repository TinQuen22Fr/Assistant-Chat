import { FolderOpen, Menu, ScrollText } from "lucide-react";
import { ModelSelect } from "@/components/ModelSelect";
import { ProfileMenu } from "@/components/ProfileMenu";

export const TopBar = ({ model, onModelChange, disabled, title, onToggleSidebar, onOpenFiles, onSummarize, canSummarize, hasConversation }) => (
  <header data-testid="app-header" className="flex h-16 shrink-0 items-center gap-2 px-3 sm:px-5">
    <button
      onClick={onToggleSidebar}
      aria-label="Ouvrir le menu"
      className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 md:hidden"
    >
      <Menu className="h-5 w-5" />
    </button>
    <ModelSelect value={model} onChange={onModelChange} disabled={disabled} />
    <p data-testid="conversation-title" className="ml-2 hidden min-w-0 flex-1 truncate text-sm text-slate-500 sm:block">
      {title}
    </p>
    <div className="ml-auto flex items-center gap-1">
      {hasConversation && (
        <button
          data-testid="summarize-conversation-button"
          onClick={onSummarize}
          disabled={!canSummarize}
          title="Résumer la discussion"
          className="flex h-10 items-center gap-2 rounded-full px-3 text-sm text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40"
        >
          <ScrollText className="h-5 w-5" />
          <span className="hidden lg:inline">Résumer la discussion</span>
        </button>
      )}
      {hasConversation && (
        <button
          data-testid="open-files-panel-button"
          onClick={onOpenFiles}
          title="Fichiers de la discussion"
          className="flex h-10 items-center gap-2 rounded-full px-3 text-sm text-slate-600 transition-colors hover:bg-slate-100"
        >
          <FolderOpen className="h-5 w-5" />
          <span className="hidden lg:inline">Fichiers</span>
        </button>
      )}
      <ProfileMenu />
    </div>
  </header>
);
