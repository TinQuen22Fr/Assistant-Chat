import { Link } from "react-router-dom";
import { ArrowLeft, Brain } from "lucide-react";
import { toast } from "sonner";
import { useMemories } from "@/hooks/useMemories";
import { MemorySettings } from "@/components/memory/MemorySettings";
import { ContextFileEditor } from "@/components/memory/ContextFileEditor";
import { MemoryToolbar } from "@/components/memory/MemoryToolbar";
import { AddMemoryForm } from "@/components/memory/AddMemoryForm";
import { MemoryItem } from "@/components/memory/MemoryItem";
import { ProfileMenu } from "@/components/ProfileMenu";

export default function MemoryPage() {
  const mem = useMemories();

  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-100 bg-white/85 px-4 backdrop-blur-md sm:px-8">
        <Link
          to="/"
          data-testid="memory-back-link"
          className="flex h-10 items-center gap-2 rounded-full px-3 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100"
        >
          <ArrowLeft className="h-4 w-4" /> Retour aux discussions
        </Link>
        <div className="ml-auto">
          <ProfileMenu />
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 pb-24 pt-10 sm:px-8">
        <div className="fade-up flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#e8f0fe]">
            <Brain className="h-6 w-6 text-[#1a73e8]" />
          </div>
          <div>
            <h1 className="font-display text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">Mémoire</h1>
            <p className="mt-2 max-w-2xl text-base text-slate-500">
              Ce que Gemini Perso retient de vous d'une discussion à l'autre. Vous gardez la main : modifiez, supprimez ou exportez à tout moment.
            </p>
          </div>
        </div>

        {mem.settings && <MemorySettings settings={mem.settings} onChange={mem.updateSettings} />}
        {mem.settings && <ContextFileEditor value={mem.settings.context_file} onSave={(context_file) => mem.updateSettings({ context_file }).then(() => toast.success("Fichier de contexte enregistré")).catch(() => {})} />}

        <section className="mt-12">
          <h2 className="font-display text-lg font-semibold text-slate-900">Souvenirs ({mem.items.length})</h2>
          <MemoryToolbar mem={mem} />
          <AddMemoryForm onAdd={mem.add} />
          <ul data-testid="memory-list" className="mt-6 space-y-3">
            {mem.items.map((m) => (
              <MemoryItem key={m.id} memory={m} onEdit={mem.edit} onDelete={mem.remove} />
            ))}
            {mem.loaded && mem.items.length === 0 && (
              <li data-testid="memory-list-empty" className="rounded-2xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                {mem.query ? "Aucun souvenir ne correspond à votre recherche." : "Aucun souvenir pour l'instant. Discutez avec Gemini ou ajoutez-en un manuellement."}
              </li>
            )}
          </ul>
        </section>
      </main>
    </div>
  );
}
