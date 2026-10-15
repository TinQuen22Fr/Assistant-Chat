import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { GoogleButton } from "@/components/GoogleButton";
import { ErrorBanner } from "@/components/ErrorBanner";

const Field = ({ label, id, ...props }) => (
  <label htmlFor={id} className="block">
    <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
    <input
      id={id}
      {...props}
      className="h-12 w-full rounded-xl border border-slate-300 bg-white px-4 text-base text-slate-900 outline-none transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-[#1a73e8] focus:ring-4 focus:ring-blue-100"
    />
  </label>
);

export default function AuthPage() {
  const { login, register } = useAuth();
  const [params] = useSearchParams();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(params.get("erreur") === "google" ? "La connexion avec Google a échoué. Veuillez réessayer." : null);
  const isLogin = mode === "login";
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isLogin) await login(form.email, form.password);
      else await register(form.name, form.email, form.password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-white">
      <section className="relative hidden flex-1 flex-col justify-between overflow-hidden bg-[#f0f4f9] p-12 lg:flex">
        <div className="flex items-center gap-2 font-display text-lg font-semibold text-slate-800">
          <Sparkles className="h-5 w-5 text-[#4285f4]" /> Gemini Perso
        </div>
        <div className="max-w-lg">
          <h1 className="fade-up font-display text-5xl font-semibold leading-tight tracking-tight">
            <span className="gemini-text">Votre assistant IA,</span>
            <br />
            <span className="text-slate-800">hébergé chez vous.</span>
          </h1>
          <p className="fade-up mt-6 text-lg text-slate-500 [animation-delay:100ms]">
            Discutez avec Gemini 3.1 Pro et Gemini 3 Flash, joignez vos documents et retrouvez toutes vos conversations.
          </p>
        </div>
        <p className="text-xs text-slate-400">Auto-hébergeable · Vos données restent les vôtres</p>
        <div className="pointer-events-none absolute -bottom-40 -right-40 h-[480px] w-[480px] rounded-full bg-[image:var(--gemini-gradient)] opacity-20 blur-3xl" />
      </section>

      <section className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="fade-up w-full max-w-sm">
          <h2 data-testid="auth-title" className="font-display text-3xl font-semibold tracking-tight text-slate-900">
            {isLogin ? "Connexion" : "Créer un compte"}
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            {isLogin ? "Heureux de vous revoir." : "Quelques secondes suffisent."}
          </p>

          <div className="mt-8 space-y-6">
            <GoogleButton />
            {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
            <form onSubmit={submit} className="space-y-4" data-testid="auth-form">
              {!isLogin && (
                <Field label="Nom" id="name" data-testid="auth-name-input" value={form.name} onChange={set("name")} placeholder="Marie Dupont" autoComplete="name" />
              )}
              <Field label="Adresse e-mail" id="email" type="email" required data-testid="auth-email-input" value={form.email} onChange={set("email")} placeholder="vous@exemple.fr" autoComplete="email" />
              <Field label="Mot de passe" id="password" type="password" required minLength={isLogin ? undefined : 8} data-testid="auth-password-input" value={form.password} onChange={set("password")} placeholder={isLogin ? "••••••••" : "8 caractères minimum"} autoComplete={isLogin ? "current-password" : "new-password"} />
              <button
                type="submit"
                data-testid="auth-submit-button"
                disabled={busy}
                className="flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#1a73e8] text-sm font-semibold text-white transition-colors hover:bg-[#1557b0] disabled:opacity-60"
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                {isLogin ? "Se connecter" : "Créer mon compte"}
              </button>
            </form>
            <p className="text-center text-sm text-slate-500">
              {isLogin ? "Pas encore de compte ?" : "Déjà inscrit ?"}{" "}
              <button
                data-testid="auth-toggle-mode"
                onClick={() => { setMode(isLogin ? "register" : "login"); setError(null); }}
                className="font-semibold text-[#1a73e8] hover:underline"
              >
                {isLogin ? "Créer un compte" : "Se connecter"}
              </button>
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
