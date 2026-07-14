import re
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfWriter


ROOT_DIR = Path(__file__).resolve().parent.parent
LINKS_FILE = ROOT_DIR / "input" / "links.txt"
PDF_DIRECTORY = ROOT_DIR / "pdfs"
OUTPUT_DIRECTORY = ROOT_DIR / "exports"
OUTPUT_FILE = OUTPUT_DIRECTORY / "combined_problems.pdf"


def filename_from_url(problem_url):
    hostname = (urlparse(problem_url).hostname or "").lower()

    if hostname == "cses.fi" or hostname.endswith(".cses.fi"):
        match = re.search(
            r"/problemset/task/(\d+)",
            problem_url
        )

        if match:
            return f"cses_{match.group(1)}.pdf"

        return None

    patterns = [
        r"/problemset/problem/(\d+)/([A-Za-z0-9]+)",
        r"/contest/(\d+)/problem/([A-Za-z0-9]+)",
        r"/gym/(\d+)/problem/([A-Za-z0-9]+)",
        r"/problem/(\d+)/([A-Za-z0-9]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, problem_url)

        if match:
            contest_id = match.group(1)
            problem_index = match.group(2)
            return f"{contest_id}{problem_index}.pdf"

    return None


def read_problem_urls():
    if not LINKS_FILE.is_file():
        raise FileNotFoundError(
            f"Could not find {LINKS_FILE}"
        )

    with LINKS_FILE.open("r", encoding="utf-8") as file:
        return [
            line.strip()
            for line in file
            if line.strip()
        ]


def combine_pdfs():
    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    try:
        problem_urls = read_problem_urls()
    except FileNotFoundError as error:
        print(error)
        return

    if not problem_urls:
        print(f"No links found inside {LINKS_FILE}")
        return

    if not PDF_DIRECTORY.is_dir():
        print(f"Could not find directory: {PDF_DIRECTORY}")
        return

    writer = PdfWriter()
    added_count = 0

    for position, problem_url in enumerate(
        problem_urls,
        start=1
    ):
        filename = filename_from_url(problem_url)

        if filename is None:
            print(
                f"[{position}/{len(problem_urls)}] "
                f"Could not determine filename from: "
                f"{problem_url}"
            )
            continue

        pdf_path = PDF_DIRECTORY / filename

        if not pdf_path.is_file():
            print(
                f"[{position}/{len(problem_urls)}] "
                f"Missing, skipping: {filename}"
            )
            continue

        try:
            writer.append(pdf_path)
            added_count += 1

            print(
                f"[{position}/{len(problem_urls)}] "
                f"Added: {filename}"
            )

        except Exception as error:
            print(
                f"[{position}/{len(problem_urls)}] "
                f"Failed to add {filename}: {error}"
            )

    if added_count == 0:
        writer.close()
        print("No PDFs were found to combine.")
        return

    try:
        with OUTPUT_FILE.open("wb") as output_pdf:
            writer.write(output_pdf)

    finally:
        writer.close()

    print(
        f"\nDone! Combined {added_count} PDFs into "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    combine_pdfs()
