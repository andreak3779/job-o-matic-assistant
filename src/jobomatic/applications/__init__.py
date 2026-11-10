"""The applications module: the event-sourced log of postings drafted for and applied to.

``from jobomatic import applications`` gives the path-based interface (``api``) and the record
types. The use cases themselves are in ``service`` and know nothing about files.
"""

from jobomatic.applications.api import (
    append_event,
    check_jd_text,
    check_posting,
    create_application,
    find_for_jd,
    get_application,
    import_csv,
    load_applications,
    log_path,
    mark_applied,
    read_events,
    record_draft,
    set_status,
    update_application,
)
from jobomatic.applications.model import (
    DUPLICATE_WINDOW_DAYS,
    FIELDS,
    NO_RESPONSE_PATTERN_COUNT,
    STATUSES,
    SUBMITTED_STATUSES,
    Application,
    ImportReport,
    PostingCheck,
    company_key,
    folder_name_for,
    is_same_posting,
    parse_date,
    parse_status,
    same_company,
)

__all__ = [
    "DUPLICATE_WINDOW_DAYS",
    "FIELDS",
    "NO_RESPONSE_PATTERN_COUNT",
    "STATUSES",
    "SUBMITTED_STATUSES",
    "Application",
    "ImportReport",
    "PostingCheck",
    "append_event",
    "check_jd_text",
    "check_posting",
    "company_key",
    "create_application",
    "find_for_jd",
    "folder_name_for",
    "get_application",
    "import_csv",
    "is_same_posting",
    "load_applications",
    "log_path",
    "mark_applied",
    "parse_date",
    "parse_status",
    "read_events",
    "record_draft",
    "same_company",
    "set_status",
    "update_application",
]
