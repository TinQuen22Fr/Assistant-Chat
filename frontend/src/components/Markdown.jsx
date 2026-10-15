import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { copyText } from "@/lib/clipboard";

const CodeBlock = ({ children }) => {
  const [copied, setCopied] = useState(false);
  const text = String(children?.props?.children ?? "").replace(/\n$/, "");
  const copy = async () => {
    if (!(await copyText(text))) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="group relative">
      <button
        data-testid="code-copy-button"
        onClick={copy}
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-white/90 px-2 py-1 text-xs text-slate-600 opacity-0 shadow-sm transition-opacity group-hover:opacity-100"
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        {copied ? "Copié" : "Copier"}
      </button>
      <pre className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-normal">
        {children}
      </pre>
    </div>
  );
};

export const Markdown = ({ text }) => (
  <div className="markdown text-base leading-relaxed text-slate-800">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: CodeBlock }}>
      {text}
    </ReactMarkdown>
  </div>
);
