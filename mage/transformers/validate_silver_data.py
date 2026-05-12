import pandas as pd
import great_expectations as gx
from great_expectations.core import ExpectationConfiguration

if 'transformer' not in dir():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in dir():
    from mage_ai.data_preparation.decorators import test

@transformer
def validate(data, *args, **kwargs):
    """
    Great Expectations Data Quality Validator.
    """
    if not isinstance(data, dict) or data.get('skip'):
        return data

    df = data.get('dataframe')
    if df is None or df.empty:
        print("[validate_silver_data] Skipping validation – empty DataFrame")
        return data

    print(f"[validate_silver_data] Starting DQ validation for {len(df)} rows...")

    try:
        # 1. Initialize GX Context (Ephemeral)
        context = gx.get_context()

        # 2. Create a Batch Request
        datasource_name = "mage_datasource"
        data_asset_name = "silver_data_asset"
        
        # Check if datasource exists, if not create it
        try:
            datasource = context.get_datasource(datasource_name)
        except Exception:
            datasource = context.sources.add_pandas(name=datasource_name)
        
        # Add or update data asset
        try:
            data_asset = datasource.get_asset(data_asset_name)
        except Exception:
            data_asset = datasource.add_dataframe_asset(name=data_asset_name)
        
        batch_request = data_asset.build_batch_request(dataframe=df)

        # 3. Define Expectation Suite
        suite_name = "silver_excel_suite"
        suite = context.add_or_update_expectation_suite(expectation_suite_name=suite_name)

        # 4. Add Expectations via Configuration (String-based for version compatibility)
        # ID column must not be null and must be unique
        if "Mã công việc (ID)" in df.columns:
            suite.add_expectation(ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "Mã công việc (ID)"}
            ))
            suite.add_expectation(ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_unique",
                kwargs={"column": "Mã công việc (ID)"}
            ))

        # Status column must be in a specific set
        if "Trạng thái" in df.columns:
            allowed_statuses = ['Đang triển khai', 'Hoàn thành', 'Chưa bắt đầu', 'Tạm dừng']
            suite.add_expectation(ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={
                    "column": "Trạng thái",
                    "value_set": allowed_statuses
                }
            ))

        # Numeric columns should be non-negative
        for col in ["Số tiền", "Diện tích (ha)"]:
            if col in df.columns:
                suite.add_expectation(ExpectationConfiguration(
                    expectation_type="expect_column_values_to_be_between",
                    kwargs={
                        "column": col,
                        "min_value": 0
                    }
                ))

        # Core metadata columns must exist
        for col in ["_extracted_at", "_source_file_key"]:
            suite.add_expectation(ExpectationConfiguration(
                expectation_type="expect_column_to_exist",
                kwargs={"column": col}
            ))

        # 5. Run Validation
        checkpoint = context.add_or_update_checkpoint(
            name="silver_dq_checkpoint",
            expectation_suite_name=suite_name,
            batch_request=batch_request
        )
        
        validation_result = checkpoint.run()

        # 6. Evaluate Results
        if not validation_result.success:
            print("\n[validate_silver_data] ❌ DATA QUALITY VALIDATION FAILED!")
            for res in validation_result.run_results.values():
                for result in res['validation_result']['results']:
                    if not result['success']:
                        print(f"  - Failed: {result['expectation_config']['expectation_type']} "
                              f"on column '{result['expectation_config']['kwargs'].get('column')}'")
            
            raise ValueError("Data Quality Validation Failed. Check Mage logs for details.")

        print("[validate_silver_data] ✅ Data Quality Validation Passed.")
    except Exception as e:
        print(f"[validate_silver_data] ERROR during validation: {e}")
        raise

    return data

@test
def test_output(output, *args):
    assert output is not None
    assert isinstance(output, dict)
    if not output.get('skip'):
        assert 'dataframe' in output
