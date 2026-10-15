import { useState } from "react";
import { Link } from "react-router-dom";
import { Brain, Check, Copy, FileText, RotateCcw, ScrollText, Sparkles } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { fileUrl } from "@/lib/api";
import { formatSize } from "@/lib/files";
import { copyText } from "@/lib/clipboard";

const MessageFile = ({ file, onSummarize }) => (
  <div className="flex flex-col items-end gap-1">
    <MessageFileBody file={file} />
    {!file.local && onSummarize && (
      <button
        data-testid={`summarize-file-chip-button-${file.id}`}
        onClick={() => onSummarize(file)}
        title="Résumer ce fichier"
        className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium text-slate-500 transition-colors hover:bg-blue-50 hover:text-[#1a73e8]"
      >
        <ScrollText className="h-3 w-3" /> Résumer
      </button>
    )}
  </div>
);

const MessageFileBody = ({ file }) => {
  const body =
    file.kind === "image" && !file.local ? (
      <img src={fileUrl(file.id)} alt={file.name} className="h-28 w-28 rounded-2xl border border-slate-200 object-cover" />
    ) : (
      <span className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700">
        <FileText className="h-4 w-4 text-[#1a73e8]" />
        <span className="max-w-[200px] truncate font-medium">{file.name}</span>
        <span className="text-slate-400">{formatSize(file.size)}</span>
      </span>
    );
  if (file.local) return <span data-testid="message-file-chip">{body}</span>;
  return (
    <a href={fileUrl(file.id)} target="_blank" rel="noreferrer" data-testid="message-file-chip" title={file.name}>
      {body}
    </a>
  );
};

const UserMessage = ({ msg, onSummarizeFile }) => (
  <div data-testid="user-message-item" className="fade-up ml-auto flex max-w-[85%] flex-col items-end gap-2">
    {msg.files?.length > 0 && (
      <div className="flex flex-wrap justify-end gap-3 pb-1">
        {msg.files.map((f) => <MessageFile key={f.id} file={f} onSummarize={onSummarizeFile} />)}
      </div>
    )}
    {msg.content && (
      <div className="whitespace-pre-wrap rounded-3xl rounded-tr-md bg-[#f0f4f9] px-5 py-3 text-base leading-relaxed text-slate-900">
        {msg.content}
      </div>
    )}
  </div>
);

const ActionButton = ({ children, ...props }) => (
  <button {...props} className="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800">
    {children}
  </button>
);

const STATUS_LABEL = { stopped: "Génération arrêtée", error: "Réponse interrompue par une erreur" };

const AssistantMessage = ({ msg, canRegenerate, onRegenerate }) => {
  const [copied, setCopied] = useState(false);
  const streaming = msg.status === "streaming";
  const copy = async () => {
    if (!(await copyText(msg.content))) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div data-testid="assistant-message-item" className="fade-up flex gap-4">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center">
        <Sparkles className={`h-6 w-6 text-[#4285f4] ${streaming ? "animate-spin [animation-duration:2.5s]" : ""}`} />
      </div>
      <div className="min-w-0 flex-1 pt-1">
        {streaming && !msg.content ? (
          <p data-testid="thinking-indicator" className="gemini-text text-base font-medium">Gemini réfléchit…</p>
        ) : (
          <div data-testid="streamed-answer-content" className={streaming ? "stream-cursor" : ""}>
            <Markdown text={msg.content} />
          </div>
        )}
        {STATUS_LABEL[msg.status] && (
          <p data-testid="message-status" className="mt-2 text-xs text-amber-600">{STATUS_LABEL[msg.status]}</p>
        )}
        {!streaming && msg.content && (
          <div className="mt-2 flex items-center gap-1">
            <ActionButton data-testid="copy-message-button" onClick={copy} title="Copier">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </ActionButton>
            {copied && <span data-testid="copy-message-feedback" className="fade-up text-xs text-emerald-600">Copié</span>}
            {canRegenerate && (
              <ActionButton data-testid="regenerate-button" onClick={onRegenerate} title="Régénérer la réponse">
                <RotateCcw className="h-4 w-4" />
              </ActionButton>
            )}
            {msg.model && <span data-testid="answer-meta" className="ml-2 text-xs text-slate-400">{msg.model}</span>}
          </div>
        )}
        {msg.memory_updated && (
          <Link
            to="/memoire"
            data-testid="memory-updated-indicator"
            className="fade-up mt-2 inline-flex items-center gap-1.5 rounded-full bg-[#e8f0fe] px-3 py-1 text-xs font-medium text-[#1a73e8] transition-colors hover:bg-[#d2e3fc]"
          >
            <Brain className="h-3.5 w-3.5" /> Mémoire mise à jour
          </Link>
        )}
        {!streaming && !msg.content && canRegenerate && (
          <ActionButton data-testid="regenerate-button" onClick={onRegenerate} title="Régénérer la réponse">
            <RotateCcw className="h-4 w-4" />
          </ActionButton>
        )}
      </div>
    </div>
  );
};

export const Message = ({ msg, canRegenerate, onRegenerate, onSummarizeFile }) =>
  msg.role === "user" ? (
    <UserMessage msg={msg} onSummarizeFile={onSummarizeFile} />
  ) : (
    <AssistantMessage msg={msg} canRegenerate={canRegenerate} onRegenerate={onRegenerate} />
  );
