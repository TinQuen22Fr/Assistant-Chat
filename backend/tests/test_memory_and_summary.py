"""Phase 2 tests: memory CRUD, settings, export/import, auto-memory via chat,
cross-conversation recall, context file, isolation, conversation + file summaries."""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8010").rstrip("/")
API = f"{BASE_URL}/api"
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests", "fixtures")

TEST_EMAIL = "test@geminiperso.fr"
TEST_PASSWORD = "Test1234!"
USER2_EMAIL = "user2@geminiperso.fr"


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def s1():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def s2():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": USER2_EMAIL, "password": TEST_PASSWORD})
    if r.status_code != 200:
        r = s.post(f"{API}/auth/register", json={
            "email": USER2_EMAIL, "password": TEST_PASSWORD, "name": "User Two"})
        assert r.status_code == 200, r.text
    return s


def _stream_message(sess, cid, content, files=None):
    """POST a message, consume SSE, return (assistant_text, assistant_id, memory_count)."""
    data = {"content": content}
    file_payload = []
    for f in files or []:
        file_payload.append(("files", (os.path.basename(f), open(f, "rb"), "application/pdf")))
    r = sess.post(f"{API}/conversations/{cid}/messages", data=data,
                  files=file_payload or None, stream=True, timeout=120)
    assert r.status_code == 200, r.text
    text, mid, mem_count = "", None, 0
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data: "):
            continue
        import json
        ev = json.loads(raw[6:])
        t = ev.get("type")
        if t == "meta":
            mid = ev["assistant_message_id"]
        elif t == "delta":
            text += ev["text"]
        elif t == "memory":
            mem_count = ev.get("count", 0)
    return text, mid, mem_count


def _new_conv(sess, model="flash"):
    r = sess.post(f"{API}/conversations", json={"model": model})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# clean slate for user1
@pytest.fixture(scope="module", autouse=True)
def clean_user1(s1):
    s1.delete(f"{API}/memories")
    s1.patch(f"{API}/memory/settings",
             json={"memory_enabled": True, "auto_memory": True, "context_file": ""})
    yield
    # restore at end
    s1.patch(f"{API}/memory/settings",
             json={"memory_enabled": True, "auto_memory": True, "context_file": ""})


# ---------- settings ----------

class TestMemorySettings:
    def test_defaults(self, s1):
        r = s1.get(f"{API}/memory/settings")
        assert r.status_code == 200
        d = r.json()
        assert d["memory_enabled"] is True
        assert d["auto_memory"] is True
        assert d["context_file"] == ""

    def test_patch_persists(self, s1):
        r = s1.patch(f"{API}/memory/settings",
                     json={"auto_memory": False, "context_file": "Hello"})
        assert r.status_code == 200
        assert r.json()["auto_memory"] is False
        assert r.json()["context_file"] == "Hello"
        # readback
        d = s1.get(f"{API}/memory/settings").json()
        assert d["auto_memory"] is False
        assert d["context_file"] == "Hello"
        # restore
        s1.patch(f"{API}/memory/settings", json={"auto_memory": True, "context_file": ""})


# ---------- CRUD ----------

class TestMemoryCrud:
    def test_add_list_patch_delete(self, s1):
        # add
        r = s1.post(f"{API}/memories", json={"content": "TEST_ L'utilisateur aime les fraises"})
        assert r.status_code == 200
        m = r.json()
        assert m["source"] == "manuel"
        assert m["content"].startswith("TEST_")
        mid = m["id"]
        # list contains
        lst = s1.get(f"{API}/memories").json()
        assert any(x["id"] == mid for x in lst)
        # search
        hits = s1.get(f"{API}/memories", params={"q": "fraises"}).json()
        assert any(x["id"] == mid for x in hits)
        # patch
        r = s1.patch(f"{API}/memories/{mid}", json={"content": "TEST_ L'utilisateur aime les framboises"})
        assert r.status_code == 200
        assert "framboises" in r.json()["content"]
        # delete
        r = s1.delete(f"{API}/memories/{mid}")
        assert r.status_code == 200
        # 404 after
        r = s1.patch(f"{API}/memories/{mid}", json={"content": "x"})
        assert r.status_code == 404
        r = s1.delete(f"{API}/memories/{mid}")
        assert r.status_code == 404

    def test_delete_all(self, s1):
        s1.post(f"{API}/memories", json={"content": "TEST_ un"})
        s1.post(f"{API}/memories", json={"content": "TEST_ deux"})
        r = s1.delete(f"{API}/memories")
        assert r.status_code == 200
        assert r.json()["deleted"] >= 2
        assert s1.get(f"{API}/memories").json() == []


