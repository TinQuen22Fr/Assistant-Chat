export const API = `${import.meta.env.VITE_BACKEND_URL ?? import.meta.env.REACT_APP_BACKEND_URL ?? ""}/api`;

const GENERIC_ERROR = "Une erreur s'est produite. Veuillez réessayer.";
const NO_REFRESH = ["/auth/refresh", "/auth/login", "/auth/register", "/auth/logout"];

export function formatDetail(detail) {
  if (detail == null) return GENERIC_ERROR;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return detail.msg || String(detail);
}

async function readError(res) {
  try {
    return formatDetail((await res.json()).detail);
  } catch {
    return `${GENERIC_ERROR} (HTTP ${res.status})`;
  }
}

let refreshing = null;
const refreshSession = () => {
  refreshing ??= fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
};

export async function apiFetch(path, opts = {}, retry = true) {
  const res = await fetch(`${API}${path}`, { credentials: "include", ...opts });
  if (res.status === 401 && retry && !NO_REFRESH.includes(path) && (await refreshSession())) {
    return apiFetch(path, opts, false);
  }
  return res;
}

export async function apiJson(path, { body, ...opts } = {}) {
  const isJson = body !== undefined && !(body instanceof FormData);
  const res = await apiFetch(path, {
    ...opts,
    headers: isJson ? { "Content-Type": "application/json" } : undefined,
    body: isJson ? JSON.stringify(body) : body,
  });
  if (!res.ok) {
    const err = new Error(await readError(res));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

function parseEvent(raw) {
  const data = raw
    .split("\n")
    .filter((l) => l.startsWith("data:"))
    .map((l) => l.slice(5).trim())
    .join("");
  return data ? JSON.parse(data) : null;
}

export async function streamSSE(path, form, { signal, onEvent }) {
  const res = await apiFetch(path, { method: "POST", body: form, signal });
  if (!res.ok) throw new Error(await readError(res));
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const ev = parseEvent(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
      if (!ev) continue;
      onEvent(ev);
      if (ev.type === "error") {
        const err = new Error(ev.message);
        err.code = ev.code;
        throw err;
      }
    }
  }
}

export const fileUrl = (id) => `${API}/files/${id}`;

export function uploadWithProgress(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}${path}`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* réponse non JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body ? formatDetail(body.detail) : `${GENERIC_ERROR} (HTTP ${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Échec de l'envoi du fichier (connexion interrompue)."));
    xhr.send(form);
  });
}
