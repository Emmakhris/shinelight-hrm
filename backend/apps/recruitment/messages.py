"""Candidate communication texts (candidates are not system users, so these bypass in-app notifications).
Rendered with Django template syntax. SMS texts carry no personal or confidential details."""

CANDIDATE_MESSAGES = {
    "acknowledgment": {
        "subject": "Application received: {{ vacancy.title }}",
        "body": "Dear {{ candidate.first_name }},\n\nThank you for applying for the position of {{ vacancy.title }} "
                "at {{ organization.name }} (reference {{ application.reference }}). We will review your application "
                "and contact you if you are shortlisted.\n\nRecruitment Team\n{{ organization.name }}",
        "sms": "{{ organization.name }}: we have received your application ({{ application.reference }}). Thank you.",
    },
    "shortlisted": {
        "subject": "Update on your application: {{ vacancy.title }}",
        "body": "Dear {{ candidate.first_name }},\n\nWe are pleased to inform you that you have been shortlisted for "
                "the position of {{ vacancy.title }}. We will contact you shortly with next steps.\n\n"
                "Recruitment Team\n{{ organization.name }}",
    },
    "interview_invite": {
        "subject": "Interview invitation: {{ vacancy.title }}",
        "body": "Dear {{ candidate.first_name }},\n\nYou are invited to a {{ interview.round_name|lower }} for the "
                "position of {{ vacancy.title }}.\n\nDate and time: {{ interview.scheduled_at|date:'l, jS F Y, H:i' }}\n"
                "Format: {{ interview.get_mode_display }}\n{% if interview.venue %}Venue / link: {{ interview.venue }}\n"
                "{% endif %}Duration: about {{ interview.duration_minutes }} minutes\n\nPlease bring your Ghana Card "
                "and original certificates. Reply to this email to confirm your attendance.\n\n"
                "Recruitment Team\n{{ organization.name }}",
        "sms": "{{ organization.name }}: you are invited to an interview on "
               "{{ interview.scheduled_at|date:'d/m/Y H:i' }}. Check your email for details.",
    },
    "interview_cancelled": {
        "subject": "Interview rescheduled: {{ vacancy.title }}",
        "body": "Dear {{ candidate.first_name }},\n\nYour interview scheduled for "
                "{{ interview.scheduled_at|date:'d/m/Y H:i' }} has been cancelled. We will contact you with a new "
                "date.\n\nRecruitment Team\n{{ organization.name }}",
    },
    "regret": {
        "subject": "Your application: {{ vacancy.title }}",
        "body": "Dear {{ candidate.first_name }},\n\nThank you for your interest in the position of {{ vacancy.title }} "
                "at {{ organization.name }}. After careful consideration, we will not be taking your application "
                "further on this occasion.{% if candidate.talent_pool %} With your permission we will keep your "
                "details on file and contact you about suitable future vacancies.{% endif %}\n\nWe wish you every "
                "success.\n\nRecruitment Team\n{{ organization.name }}",
    },
    "offer": {
        "subject": "Offer of employment: {{ offer.job_title.name }}",
        "body": "Dear {{ candidate.first_name }},\n\nWe are delighted to offer you the position of "
                "{{ offer.job_title.name }} at {{ organization.name }}. Please review your offer letter and respond "
                "by {{ offer.expiry_date|date:'jS F Y' }} using this secure link:\n\n{{ link }}\n\n"
                "Recruitment Team\n{{ organization.name }}",
        "sms": "{{ organization.name }}: an offer of employment has been sent to your email. "
               "Please respond by {{ offer.expiry_date|date:'d/m/Y' }}.",
    },
    "offer_accepted": {
        "subject": "Welcome to {{ organization.name }}",
        "body": "Dear {{ candidate.first_name }},\n\nThank you for accepting our offer. Your start date is "
                "{{ offer.start_date|date:'l, jS F Y' }}. HR will contact you about pre-employment documents and "
                "your first day.\n\nRecruitment Team\n{{ organization.name }}",
    },
}
