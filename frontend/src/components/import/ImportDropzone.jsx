import { useRef, useState } from "react";
import { FileArchive, Loader2 } from "lucide-react";

export const ImportDropzone = ({ imp }) => {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);
  const busy = imp.step !== "idle";

  const onDrop = (e) => {
    e.preventDefault();
    setOver(false);
    if (!busy && e.dataTransfer.files[0]) imp.upload(e.dataTransfer.files[0]);
  };

  return (
    <div
      data-testid="import-dropzone"
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-16 text-center transition-colors ${
        over ? "border-[#1a73e8] bg-blue-50/50" : "border-slate-200"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".zip,.json,.html,.htm"
        className="hidden"
        data-testid="import-file-input"
        onChange={(e) => { if (e.target.files[0]) imp.upload(e.target.files[0]); e.target.value = ""; }}
      />
      {busy ? (
        <div data-testid="import-progress" className="w-full max-w-sm">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-[#1a73e8]" />
          <p className="mt-4 text-sm font-medium text-slate-700">
            {imp.step === "uploading" ? `Envoi du fichier… ${Math.round(imp.progress * 100)} %` : "Analyse de l'export en cours…"}
          </p>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-[#1a73e8] transition-[width] duration-300" style={{ width: `${imp.step === "parsing" ? 100 : imp.progress * 100}%` }} />
          </div>
        </div>
      ) : (
        <>
          <FileArchive className="h-10 w-10 text-slate-300" />
          <p className="mt-4 text-base font-medium text-slate-800">Déposez votre export Google Takeout ici</p>
          <p className="mt-1 text-sm text-slate-500">.zip (jusqu'à 5 Go), MyActivity.json ou MyActivity.html</p>
          <button
            data-testid="import-pick-file-button"
            onClick={() => inputRef.current.click()}
            className="mt-6 rounded-full bg-[#1a73e8] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1557b0]"
          >
            Choisir un fichier
          </button>
        </>
      )}
    </div>
  );
};
