import { useEffect, useRef } from "react";
import { ArrowUp, Plus, Square } from "lucide-react";
import { FileChip } from "@/components/FileChip";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ACCEPT_ATTR } from "@/lib/files";

export const Composer = ({ value, onChange, files, onAddFiles, onRemoveFile, onSend, onStop, streaming, error, errorAction, onDismissError }) => {
  const textRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    const el = textRef.current;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`;
  }, [value]);

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!streaming) onSend();
    }
  };

  return (
    <div className="shrink-0 px-4 pb-4 pt-2 sm:px-6">
      <div className="mx-auto max-w-3xl">
        {error && <ErrorBanner message={error} onClose={onDismissError} action={errorAction} />}
        <div className="rounded-[28px] bg-[#f0f4f9] p-2.5 transition-[background-color,box-shadow] duration-200 focus-within:bg-white focus-within:shadow-[0_2px_12px_rgba(15,23,42,0.12)]">
          {files.length > 0 && (
            <div data-testid="attachment-chips" className="mb-1 flex flex-wrap gap-2 px-2 pt-1">
              {files.map((f, i) => (
                <FileChip key={`${f.name}-${i}`} file={f} index={i} onRemove={onRemoveFile} disabled={streaming} />
              ))}
            </div>
          )}
          <textarea
            ref={textRef}
            data-testid="prompt-textarea"
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Demandez à Gemini Perso…"
            className="max-h-48 min-h-[44px] w-full resize-none border-0 bg-transparent px-3 py-2.5 text-base text-slate-900 outline-none placeholder:text-slate-500"
          />
          <div className="flex items-center justify-between px-1">
            <input
              ref={fileRef}
              data-testid="file-picker-input"
              type="file"
              multiple
              accept={ACCEPT_ATTR}
              className="hidden"
              onChange={(e) => {
                onAddFiles(Array.from(e.target.files));
                e.target.value = "";
              }}
            />
            <button
              data-testid="file-picker-button"
              onClick={() => fileRef.current.click()}
              disabled={streaming}
              title="Joindre des fichiers (PDF, DOCX, TXT, MD, PNG, JPG, WEBP – 20 Mo max.)"
              className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-200/70 disabled:opacity-40"
            >
              <Plus className="h-5 w-5" />
            </button>
            {streaming ? (
              <button
                data-testid="stop-generation-button"
                onClick={onStop}
                title="Arrêter la génération"
                className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-900 text-white transition-transform hover:scale-105"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
              </button>
            ) : (
              <button
                data-testid="send-message-button"
                onClick={onSend}
                disabled={!value.trim() && files.length === 0}
                title="Envoyer"
                className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1a73e8] text-white transition-[transform,background-color] hover:scale-105 hover:bg-[#1557b0] disabled:scale-100 disabled:bg-transparent disabled:text-slate-400"
              >
                <ArrowUp className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>
        <p className="mt-2 text-center text-xs text-slate-400">
          Gemini Perso peut faire des erreurs. Vérifiez les informations importantes.
        </p>
      </div>
    </div>
  );
};
