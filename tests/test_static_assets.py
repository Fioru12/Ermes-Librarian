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


# ── file veri serviti dalla radice della SPA (favicon, manifest, icone) ─────────


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (tmp_path / "segreto.txt").write_text("fuori dalla cartella", encoding="utf-8")
    return dist


def test_real_root_files_are_resolved_but_unknown_paths_fall_back_to_the_app(tmp_path):
    from api.static_assets import resolve_frontend_file

    dist = _dist(tmp_path)
    assert resolve_frontend_file(str(dist), "favicon.svg").name == "favicon.svg"
    assert resolve_frontend_file(str(dist), "manifest.webmanifest").name == "manifest.webmanifest"
    # una rotta dell'interfaccia non e' un file: deve ricevere index.html dalla catch-all
    assert resolve_frontend_file(str(dist), "libraries") is None
    assert resolve_frontend_file(str(dist), "") is None
    assert resolve_frontend_file(str(dist), "index.html") is None  # lo serve la catch-all, con la sua logica


def test_a_path_cannot_escape_the_dist_folder(tmp_path):
    from api.static_assets import resolve_frontend_file

    dist = _dist(tmp_path)
    for tentativo in ("../segreto.txt", "..%2Fsegreto.txt", "assets/../../segreto.txt", str(tmp_path / "segreto.txt")):
        assert resolve_frontend_file(str(dist), tentativo) is None, tentativo


def test_the_manifest_gets_its_media_type():
    from pathlib import Path

    from api.static_assets import media_type_for

    assert media_type_for(Path("manifest.webmanifest")) == "application/manifest+json"
    assert media_type_for(Path("favicon.svg")) is None  # lo decide Starlette dall'estensione
