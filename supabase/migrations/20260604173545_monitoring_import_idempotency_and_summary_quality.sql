-- Enforce one monitoring import per workspace/product/upload/report type.
-- Re-analysis should reuse the existing import record instead of creating a
-- duplicate import row for the same uploaded report.
create unique index if not exists monitoring_imports_upload_report_unique_idx
    on monitoring_imports(workspace_id, product_id, upload_id, report_type);

comment on index monitoring_imports_upload_report_unique_idx is
    'Prevents duplicate monitoring imports for the same workspace/product/upload/report_type. Re-run analysis must reuse the existing import.';
