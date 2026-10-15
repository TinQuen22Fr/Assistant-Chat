import { useRef, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { apiJson } from "@/lib/api";

export const ImportDialog = ({ open, onOpenChange, onImported }) => {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const close = (o) => {
    if (!o) setItems(null);
    onOpenChange(o);
  };

  const preview = async (file) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const r = await apiJson("/memories/import/preview", { method: "POST", body: form });
      setItems(r.items.map((i) => ({ ...i, selected: !i.duplicate })));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      const r = await apiJson("/memories/import", { method: "POST", body: { items: items.filter((i) => i.selected).map((i) => i.content) } });
      toast.success(`${r.added} souvenir(s) importé(s)`);
      onImported();
      close(false);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const count = items?.filter((i) => i.selected).length ?? 0;
  const toggle = (idx) => setItems((prev) => prev.map((i, j) => (j === idx ? { ...i, selected: !i.selected } : i)));

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent data-testid="memory-import-dialog" className="max-h-[85vh] overflow-hidden rounded-3xl sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Importer des souvenirs</DialogTitle>
          <DialogDescription>Chaque puce ou paragraphe du fichier Markdown devient un souvenir. Vérifiez l'aperçu avant de confirmer.</DialogDescription>
        </DialogHeader>
        <input ref={fileRef} type="file" accept=".md,.markdown,.txt" className="hidden" data-testid="memory-import-file-input" onChange={(e) => { preview(e.target.files[0]); e.target.value = ""; }} />
        {!items ? (
          <button
            data-testid="memory-import-pick-button"
            onClick={() => fileRef.current.click()}
            disabled={busy}
            className="flex h-32 w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-200 text-sm text-slate-500 transition-colors hover:border-[#1a73e8] hover:text-[#1a73e8]"
          >
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <FileUp className="h-6 w-6" />}
            Choisir un fichier .md
          </button>
        ) : (
          <ul data-testid="memory-import-preview" className="max-h-[45vh] space-y-2 overflow-y-auto pr-1">
            {items.map((i, idx) => (
              <li key={idx} className="flex items-start gap-3 rounded-xl border border-slate-200 p-3">
                <Checkbox data-testid={`memory-import-item-${idx}`} checked={i.selected} onCheckedChange={() => toggle(idx)} className="mt-0.5" />
                <span className="flex-1 whitespace-pre-wrap text-sm text-slate-800">{i.content}</span>
                {i.duplicate && <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700">Déjà présent</span>}
              </li>
            ))}
          </ul>
        )}
        <DialogFooter className="gap-2">
          <button onClick={() => close(false)} className="rounded-full px-5 py-2 text-sm font-medium text-[#1a73e8] hover:bg-blue-50">Annuler</button>
          {items && (
            <button
              data-testid="memory-import-confirm-button"
              onClick={confirm}
              disabled={busy || count === 0}
              className="rounded-full bg-[#1a73e8] px-5 py-2 text-sm font-medium text-white hover:bg-[#1557b0] disabled:opacity-50"
            >
              Importer {count} souvenir(s)
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
