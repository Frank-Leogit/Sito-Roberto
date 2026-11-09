"""Genera index.html e sitemap.xml a partire da content.json + template.html.

Uso locale:   pip install jinja2 pillow markdown  &&  python build.py
In produzione lo esegue la GitHub Action ad ogni modifica di content.json.

Le immagini indicate in content.json vengono ridimensionate e convertite in
WebP dentro src/_opt/. Il nome contiene l'hash dell'originale: si rigenerano
solo se l'originale cambia, così PC e GitHub Action non producono differenze.
"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from PIL import Image

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://" + (ROOT / "CNAME").read_text(encoding="utf-8").strip()
OPT_DIR = ROOT / "src" / "_opt"


USED_OPT: set[str] = set()


def img(path: str, width: int) -> str:
    """Restituisce il percorso (relativo) di una versione WebP ottimizzata."""
    if not path:
        return ""
    rel = path.lstrip("/")
    src = ROOT / rel
    if not src.exists():
        print(f"ATTENZIONE: immagine non trovata: {path}", file=sys.stderr)
        return rel
    digest = hashlib.sha1(src.read_bytes()).hexdigest()[:8]
    OPT_DIR.mkdir(parents=True, exist_ok=True)
    out = OPT_DIR / f"{src.stem}-{width}-{digest}.webp"
    USED_OPT.add(out.name)
    if not out.exists():
        with Image.open(src) as im:
            im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(out, "WEBP", quality=82, method=6)
        print(f"  ottimizzata {rel} -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    return out.relative_to(ROOT).as_posix()


def cleanup_opt() -> None:
    """Elimina le versioni ottimizzate non più usate."""
    for f in OPT_DIR.glob("*.webp"):
        if f.name not in USED_OPT:
            f.unlink()
            print(f"  rimossa {f.relative_to(ROOT)}")


def rich(text: str) -> str:
    """Testo formattato: accetta sia HTML sia Markdown (dipende dall'editor)."""
    text = (text or "").strip()
    if not text or text.startswith("<"):
        return text
    import markdown
    return markdown.markdown(text)


def build_jsonld(c: dict) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Physician",
        "name": c["profilo"]["nome"].replace("Dott. ", ""),
        "image": SITE_URL + "/" + c["profilo"]["foto"].lstrip("/"),
        "logo": SITE_URL + "/" + c["profilo"]["logo"].lstrip("/"),
        "description": c["seo"]["descrizione_scheda_medico"],
        "url": SITE_URL + "/",
        "telephone": c["contatti"]["telefono"],
        "email": c["contatti"]["email"],
        "medicalSpecialty": "Endocrinology",
        "priceRange": "€€",
        "address": {"@type": "PostalAddress", "addressCountry": "IT"},
        "sameAs": [u for u in c["social"].values() if u],
    }
    if c["studio"]["visibile"] and c["studio"]["indirizzo"]:
        data["address"].update(streetAddress=c["studio"]["indirizzo"],
                               addressLocality=c["studio"]["citta"])
    # "</" non deve mai comparire dentro <script>
    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")


def main() -> None:
    content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    today = dt.date.today()

    env = Environment(loader=FileSystemLoader(ROOT), autoescape=True,
                      undefined=StrictUndefined, trim_blocks=False)
    env.globals["img"] = img
    env.filters["rich"] = rich
    html = env.get_template("template.html").render(
        **content,
        site_url=SITE_URL,
        jsonld=build_jsonld(content),
        anno=today.year,
        css_version=hashlib.md5((ROOT / "styles.css").read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:8],
    )
    (ROOT / "index.html").write_text(html, encoding="utf-8", newline="\n")
    cleanup_opt()

    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url>\n    <loc>{SITE_URL}/</loc>\n    <lastmod>{today.isoformat()}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n    <priority>1.0</priority>\n  </url>\n"
        "</urlset>\n", encoding="utf-8", newline="\n")
    print("index.html e sitemap.xml generati.")


if __name__ == "__main__":
    main()
