import { useState } from "react";
import { apiJson } from "@/lib/api";

const CLOSED = { open: false, title: "", kind: null, loading: false, text: "", error: null, conversationId: null };

export function useSummary() {
  const [summary, setSummary] = useState(CLOSED);

  const run = async ({ kind, id, title, conversationId }) => {
    setSummary({ ...CLOSED, open: true, kind, title, loading: true, conversationId });
    const path = kind === "file" ? `/files/${id}/summary` : `/conversations/${id}/summary`;
    try {
      const r = await apiJson(path, { method: "POST" });
      setSummary((s) => (s.title === title ? { ...s, loading: false, text: r.summary } : s));
    } catch (e) {
      setSummary((s) => ({ ...s, loading: false, error: e.message }));
    }
  };

  const setOpen = (open) => setSummary((s) => ({ ...s, open }));
  return { summary, run, setOpen };
}
