import os
import re
from datetime import datetime

import sys

MIN_PYTHON = (3, 11)
assert sys.version_info >= MIN_PYTHON, f"requires Python {'.'.join([str(n) for n in MIN_PYTHON])} or newer"

RED = '\033[0;31m'
NC = '\033[0m'

branch = os.getenv("BRANCH", "development")
logs_dir = f"logs/{branch}"

suites = ["alerts", "api", "backwards_compatibility", "datastore", "examples", "feature_store", "logs",
          "model_monitoring", "projects", "runtimes"]
suites.sort()

test_name_pattern = re.compile("[0-9-:.+ZT]+ FAILED ([^ ]+)")

localize_tz = False
abbreviated_test_names = True


def trunc(commit):
    return commit[:12]


def format_timestamp(timestamp: datetime):
    if localize_tz:
        timestamp = timestamp.astimezone()
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def extract_run_metadata(run):
    log_path = f"{logs_dir}/{run}/0_Prepare System Tests Enterprise.txt"
    with open(log_path) as file:
        found = False
        for line in file:
            if "git log -1 --format=%H" in line:
                found = True
                break
        if not found:
            return
        for commit_line in file:
            timestamp, commit = commit_line.strip().split(" ", 1)
            break
    return timestamp, commit


def extract_failures_from_log(run, suite):
    log_path = f"{logs_dir}/{run}/Test {suite} [{branch}]/9_Run System Tests.txt"
    if not os.path.exists(log_path):
        return
    failures = []
    with open(log_path) as file:
        found = False
        for line in file:
            if "= short test summary info =" in line:
                found = True
                break
        if not found:
            return
        for line in file:
            if "FAILED" not in line:
                break
            match = test_name_pattern.match(line)
            failures.append(match.group(1))
    return failures


class RunInfo:
    def __init__(self, name: str, timestamp: datetime, commit: str, previous):
        self.name = name
        self.timestamp = timestamp
        self.commit = commit
        self.previous = previous


def analyze_runs(suites):
    os.makedirs(logs_dir, exist_ok=True)
    runs = os.listdir(logs_dir)
    runs.sort()

    print("Branch:", branch)
    print(f"Analyzing {len(suites)} suites: {suites}")
    print(f"Analyzing {len(runs)} runs:", ", ".join(map(lambda r: r[5:], runs)))
    run_info_by_run = {}
    first_timestamp = None
    last_timestamp = None
    first_commit = None
    last_commit = None
    previous_run_info = None
    for run in runs:
        timestamp, commit = extract_run_metadata(run)
        timestamp = datetime.fromisoformat(timestamp)
        if first_timestamp is None or timestamp < first_timestamp:
            first_timestamp = timestamp
            first_commit = commit
        if last_timestamp is None or timestamp > last_timestamp:
            last_timestamp = timestamp
            last_commit = commit
        run_info = RunInfo(run, timestamp, commit, previous_run_info)
        run_info_by_run[run] = run_info
        previous_run_info = run_info

    if not runs:
        print("Zero runs found")
        return

    first_timestamp_str = format_timestamp(first_timestamp)
    last_timestamp_str = format_timestamp(last_timestamp)
    print(f"From {RED}{first_timestamp_str}{NC} ({trunc(first_commit)}) to {RED}{last_timestamp_str}{NC} "
          f"({trunc(last_commit)})")

    for suite in suites:
        oldest_consecutive_failure = {}
        last_failures = []
        for run in runs:
            run_info = run_info_by_run[run]
            failures = extract_failures_from_log(run, suite)
            if failures is None:
                continue
            if first_timestamp is None:
                first_timestamp = run_info.timestamp

            new_oldest_consecutive_failure = {}
            for failure in failures:
                new_oldest_consecutive_failure[failure] = oldest_consecutive_failure.get(failure, run_info_by_run[run])
            oldest_consecutive_failure = new_oldest_consecutive_failure

            last_failures = failures

        if last_failures:
            print(f"---------------- {suite} ----------------")

        for failure in last_failures:
            run_info = oldest_consecutive_failure[failure]
            timestamp_str = format_timestamp(run_info.timestamp)
            previous_run_info = run_info.previous
            if previous_run_info:
                t = format_timestamp(previous_run_info.timestamp)
                previous_timestamp_str = f"between {RED}{t}{NC} ({trunc(previous_run_info.commit)}) and"
            else:
                previous_timestamp_str = "before"
            if abbreviated_test_names:
                failure = failure[failure.find("/", len("tests/system/")) + 1:]
            print(
                f"{failure} broke {previous_timestamp_str} {RED}{timestamp_str}{NC} "
                f"({trunc(run_info.commit)})")


def main():
    analyze_runs(suites)


if __name__ == "__main__":
    main()
