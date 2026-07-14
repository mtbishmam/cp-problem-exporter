import argparse
import asyncio
import base64
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LINKS_FILE = ROOT_DIR / "input" / "links.txt"
PDF_DIRECTORY = ROOT_DIR / "pdfs"

CODEFORCES_BASE_URL = "https://codeforces.com"
CSES_BASE_URL = "https://cses.fi"


def add_common_options(subparser):
    subparser.add_argument(
        "--output",
        type=Path,
        default=PDF_DIRECTORY,
        help="Output directory (default: <repository>/pdfs)",
    )
    subparser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium without opening a browser window",
    )
    subparser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace PDFs that already exist",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Export Codeforces and CSES problem statements as PDFs."
    )

    subparsers = parser.add_subparsers(
        dest="mode",
        required=True,
    )

    problem_parser = subparsers.add_parser(
        "problem",
        help="Export one problem URL",
    )
    problem_parser.add_argument("url")
    add_common_options(problem_parser)

    file_parser = subparsers.add_parser(
        "file",
        help="Export every problem URL in a text file",
    )
    file_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_LINKS_FILE,
        help="Links file (default: input/links.txt)",
    )
    add_common_options(file_parser)

    problemset_parser = subparsers.add_parser(
        "problemset",
        help="Extract and export every problem on a problemset page",
    )
    problemset_parser.add_argument("url")
    add_common_options(problemset_parser)

    return parser


def site_from_url(url):
    host = urlparse(url).netloc.lower()

    if host == "codeforces.com" or host.endswith(".codeforces.com"):
        return "codeforces"

    if host == "cses.fi" or host.endswith(".cses.fi"):
        return "cses"

    raise ValueError(f"Unsupported problem site: {url}")


def is_problem_url(url):
    try:
        site = site_from_url(url)
    except ValueError:
        return False

    if site == "codeforces":
        return bool(
            re.search(
                r"/(?:problemset/problem|contest/\d+/problem)/",
                url,
            )
        )

    return bool(re.search(r"/problemset/task/\d+", url))


