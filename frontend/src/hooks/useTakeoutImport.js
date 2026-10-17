import { useEffect, useRef, useState } from "react";
import { apiJson, uploadWithProgress } from "@/lib/api";

// étapes : idle → uploading → parsing → preview → importing → done
export function useTakeoutImport() {
  const [step, setStep] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [preview, setPreview] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [result, setResult] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  useEffect(() => () => clearInterval(timer.current), []);

  const upload = async (file) => {
    setError(null);
    if (file.size > 5 * 1024 * 1024 * 1024) return setError("Le fichier dépasse la limite de 5 Go.");
    setStep("uploading");
    setProgress(0);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await uploadWithProgress("/imports/takeout/preview", form, (p) => {
        setProgress(p);
        if (p >= 1) setStep("parsing");
      });
      setPreview(r);
      setSelected(new Set(r.conversations.filter((c) => c.status !== "existing").map((c) => c.key)));
      setStep("preview");
    } catch (e) {
      setError(e.message);
      setStep("idle");
    }
  };

  const pollJob = (id) => {
    timer.current = setInterval(async () => {
      try {
        const j = await apiJson(`/imports/jobs/${id}`);
        setJob(j);
        if (j.status === "done") clearInterval(timer.current);
      } catch {
        clearInterval(timer.current);
      }
    }, 2000);
  };

  const commit = async (summarize) => {
    setStep("importing");
    setError(null);
    try {
      const r = await apiJson(`/imports/takeout/${preview.session_id}/commit`, {
        method: "POST",
        body: { group_keys: [...selected], summarize },
      });
      setResult(r);
      setStep("done");
      if (r.job_id) {
        setJob({ total: 0, done: 0, status: "running" });
        pollJob(r.job_id);
      }
    } catch (e) {
      setError(e.message);
      setStep("preview");
    }
  };

  const toggle = (key) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const toggleAll = (on) => setSelected(new Set(on ? preview.conversations.map((c) => c.key) : []));

  const reset = () => {
    clearInterval(timer.current);
    setStep("idle");
    setPreview(null);
    setResult(null);
    setJob(null);
    setError(null);
  };

  return { step, progress, preview, selected, toggle, toggleAll, result, job, error, setError, upload, commit, reset };
}
