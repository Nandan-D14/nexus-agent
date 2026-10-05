# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Small public-benchmark-style suites for nightly regression runs.

These are *style-matched mini sets*, not the official benchmarks:

* ``osworld_mini`` — 20 desktop/GUI tasks in the spirit of OSWorld, run in
  the E2B desktop. Scored by the agent's own end-state verification plus an
  exact answer where the task reports one.
* ``gaia_mini`` — 30 tool-assisted questions in the spirit of GAIA with
  stable, verifiable answers (facts that do not drift, or values a script can
  check). Scored by exact-answer match.

Official OSWorld/GAIA scores need their own harnesses and VMs; use these to
catch regressions cheaply between releases.

Run against staging:
    python -m nexus.eval.run_task_eval live nexus.eval.live_executor:execute \
        --suite gaia_mini --output reports/gaia_mini.json
"""

from __future__ import annotations

from nexus.eval.task_cases import TaskEvalCase

_SEARCH = (("web_search", "tavily_search", "scrape_web_page", "desktop_worker"),)
_COMPUTE = (("run_command", "terminal_worker"),)
_GUI = (("desktop_worker",),)


def _gaia(case_id: str, prompt: str, answers: tuple[str, ...], *, compute: bool = False) -> TaskEvalCase:
    return TaskEvalCase(
        f"gaia-{case_id}",
        "gaia_mini",
        prompt,
        _COMPUTE if compute else _SEARCH,
        minimum_sources=0 if compute else 1,
        expected_state="The exact answer appears in the final response.",
        tags=("gaia_style", "compute" if compute else "web"),
        expected_answers=answers,
    )


GAIA_MINI: tuple[TaskEvalCase, ...] = (
    _gaia("python-match", "Using the official Python docs, in which Python version was the match statement (structural pattern matching) added? Cite the page.", ("3.10",)),
    _gaia("http-418-rfc", "Which RFC originally defined HTTP status code 418? Cite a source.", ("2324",)),
    _gaia("linux-001-year", "In what year was Linux kernel version 0.01 released? Cite a source.", ("1991",)),
    _gaia("attention-author", "Who is the first-listed author of the paper 'Attention Is All You Need'? Cite the paper.", ("Vaswani",)),
    _gaia("postgres-port", "What is PostgreSQL's default TCP port according to its documentation? Cite it.", ("5432",)),
    _gaia("rust-sponsor", "Which organization sponsored the original development of the Rust programming language? Cite a source.", ("Mozilla",)),
    _gaia("iso-germany", "What is the ISO 3166-1 alpha-3 country code for Germany? Cite a source.", ("DEU",)),
    _gaia("ipv6-bytes", "How many bytes long is an IPv6 address? Cite a source.", ("16",)),
    _gaia("euro-codepoint", "What is the Unicode code point of the euro sign? Cite a source.", ("20AC",)),
    _gaia("http-429", "Which HTTP status code means 'Too Many Requests'? Cite the RFC.", ("429",)),
    _gaia("unix-epoch", "In what year does the Unix epoch begin? Cite a source.", ("1970",)),
    _gaia("git-default-branch", "Before Git 2.28 introduced init.defaultBranch, what branch name did git init create by default? Cite a source.", ("master",)),
    _gaia("html5-rec", "In what year did HTML5 become a W3C Recommendation? Cite a source.", ("2014",)),
    _gaia("dns-label", "What is the maximum length of a single DNS label in octets? Cite the RFC.", ("63",)),
    _gaia("https-port", "What is the default TCP port for HTTPS? Cite a source.", ("443",)),
    _gaia("python-creator", "Who created the Python programming language? Cite a source.", ("Rossum",)),
    _gaia("go-announced", "In what year was the Go programming language publicly announced? Cite a source.", ("2009",)),
    _gaia("example-heading", "Open https://example.com and report the exact text of its main heading.", ("Example Domain",)),
    _gaia("water-kelvin", "What is the boiling point of water at standard atmospheric pressure in kelvin, rounded to the nearest integer? Cite a source.", ("373",)),
    _gaia("element-74", "Which chemical element has atomic number 74? Cite a source.", ("Tungsten",)),
    _gaia("sum-100", "Use the terminal to compute the sum of the integers 1 through 100 and report the result.", ("5050",), compute=True),
    _gaia("two-64", "Use the terminal to compute 2 to the power 64 exactly and report it.", ("18446744073709551616",), compute=True),
    _gaia("primes-100", "Use a script to count the prime numbers below 100 and report the count.", ("25",), compute=True),
    _gaia("fib-20", "Use a script to compute the 20th Fibonacci number with F(1)=F(2)=1 and report it.", ("6765",), compute=True),
    _gaia("sha256-abc", "Use the terminal to compute the SHA-256 hex digest of the ASCII string abc (no newline) and report it.", ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",), compute=True),
    _gaia("factorial-20", "Use a script to compute 20 factorial and report it.", ("2432902008176640000",), compute=True),
    _gaia("leap-days", "Use a script to count how many leap years there are from 1901 through 2000 inclusive and report the count.", ("25",), compute=True),
    _gaia("word-count", "In the sandbox, create a file containing exactly the text 'the quick brown fox jumps over the lazy dog', count its words with wc, and report the number.", ("9",), compute=True),
    _gaia("base64-hello", "Use the terminal to base64-encode the ASCII string hello (no newline) and report the result.", ("aGVsbG8=",), compute=True),
    _gaia("hex-beef", "Use the terminal to convert decimal 48879 to hexadecimal and report it.", ("beef",), compute=True),
)


def _gui(case_id: str, prompt: str, state: str, answers: tuple[str, ...] = (), *, critical: bool = False) -> TaskEvalCase:
    return TaskEvalCase(
        f"osworld-{case_id}",
        "osworld_mini",
        prompt,
        _GUI,
        critical=critical,
        expected_state=state,
        tags=("osworld_style", "gui"),
        expected_answers=answers,
    )


OSWORLD_MINI: tuple[TaskEvalCase, ...] = (
    _gui("open-browser-title", "Open the browser on the desktop, go to https://example.com, and report the page title shown in the tab.", "Browser shows example.com.", ("Example Domain",), critical=True),
    _gui("browser-link", "In the desktop browser, open https://example.com and follow its only link. Report the domain you land on.", "Browser followed the example.com link.", ("iana.org",)),
    _gui("browser-new-tab", "Open two browser tabs on the desktop: example.com and example.org. Verify both are open.", "Two tabs are open with the requested sites."),
    _gui("browser-zoom", "Open https://example.com in the desktop browser, zoom the page to 150%, and verify the zoom level.", "Page zoom is 150%."),
    _gui("browser-find", "Open https://example.com in the desktop browser and use find-in-page to locate the word 'domain'. Report how many matches the find bar shows.", "Find-in-page located the word."),
    _gui("browser-back", "In the desktop browser open example.com, then example.org, then navigate back and report which site is shown.", "Browser is back on example.com.", ("example.com",)),
    _gui("browser-form-fill", "Open https://httpbin.org/forms/post in the desktop browser, fill customer name 'Ada Lovelace', choose a medium pizza, submit, and report the custname value echoed back.", "Form submitted and echoed.", ("Ada Lovelace",), critical=True),
    _gui("browser-download", "In the desktop browser download https://httpbin.org/robots.txt and verify the file exists in the Downloads folder.", "robots.txt is in Downloads."),
    _gui("browser-scroll-bottom", "Open https://en.wikipedia.org/wiki/Special:Random in the desktop browser, scroll to the very bottom, and confirm the footer is visible.", "Footer is visible after scrolling."),
    _gui("browser-select-copy", "Open https://example.com in the desktop browser, select the main heading text, copy it, and report what was copied.", "Heading text copied.", ("Example Domain",)),
    _gui("desktop-screenshot-describe", "Take a screenshot of the desktop and report how many windows are visibly open.", "Answer grounded in a fresh screenshot."),
    _gui("desktop-open-files", "Open the file manager on the desktop and report the name of one folder in the home directory.", "File manager is open on home."),
    _gui("desktop-text-editor", "Open a GUI text editor on the desktop, type 'hello osworld', save it as ~/Desktop/hello.txt, and verify the file is saved.", "hello.txt saved with the text.", critical=True),
    _gui("desktop-rename-file", "Using the desktop file manager, rename ~/Desktop/hello.txt to greeting.txt (create it first if missing) and verify.", "greeting.txt exists on the Desktop."),
    _gui("desktop-keyboard-shortcut", "Open the desktop browser and use a keyboard shortcut to open a new tab. Verify a new tab opened.", "A new tab is open."),
    _gui("desktop-close-window", "Open the desktop browser, then close it using the window controls. Verify no browser window remains.", "Browser window closed."),
    _gui("desktop-right-click", "Right-click on the desktop background and report one option shown in the context menu.", "Context menu observed in a screenshot."),
    _gui("browser-search-engine", "In the desktop browser, search the web for 'IANA example domains' and open the IANA result. Report the page heading.", "IANA page open.", ("Example Domains", "example domain")),
    _gui("browser-wiki-infobox", "In the desktop browser open the Wikipedia article for 'Python (programming language)' and report the 'Designed by' value from the infobox.", "Infobox read from the page.", ("Guido van Rossum", "Rossum")),
    _gui("browser-dropdown", "Open https://the-internet.herokuapp.com/dropdown in the desktop browser, select 'Option 2', and verify it is selected.", "Option 2 is selected.", ("Option 2",)),
)

BENCHMARK_SUITES: dict[str, tuple[TaskEvalCase, ...]] = {
    "gaia_mini": GAIA_MINI,
    "osworld_mini": OSWORLD_MINI,
}


def validate_benchmarks() -> None:
    for name, cases in BENCHMARK_SUITES.items():
        ids = [case.case_id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{name}: case ids must be unique")
        for case in cases:
            if not (case.prompt.strip() and case.expected_state.strip()):
                raise ValueError(f"{name}: {case.case_id} needs a prompt and expected state")
    if len(GAIA_MINI) != 30 or len(OSWORLD_MINI) != 20:
        raise ValueError("gaia_mini must have 30 cases and osworld_mini 20")


validate_benchmarks()

__all__ = ["BENCHMARK_SUITES", "GAIA_MINI", "OSWORLD_MINI", "validate_benchmarks"]