# ---------- export / import ----------

class TestExportImport:
    def test_export_then_import_round_trip(self, s1):
        s1.delete(f"{API}/memories")
        for c in ["TEST_ Vit à Lyon", "TEST_ Préfère le vélo", "TEST_ Développeur Python"]:
            s1.post(f"{API}/memories", json={"content": c})
        r = s1.get(f"{API}/memories/export")
        assert r.status_code == 200
        assert "attachment" in r.headers.get("Content-Disposition", "")
        md = r.text
        assert "TEST_ Vit à Lyon" in md
        # delete all
        s1.delete(f"{API}/memories")
        assert s1.get(f"{API}/memories").json() == []
        # preview
        files = {"file": ("memoire.md", io.BytesIO(md.encode("utf-8")), "text/markdown")}
        r = s1.post(f"{API}/memories/import/preview", files=files)
        assert r.status_code == 200
        items = r.json()["items"]
        contents = [i["content"] for i in items]
        assert any("Vit à Lyon" in c for c in contents)
        assert all(not i["duplicate"] for i in items)
        # import
        r = s1.post(f"{API}/memories/import", json={"items": contents})
        assert r.status_code == 200
        assert r.json()["added"] == 3
        lst = s1.get(f"{API}/memories").json()
        assert len(lst) == 3
        assert all(m["source"] == "import" for m in lst)
        # second import -> all duplicates -> 0 added
        r = s1.post(f"{API}/memories/import", json={"items": contents})
        assert r.json()["added"] == 0
        # cleanup
        s1.delete(f"{API}/memories")

    def test_import_preview_rejects_non_md(self, s1):
        files = {"file": ("bad.exe", io.BytesIO(b"blah"), "application/octet-stream")}
        r = s1.post(f"{API}/memories/import/preview", files=files)
        assert r.status_code == 415

    def test_import_preview_empty_md(self, s1):
        files = {"file": ("empty.md", io.BytesIO("# Mémoire — Gemini Perso\n\n".encode("utf-8")), "text/markdown")}
        r = s1.post(f"{API}/memories/import/preview", files=files)
        assert r.status_code == 400


# ---------- isolation ----------

class TestIsolation:
    def test_user2_cannot_see_or_edit_user1_memory(self, s1, s2):
        s1.delete(f"{API}/memories")
        m = s1.post(f"{API}/memories", json={"content": "TEST_ Secret user1"}).json()
        mid = m["id"]
        # user2 list excludes
        lst = s2.get(f"{API}/memories").json()
        assert all(x["id"] != mid for x in lst)
        # user2 patch/delete -> 404
        assert s2.patch(f"{API}/memories/{mid}", json={"content": "hack"}).status_code == 404
        assert s2.delete(f"{API}/memories/{mid}").status_code == 404
        # user2 settings independent (change user1 context, user2 unaffected)
        s1.patch(f"{API}/memory/settings", json={"context_file": "user1 ctx"})
        assert s2.get(f"{API}/memory/settings").json()["context_file"] != "user1 ctx"
        s1.patch(f"{API}/memory/settings", json={"context_file": ""})
        # cleanup
        s1.delete(f"{API}/memories/{mid}")


# ---------- auto memory via chat + cross-conversation ----------

