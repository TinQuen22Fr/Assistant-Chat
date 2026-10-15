import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";

const STATUS = {
  new: { label: "Nouvelle", cls: "bg-emerald-50 text-emerald-700" },
  partial: { label: "Messages nouveaux", cls: "bg-blue-50 text-[#1a73e8]" },
  existing: { label: "Déjà importée", cls: "bg-slate-100 text-slate-500" },
};

const fmt = (iso) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });

export const ImportPreview = ({ imp }) => {
  const [summarize, setSummarize] = useState(true);
  const { preview, selected } = imp;
  const convs = preview.conversations;
  const allOn = selected.size === convs.length;
  const msgCount = convs.filter((c) => selected.has(c.key)).reduce((n, c) => n + c.new_count, 0);

  return (
    <section data-testid="import-preview" className="fade-up">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-slate-900">Aperçu de l'import</h2>
          <p data-testid="import-preview-counts" className="mt-1 text-sm text-slate-500">
            {preview.entries} échanges trouvés, regroupés en {convs.length} discussion(s) (nouvelle discussion après 30 min d'inactivité).
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <Checkbox data-testid="import-select-all" checked={allOn} onCheckedChange={(v) => imp.toggleAll(!!v)} /> Tout sélectionner
        </label>
      </div>

      <ul className="mt-4 max-h-[50vh] space-y-2 overflow-y-auto pr-1">
        {convs.map((c) => {
          const st = STATUS[c.status];
          return (
            <li key={c.key} data-testid={`import-conversation-${c.key}`} className="flex items-start gap-3 rounded-2xl border border-slate-200 p-4">
              <Checkbox data-testid={`import-conversation-checkbox-${c.key}`} checked={selected.has(c.key)} onCheckedChange={() => imp.toggle(c.key)} className="mt-1" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-sm font-semibold text-slate-900">{c.title}</p>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${st.cls}`}>{st.label}</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {fmt(c.start)} · {c.count} échange(s){c.status === "partial" ? ` dont ${c.new_count} nouveau(x)` : ""}
                </p>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-slate-200 p-5">
        <label className="flex max-w-md items-start gap-3 text-sm text-slate-700">
          <Checkbox data-testid="import-summarize-checkbox" checked={summarize} onCheckedChange={(v) => setSummarize(!!v)} className="mt-0.5" />
          <span>
            Générer les résumés et extraire les souvenirs en arrière-plan
            <span className="block text-xs text-slate-400">Utilise Gemini 3 Flash (un à deux appels par discussion importée).</span>
          </span>
        </label>
        <div className="flex gap-2">
          <button data-testid="import-cancel-button" onClick={imp.reset} className="rounded-full px-5 py-2.5 text-sm font-medium text-[#1a73e8] hover:bg-blue-50">
            Annuler
          </button>
          <button
            data-testid="import-confirm-button"
            onClick={() => imp.commit(summarize)}
            disabled={selected.size === 0 || imp.step === "importing"}
            className="flex items-center gap-2 rounded-full bg-[#1a73e8] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1557b0] disabled:bg-slate-200 disabled:text-slate-400"
          >
            {imp.step === "importing" && <Loader2 className="h-4 w-4 animate-spin" />}
            Importer {selected.size} discussion(s) · {msgCount} échange(s)
          </button>
        </div>
      </div>
    </section>
  );
};
