import { useEffect, useRef, useState } from "react";
import { FileUp, Save } from "lucide-react";
import { toast } from "sonner";

export const ContextFileEditor = ({ value, onSave }) => {
  const [text, setText] = useState(value);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);
  useEffect(() => setText(value), [value]);
  const dirty = text !== value;

  const save = async () => {
    setSaving(true);
    try {
      await onSave(text);
    } finally {
      setSaving(false);
    }
  };

  const load = async (file) => {
    if (!file) return;
    if (file.size > 200 * 1024) return toast.error("Le fichier de contexte ne doit pas dépasser 200 Ko.");
    setText(await file.text());
  };

  return (
    <section className="fade-up mt-6 rounded-3xl border border-slate-200 p-5 [animation-delay:120ms]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Fichier de contexte permanent (.md)</h2>
          <p className="mt-1 text-sm text-slate-500">
            Instructions personnalisées toujours transmises au modèle, même si la mémoire est désactivée.
          </p>
        </div>
        <button
          data-testid="context-file-load-button"
          onClick={() => fileRef.current.click()}
          className="flex h-9 items-center gap-2 rounded-full border border-slate-200 px-4 text-sm text-slate-700 hover:bg-slate-50"
        >
          <FileUp className="h-4 w-4" /> Charger un .md
        </button>
        <input ref={fileRef} type="file" accept=".md,.markdown,.txt" className="hidden" data-testid="context-file-input" onChange={(e) => { load(e.target.files[0]); e.target.value = ""; }} />
      </div>
      <textarea
        data-testid="context-file-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        placeholder={"# À propos de moi\n- Réponds de façon concise\n- Je code principalement en Python"}
        className="mt-4 w-full resize-y rounded-2xl border border-slate-200 bg-[#f8fafd] p-4 font-mono text-sm text-slate-800 outline-none focus:border-[#1a73e8] focus:bg-white focus:ring-4 focus:ring-blue-100"
      />
      <div className="mt-3 flex justify-end">
        <button
          data-testid="context-file-save-button"
          onClick={save}
          disabled={!dirty || saving}
          className="flex h-9 items-center gap-2 rounded-full bg-[#1a73e8] px-5 text-sm font-medium text-white transition-colors hover:bg-[#1557b0] disabled:bg-slate-200 disabled:text-slate-400"
        >
          <Save className="h-4 w-4" /> Enregistrer
        </button>
      </div>
    </section>
  );
};
