import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, MessageSquare, Pencil, Trash2, X } from "lucide-react";
import { toast } from "sonner";

const SOURCE = {
  auto: { label: "Auto", cls: "bg-[#e8f0fe] text-[#1a73e8]" },
  manuel: { label: "Manuel", cls: "bg-emerald-50 text-emerald-700" },
  import: { label: "Import", cls: "bg-amber-50 text-amber-700" },
};

const IconBtn = ({ children, ...props }) => (
  <button {...props} className="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800">
    {children}
  </button>
);

export const MemoryItem = ({ memory, onEdit, onDelete }) => {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(memory.content);
  const src = SOURCE[memory.source] || SOURCE.manuel;

  const save = async () => {
    if (!text.trim()) return;
    try {
      await onEdit(memory.id, text.trim());
    } catch {
      return;
    }
    setEditing(false);
    toast.success("Souvenir modifié");
  };

  return (
    <li data-testid={`memory-item-${memory.id}`} className="group rounded-2xl border border-slate-200 p-4 transition-colors hover:border-slate-300">
      {editing ? (
        <textarea
          data-testid="memory-edit-textarea"
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full resize-y rounded-xl border border-slate-300 p-3 text-sm outline-none focus:border-[#1a73e8] focus:ring-4 focus:ring-blue-100"
        />
      ) : (
        <p data-testid="memory-item-content" className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{memory.content}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span data-testid="memory-item-source" className={`rounded-full px-2 py-0.5 font-medium ${src.cls}`}>{src.label}</span>
        <span>{new Date(memory.updated_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}</span>
        {memory.conversation_id && (
          <Link to={`/c/${memory.conversation_id}`} data-testid="memory-item-origin-link" className="flex items-center gap-1 text-[#1a73e8] hover:underline">
            <MessageSquare className="h-3 w-3" /> {memory.conversation_title || "Discussion d'origine"}
          </Link>
        )}
        <div className="ml-auto flex items-center gap-1">
          {editing ? (
            <>
              <IconBtn data-testid="memory-edit-save-button" onClick={save} title="Enregistrer"><Check className="h-4 w-4" /></IconBtn>
              <IconBtn data-testid="memory-edit-cancel-button" onClick={() => { setEditing(false); setText(memory.content); }} title="Annuler"><X className="h-4 w-4" /></IconBtn>
            </>
          ) : (
            <>
              <IconBtn data-testid="memory-edit-button" onClick={() => setEditing(true)} title="Modifier"><Pencil className="h-4 w-4" /></IconBtn>
              <IconBtn data-testid="memory-delete-button" onClick={() => onDelete(memory.id).then(() => toast.success("Souvenir supprimé")).catch(() => {})} title="Supprimer"><Trash2 className="h-4 w-4" /></IconBtn>
            </>
          )}
        </div>
      </div>
    </li>
  );
};
