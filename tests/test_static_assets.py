"""File statici dell'interfaccia: cache lunga solo per i file con hash, gzip sopra 1 kB."""

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from api.static_assets import assets_app


def _client(tmp_path):
    (tmp_path / "index-AbC12345.js").write_text("console.log('x');" * 200, encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG" + b"0" * 2000)
    (tmp_path / "tiny-AbC12345.css").write_text("a{}", encoding="utf-8")
    return TestClient(Starlette(routes=[Mount("/assets", assets_app(str(tmp_path)))]))


def test_hashed_files_are_cached_for_a_year_and_immutable(tmp_path):
    risposta = _client(tmp_path).get("/assets/index-AbC12345.js")
    assert risposta.status_code == 200
    assert risposta.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_files_without_a_hash_are_revalidated_not_cached_forever(tmp_path):
    risposta = _client(tmp_path).get("/assets/logo.png")
    assert risposta.headers["cache-control"] == "public, max-age=0, must-revalidate"


def test_large_files_are_gzipped_and_small_ones_are_not(tmp_path):
    client = _client(tmp_path)
    grande = client.get("/assets/index-AbC12345.js", headers={"accept-encoding": "gzip"})
    assert grande.headers.get("content-encoding") == "gzip"
    assert len(grande.content) == 3400  # il client decomprime: il testo arriva intero
    piccolo = client.get("/assets/tiny-AbC12345.css", headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in piccolo.headers


def test_a_missing_file_is_a_plain_404_without_cache_headers(tmp_path):
    risposta = _client(tmp_path).get("/assets/nope-AbC12345.js")
    assert risposta.status_code == 404
    assert "immutable" not in risposta.headers.get("cache-control", "")
