import os

if 'custom' not in dir():
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
    exit_code = os.system(f"dbt run --project-dir {project_dir} --profiles-dir {profiles_dir}")
    
    if exit_code != 0:
        raise Exception(f"dbt run failed with exit code {exit_code}")
    
    print("[dbt] dbt run completed successfully.")
    
    # Run dbt test (Optional but recommended for DQ)
    print("[dbt] Running dbt tests...")
    test_exit_code = os.system(f"dbt test --project-dir {project_dir} --profiles-dir {profiles_dir}")
    
    if test_exit_code != 0:
        print("[dbt] WARNING: Some dbt tests failed.")
    else:
        print("[dbt] All dbt tests passed.")

    return args[0] if args else None
