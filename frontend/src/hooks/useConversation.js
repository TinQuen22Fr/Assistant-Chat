import { useCallback, useEffect, useRef, useState } from "react";
import { apiJson, streamSSE } from "@/lib/api";
import { isImage } from "@/lib/files";
import { useConversations } from "@/context/ConversationsContext";

const tmpId = (p) => `tmp-${p}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

export function useConversation(routeId, navigate) {
  const [conv, setConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [model, setModelState] = useState("flash");
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const setError = useCallback((message, code = null) => setErr(message ? { message, code } : null), []);
  const [filesVersion, setFilesVersion] = useState(0);
  const skipLoad = useRef(null);
  const abortRef = useRef(null);
  const { reload, patch } = useConversations();

  useEffect(() => {
    if (skipLoad.current && skipLoad.current === routeId) {
      skipLoad.current = null;
      return;
    }
    abortRef.current?.abort();
    setError(null);
    if (!routeId) {
      setConv(null);
      setMessages([]);
      return;
    }
    let alive = true;
    setLoading(true);
    apiJson(`/conversations/${routeId}`)
      .then((d) => {
        if (!alive) return;
        setConv(d);
        setMessages(d.messages);
        setModelState(d.model);
      })
      .catch((e) => alive && (setConv(null), setMessages([]), setError(e.message)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [routeId]);

  const patchLast = (fn) =>
    setMessages((prev) => (prev.length ? [...prev.slice(0, -1), fn(prev[prev.length - 1])] : prev));

  const syncMemoryFlags = async (cid) => {
    try {
      const d = await apiJson(`/conversations/${cid}`);
      const flagged = new Set(d.messages.filter((m) => m.memory_updated).map((m) => m.id));
      if (flagged.size)
        setMessages((prev) => prev.map((m) => (flagged.has(m.id) && !m.memory_updated ? { ...m, memory_updated: true } : m)));
    } catch {
      /* non bloquant */
    }
  };

  const runStream = useCallback(
    async (cid, path, form) => {
      setStreaming(true);
      setError(null);
      const controller = new AbortController();
      abortRef.current = controller;
      let started = false;
      try {
        await streamSSE(path, form, {
          signal: controller.signal,
          onEvent: (ev) => {
            if (ev.type === "meta") {
              started = true;
              setMessages((prev) => {
                const next = [...prev];
                const last = next.length - 1;
                if (ev.user_message) next[last - 1] = ev.user_message;
                next[last] = { ...next[last], id: ev.assistant_message_id, model: ev.model };
                return next;
              });
            } else if (ev.type === "delta") patchLast((m) => ({ ...m, content: m.content + ev.text }));
            else if (ev.type === "done") {
              patchLast(() => ev.message);
              // la suite du flux (titre, mémoire) arrive en arrière-plan
              if (abortRef.current === controller) setStreaming(false);
            } else if (ev.type === "memory") {
              setMessages((prev) => prev.map((m) => (m.id === ev.message_id ? { ...m, memory_updated: true } : m)));
            } else if (ev.type === "title") {
              setConv((c) => (c && c.id === cid ? { ...c, title: ev.title } : c));
              patch({ id: cid, title: ev.title });
            }
          },
        });
        return true;
      } catch (e) {
        if (e.name === "AbortError") {
          setMessages((prev) => prev.map((m) => (m.status === "streaming" ? { ...m, status: "stopped" } : m)));
          return true;
        }
        setError(e.message, e.code);
        if (!started) setMessages((prev) => prev.slice(0, form.has("content") ? -2 : -1));
        else patchLast((m) => ({ ...m, status: "error" }));
        return started;
      } finally {
        if (abortRef.current === controller) setStreaming(false);
        setFilesVersion((v) => v + 1);
        reload();
        // filet de sécurité : l'extraction mémoire est asynchrone côté serveur
        [0, 6000].forEach((delay) => setTimeout(() => syncMemoryFlags(cid), delay));
      }
    },
    [patch, reload],
  );

  const send = async ({ content, files }) => {
    let cid = conv?.id;
    if (!cid) {
      try {
        const c = await apiJson("/conversations", { method: "POST", body: { model } });
        cid = c.id;
        setConv(c);
        skipLoad.current = c.id;
        navigate(`/c/${c.id}`);
      } catch (e) {
        setError(e.message);
        return false;
      }
    }
    setMessages((prev) => [
      ...prev,
      {
        id: tmpId("u"),
        role: "user",
        content,
        status: "complete",
        files: files.map((f) => ({ id: tmpId("f"), name: f.name, size: f.size, kind: isImage(f) ? "image" : "doc", local: true })),
      },
      { id: tmpId("a"), role: "model", content: "", status: "streaming" },
    ]);
    const form = new FormData();
    form.append("content", content);
    form.append("model", model);
    files.forEach((f) => form.append("files", f));
    return runStream(cid, `/conversations/${cid}/messages`, form);
  };

  const regenerate = (modelOverride) => {
    if (!conv || streaming) return;
    setMessages((prev) => [
      ...(prev[prev.length - 1]?.role === "model" ? prev.slice(0, -1) : prev),
      { id: tmpId("a"), role: "model", content: "", status: "streaming" },
    ]);
    const form = new FormData();
    form.append("model", typeof modelOverride === "string" ? modelOverride : model);
    runStream(conv.id, `/conversations/${conv.id}/regenerate`, form);
  };

  const setModel = (key) => {
    setModelState(key);
    if (conv) apiJson(`/conversations/${conv.id}`, { method: "PATCH", body: { model: key } }).catch(() => {});
  };

  const retryWithFlash = () => {
    setModelState("flash");
    regenerate("flash");
  };

  const stop = () => abortRef.current?.abort();

  return {
    conv, messages, model, setModel, streaming, loading, error: err?.message ?? null, errorCode: err?.code ?? null,
    setError, send, regenerate, retryWithFlash, stop, filesVersion,
  };
}
