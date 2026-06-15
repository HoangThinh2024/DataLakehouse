import subprocess

if "custom" not in dir():
    from mage_ai.data_preparation.decorators import custom


@custom
def run_dbt(*args, **kwargs):
    """
    Run dbt models using the shell.
    Mage has native dbt blocks, but shell execution gives more control over profiles-dir.
    """
    project_dir = "/home/src/dbt_lakehouse"
    profiles_dir = "/home/src/dbt_lakehouse"

    print(f"[dbt] Running models in {project_dir}...")

    # Run dbt run
    cmd_run = [
        "dbt",
        "run",
        "--project-dir",
        project_dir,
        "--profiles-dir",
        profiles_dir,
    ]
    res_run = subprocess.run(cmd_run)

    if res_run.returncode != 0:
        raise Exception(f"dbt run failed with exit code {res_run.returncode}")

    print("[dbt] dbt run completed successfully.")

    # Run dbt test (Optional but recommended for DQ)
    print("[dbt] Running dbt tests...")
    cmd_test = [
        "dbt",
        "test",
        "--project-dir",
        project_dir,
        "--profiles-dir",
        profiles_dir,
    ]
    res_test = subprocess.run(cmd_test)

    if res_test.returncode != 0:
        print(
            f"[dbt] WARNING: Some dbt tests failed with exit code {res_test.returncode}."
        )
    else:
        print("[dbt] All dbt tests passed.")

    return args[0] if args else None
