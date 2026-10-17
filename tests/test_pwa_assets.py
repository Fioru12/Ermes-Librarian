"""L'app deve essere installabile: manifest valido e icone che esistono davvero."""

import json
from pathlib import Path

from PIL import Image

PUBLIC = Path(__file__).resolve().parent.parent / "frontend" / "public"


def test_the_manifest_is_valid_and_points_to_real_icons_of_the_declared_size():
    manifesto = json.loads((PUBLIC / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifesto["display"] == "standalone"
    assert manifesto["start_url"] == "/" and manifesto["scope"] == "/"
    assert manifesto["name"] and manifesto["short_name"]
    tagli = {icona["sizes"] for icona in manifesto["icons"]}
    assert {"192x192", "512x512"} <= tagli
    assert any(icona.get("purpose") == "maskable" for icona in manifesto["icons"])

    for icona in manifesto["icons"]:
        percorso = PUBLIC / icona["src"].lstrip("/")
        assert percorso.is_file(), icona["src"]
        larghezza, altezza = (int(n) for n in icona["sizes"].split("x"))
        with Image.open(percorso) as immagine:
            assert immagine.size == (larghezza, altezza), icona["src"]


def test_index_html_links_the_manifest_and_declares_a_theme_colour():
    indice = (PUBLIC.parent / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest" href="/manifest.webmanifest"' in indice
    assert 'name="theme-color"' in indice
    assert "fonts.googleapis.com" not in indice, "nessuna risorsa da altri domini"
