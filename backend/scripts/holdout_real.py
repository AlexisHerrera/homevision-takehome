"""Build the real-form part of the held-out set from public PDFs.

  fetch   download the PDFs into data/holdout/pdf/ (checked against SOURCES' sha256)
  render  render the selected pages to data/holdout/real/<dpi>/<source>_p<NN>.png
  labels  copy the boxes reviewed on the REVIEW_DPI renders to every DPI -> data/holdout/real.json
          (rendering is vector, so percent coordinates are the same at every DPI)

Usage:
    uv run scripts/holdout_real.py fetch
    uv run scripts/holdout_real.py render
    uv run scripts/detect_checkboxes.py --images data/holdout/real/300 --out output/holdout_real_tasks.json
    # review in Label Studio, export JSON to data/holdout/real_reviewed.json
    uv run scripts/holdout_real.py labels
"""

import argparse
import copy
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import cv2
import pypdfium2 as pdfium

REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDOUT = REPO_ROOT / "data" / "holdout"
PDF_DIR = HOLDOUT / "pdf"
REAL_DIR = HOLDOUT / "real"
REVIEWED = HOLDOUT / "real_reviewed.json"
LABELS = HOLDOUT / "real.json"
DPIS = (100, 150, 200, 300)
REVIEW_DPI = 300
URL_PREFIX = "/data/local-files/?d="
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    sha256: str
    pages: tuple[int, ...] | None = None  # 1-based; None = all


FREDDIE = "https://sf.freddiemac.com/docs/pdf/forms/"
SOURCES = (
    # Blank GSE forms.
    Source("b1_1004", FREDDIE + "70.pdf", "ef4751e9635bfeac5dc6d7988728d08f370ae2e3122fad56b5f3e747a83f35dd"),
    Source("b2_1004c", FREDDIE + "70B.pdf", "12d8a7ee474fd896d827fbd3c7f34281ea9b4960ab37835fe0b17ffd23035640"),
    Source("b3_1025", FREDDIE + "72.pdf", "9affe807927974ba55043ccac439d9ee500124a74dc242aea2be22e6171b5991"),
    Source("b4_1073", FREDDIE + "465.pdf", "58b7d70538b1220d16a1ea96b3fdc17c4fbca55303def7a1a877e899f0a66f38"),
    Source("b5_1075", FREDDIE + "466.pdf", "e58b51c839f26e8c82efdc392cd79a195b1bae569007ba552085effd47834664"),
    Source("b6_2055", FREDDIE + "2055.pdf", "42debb51ade9a9a1b97b8a303c4e1b3763281eac622286d3e0dd15d136267b88"),
    Source(
        "b7_1004mc",
        "https://www.reginfo.gov/public/do/DownloadDocument?objectID=51546801",
        "5add66f4f15cfbbb6501105d42f38d9154da270979a2723af56add7134c2bc3a",
    ),
    Source(
        "b8_2055_legacy",
        "https://e-appraise.com/pdf/2055-FNMAE.pdf",
        "d6d01cb981be3e40a2bf06800174369d2c1c9a28bb52c73856a212fd23e1f106",
    ),
    # Filled samples with fictitious data.
    Source(
        "f1_realvals_1004",
        "https://realvals.com/wp-content/uploads/2019/04/1004_Appraisal_Report_Sample.pdf",
        "165f855a2065ca4fa49b273ade4964fb3400e6e39cc143b6aa67da48a5add1a4",
        (3, 4, 5, 9),
    ),
    Source(
        "f2_mgic",
        "https://www.mgic.com/-/media/value-adds/training/Appraisal-training-materials/"
        "71-40263-manual-pdf-appraisal-participant-book.pdf",
        "8e232acb0ee0ff7079a217e6da7ff6c48feffdda916462932c115bff53a1e3ba",
        (5, 7, 9, 26, 27, 28),
    ),
    Source(
        "f3_plaza",
        "https://www.plazahomemortgage.com/downloadfile.aspx?"
        "FilePath=\\Documents\\BrokerEducation\\ParticipantManual.pdf&FileName=ParticipantManual.pdf",
        "364e32be73d7c2a546bfcf16598ff7f1d38c73156b67bb92da92de975dbcdd95",
        (9, 10, 11, 24),
    ),
    Source(
        "f4_ocrolus_1004",
        "https://drive.google.com/uc?export=download&id=1U9UKrLZhEZlWvkIHFV3I-eCSkKPZHI15",
        "ebecbbe279dd5d5fa37ef066e648f9f3b5e32cea4fd47940e8c798840eb3a5be",
        (1, 2, 3, 6),
    ),
)


def fetch() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for s in SOURCES:
        path = PDF_DIR / f"{s.name}.pdf"
        if not path.exists():
            req = urllib.request.Request(s.url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != s.sha256:
            raise ValueError(f"{path.name}: sha256 {digest} != {s.sha256}")
        print(f"{path.name}: ok")


def render() -> None:
    for s in SOURCES:
        pdf = pdfium.PdfDocument(PDF_DIR / f"{s.name}.pdf")
        pages = s.pages or range(1, len(pdf) + 1)
        for dpi in DPIS:
            out_dir = REAL_DIR / str(dpi)
            out_dir.mkdir(parents=True, exist_ok=True)
            for n in pages:
                rgb = pdf[n - 1].render(scale=dpi / 72).to_numpy()[..., :3]
                cv2.imwrite(str(out_dir / f"{s.name}_p{n:02d}.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        print(f"{s.name}: {len(pages)} pages x {len(DPIS)} DPIs")


def labels() -> None:
    tasks = []
    for task in json.loads(REVIEWED.read_text()):
        rel = Path(unquote(task["data"]["image"].split("?d=")[-1]))
        annotations = [a for a in task["annotations"] if not a.get("was_cancelled")]
        if not annotations:
            raise ValueError(f"{rel} has no annotation; review every task before exporting")
        for dpi in DPIS:
            image = rel.parent.parent / str(dpi) / rel.name
            h, w = cv2.imread(str(REPO_ROOT / image), cv2.IMREAD_GRAYSCALE).shape
            result = copy.deepcopy(annotations[0]["result"])
            for r in result:
                r["original_width"], r["original_height"] = w, h
            tasks.append({"data": {"image": URL_PREFIX + image.as_posix()}, "annotations": [{"result": result}]})
    LABELS.write_text(json.dumps(tasks, indent=1))
    print(f"Wrote {len(tasks)} tasks to {LABELS.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("fetch", "render", "labels"))
    {"fetch": fetch, "render": render, "labels": labels}[parser.parse_args().command]()


if __name__ == "__main__":
    main()
