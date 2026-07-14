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


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Export Codeforces and CSES problem statements "
            "as PDFs."
        )
    )

    subparsers = parser.add_subparsers(
        dest="mode",
        required=True
    )

    problem_parser = subparsers.add_parser(
        "problem",
        help="Export one Codeforces or CSES problem URL."
    )
    problem_parser.add_argument(
        "url",
        help="A Codeforces or CSES problem URL."
    )

    file_parser = subparsers.add_parser(
        "file",
        help="Export problem URLs listed in a text file."
    )
    file_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_LINKS_FILE,
        help=(
            "Path to the links file. Defaults to "
            "input/links.txt in the repository."
        )
    )

    problemset_parser = subparsers.add_parser(
        "problemset",
        help=(
            "Export every problem shown on a Codeforces "
            "or CSES problemset page."
        )
    )
    problemset_parser.add_argument(
        "url",
        help="A Codeforces or CSES problemset page URL."
    )

    return parser


def site_from_url(url):
    hostname = (urlparse(url).hostname or "").lower()

    if (
        hostname == "codeforces.com"
        or hostname.endswith(".codeforces.com")
    ):
        return "codeforces"

    if hostname == "cses.fi" or hostname.endswith(".cses.fi"):
        return "cses"

    raise ValueError(
        f"Unsupported site: {hostname or url}"
    )


def read_problem_urls(links_file):
    links_file = links_file.expanduser().resolve()

    if not links_file.is_file():
        raise FileNotFoundError(
            f"Could not find links file: {links_file}"
        )

    problem_urls = []
    seen = set()

    with links_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            url = line.strip()

            if not url:
                continue

            if not url.startswith(("http://", "https://")):
                print(
                    f"Skipping invalid URL on line "
                    f"{line_number}: {url}"
                )
                continue

            try:
                site_from_url(url)
            except ValueError as error:
                print(
                    f"Skipping URL on line {line_number}: "
                    f"{error}"
                )
                continue

            if url not in seen:
                seen.add(url)
                problem_urls.append(url)

    return problem_urls


async def verification_page_detected(page):
    return (
        "Just a moment..." in await page.title()
        or await page.locator(
            "text=Verify you are human"
        ).count() > 0
    )


async def extract_problemset_urls(page, problemset_url):
    site = site_from_url(problemset_url)

    print(f"Opening {site} problemset: {problemset_url}")

    await page.goto(
        problemset_url,
        wait_until="domcontentloaded",
        timeout=30000
    )

    if site == "codeforces":
        print("Waiting 5 seconds for Cloudflare...")
        await page.wait_for_timeout(5000)

        if await verification_page_detected(page):
            print("Verification page detected...")
            print("Complete the verification in the browser.")
            await page.wait_for_timeout(10000)

        selector = (
            'table.problems '
            'a[href*="/problemset/problem/"]'
        )
        base_url = CODEFORCES_BASE_URL

    else:
        selector = 'a[href*="/problemset/task/"]'
        base_url = CSES_BASE_URL

    await page.locator(selector).first.wait_for(
        state="attached",
        timeout=30000
    )

    hrefs = await page.locator(selector).evaluate_all(
        "elements => elements.map(element => element.href)"
    )

    problem_urls = []
    seen = set()

    for href in hrefs:
        problem_url = urljoin(base_url, href)

        if site == "codeforces":
            valid = re.search(
                r"/problemset/problem/\d+/[A-Za-z0-9]+",
                problem_url
            )
        else:
            valid = re.search(
                r"/problemset/task/\d+/?(?:[?#].*)?$",
                problem_url
            )

        if valid and problem_url not in seen:
            seen.add(problem_url)
            problem_urls.append(problem_url)

    return problem_urls


def filename_from_url(problem_url, fallback_index):
    site = site_from_url(problem_url)

    if site == "cses":
        match = re.search(
            r"/problemset/task/(\d+)",
            problem_url
        )

        if match:
            return f"cses_{match.group(1)}.pdf"

        return f"cses_problem_{fallback_index}.pdf"

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

    return f"codeforces_problem_{fallback_index}.pdf"


