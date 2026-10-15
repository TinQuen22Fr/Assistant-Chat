import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  const port = Number(env.PORT || 3000);
  const hmrPort = env.WDS_SOCKET_PORT ? Number(env.WDS_SOCKET_PORT) : undefined;
  // Cible du proxy : backend FastAPI local. En dev comme en preview, le
  // navigateur n'appelle que des chemins relatifs `/api/...` ; c'est le
  // serveur Vite qui relaie vers uvicorn. Plus aucune URL absolue cote client.
  const backendTarget = env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8010";
  const proxy = {
    "/api": {
      target: backendTarget,
      changeOrigin: true,
      ws: true,
    },
  };
  return {
    plugins: [react()],
    envPrefix: ["VITE_", "REACT_APP_"],
    resolve: { alias: { "@": path.resolve(root, "src") } },
    server: {
      host: "0.0.0.0",
      port,
      strictPort: true,
      allowedHosts: true,
      hmr: hmrPort ? { clientPort: hmrPort, protocol: "wss" } : undefined,
      watch: { ignored: ["**/node_modules/**", "**/build/**"] },
      proxy,
    },
    preview: { host: "0.0.0.0", port, strictPort: true, allowedHosts: true, proxy },
    build: { outDir: "build" },
  };
});
