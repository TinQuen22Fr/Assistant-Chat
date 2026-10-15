import { FileText, Mail, Lightbulb, Code2 } from "lucide-react";

const PROMPTS = [
  { icon: FileText, text: "Résume le document joint en 5 points clés" },
  { icon: Mail, text: "Rédige un e-mail professionnel pour décaler une réunion" },
  { icon: Lightbulb, text: "Explique simplement le fonctionnement d'un LLM" },
  { icon: Code2, text: "Écris une fonction Python qui valide un IBAN" },
];

export const EmptyState = ({ name, onPick }) => (
  <div data-testid="empty-state" className="pt-10 sm:pt-20">
    <h2 className="fade-up font-display text-4xl font-semibold tracking-tight sm:text-5xl">
      <span className="gemini-text">Bonjour{name ? `, ${name.split(" ")[0]}` : ""}</span>
    </h2>
    <p className="fade-up mt-2 font-display text-2xl text-slate-400 [animation-delay:80ms] sm:text-3xl">
      Comment puis-je vous aider aujourd'hui ?
    </p>
    <div className="mt-12 grid grid-cols-1 gap-3 sm:grid-cols-2">
      {PROMPTS.map(({ icon: Icon, text }, i) => (
        <button
          key={text}
          data-testid={`quick-prompt-chip-${i}`}
          onClick={() => onPick(text)}
          style={{ animationDelay: `${150 + i * 60}ms` }}
          className="fade-up group flex items-start gap-3 rounded-2xl bg-[#f0f4f9] p-4 text-left text-sm text-slate-700 transition-colors hover:bg-[#dde3ea]"
        >
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 transition-colors group-hover:text-[#1a73e8]" />
          {text}
        </button>
      ))}
    </div>
  </div>
);
