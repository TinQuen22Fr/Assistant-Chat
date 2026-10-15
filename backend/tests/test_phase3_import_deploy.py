"""Phase 3 — Google Takeout import + deploy routes."""
import io
import os
import time
import zipfile
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values(Path(__file__).resolve().parents[2] / "frontend" / ".env").get("VITE_BACKEND_URL")
            or "http://localhost:8010").rstrip("/")
API = BASE_URL + "/api"
FIXT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "takeout"


# ---------- auth fixtures ----------

def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def s1():
    return _login("test@geminiperso.fr", "Test1234!")


@pytest.fixture(scope="module")
def s2():
    s = requests.Session()
    # register user2 if not already
    s.post(f"{API}/auth/register", json={"email": "user2@geminiperso.fr", "password": "Test1234!", "name": "User Two"}, timeout=20)
    r = s.post(f"{API}/auth/login", json={"email": "user2@geminiperso.fr", "password": "Test1234!"}, timeout=20)
    assert r.status_code == 200, r.text
    return s


def _clear_imports(s):
    convs = s.get(f"{API}/conversations", timeout=20).json()
    for c in convs:
        if c.get("imported"):
            s.delete(f"{API}/conversations/{c['id']}", timeout=20)


# ---------- deploy ----------

class TestDeploy:
    def test_guide(self, s1):
        r = s1.get(f"{API}/deploy/guide", timeout=20)
        assert r.status_code == 200
        assert "markdown" in r.headers["content-type"]
        assert "Créer votre identifiant Google OAuth" in r.text
        assert "google-account" in r.text

    def test_bundle(self, s1):
        r = s1.get(f"{API}/deploy/bundle", timeout=20)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        for rel in ["gemini-perso-deploy/DEPLOIEMENT.md",
                    "gemini-perso-deploy/deploy/nginx.conf",
                    "gemini-perso-deploy/deploy/gemini-perso.service",
                    "gemini-perso-deploy/deploy/docker-compose.yml",
                    "gemini-perso-deploy/backend/requirements.txt",
                    "gemini-perso-deploy/backend/.env.example",
                    "gemini-perso-deploy/frontend/.env.example"]:
            assert rel in names, f"missing {rel} in bundle"


# ---------- import preview parity ----------

@pytest.fixture(autouse=True)
def _cleanup(s1, s2):
    _clear_imports(s1)
    _clear_imports(s2)
    yield
    _clear_imports(s1)
    _clear_imports(s2)


def _preview(s, path, filename=None):
    with open(path, "rb") as f:
        r = s.post(f"{API}/imports/takeout/preview",
                   files={"file": (filename or Path(path).name, f, "application/octet-stream")},
                   timeout=60)
    return r


class TestImportPreview:
    @pytest.mark.parametrize("fname", ["takeout-gemini.zip", "MyActivity.json", "MyActivity.html"])
    def test_preview_three_formats(self, s1, fname):
        r = _preview(s1, FIXT / fname)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["entries"] == 6
        assert len(data["conversations"]) == 3
        titles = [c["title"] for c in data["conversations"]]
        assert any("capitale de l'Australie" in t for t in titles)
        assert any("Python" in t for t in titles)
        counts = sorted(c["count"] for c in data["conversations"])
        assert counts == [1, 2, 3]
        # fresh import => all new
        assert all(c["status"] == "new" for c in data["conversations"])

    def test_invalid_json(self, s1):
        r = _preview(s1, FIXT / "invalid.json")
        assert r.status_code == 400
        assert "Format non reconnu" in r.json()["detail"] or "JSON" in r.json()["detail"]

    def test_zip_without_gemini_activity(self, s1, tmp_path):
        p = tmp_path / "empty.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("Takeout/Other/foo.txt", "hello")
        r = _preview(s1, p)
        assert r.status_code == 400
        assert "Aucun fichier d'activité Gemini" in r.json()["detail"]


# ---------- commit + dedupe + isolation ----------

