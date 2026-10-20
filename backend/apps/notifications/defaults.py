"""Built-in notification texts. Override any of them with NotificationTemplate rows.
SMS texts intentionally carry no confidential details (features.txt section 25)."""

DEFAULTS = {
    "workflow.task_assigned": {
        "title": "Action required: {{ title }}",
        "body": "A request is waiting for your action at step '{{ step }}'.{% if due_at %} Due {{ due_at|date:'d/m/Y H:i' }}.{% endif %}",
        "sms": "ShineLight HRM: you have a new request awaiting your approval. Please sign in to review.",
    },
    "workflow.reminder": {
        "title": "Reminder: {{ title }}",
        "body": "This request is approaching its deadline{% if due_at %} ({{ due_at|date:'d/m/Y H:i' }}){% endif %}.",
    },
    "workflow.escalated": {
        "title": "Escalated: {{ title }}",
        "body": "The request has passed its service deadline at step '{{ step }}' and has been escalated.",
    },
    "workflow.approved": {
        "title": "Approved: {{ title }}",
        "body": "Your request has been approved.{% if comment %} Comment: {{ comment }}{% endif %}",
        "sms": "ShineLight HRM: your request has been approved. Sign in for details.",
    },
    "workflow.rejected": {
        "title": "Not approved: {{ title }}",
        "body": "Your request was not approved.{% if comment %} Reason: {{ comment }}{% endif %}",
        "sms": "ShineLight HRM: there is an update on your request. Sign in for details.",
    },
    "workflow.returned": {
        "title": "Returned for correction: {{ title }}",
        "body": "Your request needs changes before it can proceed.{% if comment %} Note: {{ comment }}{% endif %}",
    },
    "leave.recalled": {
        "title": "Leave recall: {{ title }}",
        "body": "You have been recalled from leave effective {{ date|date:'d/m/Y' }}. {{ reason }}",
        "sms": "ShineLight HRM: you have been recalled from leave. Please sign in or contact your supervisor.",
    },
    "payroll.payslip_ready": {
        "title": "Your payslip for {{ period }} is available",
        "body": "Your payslip for {{ period }} has been published. View it under My Payslips.",
        "sms": "ShineLight HRM: your payslip for {{ period }} is available in the portal.",
    },
    "payroll.submitted": {
        "title": "Payroll {{ period }} awaiting approval",
        "body": "Payroll for {{ period }} has been calculated and submitted for approval.",
    },
    "expiry.contract": {
        "title": "Contract expiring: {{ employee }}",
        "body": "The contract for {{ employee }} expires on {{ date|date:'d/m/Y' }}.",
    },
    "expiry.probation": {
        "title": "Probation review due: {{ employee }}",
        "body": "Probation for {{ employee }} ends on {{ date|date:'d/m/Y' }}. Please complete the review.",
    },
    "expiry.document": {
        "title": "Document expiring: {{ document }}",
        "body": "{{ document }} for {{ employee }} expires on {{ date|date:'d/m/Y' }}.",
    },
    "expiry.license": {
        "title": "Professional licence expiring: {{ employee }}",
        "body": "{{ license }} for {{ employee }} expires on {{ date|date:'d/m/Y' }}.",
        "sms": "ShineLight HRM: a professional licence on your record is due for renewal. Please update HR.",
    },
    "attendance.missing_punch": {
        "title": "Missing clock-in/out on {{ date|date:'d/m/Y' }}",
        "body": "We could not find a complete attendance record for {{ date|date:'d/m/Y' }}. Submit a correction if needed.",
    },
    "announcement.published": {
        "title": "{{ title }}",
        "body": "{{ summary }}",
    },
    "celebration.birthday": {
        "title": "Happy birthday, {{ name }}!",
        "body": "Best wishes from all of us at {{ organization }}.",
    },
    "celebration.anniversary": {
        "title": "Happy work anniversary, {{ name }}!",
        "body": "Congratulations on {{ years }} year{{ years|pluralize }} with {{ organization }}.",
    },
    "generic": {"title": "{{ title }}", "body": "{{ body }}"},
}
