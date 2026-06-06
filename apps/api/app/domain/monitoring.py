PROCESS_MONITORING_IMPORT_JOB_TYPE = "process_monitoring_import"
MONITORING_RULE_VERSION = "sp_search_term_monitoring_rules_v2"
MONITORING_EVIDENCE_SCHEMA_VERSION = "monitoring_evidence_v1"
AGENT_SCHEMA_VERSION = "agent_council_v1"

SP_SEARCH_TERM_REQUIRED_COLUMNS = {
    "campaign name",
    "ad group name",
    "targeting",
    "customer search term",
    "impressions",
    "clicks",
    "spend",
    # sales and orders are checked via SP_SEARCH_TERM_COLUMN_ALIASES in monitoring_rules.py
    # to support both 7-day and 14-day attribution windows
    "7 day total sales",
    "7 day total orders",
}

# Columns that satisfy the sales/orders requirement regardless of attribution window.
# monitoring_rules.py resolves these before checking SP_SEARCH_TERM_REQUIRED_COLUMNS.
SP_SEARCH_TERM_SALES_ALIASES = {
    "7 day total sales", "14 day total sales", "total sales", "sales",
}
SP_SEARCH_TERM_ORDERS_ALIASES = {
    "7 day total orders", "14 day total orders", "total orders",
    "7 day total orders #", "7 day total orders number",
    "14 day total orders #", "14 day total orders number",
    "orders",
}

SP_SEARCH_TERM_REPORT_SOURCE_TYPE = "amazon_ads_sp_search_term_report"