class TestImportCommit:
    def test_commit_creates_3_and_dedupe_cross_format(self, s1):
        # 1) first preview+commit with zip
        pr = _preview(s1, FIXT / "takeout-gemini.zip").json()
        sid = pr["session_id"]
        keys = [c["key"] for c in pr["conversations"]]
        r = s1.post(f"{API}/imports/takeout/{sid}/commit",
                    json={"group_keys": keys, "summarize": False}, timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["created"] == 3
        assert res["skipped"] == 0

        # 2) re-preview with JSON -> all existing
        pr2 = _preview(s1, FIXT / "MyActivity.json").json()
        for c in pr2["conversations"]:
            assert c["status"] == "existing", c

        # 3) re-preview with HTML -> all existing (cross-format dedupe)
        pr3 = _preview(s1, FIXT / "MyActivity.html").json()
        for c in pr3["conversations"]:
            assert c["status"] == "existing", c

        # 4) force commit all 3 keys on html session -> 0 created, 3 skipped
        sid3 = pr3["session_id"]
        r = s1.post(f"{API}/imports/takeout/{sid3}/commit",
                    json={"group_keys": [c["key"] for c in pr3["conversations"]], "summarize": False},
                    timeout=30)
        assert r.status_code == 200
        res = r.json()
        assert res["created"] == 0
        assert res["skipped"] == 3

        # 5) sidebar: conversations are imported=True, dated 2025-03
        convs = s1.get(f"{API}/conversations", timeout=20).json()
        imported = [c for c in convs if c.get("imported")]
        assert len(imported) == 3
        titles = [c["title"] for c in imported]
        assert any("capitale" in t.lower() for t in titles)
        assert any("python" in t.lower() for t in titles)
        for c in imported:
            assert "2025-03" in c["updated_at"]

        # 6) messages for 'capitale' conv: 2 user + 2 model
        cap = next(c for c in imported if "capitale" in c["title"].lower())
        msgs = s1.get(f"{API}/conversations/{cap['id']}", timeout=20).json()["messages"]
        roles = [m["role"] for m in msgs]
        assert roles.count("user") == 2
        assert roles.count("model") == 2
        content = " ".join(m["content"] for m in msgs)
        assert "Canberra" in content
        assert "460" in content.replace(" ", "").replace("\u00a0", "") or "460000" in content.replace(" ", "")

        # 7) python conv: code block
        py = next(c for c in imported if "python" in c["title"].lower())
        pymsgs = s1.get(f"{API}/conversations/{py['id']}", timeout=20).json()["messages"]
        assert any("```" in m["content"] and "def" in m["content"] for m in pymsgs)

        # 8) third (budget) conv: file joint annotation
        # file-joined annotation present somewhere among imported python-conv messages
        assert any("[Fichiers joints dans Gemini" in m["content"] and "budget_hermes.pdf" in m["content"] for m in pymsgs)

    def test_isolation_user2_cannot_commit_user1_session(self, s1, s2):
        pr = _preview(s1, FIXT / "takeout-gemini.zip").json()
        sid = pr["session_id"]
        # user2 cannot see user1's session (404)
        r = s2.post(f"{API}/imports/takeout/{sid}/commit",
                    json={"group_keys": [pr["conversations"][0]["key"]], "summarize": False}, timeout=20)
        assert r.status_code == 404

        # user1 commits normally
        r = s1.post(f"{API}/imports/takeout/{sid}/commit",
                    json={"group_keys": [c["key"] for c in pr["conversations"]], "summarize": False}, timeout=30)
        assert r.status_code == 200

        # user2 imports same file -> its own 3 convs, no cross contamination
        pr2 = _preview(s2, FIXT / "takeout-gemini.zip").json()
        assert all(c["status"] == "new" for c in pr2["conversations"])
        r = s2.post(f"{API}/imports/takeout/{pr2['session_id']}/commit",
                    json={"group_keys": [c["key"] for c in pr2["conversations"]], "summarize": False}, timeout=30)
        assert r.status_code == 200
        assert r.json()["created"] == 3

    def test_isolation_user2_cannot_read_user1_job(self, s1, s2):
        pr = _preview(s1, FIXT / "takeout-gemini.zip").json()
        r = s1.post(f"{API}/imports/takeout/{pr['session_id']}/commit",
                    json={"group_keys": [c["key"] for c in pr["conversations"]], "summarize": True}, timeout=30)
        job_id = r.json()["job_id"]
        assert job_id
        assert s2.get(f"{API}/imports/jobs/{job_id}", timeout=20).status_code == 404
        assert s1.get(f"{API}/imports/jobs/{job_id}", timeout=20).status_code == 200


# ---------- auth config / smoke ----------

class TestSmoke:
    def test_auth_config(self, s1):
        r = s1.get(f"{API}/auth/config", timeout=20)
        assert r.status_code == 200
        assert r.json()["google_mode"] in ("oauth", "disabled")
