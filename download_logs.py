import asyncio
import copy
import sys

import aiohttp
import os
import os.path
import re

token = os.getenv("GITHUB_TOKEN")
branch = os.getenv("BRANCH", "development")

log_archive_dir = f"log_archives/{branch}"
log_archive_tmp_dir = f"log_archives/{branch}/tmp"
branch_pattern = re.compile(r"\[[^]]+\]$")

MAX_CONCURRENT_REQUESTS = 20
MAX_PAGES = 2

GITHUB_API_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def download_logs(session, run_id, logs_url):
    target_tmp_path = f"{log_archive_dir}/tmp/logs_{run_id}.zip"
    target_path = f"{log_archive_dir}/logs_{run_id}.zip"

    logs_response = await session.get(
        url=logs_url,
        headers=GITHUB_API_REQUEST_HEADERS,
    )
    if logs_response.status != 200:
        response_text = await logs_response.text()
        response_text = response_text.strip()
        if response_text:
            response_text = f": {response_text}"
        print(f"Skipping run {run_id} due to error {logs_response.status}{response_text}")
        return
    try:
        logs_data = await logs_response.read()
    except Exception as exc:
        print(f"Skipping run {run_id} due to error reading logs data: {exc}")
        return
    print(f"Writing {len(logs_data) / 1000000:.2f} MB of logs data to {target_path}")
    with open(target_tmp_path, "wb") as logs_zip_file:
        logs_zip_file.write(logs_data)
    os.rename(target_tmp_path, target_path)


async def get_job(session, jobs_url):
    jobs_response = await session.get(
        url=jobs_url,
        headers=GITHUB_API_REQUEST_HEADERS,
    )
    assert jobs_response.status == 200, jobs_response
    jobs_dict = await jobs_response.json()
    return jobs_dict


async def make_reqs(session, page):
    runs_response = await session.get(
        url=f"https://api.github.com/repos/mlrun/mlrun/actions/workflows/system-tests-enterprise.yml/runs?status=completed&per_page=100&page={page}",
        headers=GITHUB_API_REQUEST_HEADERS,
    )
    assert runs_response.status == 200, runs_response
    runs_dict = await runs_response.json()

    num_runs = runs_dict["total_count"]
    print("Total number of runs:", num_runs)
    workflow_runs = runs_dict["workflow_runs"]
    runs_on_page = len(workflow_runs)
    print(f"Runs on page {page}:", runs_on_page)

    print(f"Listing jobs for {len(workflow_runs)} runs...")

    tasks = []
    runs = []
    remaining_runs_to_list = copy.copy(workflow_runs)
    index = 0
    jobs_dicts = []
    while remaining_runs_to_list:
        if len(tasks) == MAX_CONCURRENT_REQUESTS:
            job_dict = await tasks[0]
            jobs_dicts.append(job_dict)
            tasks = tasks[1:]
        index += 1
        print(f"Getting workflow run {index}/{len(workflow_runs)}...")
        run = remaining_runs_to_list[0]
        remaining_runs_to_list = remaining_runs_to_list[1:]
        runs.append(run)
        task = asyncio.create_task(get_job(session, run["jobs_url"]))
        tasks.append(task)

    for task in tasks:
        job_dict = await task
        jobs_dicts.append(job_dict)

    runs_to_download = []
    for index, jobs_dict in enumerate(jobs_dicts):
        run = runs[index]
        run_id = run["id"]
        branch_found = None
        for job in jobs_dict["jobs"]:
            if job["name"].startswith("Test api"):
                branch_found = branch_pattern.search(job["name"]).group(0)[1:-1]
                break

        if not branch_found:
            print(f"Skipping run {run_id} because its branch could not be determined")
            continue
        elif branch_found != branch:
            print(f"Skipping run {run_id} because it's for branch {branch_found}")
            continue

        if os.path.exists(f"{log_archive_dir}/logs_{run_id}.zip"):
            print(f"Skipping run {run_id} because target file already exists")
            continue

        runs_to_download.append(run)

    run_ids_to_download = [run["id"] for run in runs_to_download]
    print(f"{len(run_ids_to_download)} run IDs to download:", run_ids_to_download)

    tasks = []
    os.makedirs(log_archive_tmp_dir, exist_ok=True)
    remaining_runs_to_download = copy.copy(runs_to_download)
    index = 0
    while remaining_runs_to_download:
        if len(tasks) == MAX_CONCURRENT_REQUESTS:
            await tasks[0]
            tasks = tasks[1:]
        index += 1
        print(f"Starting to download file {index}/{len(runs_to_download)}...")
        run = remaining_runs_to_download[0]
        remaining_runs_to_download = remaining_runs_to_download[1:]
        task = asyncio.create_task(download_logs(session, run["id"], run["logs_url"]))
        tasks.append(task)

        for task in tasks:
            await task


async def main():
    if not token:
        print(f"{sys.argv[0]}: ERROR: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)
    async with aiohttp.ClientSession() as session:
        for page in range(1, MAX_PAGES + 1):
            await make_reqs(session, page)


if __name__ == "__main__":
    asyncio.run(main())
