import { AlertCircle, RotateCcw, X } from "lucide-react";

export const ErrorBanner = ({ message, onClose, action }) => (
  <div
    data-testid="error-banner-container"
    role="alert"
    className="fade-up mb-3 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
  >
    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
    <div className="flex-1">
      <p data-testid="error-banner-message">{message}</p>
      {action && (
        <button
          data-testid="error-retry-flash-button"
          onClick={action.onClick}
          className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#1a73e8] shadow-sm ring-1 ring-blue-100 transition-colors hover:bg-blue-50"
        >
          <RotateCcw className="h-3.5 w-3.5" /> {action.label}
        </button>
      )}
    </div>
    <button
      data-testid="error-banner-close-button"
      onClick={onClose}
      aria-label="Fermer"
      className="rounded-full p-0.5 text-red-500 transition-colors hover:bg-red-100"
    >
      <X className="h-4 w-4" />
    </button>
  </div>
);
