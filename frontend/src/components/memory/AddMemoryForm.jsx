import { useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";

export const AddMemoryForm = ({ onAdd }) => {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await onAdd(text.trim());
      setText("");
      toast.success("Souvenir ajouté");
    } catch {
      /* erreur déjà affichée */
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mt-4 flex gap-2">
      <input
        data-testid="memory-add-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Ajouter un souvenir ou une instruction (ex. « Je vis à Lyon »)"
        className="h-11 flex-1 rounded-full border border-slate-200 px-5 text-sm outline-none focus:border-[#1a73e8] focus:ring-4 focus:ring-blue-100"
      />
      <button
        data-testid="memory-add-button"
        type="submit"
        disabled={busy || !text.trim()}
        className="flex h-11 items-center gap-2 rounded-full bg-[#1a73e8] px-5 text-sm font-medium text-white transition-colors hover:bg-[#1557b0] disabled:bg-slate-200 disabled:text-slate-400"
      >
        <Plus className="h-4 w-4" /> Ajouter
      </button>
    </form>
  );
};