async def prepare_codeforces_statement(page):
    statement = page.locator(".problem-statement")
    await statement.wait_for(
        state="visible",
        timeout=30000
    )

    await page.evaluate(
        """
        () => {
            const statement = document.querySelector(
                '.problem-statement'
            );

            if (!statement) {
                throw new Error(
                    'Codeforces problem statement was not found'
                );
            }

            // Remove elements containing only "Copy".
            statement.querySelectorAll('*').forEach(element => {
                const text = element.textContent
                    .trim()
                    .toLowerCase();

                if (
                    element.children.length === 0
                    && text === 'copy'
                ) {
                    element.remove();
                }
            });

            document.body.innerHTML = '';
            document.body.appendChild(statement);

            document.documentElement.style.background = 'white';
            document.body.style.margin = '20px';
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

        body {
            font-family: serif;
            font-size: 12pt;
        }

        img {
            max-width: 100%;
        }

        pre {
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        /* Place each sample input beside its output. */
        .sample-tests .sample-test {
            display: grid !important;
            grid-template-columns:
                minmax(0, 1fr)
                minmax(0, 1fr);
            gap: 10px;
            align-items: start;
            margin-bottom: 10px;
        }

        .sample-tests .sample-test > .input {
            grid-column: 1;
            min-width: 0;
            width: auto !important;
            margin: 0 !important;
        }

        .sample-tests .sample-test > .output {
            grid-column: 2;
            min-width: 0;
            width: auto !important;
            margin: 0 !important;
        }

        .sample-tests .input,
        .sample-tests .output {
            break-inside: avoid;
        }

        .sample-tests .title {
            padding: 4px 6px !important;
            margin: 0 !important;
        }

        .sample-tests pre {
            white-space: pre-wrap !important;
            overflow-wrap: anywhere;
            word-break: break-word;
            margin: 0 !important;
            font-size: 10pt !important;
        }

        .sample-tests button,
        .sample-tests .test-example-line-copy-button,
        .sample-tests .input-output-copier,
        .sample-tests .copy-button {
            display: none !important;
        }
        """
    )


async def prepare_cses_statement(page):
    statement = page.locator(".content > .md")
    await statement.wait_for(
        state="visible",
        timeout=30000
    )

    await page.locator(
        ".title-block > h1"
    ).wait_for(
        state="visible",
        timeout=30000
    )

    await page.evaluate(
        """
        () => {
            const title = document.querySelector(
                '.title-block > h1'
            );
            const constraints = document.querySelector(
                '.content > .task-constraints'
            );
            const statement = document.querySelector(
                '.content > .md'
            );

            if (!title || !statement) {
                throw new Error(
                    'CSES problem statement was not found'
                );
            }

            /*
             * CSES places sample labels and pre blocks one
             * after another. Wrap each input/output pair so
             * CSS can display it in two columns.
             */
            const exampleHeadings = Array.from(
                statement.querySelectorAll('h1')
            ).filter(heading =>
                (heading.id || '')
                    .toLowerCase()
                    .startsWith('example')
                || heading.textContent
                    .trim()
                    .toLowerCase()
                    .startsWith('example')
            );

            exampleHeadings.forEach(heading => {
                const sectionElements = [];
                let current = heading.nextElementSibling;

                while (current && current.tagName !== 'H1') {
                    sectionElements.push(current);
                    current = current.nextElementSibling;
                }

                const inputLabel = sectionElements.find(
                    element =>
                        element.tagName === 'P'
                        && /^input\\s*:?$/i.test(
                            element.textContent.trim()
                        )
                );

                const outputLabel = sectionElements.find(
                    element =>
                        element.tagName === 'P'
                        && /^output\\s*:?$/i.test(
                            element.textContent.trim()
                        )
                );

                const inputPre = inputLabel
                    && inputLabel.nextElementSibling
                    && inputLabel.nextElementSibling.tagName
                        === 'PRE'
                    ? inputLabel.nextElementSibling
                    : null;

                const outputPre = outputLabel
                    && outputLabel.nextElementSibling
                    && outputLabel.nextElementSibling.tagName
                        === 'PRE'
                    ? outputLabel.nextElementSibling
                    : null;

                if (
                    !inputLabel
                    || !inputPre
                    || !outputLabel
                    || !outputPre
                ) {
                    return;
                }

                inputLabel.textContent = 'Input';
                outputLabel.textContent = 'Output';

                const grid = document.createElement('div');
                grid.className = 'cses-sample-grid';

                const inputBlock = document.createElement('div');
                inputBlock.className = 'cses-sample-block';
                inputBlock.append(inputLabel, inputPre);

                const outputBlock = document.createElement('div');
                outputBlock.className = 'cses-sample-block';
                outputBlock.append(outputLabel, outputPre);

                grid.append(inputBlock, outputBlock);
                heading.insertAdjacentElement('afterend', grid);
            });

            const wrapper = document.createElement('main');
            wrapper.className = 'cses-problem-statement';

            wrapper.appendChild(title);

            if (constraints) {
                wrapper.appendChild(constraints);
            }

            wrapper.appendChild(statement);
            document.body.replaceChildren(wrapper);

            document.documentElement.style.background = 'white';
            document.body.style.margin = '20px';
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

        body {
            color: black;
            font-family: serif;
            font-size: 12pt;
        }

        .cses-problem-statement {
            width: 100%;
            max-width: none;
        }

        .cses-problem-statement > h1 {
            margin: 0 0 8px;
            font-size: 22pt;
            text-align: center;
        }

        .task-constraints {
            display: flex;
            justify-content: center;
            gap: 24px;
            margin: 0 0 16px;
            padding: 0;
            list-style: none;
        }

        .md h1 {
            margin: 16px 0 6px;
            font-size: 15pt;
        }

        .md p {
            margin: 6px 0;
        }

        img {
            max-width: 100%;
        }

        pre {
            white-space: pre-wrap !important;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .cses-sample-grid {
            display: grid;
            grid-template-columns:
                minmax(0, 1fr)
                minmax(0, 1fr);
            gap: 10px;
            align-items: start;
            margin-bottom: 10px;
            break-inside: avoid;
        }

        .cses-sample-block {
            min-width: 0;
        }

        .cses-sample-block > p {
            margin: 0 !important;
            border: 1px solid #999;
            border-bottom: 0;
            padding: 4px 6px;
            font-weight: bold;
        }

        .cses-sample-block > pre {
            box-sizing: border-box;
            min-height: 42px;
            margin: 0 !important;
            border: 1px solid #999;
            padding: 6px;
            font-size: 10pt !important;
        }
        """
    )


