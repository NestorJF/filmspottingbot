from fastapi.testclient import TestClient

from filmspotting.api.main import app

client = TestClient(app)


def test_text_command_returns_downloadable_image(library):
    res = client.post("/command", json={"cmd": 'frame "Sample Movie@00:00:01" --aspect 9:16'})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] and body["files"][0].startswith("/outputs/")
    image = client.get(body["files"][0])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"


def test_structured_command(library):
    res = client.post("/command/structured", json={
        "action": "frame", "source": {"title": "Sample Movie", "quote": "como estas"}, "format": "jpg",
    })
    assert res.status_code == 200 and res.json()["files"][0].endswith(".jpg")


def test_bad_command_is_422(library):
    assert client.post("/command", json={"cmd": "frame --nope"}).status_code == 422


def test_search_quotes(library):
    res = client.get("/media/search", params={"q": "tren", "quotes": True})
    assert res.json()["candidates"][0]["text"] == "El tren llega tarde."


def test_outputs_blocks_path_traversal(library):
    assert client.get("/outputs/..%2Flibrary.db").status_code == 404
