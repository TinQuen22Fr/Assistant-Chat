import { Link } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";

export const ImportResult = ({ imp }) => {
  const { result, job } = imp;
  const running = job && job.status !== "done";

  return (
    <section data-testid="import-result" className="fade-up rounded-3xl border border-slate-200 p-8">
      <CheckCircle2 className="h-10 w-10 text-emerald-500" />
      <h2 className="mt-4 font-display text-2xl font-semibold text-slate-900">Import terminé</h2>
      <p data-testid="import-result-counts" className="mt-2 text-sm text-slate-600">
        {result.created} discussion(s) créée(s), {result.appended} complétée(s), {result.skipped} ignorée(s) (déjà importées).
      </p>
      {job && (
        <div data-testid="import-job-progress" className="mt-6 max-w-md">
          <p className="flex items-center gap-2 text-sm text-slate-700">
            {running && <Loader2 className="h-4 w-4 animate-spin text-[#1a73e8]" />}
            {running
              ? `Résumés et souvenirs en cours… ${job.done}/${job.total || "?"}`
              : `Résumés et souvenirs générés (${job.done}/${job.total}).`}
          </p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-[#1a73e8] transition-[width] duration-500" style={{ width: `${job.total ? (job.done / job.total) * 100 : 5}%` }} />
          </div>
        </div>
      )}
      <div className="mt-8 flex flex-wrap gap-2">
        <Link to="/" data-testid="import-go-chats-link" className="rounded-full bg-[#1a73e8] px-6 py-2.5 text-sm font-medium text-white hover:bg-[#1557b0]">
          Voir mes discussions
        </Link>
        <button data-testid="import-again-button" onClick={imp.reset} className="rounded-full px-5 py-2.5 text-sm font-medium text-[#1a73e8] hover:bg-blue-50">
          Importer un autre fichier
        </button>
      </div>
    </section>
  );
};
