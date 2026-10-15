import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

const ConversationsContext = createContext(null);

export function ConversationsProvider({ children }) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    const q = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
    try {
      setItems(await apiJson(`/conversations${q}`));
    } finally {
      setLoaded(true);
    }
  }, [query]);

  useEffect(() => {
    const t = setTimeout(reload, 250);
    return () => clearTimeout(t);
  }, [reload]);

  const patch = (c) => setItems((prev) => prev.map((x) => (x.id === c.id ? { ...x, ...c } : x)));

  const rename = async (id, title) =>
    patch(await apiJson(`/conversations/${id}`, { method: "PATCH", body: { title } }));

  const remove = async (id) => {
    await apiJson(`/conversations/${id}`, { method: "DELETE" });
    setItems((prev) => prev.filter((x) => x.id !== id));
  };

  return (
    <ConversationsContext.Provider value={{ items, query, setQuery, loaded, reload, patch, rename, remove }}>
      {children}
    </ConversationsContext.Provider>
  );
}

export const useConversations = () => useContext(ConversationsContext);
