from pathlib import Path

from colorama import Fore, Style
from tqdm import tqdm

progress_bar = None


def pytest_sessionstart(session):
    session.progress_total = 0  # will be set later


def pytest_collection_modifyitems(session, config, items):
    global progress_bar
    session.progress_total = len(items)
    session.progress_index = 0
    progress_bar = tqdm(
        total=session.progress_total,
        desc=f"{Fore.GREEN}Running tests{Style.RESET_ALL}",
        ncols=100,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        colour="green",
        dynamic_ncols=False,
    )


def pytest_runtest_logreport(report):
    if report.when == "call":
        test_file = Path(report.fspath).name
        progress_bar.set_description(
            f"{Fore.GREEN}Running {test_file}{Style.RESET_ALL}"
        )
        progress_bar.update(1)


def pytest_sessionfinish(session, exitstatus):
    if progress_bar:
        progress_bar.close()
