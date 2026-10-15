import { useEffect, useState } from "react";
import { Download, FileText, Image as ImageIcon, ScrollText } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { apiJson, fileUrl } from "@/lib/api";
import { formatSize } from "@/lib/files";

export const FilesPanel = ({ open, onOpenChange, conversationId, version, onSummarize }) => {
  const [files, setFiles] = useState([]);

  useEffect(() => {
    if (!open || !conversationId) return;
    apiJson(`/conversations/${conversationId}/files`).then(setFiles).catch(() => setFiles([]));
  }, [open, conversationId, version]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid="files-panel" className="w-full bg-white sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="font-display">Fichiers de la discussion</SheetTitle>
          <SheetDescription>Ces fichiers restent disponibles comme contexte pour toute la discussion.</SheetDescription>
        </SheetHeader>
        <ul className="mt-6 space-y-2">
          {files.length === 0 && (
            <li data-testid="files-panel-empty" className="text-sm text-slate-400">Aucun fichier joint pour l'instant.</li>
          )}
          {files.map((f) => {
            const Icon = f.kind === "image" ? ImageIcon : FileText;
            return (
              <li key={f.id} data-testid={`files-panel-item-${f.id}`} className="flex items-center gap-3 rounded-2xl border border-slate-200 p-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-[#f0f4f9]">
                  {f.kind === "image" ? <img src={fileUrl(f.id)} alt="" className="h-full w-full object-cover" /> : <Icon className="h-5 w-5 text-[#1a73e8]" />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">{f.name}</p>
                  <p className="text-xs text-slate-400">
                    {formatSize(f.size)} · {new Date(f.created_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
                  </p>
                </div>
                <button
                  data-testid={`files-panel-summarize-${f.id}`}
                  onClick={() => onSummarize(f)}
                  title="Résumer"
                  className="flex h-9 items-center gap-1 rounded-full px-3 text-xs font-medium text-[#1a73e8] hover:bg-blue-50"
                >
                  <ScrollText className="h-4 w-4" /> Résumer
                </button>
                <a
                  href={fileUrl(f.id)}
                  download={f.name}
                  data-testid={`files-panel-download-${f.id}`}
                  title="Télécharger"
                  className="flex h-9 w-9 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
                >
                  <Download className="h-4 w-4" />
                </a>
              </li>
            );
          })}
        </ul>
      </SheetContent>
    </Sheet>
  );
};