async def prepare_statement_for_pdf(page, site):
    if site == "codeforces":
        await prepare_codeforces_statement(page)
    else:
        await prepare_cses_statement(page)

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
                "preferCSSPageSize": True
            }
        )

        with pdf_path.open("wb") as file:
            file.write(
                base64.b64decode(pdf_data["data"])
            )

    finally:
        await client.detach()


async def download_problem(
    page,
    context,
    problem_url,
    position,
    total
):
    print(f"[{position}/{total}] {problem_url}")

    try:
        site = site_from_url(problem_url)
        filename = filename_from_url(
            problem_url,
            position
        )
        pdf_path = PDF_DIRECTORY / filename

        await page.goto(
            problem_url,
            wait_until="load",
            timeout=30000
        )

        if (
            site == "codeforces"
            and await verification_page_detected(page)
        ):
            print("    Verification page detected...")
            print("    Complete it in the browser if needed.")
            await page.wait_for_timeout(10000)

        await page.wait_for_timeout(2000)
        await prepare_statement_for_pdf(page, site)
        await save_page_as_pdf(page, context, pdf_path)

        print(f"    Saved: {filename}")

    except Exception as error:
        print(f"    Failed: {error}")


async def export_pdfs(args):
    PDF_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    async with async_playwright() as playwright:
        print("Launching browser...")

        browser = await playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                device_scale_factor=2,
                is_mobile=False,
                has_touch=False
            )

            page = await context.new_page()

            await page.add_init_script(
                """
                Object.defineProperty(
                    navigator,
                    'webdriver',
                    {get: () => undefined}
                )
                """
            )

            if args.mode == "problem":
                problem_urls = [args.url]

            elif args.mode == "file":
                problem_urls = read_problem_urls(args.path)

            else:
                problem_urls = await extract_problemset_urls(
                    page,
                    args.url
                )

            if not problem_urls:
                print("No supported problem links were found.")
                return

            print(f"Found {len(problem_urls)} problems.\n")

            for position, problem_url in enumerate(
                problem_urls,
                start=1
            ):
                await download_problem(
                    page,
                    context,
                    problem_url,
                    position,
                    len(problem_urls)
                )

                await page.wait_for_timeout(2000)

        except (FileNotFoundError, ValueError) as error:
            print(error)

        except Exception as error:
            print(f"Failed: {error}")

        finally:
            await browser.close()

    print("\nDone!")


def main():
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(export_pdfs(args))


if __name__ == "__main__":
    main()