def read_problem_urls(links_file):
    links_file = Path(links_file)

    if not links_file.is_absolute():
        links_file = ROOT_DIR / links_file

    if not links_file.exists():
        raise FileNotFoundError(f"Links file not found: {links_file}")

    problem_urls = []
    seen = set()

    for line_number, line in enumerate(
        links_file.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        url = line.strip()

        if not url or url.startswith("#"):
            continue

        if not is_problem_url(url):
            print(
                f"Skipping invalid or unsupported URL "
                f"on line {line_number}: {url}"
            )
            continue

        if url not in seen:
            seen.add(url)
            problem_urls.append(url)

    return problem_urls


async def extract_problemset_urls(page, problemset_url):
    site = site_from_url(problemset_url)

    print(f"Opening problemset: {problemset_url}")
    await page.goto(
        problemset_url,
        wait_until="load",
        timeout=60_000,
    )

    if site == "codeforces":
        print("Waiting 5 seconds for Cloudflare...")
        await page.wait_for_timeout(5_000)

        if await verification_page_detected(page):
            print("Verification page detected.")
            print("Complete the verification in the browser.")
            await page.wait_for_timeout(10_000)

        selector = (
            'table.problems '
            'a[href*="/problemset/problem/"]'
        )
        base_url = CODEFORCES_BASE_URL
    else:
        selector = 'a[href*="/problemset/task/"]'
        base_url = CSES_BASE_URL

    await page.wait_for_selector(selector, timeout=30_000)

    hrefs = await page.locator(selector).evaluate_all(
        "elements => elements.map(element => element.getAttribute('href'))"
    )

    problem_urls = []
    seen = set()

    for href in hrefs:
        if not href:
            continue

        url = urljoin(base_url, href)

        if is_problem_url(url) and url not in seen:
            seen.add(url)
            problem_urls.append(url)

    print(f"Found {len(problem_urls)} problems.")
    return problem_urls


def filename_from_url(problem_url, fallback_index):
    codeforces_match = re.search(
        r"/(?:problemset/problem/|contest/)"
        r"(\d+)(?:/problem)?/([A-Za-z0-9]+)",
        problem_url,
    )

    if codeforces_match:
        contest_id, problem_index = codeforces_match.groups()
        return f"{contest_id}{problem_index}.pdf"

    cses_match = re.search(
        r"/problemset/task/(\d+)",
        problem_url,
    )

    if cses_match:
        return f"cses_{cses_match.group(1)}.pdf"

    return f"problem_{fallback_index}.pdf"


async def verification_page_detected(page):
    title = await page.title()

    return (
        "Just a moment" in title
        or await page.locator("text=Verify you are human").count() > 0
        or await page.locator("text=Performing security verification").count() > 0
    )


async def prepare_codeforces_statement(page):
    await page.wait_for_selector(
        ".problem-statement",
        timeout=30_000,
    )

    await page.evaluate(
        """
        () => {
            const statement = document.querySelector('.problem-statement');

            if (!statement) {
                throw new Error('Codeforces problem statement was not found');
            }

            /* Remove the visible Copy controls without touching sample text. */
            statement.querySelectorAll(
                '.input-output-copier, .test-example-line-even, button'
            ).forEach(element => {
                if (
                    element.classList.contains('input-output-copier') ||
                    element.textContent.trim().toLowerCase() === 'copy'
                ) {
                    element.remove();
                }
            });

            Array.from(statement.querySelectorAll('*')).forEach(element => {
                if (
                    element.children.length === 0 &&
                    element.textContent.trim().toLowerCase() === 'copy'
                ) {
                    element.remove();
                }
            });

            /* Put each sample input beside its corresponding output. */
            statement.querySelectorAll('.sample-tests').forEach(samples => {
                if (samples.querySelector('.sample-test')) return;

                const inputs = Array.from(
                    samples.querySelectorAll(':scope > .input')
                );
                const outputs = Array.from(
                    samples.querySelectorAll(':scope > .output')
                );
                const count = Math.max(inputs.length, outputs.length);

                for (let index = 0; index < count; index += 1) {
                    const row = document.createElement('div');
                    row.className = 'sample-test';

                    if (inputs[index]) row.appendChild(inputs[index]);
                    if (outputs[index]) row.appendChild(outputs[index]);

                    samples.appendChild(row);
                }
            });

            document.body.replaceChildren(statement);
            document.documentElement.style.background = 'white';
            document.body.style.background = 'white';
        }
        """
    )

    await page.add_style_tag(
        content="""
        @page {
            size: A4;
            margin: 12mm;
        }

        html,
        body {
            margin: 0 !important;
            padding: 0 !important;
            background: white !important;
            color: black !important;
        }

        body {
            font-family: serif;
            font-size: 12pt;
        }

        .problem-statement {
            width: auto !important;
            max-width: none !important;
            margin: 0 !important;
        }

        .problem-statement .header {
            margin-bottom: 18px;
        }

        .problem-statement .title {
            font-size: 20pt !important;
        }

        .problem-statement p {
            margin: 6px 0;
        }

        .problem-statement .section-title {
            margin-top: 16px;
        }

        .sample-tests .sample-test {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 10px;
            width: 100%;
            padding-right: 1px;
            box-sizing: border-box;
            margin: 8px 0 14px;
            break-inside: avoid;
            page-break-inside: avoid;
        }

        .sample-tests .sample-test > .input,
        .sample-tests .sample-test > .output {
            min-width: 0;
            width: 100%;
            box-sizing: border-box;
            margin: 0 !important;
            border: 1px solid #aaa !important;
        }

        .sample-tests .title {
            padding: 5px 8px !important;
            border-bottom: 1px solid #aaa;
            font-weight: bold;
        }

        .sample-tests pre {
            margin: 0 !important;
            padding: 7px 8px !important;
            white-space: pre-wrap !important;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .input-output-copier,
        button {
            display: none !important;
        }

        img {
            max-width: 100%;
        }
        """
    )


async def prepare_cses_statement(page):
    await page.wait_for_selector(
        ".content > .md",
        timeout=30_000,
    )
    await page.wait_for_selector(
        ".title-block > h1",
        timeout=30_000,
    )

    await page.evaluate(
        """
        () => {
            const title = document.querySelector('.title-block > h1');
            const constraints = document.querySelector('.task-constraints');
            const statement = document.querySelector('.content > .md');

            if (!title || !statement) {
                throw new Error('CSES problem statement was not found');
            }

            /*
             * CSES stores sample labels and pre blocks sequentially.
             * Turn every Input/Output pair into a two-column row.
             */
            const labels = Array.from(statement.querySelectorAll('p'));

            labels.forEach(inputLabel => {
                const inputText = inputLabel.textContent
                    .trim()
                    .replace(/:$/, '')
                    .toLowerCase();

                if (inputText !== 'input') return;
                if (inputLabel.dataset.pairedSample === 'true') return;

                let inputPre = inputLabel.nextElementSibling;
                while (inputPre && inputPre.tagName !== 'PRE') {
                    if (inputPre.tagName === 'H1') return;
                    inputPre = inputPre.nextElementSibling;
                }

                if (!inputPre) return;

                let outputLabel = inputPre.nextElementSibling;
                while (outputLabel) {
                    const text = outputLabel.textContent
                        .trim()
                        .replace(/:$/, '')
                        .toLowerCase();

                    if (
                        outputLabel.tagName === 'P' &&
                        text === 'output'
                    ) {
                        break;
                    }

                    if (outputLabel.tagName === 'H1') return;
                    outputLabel = outputLabel.nextElementSibling;
                }

                if (!outputLabel) return;

                let outputPre = outputLabel.nextElementSibling;
                while (outputPre && outputPre.tagName !== 'PRE') {
                    if (outputPre.tagName === 'H1') return;
                    outputPre = outputPre.nextElementSibling;
                }

                if (!outputPre) return;

                const grid = document.createElement('div');
                grid.className = 'cses-sample-grid';

                const inputBlock = document.createElement('section');
                inputBlock.className = 'cses-sample-block';
                const inputHeading = document.createElement('div');
                inputHeading.className = 'cses-sample-heading';
                inputHeading.textContent = 'Input';
                inputBlock.append(inputHeading, inputPre);

                const outputBlock = document.createElement('section');
                outputBlock.className = 'cses-sample-block';
                const outputHeading = document.createElement('div');
                outputHeading.className = 'cses-sample-heading';
                outputHeading.textContent = 'Output';
                outputBlock.append(outputHeading, outputPre);

                grid.append(inputBlock, outputBlock);
                inputLabel.replaceWith(grid);
                outputLabel.remove();
            });

            const main = document.createElement('main');
            main.className = 'cses-problem-statement';

            const header = document.createElement('header');
            header.className = 'cses-header';
            header.appendChild(title);

            if (constraints) {
                header.appendChild(constraints);
            }

            main.append(header, statement);
            document.body.replaceChildren(main);
            document.documentElement.style.background = 'white';
            document.body.style.background = 'white';
        }
        """
    )

    await page.add_style_tag(
        content="""
        @page {
            size: A4;
            margin: 12mm;
        }

        html,
        body {
            margin: 0 !important;
            padding: 0 !important;
            background: white !important;
            color: black !important;
        }

        body {
            font-family: serif;
            font-size: 12pt;
        }

        .cses-problem-statement {
            width: auto;
            max-width: none;
            margin: 0;
        }

        .cses-header {
            margin-bottom: 18px;
            text-align: center;
        }

        .cses-header > h1 {
            margin: 0 0 12px;
            font-size: 22pt;
        }

        .task-constraints {
            display: flex !important;
            justify-content: center;
            gap: 38px;
            margin: 0 !important;
        }

        .task-constraints > * {
            margin: 0 !important;
        }

        .md h1 {
            margin: 16px 0 6px;
            font-size: 15pt;
        }

        .md p {
            margin: 6px 0;
        }

        .md ul,
        .md ol {
            margin-top: 6px;
            margin-bottom: 8px;
        }

        img {
            max-width: 100%;
        }

        pre {
            margin: 0;
            white-space: pre-wrap !important;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .cses-sample-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 10px;
            width: 100%;
            padding-right: 1px;
            box-sizing: border-box;
            margin: 8px 0 14px;
            break-inside: avoid;
            page-break-inside: avoid;
        }

        .cses-sample-block {
            min-width: 0;
            width: 100%;
            box-sizing: border-box;
            border: 1px solid #aaa !important;
        }

        .cses-sample-block:last-child {
            border-right: 1px solid #aaa !important;
        }

        .cses-sample-heading {
            padding: 5px 8px;
            border-bottom: 1px solid #aaa;
            font-weight: bold;
        }

        .cses-sample-block pre {
            padding: 7px 8px;
        }
        """
    )


async def keep_only_typeset_math(page):
    """
    CSES currently exposes two KaTeX representations while printing:

    1. MathML, which Chromium renders with proper mathematical typography.
    2. KaTeX HTML, which becomes an unstyled plain-text duplicate in the PDF.

    Keep the properly typeset MathML and remove the plain HTML duplicate.
    MathJax is handled separately: its assistive MathML is removed while its
    normal visual output is retained.
    """

    await page.add_style_tag(
        content="""
        /* Keep the clean mathematical rendering. */
        .katex .katex-mathml {
            position: static !important;
            display: inline-block !important;
            visibility: visible !important;
            width: auto !important;
            height: auto !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            clip: auto !important;
            clip-path: none !important;
            white-space: normal !important;
        }

        .katex-display .katex-mathml {
            display: block !important;
            text-align: center;
        }

        /* Remove the unstyled a1, a2, ..., an duplicate. */
        .katex .katex-html {
            display: none !important;
            visibility: hidden !important;
        }

        /* MathJax already has a separate properly styled visual layer. */
        .MJX_Assistive_MathML,
        mjx-assistive-mml {
            display: none !important;
            visibility: hidden !important;
        }
        """
    )

    await page.locator(
        ".katex .katex-html, "
        ".MJX_Assistive_MathML, "
        "mjx-assistive-mml"
    ).evaluate_all(
        "elements => elements.forEach(element => element.remove())"
    )


async def prepare_statement_for_pdf(page, site):
    if site == "codeforces":
        await prepare_codeforces_statement(page)
    else:
        await prepare_cses_statement(page)

    await keep_only_typeset_math(page)

    await page.evaluate(
        """
        async () => {
            if (document.fonts && document.fonts.ready) {
                await document.fonts.ready;
            }
        }
        """
    )

    await page.emulate_media(media="print")


async def save_page_as_pdf(page, context, pdf_path):
    client = await context.new_cdp_session(page)

    try:
        pdf_data = await client.send(
            "Page.printToPDF",
            {
                "printBackground": True,
                "paperWidth": 8.27,
                "paperHeight": 11.69,
                "marginTop": 0.4,
                "marginBottom": 0.4,
                "marginLeft": 0.4,
                "marginRight": 0.4,
                "preferCSSPageSize": True,
            },
        )

        with pdf_path.open("wb") as file:
            file.write(base64.b64decode(pdf_data["data"]))
    finally:
        await client.detach()


async def download_problem(
    page,
    context,
    problem_url,
    position,
    total,
    output_directory,
    overwrite,
):
    filename = filename_from_url(problem_url, position)
    pdf_path = output_directory / filename

    print(f"[{position}/{total}] {problem_url}")

    if pdf_path.exists() and not overwrite:
        print(f"    Skipped: {filename} already exists")
        return True

    try:
        site = site_from_url(problem_url)

        await page.goto(
            problem_url,
            wait_until="load",
            timeout=60_000,
        )

        if site == "codeforces":
            if await verification_page_detected(page):
                print("    Verification page detected.")
                print("    Complete the verification in the browser.")
                await page.wait_for_timeout(10_000)

            await page.wait_for_timeout(2_000)
        else:
            await page.wait_for_timeout(500)

        await prepare_statement_for_pdf(page, site)
        await save_page_as_pdf(page, context, pdf_path)

        print(f"    Saved: {filename}")
        return True
    except Exception as error:
        print(f"    Failed: {error}")
        return False


def resolve_output_directory(output):
    output = Path(output)

    if output.is_absolute():
        return output

    return ROOT_DIR / output


async def export_pdfs(args):
    output_directory = resolve_output_directory(args.output)
    output_directory.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        print("Launching browser...")

        browser = await playwright.chromium.launch(
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            is_mobile=False,
            has_touch=False,
        )

        page = await context.new_page()

        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', "
            "{get: () => undefined})"
        )

        try:
            if args.mode == "problem":
                if not is_problem_url(args.url):
                    raise ValueError(
                        f"Invalid or unsupported problem URL: {args.url}"
                    )
                problem_urls = [args.url]

            elif args.mode == "file":
                problem_urls = read_problem_urls(args.path)

            else:
                problem_urls = await extract_problemset_urls(
                    page,
                    args.url,
                )

            if not problem_urls:
                print("No valid problem URLs found.")
                return

            successful = 0

            for position, problem_url in enumerate(
                problem_urls,
                start=1,
            ):
                if await download_problem(
                    page,
                    context,
                    problem_url,
                    position,
                    len(problem_urls),
                    output_directory,
                    args.overwrite,
                ):
                    successful += 1

            failed = len(problem_urls) - successful
            print()
            print(
                f"Done: {successful} successful, "
                f"{failed} failed."
            )
            print(f"PDF directory: {output_directory}")
        finally:
            await context.close()
            await browser.close()


def main():
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(export_pdfs(args))


if __name__ == "__main__":
    main()
