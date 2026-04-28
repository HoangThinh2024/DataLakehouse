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
            "name": "project_reports",
            "description": "Chi tiết từng công việc từ 12 dự án. Dùng để tra cứu trạng thái, người thực hiện và mức độ khẩn cấp của từng task.",
            "columns": {
                "_source_file_key": "Tên dự án hoặc tên file Excel gốc",
                "Mã công việc (ID)": "Mã định danh duy nhất của công việc",
                "Tên công việc": "Mô tả ngắn về công việc",
                "Trạng thái": "Trạng thái hiện tại (Hoàn thành / Đang làm / Trễ hạn / Chưa làm)",
                "Người thực hiện": "Cán bộ được giao phụ trách công việc",
                "Khẩn cấp": "Mức độ khẩn cấp (Có / Không)",
                "_db_processed_at": "Thời điểm dữ liệu được nạp vào ClickHouse"
            }
        },
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
