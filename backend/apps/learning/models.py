from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

MONEY = {"max_digits": 14, "decimal_places": 2, "default": Decimal("0")}


class Course(TenantModel):
    CATEGORIES = [("clinical", "Clinical"), ("safety", "Health & safety"), ("compliance", "Compliance / policy"),
                  ("leadership", "Leadership & management"), ("technical", "Technical / functional"),
                  ("soft_skills", "Personal effectiveness"), ("induction", "Induction")]
    DELIVERY = [("classroom", "Classroom"), ("elearning", "E-learning"), ("external", "External programme"),
                ("on_the_job", "On-the-job"), ("blended", "Blended")]
    code = models.CharField(max_length=30, blank=True)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=12, choices=CATEGORIES, default="technical")
    delivery = models.CharField(max_length=12, choices=DELIVERY, default="classroom")
    provider = models.CharField(max_length=150, blank=True, help_text="Blank = internal.")
    description = models.TextField(blank=True)
    objectives = models.TextField(blank=True, help_text="Learning outcomes.")
    duration_hours = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("1"))
    cpd_credits = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    cost_per_participant = models.DecimalField(**MONEY)
    pass_mark = models.PositiveSmallIntegerField(default=70, help_text="% required on the assessment.")
    # mandatory training
    is_mandatory = models.BooleanField(default=False)
    applies_to_all = models.BooleanField(default=False, help_text="Mandatory for every employee.")
    job_titles = models.ManyToManyField("organization.JobTitle", blank=True, related_name="mandatory_courses")
    refresher_months = models.PositiveSmallIntegerField(null=True, blank=True,
                                                        help_text="Completion expires after this many months.")
    competency_requirement = models.ForeignKey("hospital.CompetencyRequirement", null=True, blank=True,
                                               on_delete=models.SET_NULL, related_name="courses",
                                               help_text="Completing the course renews this clinical competency.")
    competencies = models.ManyToManyField("performance.Competency", blank=True, related_name="courses",
                                          help_text="Competencies this course develops (for gap analysis).")
    self_enrol = models.BooleanField(default=True, help_text="Employees may request it from the catalogue.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class CourseModule(TenantModel):
    KINDS = [("text", "Reading"), ("video", "Video"), ("document", "Document / slides"), ("link", "External link")]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=KINDS, default="text")
    content = models.TextField(blank=True)
    url = models.URLField(blank=True, help_text="Video or resource link.")
    minutes = models.PositiveSmallIntegerField(default=10)

    class Meta:
        ordering = ["course", "order", "id"]


class QuizQuestion(TenantModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(default=0)
    text = models.TextField()
    options = models.JSONField(default=list, help_text='["Option A", "Option B", ...]')
    correct = models.JSONField(default=list, help_text="Indexes of the correct option(s), e.g. [1].")
    points = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["course", "order", "id"]


class Session(TenantModel):
    STATUS = [("scheduled", "Scheduled"), ("completed", "Completed"), ("cancelled", "Cancelled")]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    start = models.DateTimeField()
    end = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    trainer = models.CharField(max_length=150, blank=True)
    capacity = models.PositiveSmallIntegerField(default=20)
    registration_deadline = models.DateField(null=True, blank=True)
    actual_cost = models.DecimalField(**MONEY, help_text="Total cost (trainer, venue, materials).")
    status = models.CharField(max_length=10, choices=STATUS, default="scheduled")

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return f"{self.course.title} ({self.start:%d/%m/%Y})"


class Enrollment(TenantModel):
    SOURCES = [("request", "Employee request"), ("manager", "Nominated by manager"), ("mandatory", "Mandatory"),
               ("development", "Development plan"), ("hr", "Assigned by HR")]
    STATUS = [("pending", "Pending approval"), ("returned", "Returned"), ("rejected", "Not approved"),
              ("enrolled", "Enrolled"), ("waitlisted", "Waitlisted"), ("in_progress", "In progress"),
              ("completed", "Completed"), ("failed", "Not passed"), ("no_show", "Did not attend"),
              ("cancelled", "Cancelled")]
    OPEN = ["pending", "returned", "enrolled", "waitlisted", "in_progress"]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrollments")
    source = models.CharField(max_length=12, choices=SOURCES, default="request")
    reason = models.TextField(blank=True, help_text="Why this training is needed.")
    status = models.CharField(max_length=12, choices=STATUS, default="enrolled", db_index=True)
    due_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(**MONEY)
    modules_done = models.JSONField(default=list, blank=True)
    quiz_score = models.PositiveSmallIntegerField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    # level 1 evaluation (participant) and level 3 (manager, some weeks later)
    feedback_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback_comments = models.TextField(blank=True)
    effectiveness_rating = models.PositiveSmallIntegerField(null=True, blank=True,
                                                            help_text="Manager: applied on the job (1-5).")
    effectiveness_comments = models.TextField(blank=True)
    effectiveness_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="+")
    development_goal = models.ForeignKey("DevelopmentGoal", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="enrollments")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee.full_name} - {self.course.title}"


class TrainingBudget(TenantModel):
    department = models.ForeignKey("organization.Department", on_delete=models.CASCADE, related_name="+")
    year = models.PositiveSmallIntegerField()
    amount = models.DecimalField(**MONEY)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "department", "year"],
                                               name="uniq_training_budget")]


class CPDRecord(TenantModel):
    STATUS = [("pending", "Awaiting verification"), ("verified", "Verified"), ("rejected", "Rejected")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="cpd_records")
    title = models.CharField(max_length=200)
    provider = models.CharField(max_length=150, blank=True)
    activity_date = models.DateField()
    credits = models.DecimalField(max_digits=5, decimal_places=1)
    category = models.CharField(max_length=60, blank=True)
    evidence = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    enrollment = models.OneToOneField(Enrollment, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="cpd_record")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-activity_date"]


class CPDRequirement(TenantModel):
    """Annual CPD credits a role must earn (e.g. a professional council's renewal requirement)."""

    name = models.CharField(max_length=150)
    job_titles = models.ManyToManyField("organization.JobTitle", related_name="cpd_requirements")
    credits_per_year = models.DecimalField(max_digits=5, decimal_places=1)

    def __str__(self):
        return self.name


class DevelopmentGoal(TenantModel):
    """Individual development plan item, often from an appraisal's development needs."""

    STATUS = [("planned", "Planned"), ("in_progress", "In progress"), ("achieved", "Achieved"),
              ("dropped", "Dropped")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="development_goals")
    title = models.CharField(max_length=200)
    competency = models.ForeignKey("performance.Competency", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    actions = models.TextField(blank=True, help_text="Training, stretch assignments, coaching...")
    appraisal = models.ForeignKey("performance.Appraisal", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="development_goals")
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="planned")
    progress_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "target_date"]


class Mentorship(TenantModel):
    STATUS = [("active", "Active"), ("completed", "Completed"), ("ended", "Ended early")]
    mentor = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="mentees")
    mentee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="mentors")
    kind = models.CharField(max_length=10, choices=[("mentoring", "Mentoring"), ("coaching", "Coaching")],
                            default="mentoring")
    objectives = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active")

    class Meta:
        ordering = ["-start_date"]


class MentoringSession(TenantModel):
    mentorship = models.ForeignKey(Mentorship, on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField()
    notes = models.TextField()
    next_steps = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-date"]
