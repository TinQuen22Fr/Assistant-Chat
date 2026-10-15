import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const OPTIONS = [
  { key: "pro", name: "Gemini 3.1 Pro", desc: "Raisonnement avancé" },
  { key: "flash", name: "Gemini 3 Flash", desc: "Rapide et réactif" },
];

export const ModelSelect = ({ value, onChange, disabled }) => (
  <Select value={value} onValueChange={onChange} disabled={disabled}>
    <SelectTrigger
      data-testid="model-select-trigger"
      aria-label="Modèle IA"
      className="h-9 w-auto gap-2 rounded-full border-slate-200 bg-slate-50 px-4 text-sm font-medium text-slate-700 hover:bg-slate-100"
    >
      <SelectValue />
    </SelectTrigger>
    <SelectContent align="end" className="rounded-2xl">
      {OPTIONS.map((o) => (
        <SelectItem
          key={o.key}
          value={o.key}
          data-testid={`model-select-option-${o.key}`}
          className="rounded-xl py-2"
        >
          <span className="font-medium">{o.name}</span>
          <span className="ml-2 text-xs text-slate-400">{o.desc}</span>
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
);
