import { FileText, Image as ImageIcon, X } from "lucide-react";
import { formatSize, isImage } from "@/lib/files";

export const FileChip = ({ file, index, onRemove, disabled }) => {
  const Icon = isImage(file) ? ImageIcon : FileText;
  return (
    <div
      data-testid={`file-chip-${index}`}
      className="fade-up flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 py-1 pl-3 pr-1 text-xs text-slate-700"
    >
      <Icon className="h-3.5 w-3.5 text-blue-600" />
      <span className="max-w-[180px] truncate font-medium">{file.name}</span>
      <span className="text-slate-400">{formatSize(file.size)}</span>
      <button
        data-testid={`file-chip-remove-button-${index}`}
        onClick={() => onRemove(index)}
        disabled={disabled}
        aria-label={`Retirer ${file.name}`}
        className="rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
};
