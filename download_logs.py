import asyncio
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
pages = 2


async def download_logs(session, run_id, logs_url):
    target_tmp_path = f"{log_archive_dir}/tmp/logs_{run_id}.zip"
    target_path = f"{log_archive_dir}/logs_{run_id}.zip"

    logs_response = await session.get(
        url=logs_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if logs_response.status != 200:
        print(f"Skipping run {run_id} due to error {logs_response.status}: {await logs_response.text()}")
        return
    logs_data = await logs_response.read()
    print(f"Writing {len(logs_data) / 1000000:.2f} MB of logs data to {target_path}")
    with open(target_tmp_path, "wb") as logs_zip_file:
        logs_zip_file.write(logs_data)
    os.rename(target_tmp_path, target_path)


async def get_job(session, jobs_url):
    jobs_response = await session.get(
        url=jobs_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    assert jobs_response.status == 200
    jobs_dict = await jobs_response.json()
    return jobs_dict


async def get_until_done(q: asyncio.Queue):
    while True:
        task = await q.get()
        if task is None:
            break
        await task


async def make_reqs(session, page):
    runs_response = await session.get(
        url=f"https://api.github.com/repos/mlrun/mlrun/actions/workflows/system-tests-enterprise.yml/runs?status=completed&per_page=100&page={page}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    assert runs_response.status == 200
    runs_dict = await runs_response.json()

    num_runs = runs_dict["total_count"]
    print("Total number of runs:", num_runs)
    workflow_runs = runs_dict["workflow_runs"]
    runs_on_page = len(workflow_runs)
    print(f"Runs on page {page}:", runs_on_page)

    jobs_tasks = []
    runs = []
    q = asyncio.Queue(MAX_CONCURRENT_REQUESTS)
    get_until_done_task = asyncio.create_task(get_until_done(q))
    for index, run in enumerate(workflow_runs):
        print(f"Getting workflow run {index + 1}/{len(workflow_runs)}...")
        runs.append(run)
        task = asyncio.create_task(get_job(session, run["jobs_url"]))
        jobs_tasks.append(task)
        await q.put(task)
    await q.put(None)
    await get_until_done_task

    print(f"Listing jobs for {len(jobs_tasks)} runs...")
    jobs_dicts = await asyncio.gather(*jobs_tasks)

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
    q = asyncio.Queue(MAX_CONCURRENT_REQUESTS)
    get_until_done_task = asyncio.create_task(get_until_done(q))
    os.makedirs(log_archive_tmp_dir, exist_ok=True)
    for index, run in enumerate(runs_to_download):
        print(f"Starting to download file {index + 1}/{len(runs_to_download)}...")
        task = asyncio.create_task(download_logs(session, run["id"], run["logs_url"]))
        tasks.append(task)
        await q.put(task)
    await q.put(None)
    await get_until_done_task
    await asyncio.gather(*tasks)


async def main():
    if not token:
        print(f"{sys.argv[0]}: ERROR: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)
    async with aiohttp.ClientSession() as session:
        for page in range(1, pages + 1):
            await make_reqs(session, page)


if __name__ == "__main__":
    asyncio.run(main())
