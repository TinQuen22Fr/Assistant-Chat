"""Phase 1 tests: auth + chat + attachments + isolation for Gemini Perso."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://assistant-chat-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
FIX = "/app/tests/fixtures"

TEST_EMAIL = "test@geminiperso.fr"
TEST_PASSWORD = "Test1234!"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def session1():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def session2():
    s = requests.Session()
    # Try login, else register
    r = s.post(f"{API}/auth/login", json={"email": "user2@geminiperso.fr", "password": TEST_PASSWORD})
    if r.status_code != 200:
        r = s.post(f"{API}/auth/register", json={
            "email": "user2@geminiperso.fr", "password": TEST_PASSWORD, "name": "User Two"})
        assert r.status_code == 200, r.text
    return s


# ---------- auth ----------
class TestAuth:
    def test_config(self):
        r = requests.get(f"{API}/auth/config")
        assert r.status_code == 200
        assert r.json()["google_mode"] == "emergent"

    def test_login_success_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == TEST_EMAIL
        assert "user_id" in data
        assert "access_token" in s.cookies
        assert "refresh_token" in s.cookies
        # /me works with cookies
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == TEST_EMAIL

    def test_login_wrong_password_french_401(self):
        r = requests.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": "WrongPass123!"})
        assert r.status_code == 401
        assert "incorrect" in r.json()["detail"].lower()

    def test_register_duplicate_409(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD, "name": "x"})
        assert r.status_code == 409
        assert "existe" in r.json()["detail"].lower()

    def test_register_new_then_logout(self):
        email = f"test_user_{uuid.uuid4().hex[:8]}@geminiperso.fr"
        s = requests.Session()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "Temp"})
        assert r.status_code == 200
        assert r.json()["email"] == email
        assert "access_token" in s.cookies
        # logout clears cookies
        lo = s.post(f"{API}/auth/logout")
        assert lo.status_code == 200
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 401

    def test_refresh_rotation(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        r = s.post(f"{API}/auth/refresh")
        assert r.status_code == 200
        assert "access_token" in s.cookies

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_brute_force_lockout_429(self):
        # Use unique bogus email to not pollute real account lockout
        bogus = f"TEST_bogus_{uuid.uuid4().hex[:8]}@geminiperso.fr"
        last = None
        for _ in range(6):
            last = requests.post(f"{API}/auth/login", json={"email": bogus, "password": "wrong"})
        assert last.status_code == 429
        assert "tentatives" in last.json()["detail"].lower()


# ---------- models + conversations ----------
class TestConversations:
    def test_list_models(self, session1):
        r = session1.get(f"{API}/models")
        assert r.status_code == 200
        data = r.json()
        keys = {m["key"] for m in data["models"]}
        assert {"pro", "flash"}.issubset(keys)
        assert data["max_file_bytes"] == 20 * 1024 * 1024

    def test_create_rename_delete_conversation(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        assert r.status_code == 200
        cid = r.json()["id"]
        assert r.json()["title"] == "Nouvelle discussion"
        assert r.json()["model"] == "flash"

        # GET
        g = session1.get(f"{API}/conversations/{cid}")
        assert g.status_code == 200
        assert g.json()["messages"] == []

        # Rename
        p = session1.patch(f"{API}/conversations/{cid}", json={"title": "TEST_renamed"})
        assert p.status_code == 200
        assert p.json()["title"] == "TEST_renamed"

        # Model switch
        p2 = session1.patch(f"{API}/conversations/{cid}", json={"model": "pro"})
        assert p2.status_code == 200
        assert p2.json()["model"] == "pro"

        # Delete
        d = session1.delete(f"{API}/conversations/{cid}")
        assert d.status_code == 200
        g2 = session1.get(f"{API}/conversations/{cid}")
        assert g2.status_code == 404

    def test_create_invalid_model_422(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "bogus"})
        assert r.status_code == 422

    def test_list_filter_by_search(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        session1.patch(f"{API}/conversations/{cid}", json={"title": "TEST_UNIQUEWORDXYZ chat"})
        lst = session1.get(f"{API}/conversations", params={"q": "UNIQUEWORDXYZ"})
        assert lst.status_code == 200
        assert any(c["id"] == cid for c in lst.json())
        session1.delete(f"{API}/conversations/{cid}")


# ---------- isolation ----------
class TestIsolation:
    def test_user2_cannot_access_user1_conversation(self, session1, session2):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        try:
            # user2 attempts
            r1 = session2.get(f"{API}/conversations/{cid}")
            assert r1.status_code == 404
            r2 = session2.patch(f"{API}/conversations/{cid}", json={"title": "pwn"})
            assert r2.status_code == 404
            r3 = session2.delete(f"{API}/conversations/{cid}")
            assert r3.status_code == 404
            r4 = session2.post(f"{API}/conversations/{cid}/messages",
                               data={"content": "x"})
            assert r4.status_code == 404
            # user2 list doesn't include it
            lst = session2.get(f"{API}/conversations").json()
            assert all(c["id"] != cid for c in lst)
        finally:
            session1.delete(f"{API}/conversations/{cid}")


# ---------- streaming helper ----------
def _stream_message(sess, cid, content, files=None, model=None, read_timeout=120):
    data = {"content": content}
    if model:
        data["model"] = model
    with sess.post(f"{API}/conversations/{cid}/messages",
                   data=data, files=files or [], stream=True, timeout=read_timeout) as r:
        assert r.status_code == 200, r.text
        events = []
        text = ""
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            import json
            ev = json.loads(line[6:])
            events.append(ev)
            if ev.get("type") == "delta":
                text += ev["text"]
        return events, text


# ---------- chat streaming + multi-turn + files ----------
class TestChatStreaming:
    def test_streaming_multiturn_name_recall(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        try:
            evs1, _ = _stream_message(session1, cid, "Je m'appelle Arthur. Dis seulement 'ok'.")
            assert any(e["type"] == "meta" for e in evs1)
            assert any(e["type"] == "done" for e in evs1)

            evs2, text2 = _stream_message(session1, cid, "Comment je m'appelle ? Réponds en un mot.")
            assert "arthur" in text2.lower(), f"got: {text2!r}"
        finally:
            session1.delete(f"{API}/conversations/{cid}")

    def test_pdf_attachment_remembered_turn3(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        try:
            with open(f"{FIX}/test.pdf", "rb") as f:
                files = [("files", ("test.pdf", f.read(), "application/pdf"))]
            evs1, _ = _stream_message(session1, cid,
                                      "Voici un document. Réponds juste 'reçu'.",
                                      files=files)
            # verify file chip persisted
            fs = session1.get(f"{API}/conversations/{cid}/files").json()
            assert len(fs) == 1 and fs[0]["name"] == "test.pdf"
            fid = fs[0]["id"]

            # unrelated turn 2
            _stream_message(session1, cid, "Dis bonjour.")

            # turn 3 asks for secret
            _, text3 = _stream_message(session1, cid,
                                       "Quel est le code secret mentionné dans le document joint plus tôt ? Réponds uniquement par le code.")
            assert "ZEBRE-7731" in text3.upper(), f"got: {text3!r}"

            # download works for owner, 404 for other user
            dl = session1.get(f"{API}/files/{fid}")
            assert dl.status_code == 200
        finally:
            session1.delete(f"{API}/conversations/{cid}")

    def test_oversized_file_413(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        try:
            with open(f"{FIX}/big.png", "rb") as f:
                files = [("files", ("big.png", f.read(), "image/png"))]
            r = session1.post(f"{API}/conversations/{cid}/messages",
                              data={"content": "x"}, files=files, timeout=60)
            assert r.status_code == 413
            assert "limite" in r.json()["detail"].lower() or "mo" in r.json()["detail"].lower()
        finally:
            session1.delete(f"{API}/conversations/{cid}")

    def test_regenerate(self, session1):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        try:
            _stream_message(session1, cid, "Dis simplement 'bonjour'.")
            # count messages
            before = len(session1.get(f"{API}/conversations/{cid}").json()["messages"])
            with session1.post(f"{API}/conversations/{cid}/regenerate",
                               data={"model": "flash"}, stream=True, timeout=120) as rr:
                assert rr.status_code == 200
                for line in rr.iter_lines():
                    pass
            after = len(session1.get(f"{API}/conversations/{cid}").json()["messages"])
            # same number of messages (old model msg deleted, new one streamed)
            assert after == before
        finally:
            session1.delete(f"{API}/conversations/{cid}")

    def test_user2_cannot_download_user1_file(self, session1, session2):
        r = session1.post(f"{API}/conversations", json={"model": "flash"})
        cid = r.json()["id"]
        try:
            with open(f"{FIX}/test.pdf", "rb") as f:
                files = [("files", ("test.pdf", f.read(), "application/pdf"))]
            _stream_message(session1, cid, "test", files=files)
            fs = session1.get(f"{API}/conversations/{cid}/files").json()
            fid = fs[0]["id"]
            r2 = session2.get(f"{API}/files/{fid}")
            assert r2.status_code == 404
        finally:
            session1.delete(f"{API}/conversations/{cid}")
