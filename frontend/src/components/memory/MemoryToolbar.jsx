import { useState } from "react";
import { Download, Search, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ImportDialog } from "@/components/memory/ImportDialog";
import { apiFetch } from "@/lib/api";
import { downloadText } from "@/lib/clipboard";

const ToolButton = ({ children, className = "", ...props }) => (
  <button {...props} className={`flex h-10 items-center gap-2 rounded-full border border-slate-200 px-4 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-40 ${className}`}>
    {children}
  </button>
);

export const MemoryToolbar = ({ mem }) => {
  const [confirmAll, setConfirmAll] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const exportMd = async () => {
    const res = await apiFetch("/memories/export");
    if (!res.ok) return toast.error("L'export a échoué.");
    downloadText("memoire-gemini-perso.md", await res.text());
  };

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <div className="flex h-10 min-w-[220px] flex-1 items-center gap-2 rounded-full bg-[#f0f4f9] px-4 focus-within:ring-2 focus-within:ring-blue-200">
        <Search className="h-4 w-4 text-slate-400" />
        <input
          data-testid="memory-search-input"
          value={mem.query}
          onChange={(e) => mem.setQuery(e.target.value)}
          placeholder="Rechercher dans la mémoire"
          className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
        />
      </div>
      <ToolButton data-testid="memory-export-button" onClick={exportMd}>
        <Download className="h-4 w-4" /> Exporter .md
      </ToolButton>
      <ToolButton data-testid="memory-import-button" onClick={() => setImportOpen(true)}>
        <Upload className="h-4 w-4" /> Importer .md
      </ToolButton>
      <ToolButton data-testid="memory-delete-all-button" onClick={() => setConfirmAll(true)} disabled={!mem.items.length} className="text-red-600 hover:bg-red-50">
        <Trash2 className="h-4 w-4" /> Tout supprimer
      </ToolButton>

      <ImportDialog open={importOpen} onOpenChange={setImportOpen} onImported={mem.reload} />

      <AlertDialog open={confirmAll} onOpenChange={setConfirmAll}>
        <AlertDialogContent className="rounded-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer toute la mémoire ?</AlertDialogTitle>
            <AlertDialogDescription>Tous vos souvenirs seront définitivement effacés. Pensez à exporter avant si besoin.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-full">Annuler</AlertDialogCancel>
            <AlertDialogAction
              data-testid="memory-delete-all-confirm-button"
              onClick={() => mem.removeAll().then(() => toast.success("Mémoire effacée")).catch(() => {})}
              className="rounded-full bg-red-600 hover:bg-red-700"
            >
              Tout supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
