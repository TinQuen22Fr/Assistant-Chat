import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { apiJson } from "@/lib/api";

export function useMemories() {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [settings, setSettings] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    const q = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
    try {
      setItems(await apiJson(`/memories${q}`));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoaded(true);
    }
  }, [query]);

  useEffect(() => {
    const t = setTimeout(reload, 250);
    return () => clearTimeout(t);
  }, [reload]);

  useEffect(() => {
    apiJson("/memory/settings").then(setSettings).catch((e) => toast.error(e.message));
  }, []);

  const guard = (fn) => async (...args) => {
    try {
      return await fn(...args);
    } catch (e) {
      toast.error(e.message);
      throw e;
    }
  };

  const updateSettings = guard(async (patch) => {
    setSettings(await apiJson("/memory/settings", { method: "PATCH", body: patch }));
  });

  const add = guard(async (content) => {
    const m = await apiJson("/memories", { method: "POST", body: { content } });
    setItems((prev) => [m, ...prev]);
  });

  const edit = guard(async (id, content) => {
    const m = await apiJson(`/memories/${id}`, { method: "PATCH", body: { content } });
    setItems((prev) => prev.map((x) => (x.id === id ? m : x)));
  });

  const remove = guard(async (id) => {
    await apiJson(`/memories/${id}`, { method: "DELETE" });
    setItems((prev) => prev.filter((x) => x.id !== id));
  });

  const removeAll = guard(async () => {
    await apiJson("/memories", { method: "DELETE" });
    setItems([]);
  });

  return { items, query, setQuery, loaded, reload, settings, updateSettings, add, edit, remove, removeAll };
}
