import { Link } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { ProfileMenu } from "@/components/ProfileMenu";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ImportDropzone } from "@/components/import/ImportDropzone";
import { ImportPreview } from "@/components/import/ImportPreview";
import { ImportResult } from "@/components/import/ImportResult";
import { useTakeoutImport } from "@/hooks/useTakeoutImport";

export default function ImportPage() {
  const imp = useTakeoutImport();

  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-100 bg-white/85 px-4 backdrop-blur-md sm:px-8">
        <Link to="/" data-testid="import-back-link" className="flex h-10 items-center gap-2 rounded-full px-3 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100">
          <ArrowLeft className="h-4 w-4" /> Retour aux discussions
        </Link>
        <div className="ml-auto"><ProfileMenu /></div>
      </header>

      <main className="mx-auto max-w-4xl px-4 pb-24 pt-10 sm:px-8">
        <div className="fade-up flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#e8f0fe]">
            <Upload className="h-6 w-6 text-[#1a73e8]" />
          </div>
          <div>
            <h1 className="font-display text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">Importer depuis Gemini</h1>
            <p className="mt-2 max-w-2xl text-base text-slate-500">
              Récupérez l'historique de vos discussions gemini.google.com via Google Takeout et poursuivez-les ici.
            </p>
          </div>
        </div>

        <ol className="fade-up mt-8 space-y-1 rounded-3xl bg-[#f8fafd] p-5 text-sm text-slate-600 [animation-delay:80ms]">
          <li>1. Ouvrez <a href="https://takeout.google.com" target="_blank" rel="noreferrer" className="font-medium text-[#1a73e8] hover:underline">takeout.google.com</a>, cliquez sur « Tout désélectionner ».</li>
          <li>2. Cochez « Mon activité », puis dans « Toutes les données d'activité incluses » ne gardez que « Applications Gemini ».</li>
          <li>3. (Conseillé) Dans « Plusieurs formats », choisissez JSON pour les relevés d'activité.</li>
          <li>4. Exportez, téléchargez l'archive .zip et déposez-la ci-dessous (ou le fichier MyActivity.json / .html extrait).</li>
        </ol>

        <div className="mt-8">
          {imp.error && <ErrorBanner message={imp.error} onClose={() => imp.setError(null)} />}
          {["idle", "uploading", "parsing"].includes(imp.step) && <ImportDropzone imp={imp} />}
          {["preview", "importing"].includes(imp.step) && <ImportPreview imp={imp} />}
          {imp.step === "done" && <ImportResult imp={imp} />}
        </div>
      </main>
    </div>
  );
}