class TestAutoMemoryE2E:
    @pytest.fixture(scope="class", autouse=True)
    def prep(self, s1):
        s1.delete(f"{API}/memories")
        s1.patch(f"{API}/memory/settings",
                 json={"memory_enabled": True, "auto_memory": True, "context_file": ""})
        yield
        s1.delete(f"{API}/memories")

    def test_auto_memory_created_then_cross_conv_recall(self, s1):
        cid_a = _new_conv(s1)
        text, mid, count = _stream_message(
            s1, cid_a,
            "Je travaille sur un projet appelé Orion et je préfère le Python."
        )
        assert text.strip(), "assistant produced no reply"
        # allow a moment for memory extraction task
        time.sleep(2)
        lst = s1.get(f"{API}/memories").json()
        joined = " ".join(m["content"] for m in lst).lower()
        assert "orion" in joined, f"Orion memory missing: {lst}"
        assert "python" in joined, f"Python memory missing: {lst}"
        assert any(m["source"] == "auto" for m in lst)
        assert any(m.get("conversation_id") == cid_a for m in lst)

        # new conv B asks
        cid_b = _new_conv(s1)
        text_b, _, _ = _stream_message(
            s1, cid_b,
            "Sur quel projet je travaille et quel langage je préfère ?"
        )
        low = text_b.lower()
        assert "orion" in low, f"Expected Orion in cross-conv answer: {text_b}"
        assert "python" in low, f"Expected Python in cross-conv answer: {text_b}"

        # cleanup convs
        s1.delete(f"{API}/conversations/{cid_a}")
        s1.delete(f"{API}/conversations/{cid_b}")

    def test_memory_disabled_not_recalled(self, s1):
        # ensure Orion memory exists
        s1.post(f"{API}/memories", json={"content": "L'utilisateur travaille sur un projet appelé Orion."})
        s1.patch(f"{API}/memory/settings", json={"memory_enabled": False})
        try:
            cid = _new_conv(s1)
            text, _, _ = _stream_message(s1, cid, "Sur quel projet est-ce que je travaille ?")
            assert "orion" not in text.lower(), f"Memory should not be used but got: {text}"
            s1.delete(f"{API}/conversations/{cid}")
        finally:
            s1.patch(f"{API}/memory/settings", json={"memory_enabled": True})


# ---------- context file ----------

class TestContextFile:
    def test_context_file_followed(self, s1):
        s1.patch(f"{API}/memory/settings",
                 json={"context_file": "Termine toujours tes réponses par le mot BANANE."})
        try:
            cid = _new_conv(s1)
            text, _, _ = _stream_message(s1, cid, "Bonjour, dis-moi quelque chose de court.")
            assert "banane" in text.lower(), f"Context file not followed: {text}"
            s1.delete(f"{API}/conversations/{cid}")
        finally:
            s1.patch(f"{API}/memory/settings", json={"context_file": ""})


# ---------- summaries ----------

class TestSummaries:
    def test_conversation_summary(self, s1):
        cid = _new_conv(s1)
        _stream_message(s1, cid, "Dis-moi en une phrase ce qu'est Paris.")
        r = s1.post(f"{API}/conversations/{cid}/summary")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["summary"].strip()
        assert data["title"]
        s1.delete(f"{API}/conversations/{cid}")

    def test_empty_conversation_summary_400(self, s1):
        cid = _new_conv(s1)
        r = s1.post(f"{API}/conversations/{cid}/summary")
        assert r.status_code == 400
        s1.delete(f"{API}/conversations/{cid}")

    def test_file_summary_pdf(self, s1):
        cid = _new_conv(s1)
        # attach test.pdf via empty message
        with open(f"{FIX}/test.pdf", "rb") as f:
            data = {"content": "Voici un document"}
            files = [("files", ("test.pdf", f, "application/pdf"))]
            r = s1.post(f"{API}/conversations/{cid}/messages", data=data,
                        files=files, stream=True, timeout=120)
            for _ in r.iter_lines():
                pass
        file_list = s1.get(f"{API}/conversations/{cid}/files").json()
        assert file_list
        fid = file_list[0]["id"]
        r = s1.post(f"{API}/files/{fid}/summary", timeout=120)
        assert r.status_code == 200, r.text
        summary = r.json()["summary"].lower()
        assert "zebre-7731" in summary or "48" in summary, f"Expected ZEBRE-7731/48000 in: {summary}"
        s1.delete(f"{API}/conversations/{cid}")

    def test_file_summary_isolation(self, s1, s2):
        cid = _new_conv(s1)
        with open(f"{FIX}/test.pdf", "rb") as f:
            r = s1.post(f"{API}/conversations/{cid}/messages",
                        data={"content": "doc"}, files=[("files", ("test.pdf", f, "application/pdf"))],
                        stream=True, timeout=120)
            for _ in r.iter_lines():
                pass
        fid = s1.get(f"{API}/conversations/{cid}/files").json()[0]["id"]
        r = s2.post(f"{API}/files/{fid}/summary")
        assert r.status_code == 404
        r = s2.post(f"{API}/conversations/{cid}/summary")
        assert r.status_code == 404
        s1.delete(f"{API}/conversations/{cid}")
