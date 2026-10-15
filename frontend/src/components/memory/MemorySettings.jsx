import { Switch } from "@/components/ui/switch";

const Row = ({ id, title, desc, checked, disabled, onChange }) => (
  <label htmlFor={id} className={`flex items-start justify-between gap-6 p-5 ${disabled ? "opacity-50" : ""}`}>
    <span>
      <span className="block text-sm font-semibold text-slate-900">{title}</span>
      <span className="mt-1 block text-sm text-slate-500">{desc}</span>
    </span>
    <Switch id={id} data-testid={id} checked={checked} disabled={disabled} onCheckedChange={onChange} />
  </label>
);

export const MemorySettings = ({ settings, onChange }) => (
  <section className="fade-up mt-10 divide-y divide-slate-100 rounded-3xl border border-slate-200 [animation-delay:80ms]">
    <Row
      id="memory-enabled-switch"
      title="Mémoire activée"
      desc="Les souvenirs et les résumés de vos discussions passées sont fournis au modèle dans toutes les discussions."
      checked={settings.memory_enabled}
      onChange={(v) => onChange({ memory_enabled: v })}
    />
    <Row
      id="auto-memory-switch"
      title="Mémorisation automatique"
      desc="Après chaque réponse, Gemini Perso extrait les informations durables vous concernant (projets, préférences…)."
      checked={settings.auto_memory}
      disabled={!settings.memory_enabled}
      onChange={(v) => onChange({ auto_memory: v })}
    />
  </section>
);
