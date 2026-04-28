"""
Gemini Semantic Layer - Metadata for RAG.
This file helps Gemini CLI understand our Data Lakehouse structure.
"""

# Database: analytics
# Table: project_reports (Detailed tasks)
# Table: gold_projects_summary (Project KPIs)
# Table: gold_workload_report (Resource metrics)

METADATA = {
    "tables": [
        {
            "name": "gold_projects_summary",
            "description": "Báo cáo tổng hợp tiến độ của 12 dự án. Dùng để so sánh tỷ lệ hoàn thành giữa các dự án.",
            "columns": {
                "_source_file_key": "Tên dự án hoặc tên file gốc",
                "total_tasks": "Tổng số công việc trong dự án",
                "completion_rate": "Tỷ lệ hoàn thành (0-100%)",
                "overdue_tasks": "Số lượng công việc bị trễ hạn"
            }
        },
        {
            "name": "gold_workload_report",
            "description": "Báo cáo khối lượng công việc theo nhân sự.",
            "columns": {
                "Người thực hiện": "Tên cán bộ phụ trách",
                "task_count": "Số lượng công việc đang đảm nhiệm",
                "urgent_tasks": "Số lượng công việc khẩn cấp"
            }
        }
    ]
}
