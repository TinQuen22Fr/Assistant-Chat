import { useState } from "react";
import { Brain, Check, Copy, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Markdown } from "@/components/Markdown";
import { apiJson } from "@/lib/api";
import { copyText, downloadText, slugify } from "@/lib/clipboard";

const PanelButton = ({ children, ...props }) => (
  <button
    {...props}
    className="flex h-9 items-center gap-2 rounded-full border border-slate-200 px-4 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
  >
    {children}
  </button>
);

export const SummaryPanel = ({ summary, onOpenChange }) => {
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const { open, title, kind, loading, text, error, conversationId } = summary;
  const heading = kind === "file" ? `Résumé du fichier « ${title} »` : `Résumé de la discussion « ${title} »`;

  const copy = async () => {
    if (!(await copyText(text))) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const saveToMemory = async () => {
    setSaving(true);
    try {
      await apiJson("/memories", { method: "POST", body: { content: `${heading} :\n${text}`, conversation_id: conversationId } });
      toast.success("Résumé enregistré en mémoire");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid="summary-panel" className="flex w-full flex-col bg-white sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="pr-6 font-display">{heading}</SheetTitle>
          <SheetDescription>Synthèse générée par Gemini 3 Flash.</SheetDescription>
        </SheetHeader>
        <div className="mt-4 flex-1 overflow-y-auto pr-1">
          {loading && (
            <p data-testid="summary-loading" className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Génération du résumé…
            </p>
          )}
          {error && <p data-testid="summary-error" className="text-sm text-red-600">{error}</p>}
          {!loading && text && (
            <div data-testid="summary-content">
              <Markdown text={text} />
            </div>
          )}
        </div>
        {!loading && text && (
          <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
            <PanelButton data-testid="summary-copy-button" onClick={copy}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} {copied ? "Copié" : "Copier"}
            </PanelButton>
            <PanelButton data-testid="summary-export-button" onClick={() => downloadText(`resume-${slugify(title)}.md`, `# ${heading}\n\n${text}\n`)}>
              <Download className="h-4 w-4" /> Exporter .md
            </PanelButton>
            <PanelButton data-testid="summary-save-memory-button" onClick={saveToMemory} disabled={saving}>
              <Brain className="h-4 w-4" /> Enregistrer en mémoire
            </PanelButton>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};
