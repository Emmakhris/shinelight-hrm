"""Demo data for evaluation and training. NEVER run against production.

Demo logins (all share DEMO_PASSWORD below; MFA disabled for the demo org):
  admin, hrdirector, hrofficer, payroll, approver, manager, employee, auditor,
  recruiter (recruitment officer), itsupport (IT provisioning), newhire (employee in onboarding),
  safety (health & safety officer), ohdoctor (occupational health - the only role that sees clinical notes)
Public career site: /careers/shinelight
Multi-organization demo: platform (platform operator console, no HR data); a second organization
"Accra Family Clinic" at accraclinic.localhost:5173 with administrator clinicadmin. The main demo
organization is at shinelight.localhost:5173 (plain localhost also works).
"""

import datetime as dt
import random
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.context import org_context
from apps.core.setup import setup_organization

DEMO_PASSWORD = "Demo@ShineLight2026"
D = Decimal


class Command(BaseCommand):
    help = "Load demo organization, structure, employees, leave, attendance and payroll data."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Allow running with DEBUG=False")

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("Refusing to seed demo data with DEBUG=False (use --force on a test server only).")
        random.seed(42)
        org, admin = setup_organization("ShineLight Health Services", "shinelight", "admin", DEMO_PASSWORD,
                                        "admin@shinelight.local", ["payroll", "hospital", "sms", "geofence", "ai_assistant"],
                                        require_mfa=False)
        org.address = "12 Independence Avenue\nRidge, Accra\nGA-012-3456"
        org.phone = "0302 123 456"
        org.email = "hr@shinelight.local"
        org.tin = "C0001234567"
        org.ssnit_employer_no = "ER12345678"
        org.settings = {**org.settings, "leave_encashment": True, "session_timeout_minutes": 30,
                        "celebration_notifications": True}
        org.save()
        with org_context(org, admin), transaction.atomic():
            self._seed(org)
        with org_context(org, admin), transaction.atomic():
            self._seed_talent(org, admin)
        with org_context(org, admin), transaction.atomic():
            self._seed_performance(org, admin)
        with org_context(org, admin), transaction.atomic():
            self._seed_learning(org, admin)
        with org_context(org, admin), transaction.atomic():
            self._seed_exits(org, admin)
        with org_context(org, admin), transaction.atomic():
            self._seed_wellbeing(org, admin)
        with org_context(org, admin), transaction.atomic():
            self._seed_planning(org, admin)
        with org_context(org, admin), transaction.atomic():
            self._seed_reports(org, admin)
        if settings.DEPLOYMENT_MODE == "cloud":
            self._seed_platform(org)
        self.stdout.write(self.style.SUCCESS("Demo data loaded. See backend/apps/core/management/commands/"
                                             "seed_demo.py for demo usernames."))

    def _seed(self, org):
        from apps.attendance.models import ClockEvent
        from apps.attendance.services import build_period_summary
        from apps.employees.models import BankAccount, EmergencyContact, Employee, EmployeeCategory
        from apps.employees.services import hire
        from apps.hospital.models import ProfessionalLicense
        from apps.organization.models import (
            Branch,
            CostCenter,
            Department,
            Grade,
            GradeStep,
            JobFamily,
            JobTitle,
            Location,
            Position,
        )
        from apps.payroll.models import EmployeePayElement, EmployeePayProfile, PayElement, PayGroup
        from apps.rbac.models import Role, RoleAssignment

        if Employee.objects.exists():
            self.stdout.write("Demo employees already exist - skipping.")
            return
        User = get_user_model()
        hq = Branch.objects.create(code="HQ", name="Head Office", region="Greater Accra", is_head_office=True)
        kumasi = Branch.objects.create(code="KSI", name="Kumasi Clinic", region="Ashanti")
        loc_hq = Location.objects.create(name="Ridge Campus", branch=hq, gps_address="GA-012-3456",
                                         latitude=D("5.5600"), longitude=D("-0.2000"), geofence_radius_m=300)
        loc_ksi = Location.objects.create(name="Kumasi Adum", branch=kumasi, gps_address="AK-039-5028",
                                          latitude=D("6.6930"), longitude=D("-1.6240"))
        cc = {c: CostCenter.objects.create(code=c, name=n, gl_code=g) for c, n, g in [
            ("CC100", "Administration", "6010"), ("CC200", "Clinical Services", "6020"),
            ("CC300", "Finance", "6030"), ("CC400", "ICT", "6040")]}
        ceo = Department.objects.create(code="EXEC", name="Executive Office", unit_type="directorate", branch=hq,
                                        cost_center=cc["CC100"])
        depts = {
            "HR": Department.objects.create(code="HR", name="Human Resource", parent=ceo, branch=hq,
                                            cost_center=cc["CC100"]),
            "FIN": Department.objects.create(code="FIN", name="Finance", parent=ceo, branch=hq,
                                             cost_center=cc["CC300"]),
            "ICT": Department.objects.create(code="ICT", name="ICT", parent=ceo, branch=hq, cost_center=cc["CC400"]),
            "CLIN": Department.objects.create(code="CLIN", name="Clinical Services", parent=ceo, branch=hq,
                                              unit_type="directorate", cost_center=cc["CC200"]),
        }
        depts["WARD_A"] = Department.objects.create(code="WARD_A", name="Ward A (Medical)", parent=depts["CLIN"],
                                                    unit_type="ward", branch=hq, cost_center=cc["CC200"],
                                                    min_staffing=3)
        depts["LAB"] = Department.objects.create(code="LAB", name="Laboratory", parent=depts["CLIN"], unit_type="unit",
                                                 branch=hq, cost_center=cc["CC200"], min_staffing=1)
        depts["KSI_OPD"] = Department.objects.create(code="KSI_OPD", name="Kumasi OPD", parent=depts["CLIN"],
                                                     unit_type="ward", branch=kumasi, cost_center=cc["CC200"])
        cats = {c: EmployeeCategory.objects.create(code=c, name=n) for c, n in [
            ("management", "Management"), ("senior", "Senior staff"), ("junior", "Junior staff")]}
        grades = {}
        for lvl, (code, name, base) in enumerate([("G1", "Junior I", 1800), ("G2", "Junior II", 2500),
                                                  ("G3", "Senior I", 4200), ("G4", "Senior II", 6500),
                                                  ("G5", "Management", 11000), ("G6", "Executive", 22000)], start=1):
            g = Grade.objects.create(code=code, name=name, level=lvl, min_salary=base, max_salary=int(base * 1.4))
            for step in range(1, 6):
                GradeStep.objects.create(grade=g, step=step, basic_salary=D(base) * (1 + D("0.05") * (step - 1)))
            grades[code] = g
        fam_admin = JobFamily.objects.create(name="Administration & Support")
        fam_clin = JobFamily.objects.create(name="Clinical")
        titles = {
            "ceo": JobTitle.objects.create(name="Chief Executive Officer", family=fam_admin, default_grade=grades["G6"]),
            "hrm": JobTitle.objects.create(name="Human Resource Manager", family=fam_admin, default_grade=grades["G5"]),
            "hro": JobTitle.objects.create(name="HR Officer", family=fam_admin, default_grade=grades["G3"]),
            "fm": JobTitle.objects.create(name="Finance Manager", family=fam_admin, default_grade=grades["G5"]),
            "acc": JobTitle.objects.create(name="Accountant", family=fam_admin, default_grade=grades["G3"]),
            "pay": JobTitle.objects.create(name="Payroll Officer", family=fam_admin, default_grade=grades["G3"]),
            "ict": JobTitle.objects.create(name="ICT Officer", family=fam_admin, default_grade=grades["G3"]),
            "audit": JobTitle.objects.create(name="Internal Auditor", family=fam_admin, default_grade=grades["G4"]),
            "md": JobTitle.objects.create(name="Medical Director", family=fam_clin, default_grade=grades["G6"],
                                          is_clinical=True, required_license_type="Medical Practitioner"),
            "mo": JobTitle.objects.create(name="Medical Officer", family=fam_clin, default_grade=grades["G5"],
                                          is_clinical=True, required_license_type="Medical Practitioner"),
            "ns": JobTitle.objects.create(name="Nursing Officer (Ward In-charge)", family=fam_clin,
                                          default_grade=grades["G4"], is_clinical=True,
                                          required_license_type="Registered General Nurse"),
            "rgn": JobTitle.objects.create(name="Staff Nurse", family=fam_clin, default_grade=grades["G3"],
                                           is_clinical=True, required_license_type="Registered General Nurse"),
            "lab": JobTitle.objects.create(name="Medical Laboratory Scientist", family=fam_clin,
                                           default_grade=grades["G3"], is_clinical=True,
                                           required_license_type="Medical Laboratory Scientist"),
            "porter": JobTitle.objects.create(name="Porter", family=fam_admin, default_grade=grades["G1"]),
        }
        seq = [0]

        def position(title_key, dept, grade, headcount=1, critical=False, branch=hq, loc=loc_hq, etype="permanent"):
            seq[0] += 1
            return Position.objects.create(code=f"P{seq[0]:03d}", job_title=titles[title_key], department=dept,
                                           grade=grade, headcount=headcount, is_critical=critical, branch=branch,
                                           location=loc, employment_type=etype,
                                           budgeted_annual_cost=grade.max_salary * 12 * headcount)

        P = {
            "ceo": position("ceo", ceo, grades["G6"], critical=True),
            "hrm": position("hrm", depts["HR"], grades["G5"], critical=True),
            "hro": position("hro", depts["HR"], grades["G3"], 2),
            "fm": position("fm", depts["FIN"], grades["G5"], critical=True),
            "acc": position("acc", depts["FIN"], grades["G3"], 2),
            "pay": position("pay", depts["FIN"], grades["G3"]),
            "ict": position("ict", depts["ICT"], grades["G3"], 2),
            "audit": position("audit", ceo, grades["G4"]),
            "md": position("md", depts["CLIN"], grades["G6"], critical=True),
            "mo": position("mo", depts["WARD_A"], grades["G5"], 3),
            "ns": position("ns", depts["WARD_A"], grades["G4"], critical=True),
            "rgn": position("rgn", depts["WARD_A"], grades["G3"], 8),
            "lab": position("lab", depts["LAB"], grades["G3"], 3),
            "porter": position("porter", depts["WARD_A"], grades["G1"], 3, etype="contract"),
            "ksi_rgn": position("rgn", depts["KSI_OPD"], grades["G3"], 3, branch=kumasi, loc=loc_ksi),
        }
        first_names_m = ["Kwame", "Kofi", "Yaw", "Kwabena", "Kojo", "Kwaku", "Kwesi", "Emmanuel", "Daniel", "Samuel",
                         "Isaac", "Prince", "Ebenezer"]
        first_names_f = ["Ama", "Akosua", "Abena", "Efua", "Adwoa", "Yaa", "Afua", "Esi", "Gifty", "Mercy", "Grace",
                         "Patience", "Comfort"]
        last_names = ["Mensah", "Owusu", "Boateng", "Asante", "Osei", "Agyeman", "Appiah", "Addo", "Ofori", "Amoah",
                      "Darko", "Tetteh", "Quaye", "Nkrumah", "Sarpong", "Acheampong", "Antwi", "Badu", "Frimpong"]
        today = dt.date.today()
        counter = [0]

        def person(pos_key, supervisor=None, gender=None, step=1, hire_years=None, cat="senior", status=None,
                   etype=None, first=None, last=None):
            counter[0] += 1
            gender = gender or random.choice(["male", "female"])
            fn = first or random.choice(first_names_m if gender == "male" else first_names_f)
            ln = last or random.choice(last_names)
            pos = P[pos_key]
            years = hire_years if hire_years is not None else random.randint(1, 15)
            hire_date = today.replace(day=1) - dt.timedelta(days=int(years * 365.25))
            dob = hire_date - dt.timedelta(days=random.randint(23, 38) * 365)
            data = {
                "title": "mr" if gender == "male" else random.choice(["mrs", "ms"]), "first_name": fn, "last_name": ln,
                "gender": gender, "date_of_birth": dob, "marital_status": random.choice(["single", "married"]),
                "ghana_card_no": f"GHA-{700000000 + counter[0] * 7919:09d}-{counter[0] % 10}",
                "ssnit_number": f"C{100000000000 + counter[0] * 104729:012d}",
                "tin": f"P00{10000000 + counter[0]:08d}", "phone": f"024{1000000 + counter[0] * 37:07d}",
                "work_email": f"{fn.lower()}.{ln.lower()}{counter[0]}@shinelight.local",
                "residential_address": random.choice(["East Legon, Accra", "Dansoman, Accra", "Tema Comm. 25",
                                                      "Adenta, Accra", "Kasoa", "Bantama, Kumasi"]),
                "digital_address": f"GA-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                "hire_date": hire_date, "position": pos, "supervisor": supervisor, "category": cats[cat],
                "grade_step": GradeStep.objects.get(grade=pos.grade, step=step),
            }
            if years < 0.5:
                data["probation_end_date"] = hire_date + dt.timedelta(days=180)
            if etype or pos.employment_type == "contract":
                data["employment_type"] = etype or "contract"
                data["contract_end_date"] = today + dt.timedelta(days=random.choice([20, 45, 120, 300]))
            emp = hire(data, allow_duplicate=True)
            BankAccount.objects.create(employee=emp, payment_method="bank", bank_name=random.choice(
                ["GCB Bank", "Ecobank Ghana", "Fidelity Bank", "Stanbic Bank", "CalBank", "Absa Bank Ghana"]),
                bank_code=f"{random.randint(10, 99)}0", branch_code=f"{random.randint(100000, 999999)}",
                account_name=emp.full_name, account_number=f"{random.randint(10**12, 10**13 - 1)}")
            EmergencyContact.objects.create(employee=emp, name=f"{random.choice(first_names_f)} {ln}",
                                            relationship=random.choice(["Spouse", "Sibling", "Parent"]),
                                            phone=f"020{random.randint(1000000, 9999999)}", is_primary=True)
            return emp

        ceo_e = person("ceo", gender="male", step=3, hire_years=12, cat="management", first="Kwabena", last="Asante")
        hrm = person("hrm", ceo_e, gender="female", step=2, hire_years=8, cat="management", first="Akosua",
                     last="Boateng")
        hro = person("hro", hrm, gender="male", hire_years=4, first="Kofi", last="Mensah")
        hro2 = person("hro", hrm, gender="female", hire_years=0.3, first="Efua", last="Quaye")
        fm = person("fm", ceo_e, gender="male", step=2, hire_years=9, cat="management", first="Samuel", last="Osei")
        pay = person("pay", fm, gender="female", hire_years=5, first="Abena", last="Owusu")
        acc = [person("acc", fm) for _ in range(2)]
        ict = [person("ict", ceo_e) for _ in range(2)]
        aud = person("audit", ceo_e, gender="male", hire_years=6, first="Daniel", last="Addo")
        md = person("md", ceo_e, gender="male", step=2, hire_years=10, cat="management", first="Emmanuel",
                    last="Agyeman")
        ns = person("ns", md, gender="female", step=3, hire_years=11, first="Grace", last="Tetteh")
        mos = [person("mo", md) for _ in range(2)]
        nurses = [person("rgn", ns, gender=random.choice(["female", "female", "male"]), step=random.randint(1, 4))
                  for _ in range(6)]
        nurses.append(person("rgn", ns, gender="female", hire_years=0.2, first="Ama", last="Darko"))
        labs = [person("lab", md) for _ in range(2)]
        porters = [person("porter", ns, cat="junior", hire_years=2) for _ in range(2)]
        ksi = [person("ksi_rgn", ns, gender="female") for _ in range(2)]
        depts["HR"].head = hrm
        depts["FIN"].head = fm
        depts["CLIN"].head = md
        depts["WARD_A"].head = ns
        ceo.head = ceo_e
        for d in list(depts.values()) + [ceo]:
            d.save()

        # user accounts
        def account(username, emp, roles):
            user = User.objects.create_user(username, emp.work_email, DEMO_PASSWORD, organization=org,
                                            first_name=emp.first_name, last_name=emp.last_name, phone=emp.phone)
            emp.user = user
            emp.save(update_fields=["user"])
            for rc in roles:
                RoleAssignment.objects.create(user=user, role=Role.objects.get(code=rc))
            return user

        account("hrdirector", hrm, ["employee", "hr_director", "line_manager"])
        account("hrofficer", hro, ["employee", "hr_officer"])
        account("payroll", pay, ["employee", "payroll_officer"])
        account("approver", fm, ["employee", "payroll_approver", "line_manager", "finance_officer"])
        account("manager", ns, ["employee", "line_manager", "dept_head"])
        account("employee", nurses[0], ["employee"])
        account("auditor", aud, ["employee", "internal_auditor"])
        account("ceo", ceo_e, ["employee", "line_manager", "dept_head"])
        account("medical", md, ["employee", "line_manager", "dept_head"])
        for e in [hro2, *acc, *ict, *mos, *nurses[1:], *labs, *porters, *ksi]:
            account(e.work_email.split("@")[0].replace(".", "")[:30], e, ["employee"])

        # payroll setup
        group = PayGroup.objects.get(code="monthly")
        transport = PayElement.objects.get(code="TRANSPORT")
        housing = PayElement.objects.get(code="HOUSING")
        resp = PayElement.objects.get(code="RESPONSIBILITY")
        night = PayElement.objects.get(code="NIGHT")
        welfare = PayElement.objects.get(code="WELFARE")
        union = PayElement.objects.get(code="UNION")
        welfare.applies_to_all = True
        welfare.default_amount = D("20")
        welfare.save()
        start = today.replace(month=1, day=1)
        for emp in Employee.objects.all():
            EmployeePayProfile.objects.create(employee=emp, pay_group=group,
                                              tier3_employee_percent=D("5") if emp.grade.level >= 4 else D("0"),
                                              tier3_employer_percent=D("5") if emp.grade.level >= 4 else D("0"))
            EmployeePayElement.objects.create(employee=emp, element=transport, start_date=start,
                                              amount=D("300") if emp.grade.level < 4 else D("800"))
            if emp.grade.level >= 4:
                EmployeePayElement.objects.create(employee=emp, element=housing, start_date=start, percent=D("15"))
                EmployeePayElement.objects.create(employee=emp, element=resp, start_date=start, amount=D("500"))
            if emp.job_title.is_clinical:
                EmployeePayElement.objects.create(employee=emp, element=night, start_date=start, amount=D("240"),
                                                  note="4 night duties x GHS 60")
            if emp.grade.level <= 3:
                EmployeePayElement.objects.create(employee=emp, element=union, start_date=start)
        night.calculation = "fixed"
        night.save()

        # professional licences
        for emp in Employee.objects.filter(job_title__is_clinical=True):
            lic_type = emp.job_title.required_license_type
            reg = "mdc" if "Medical Practitioner" in lic_type else "nmc" if "Nurse" in lic_type else "ahpc"
            exp = today + dt.timedelta(days=random.choice([25, 90, 200, 365]))
            ProfessionalLicense.objects.create(employee=emp, license_type=lic_type, regulator=reg,
                                               registration_number=f"{reg.upper()}/{random.randint(10000, 99999)}",
                                               issue_date=exp - dt.timedelta(days=730), expiry_date=exp,
                                               status="active", verified_at=timezone.now())

        # attendance for the last 10 working days
        tz = timezone.get_current_timezone()
        d = today - dt.timedelta(days=14)
        while d < today:
            if d.weekday() < 5:
                for emp in Employee.objects.all():
                    r = random.random()
                    if r < 0.05:
                        continue  # absent
                    t_in = dt.datetime.combine(d, dt.time(7, 45)) + dt.timedelta(minutes=random.randint(0, 50))
                    ClockEvent.objects.create(employee=emp, timestamp=timezone.make_aware(t_in, tz), direction="in",
                                              source="biometric")
                    if r < 0.08:
                        continue  # missing clock-out
                    t_out = dt.datetime.combine(d, dt.time(17, 0)) + dt.timedelta(minutes=random.randint(-20, 150))
                    ClockEvent.objects.create(employee=emp, timestamp=timezone.make_aware(t_out, tz),
                                              direction="out", source="biometric")
            d += dt.timedelta(days=1)
        build_period_summary(today - dt.timedelta(days=14), today - dt.timedelta(days=1))
        self.stdout.write(f"Created {Employee.objects.count()} employees.")


    def _seed_talent(self, org, admin):
        """Recruitment pipeline, a new hire in onboarding and probation reviews (Phase 3). Idempotent."""
        from django.core.files.base import ContentFile

        from apps.core.pdf import html_to_pdf
        from apps.employees.models import Employee
        from apps.employees.services import hire
        from apps.onboarding import services as onboarding
        from apps.onboarding.models import ProbationReview
        from apps.organization.models import Department, GradeStep, Position
        from apps.rbac.models import Role, RoleAssignment
        from apps.recruitment import services as rec
        from apps.recruitment.models import Interview, ReferenceCheck, Requisition, Scorecard, Vacancy

        User = get_user_model()
        if Vacancy.objects.exists() or not Employee.objects.exists():
            return
        today = dt.date.today()

        def user(username, first, last, roles, employee=None):
            u = User.objects.filter(username=username).first() or User.objects.create_user(
                username, f"{username}@shinelight.local", DEMO_PASSWORD, organization=org, first_name=first,
                last_name=last)
            for rc in roles:
                RoleAssignment.objects.get_or_create(user=u, role=Role.objects.get(code=rc))
            if employee is not None:
                employee.user = u
                employee.save(update_fields=["user"])
            return u

        recruiter = user("recruiter", "Yaa", "Frimpong", ["recruitment_officer"])
        user("itsupport", "Prince", "Badu", ["it_support"])
        mgr = User.objects.get(username="manager")
        hro = User.objects.get(username="hrofficer")
        ward = Department.objects.get(code="WARD_A")
        rgn = Position.objects.filter(department=ward, job_title__name="Staff Nurse").first()

        # approved requisition -> published vacancy with applicants
        req = Requisition.objects.create(
            job_title=rgn.job_title, department=ward, position=rgn, grade=rgn.grade, headcount=1, reason="expansion",
            justification="Bed capacity on Ward A increased from 24 to 30; nurse-to-patient ratio above standard.",
            salary_min=D("4200"), salary_max=D("5200"), target_start_date=today + dt.timedelta(days=45),
            requested_by=mgr.employee, created_by=mgr, status="approved", reference="REQ-DEMO-0001",
            submitted_at=timezone.now() - dt.timedelta(days=12), approved_at=timezone.now() - dt.timedelta(days=9))
        vac = rec.vacancy_from_requisition(req, recruiter)
        vac.summary = ("ShineLight Health Services is recruiting a Staff Nurse (Registered General Nurse) for its 30-bed medical "
                       "ward at Ridge, Accra.")
        vac.responsibilities = ("- Deliver safe, evidence-based nursing care\n- Administer medication and monitor "
                                "patients\n- Maintain accurate nursing records\n- Work rotating shifts including nights")
        vac.requirements = "- Diploma or degree in Nursing\n- Valid NMC licence (PIN)\n- At least 2 years' ward experience"
        vac.min_qualification, vac.min_experience_years = "diploma", 2
        vac.salary_display = "Competitive, plus night and transport allowances"
        vac.closing_date = today + dt.timedelta(days=21)
        vac.advertising_cost = D("1800")
        vac.channels = ["career_site", "Daily Graphic", "LinkedIn"]
        vac.screening_questions = [
            {"key": "nmc_pin", "question": "Do you hold a valid NMC licence (PIN)?", "type": "yes_no", "knockout": "no"},
            {"key": "nights", "question": "Are you able to work night shifts?", "type": "yes_no", "knockout": "no"}]
        vac.save()
        rec.publish_vacancy(vac, recruiter)
        vac.published_at = timezone.now() - dt.timedelta(days=8)
        vac.save(update_fields=["published_at"])
        cv = html_to_pdf("<h2>Curriculum vitae</h2><p>Demo candidate CV.</p>")
        people = [("Abena", "Ofori", "degree", 5, "yes", "yes", "career_site"),
                  ("Mercy", "Acheampong", "diploma", 3, "yes", "yes", "career_site"),
                  ("Isaac", "Sarpong", "diploma", 2, "yes", "yes", "referral"),
                  ("Gifty", "Antwi", "degree", 1, "yes", "no", "job_board"),
                  ("Comfort", "Nkrumah", "certificate", 4, "no", "yes", "career_site"),
                  ("Prince", "Appiah", "degree", 6, "yes", "yes", "agency")]
        apps = []
        for i, (fn, ln, qual, yrs, pin, nights, src) in enumerate(people):
            a = rec.apply(vac, {"first_name": fn, "last_name": ln, "email": f"{fn.lower()}.{ln.lower()}@example.com",
                                "phone": f"0244{100000 + i * 1111:06d}", "highest_qualification": qual,
                                "years_experience": yrs, "gender": "male" if fn in ("Isaac", "Prince") else "female",
                                "current_employer": random.choice(["Korle Bu Teaching Hospital", "37 Military Hospital",
                                                                   "Ridge Hospital", "Nyaho Clinic"]),
                                "current_title": "Staff Nurse"},
                          cv=ContentFile(cv, name=f"cv-{ln.lower()}.pdf"), answers={"nmc_pin": pin, "nights": nights},
                          source=src, consent=True, talent_pool=i % 2 == 0, actor=recruiter)
            apps.append(a)
        abena, mercy, isaac, gifty, comfort, prince = apps
        rec.move_stage(comfort, "rejected", recruiter, reason="No valid NMC licence", notify_candidate=False)
        for a in (abena, mercy, isaac, prince):
            rec.move_stage(a, "shortlisted", recruiter, notify_candidate=False)
        # Abena: interviewed, scored, checked; offer awaiting HR Director approval
        iv = Interview.objects.create(application=abena, round_name="Panel interview", mode="in_person",
                                      venue="Board room, Ridge campus",
                                      scheduled_at=timezone.now() - dt.timedelta(days=2), status="completed")
        iv.panel.set([mgr, hro])
        crit = vac.criteria
        for u, base in ((mgr, 5), (hro, 4)):
            ratings = {c["name"]: base if j % 2 == 0 else 4 for j, c in enumerate(crit)}
            Scorecard.objects.create(interview=iv, panelist=u, ratings=ratings,
                                     recommendation="strong_yes" if base == 5 else "yes",
                                     overall_score=rec.weighted_score(crit, ratings),
                                     strengths="Calm under pressure; strong medication-safety knowledge.")
        rec._advance_to(abena, "interview", recruiter)
        for t, name in (("reference", "Matron, Korle Bu"), ("professional", "NMC Ghana")):
            chk = ReferenceCheck.objects.create(application=abena, check_type=t, referee_name=name,
                                                consent_obtained=True)
            rec.update_check(chk, recruiter, "verified", "Confirmed by phone; no concerns.")
        step2 = GradeStep.objects.get(grade=rgn.grade, step=2)
        offer = rec.create_offer(abena, {"job_title": rgn.job_title, "department": ward, "grade_step": step2,
                                         "basic_salary": step2.basic_salary,
                                         "allowances": [{"name": "Transport", "amount": 300}],
                                         "start_date": today + dt.timedelta(days=30), "probation_months": 6,
                                         "expiry_date": today + dt.timedelta(days=10)}, recruiter)
        rec.submit_offer(offer, recruiter)
        # Mercy: interview tomorrow
        tomorrow = timezone.make_aware(dt.datetime.combine(today + dt.timedelta(days=1), dt.time(10, 0)))
        rec.schedule_interview(mercy, {"round_name": "Panel interview", "scheduled_at": tomorrow, "mode": "in_person",
                                       "venue": "Board room, Ridge campus"}, [mgr, hro], recruiter, notify=False)
        # a pending requisition in the approval inbox
        porter = Position.objects.filter(job_title__name="Porter").first()
        req2 = Requisition.objects.create(
            job_title=porter.job_title, department=porter.department, position=porter, grade=porter.grade,
            employment_type="contract", headcount=1, reason="expansion", created_by=mgr, requested_by=mgr.employee,
            justification="Extra porter needed for the new night shift on Ward A.", salary_max=D("2200"))
        rec.submit_requisition(req2, mgr)

        # a new hire who started 3 days ago: onboarding and probation reviews start automatically
        lab = Position.objects.filter(job_title__name="Medical Laboratory Scientist").first()
        md = Employee.objects.get(user__username="medical")
        start = today - dt.timedelta(days=3)
        emp = hire({"title": "mr", "first_name": "Kwesi", "last_name": "Antwi", "gender": "male",
                    "date_of_birth": dt.date(1997, 4, 12), "hire_date": start, "position": lab, "supervisor": md,
                    "grade_step": GradeStep.objects.get(grade=lab.grade, step=1), "phone": "0244998877",
                    "work_email": "kwesi.antwi@shinelight.local", "probation_end_date": start + dt.timedelta(days=182),
                    "ghana_card_no": "GHA-799999999-1"}, allow_duplicate=True)
        user("newhire", "Kwesi", "Antwi", ["employee"], employee=emp)
        from apps.payroll.models import EmployeePayProfile, PayGroup

        EmployeePayProfile.objects.create(employee=emp, pay_group=PayGroup.objects.get(code="monthly"))
        ob = emp.onboardings.first()
        if ob:
            for t in ob.tasks.filter(due_date__lt=start, owner_type__in=["hr", "it", "finance"])[:6]:
                t.status, t.completed_by, t.completed_at = "done", hro, timezone.now() - dt.timedelta(days=4)
                t.save()
        # probation reviews for staff already on probation
        for e in Employee.objects.filter(status="probation", probation_end_date__isnull=False):
            if not ProbationReview.objects.filter(employee=e).exists():
                onboarding.schedule_probation_reviews(e)
        self.stdout.write(f"Recruitment demo: {vac.reference} with {len(apps)} applicants; career site "
                          f"/careers/{org.code}. New hire {emp.staff_number} in onboarding.")


    def _seed_performance(self, org, admin):
        """Last year's closed appraisal cycle and this year's cycle in year-end review (Phase 3). Idempotent."""
        from apps.employees.models import Employee, EmployeeCategory
        from apps.performance import services as perf
        from apps.performance.models import (Appraisal, AppraisalTemplate, Competency, FeedbackRequest, Goal,
                                             ImprovementPlan, Objective, PlanMilestone, ReviewCycle)
        from apps.organization.models import Department

        if ReviewCycle.objects.exists() or not Employee.objects.exists():
            return
        User = get_user_model()
        today = dt.date.today()
        year = today.year
        hrd = User.objects.get(username="hrdirector")
        mgmt = EmployeeCategory.objects.filter(code="management").first()
        if mgmt:
            tpl, created = AppraisalTemplate.objects.get_or_create(name="Management appraisal", defaults={
                "rating_scale": perf.default_scale(), "objectives_weight": 60, "category": mgmt, "include_360": True})
            if created:
                tpl.competencies.set(list(Competency.objects.filter(category__in=["core", "leadership"])))
        dist = {"5": 10, "4": 25, "3": 45, "2": 15, "1": 5}
        ward = Department.objects.get(code="WARD_A")
        objectives_by_family = {
            True: [("Deliver safe patient care with zero medication errors", "Incident reports", "0 errors"),
                   ("Complete nursing documentation for every shift", "Audit of 20 charts / quarter", "95%"),
                   ("Complete 20 CPD credit hours", "NMC CPD record", "20 hours")],
            False: [("Deliver core duties on schedule", "Deadlines met", "95%"),
                    ("Improve a key process in the unit", "Process change implemented", "1 improvement"),
                    ("Complete agreed training", "Training records", "2 courses")],
        }

        def setup_objectives(ap, goal=None):
            rows = objectives_by_family[bool(ap.employee.job_title and ap.employee.job_title.is_clinical)]
            for (title, measure, target), w in zip(rows, (40, 30, 30), strict=True):
                Objective.objects.create(appraisal=ap, title=title, measure=measure, target=target, weight=D(w),
                                         goal=goal if w == 40 else None)

        def rate_all(ap, field, base):
            for o in ap.objectives.all():
                setattr(o, field, max(1, min(5, base + random.choice([-1, 0, 0, 1]))))
                o.achievement = o.achievement or "Achieved as agreed; evidence in the unit records."
                o.save()
            for c in ap.competency_ratings.all():
                setattr(c, field, max(1, min(5, base + random.choice([-1, 0, 0, 1]))))
                c.save()

        # last year: closed, with calibrated final ratings (drives merit guidelines and history)
        last = ReviewCycle.objects.create(name=f"Annual appraisal {year - 1}", period_start=dt.date(year - 1, 1, 1),
                                          period_end=dt.date(year - 1, 12, 31), target_distribution=dist)
        perf.launch_cycle(last, hrd)
        for ap in last.appraisals.select_related("employee__job_title"):
            setup_objectives(ap)
            base = random.choice([2, 3, 3, 3, 4, 4, 5])
            rate_all(ap, "self_rating", base)
            rate_all(ap, "manager_rating", base)
            ap.objectives_score, ap.competencies_score, ap.overall_score = perf._scores(ap)
            ap.manager_rating = ap.final_rating = perf.rating_from_score(perf.scale_of(ap), ap.overall_score)
            ap.manager_comments = "Solid year." if ap.final_rating >= 3 else "Below expectations on key objectives."
            ap.development_needs = "Continue CPD; leadership short course." if ap.final_rating >= 3 else \
                "Coaching on prioritisation; refresher training."
            ap.status, ap.employee_agrees = "completed", True
            ap.acknowledged_at = ap.completed_at = timezone.now() - dt.timedelta(days=200)
            ap.save()
        last.status, last.closed_at = "closed", timezone.now() - dt.timedelta(days=210)
        last.save()

        # this year: in year-end review
        cur = ReviewCycle.objects.create(
            name=f"Annual appraisal {year}", period_start=dt.date(year, 1, 1), period_end=dt.date(year, 12, 31),
            goal_setting_deadline=dt.date(year, 2, 28), midyear_date=dt.date(year, 7, 31),
            self_review_deadline=today + dt.timedelta(days=14), manager_review_deadline=today + dt.timedelta(days=28),
            target_distribution=dist)
        g_org = Goal.objects.create(cycle=cur, title="Improve patient satisfaction to 85%",
                                    measure="Quarterly patient survey", target="85%")
        g_ward = Goal.objects.create(cycle=cur, parent=g_org, department=ward,
                                     title="Zero avoidable medication errors on Ward A", measure="Incident log",
                                     target="0")
        Goal.objects.create(cycle=cur, title="Keep staff costs within the approved budget", measure="Payroll vs budget",
                            target="≤ 100%")
        perf.launch_cycle(cur, hrd)
        for ap in cur.appraisals.select_related("employee__department", "employee__job_title"):
            setup_objectives(ap, g_ward if ap.employee.department_id == ward.id else g_org)
            ap.status = "objectives_agreed"
            ap.midyear_comments = "Mid-year discussion held; on track overall."
            ap.midyear_done_at = timezone.make_aware(dt.datetime(year, 7, 20, 10))
            ap.save()
            for o in ap.objectives.all():
                o.midyear_status = random.choice(["on_track", "on_track", "at_risk"])
                o.save(update_fields=["midyear_status"])
        cur.status = "in_progress"
        cur.save()
        perf.advance_cycle(cur, hrd)  # -> year-end review: everyone in self-assessment
        # the ward manager's nurses (except the demo employee) have submitted self-assessments
        demo_emp = User.objects.get(username="employee").employee
        mgr = User.objects.get(username="manager")
        for ap in cur.appraisals.filter(reviewer=mgr).exclude(employee=demo_emp)[:4]:
            rate_all(ap, "self_rating", 4)
            ap.self_comments = "Busy year on the ward; completed my CPD."
            ap.status, ap.self_submitted_at = "manager_review", timezone.now() - dt.timedelta(days=2)
            ap.save()
        # 360 for a manager: the demo employee has a pending request
        hrd_ap = cur.appraisals.filter(employee=hrd.employee).first()
        if hrd_ap and hrd_ap.template.include_360:
            for u in User.objects.filter(username__in=["employee", "hrofficer", "payroll", "approver"]):
                FeedbackRequest.objects.create(appraisal=hrd_ap, respondent=u, relationship="peer")
        # an improvement plan in draft for last year's lowest-rated nurse under the ward manager
        low = last.appraisals.filter(reviewer=mgr, final_rating__lte=2).first()
        if low:
            plan = ImprovementPlan.objects.create(
                employee=low.employee, appraisal=low, supervisor=mgr, start_date=today,
                end_date=today + dt.timedelta(days=60), reason="Late completion of nursing documentation.",
                support="Weekly coaching with the ward in-charge; documentation refresher course.", status="draft")
            PlanMilestone.objects.create(plan=plan, objective="Complete shift documentation before handover",
                                         measure="Chart audit", due_date=today + dt.timedelta(days=30))
        self.stdout.write(f"Performance demo: {last.name} (closed) and {cur.name} "
                          f"({Appraisal.objects.filter(cycle=cur).count()} appraisals in year-end review).")


    def _seed_learning(self, org, admin):
        """Training sessions, mandatory compliance mix, budgets, CPD, development and mentoring (Phase 3). Idempotent."""
        from apps.employees.models import Employee
        from apps.hospital.models import CompetencyRequirement
        from apps.learning import services as lms
        from apps.learning.models import (CPDRecord, CPDRequirement, Course, DevelopmentGoal, Enrollment, Mentorship,
                                          MentoringSession, Session, TrainingBudget)
        from apps.organization.models import Department, JobTitle
        from apps.performance.models import Appraisal

        if Session.objects.exists() or not Employee.objects.exists() or not Course.objects.exists():
            return
        User = get_user_model()
        today = dt.date.today()
        now = timezone.now()
        clinical = list(JobTitle.objects.filter(is_clinical=True))
        nurse_titles = [j for j in clinical if "Nurs" in j.name]
        ipc, bls = Course.objects.get(code="CL-301"), Course.objects.get(code="CL-302")
        ipc.job_titles.set(clinical)
        bls.job_titles.set(clinical)
        req = CompetencyRequirement.objects.filter(name__icontains="life support").first()
        if req:
            bls.competency_requirement = req
            bls.save(update_fields=["competency_requirement"])
        excel = Course.objects.get(code="TS-501")
        for code, amount in (("WARD_A", "15000"), ("HR", "8000"), ("FIN", "6000"), ("LAB", "5000")):
            dep = Department.objects.filter(code=code).first()
            if dep:
                TrainingBudget.objects.get_or_create(department=dep, year=today.year, defaults={"amount": D(amount)})
        req_cpd = CPDRequirement.objects.create(name="Nursing council licence renewal", credits_per_year=D("20"))
        req_cpd.job_titles.set(nurse_titles)

        lms.assign_mandatory()
        # history: fire safety done by most staff (some long ago, so refreshers fall due); data protection by some
        fire, dp = Course.objects.get(code="HS-101"), Course.objects.get(code="CP-201")
        for i, e in enumerate(Enrollment.objects.filter(course=fire, status="enrolled").select_related("employee")):
            if i % 5 == 4:
                continue
            ago = 340 if i % 4 == 0 else random.randint(20, 200)
            e.modules_done = list(fire.modules.values_list("pk", flat=True))
            e.save(update_fields=["modules_done"])
            lms.complete(e, today - dt.timedelta(days=ago), score=random.choice([80, 90, 100]))
        for i, e in enumerate(Enrollment.objects.filter(course=dp, status="enrolled")):
            if i % 2 == 0:
                lms.complete(e, today - dt.timedelta(days=random.randint(30, 300)), score=100)
        # an infection-control session last week with attendance recorded
        past = Session.objects.create(course=ipc, start=now - dt.timedelta(days=6, hours=3),
                                      end=now - dt.timedelta(days=6), venue="Training room 2", trainer="IPC focal person",
                                      capacity=15, actual_cost=D("1200"))
        attendees = list(Enrollment.objects.filter(course=ipc, status="enrolled")[:8])
        Enrollment.objects.filter(pk__in=[e.pk for e in attendees]).update(session=past)
        rows = [{"enrollment": e.pk, "attended": j != 7, "score": None} for j, e in enumerate(attendees)]
        trainer = User.objects.get(username="hrdirector")
        lms.record_attendance(past, trainer, rows)
        for e in Enrollment.objects.filter(session=past, status="completed")[:5]:
            e.feedback_rating, e.feedback_comments = random.choice([4, 5, 5]), "Practical and relevant."
            e.save(update_fields=["feedback_rating", "feedback_comments"])
        # upcoming sessions
        nxt = Session.objects.create(course=bls, start=now + dt.timedelta(days=8), end=now + dt.timedelta(days=8, hours=6),
                                     venue="Skills lab", trainer="Resuscitation council instructor", capacity=12,
                                     registration_deadline=today + dt.timedelta(days=6))
        for e in Enrollment.objects.filter(course=bls, status="enrolled")[:6]:
            e.session = nxt
            e.save(update_fields=["session"])
        Session.objects.create(course=excel, start=now + dt.timedelta(days=15), end=now + dt.timedelta(days=15, hours=6),
                               venue="ICT lab", trainer="ICT unit", capacity=10)
        Session.objects.create(course=ipc, start=now + dt.timedelta(days=20), end=now + dt.timedelta(days=20, hours=3),
                               venue="Training room 2", trainer="IPC focal person", capacity=15)
        # a pending paid request: the ward manager asks for the supervisor programme (approved by the Medical Director)
        mgr = User.objects.get(username="manager")
        lms.request_training(mgr.employee, Course.objects.get(code="LD-401"), mgr,
                             reason="Newly responsible for 12 staff; need supervision and feedback skills.")
        # CPD records for nurses
        for emp in Employee.objects.filter(job_title__in=nurse_titles)[:8]:
            CPDRecord.objects.create(employee=emp, title="Ghana Nurses conference", provider="GRNMA",
                                     activity_date=today - dt.timedelta(days=random.randint(20, 200)),
                                     credits=D(random.choice(["4", "6", "8"])), category="Conference",
                                     status=random.choice(["verified", "verified", "pending"]))
        # development goals from last year's low competency ratings
        for ap in Appraisal.objects.filter(status="completed", competency_ratings__manager_rating__lte=2).distinct()[:6]:
            for cr in ap.competency_ratings.filter(manager_rating__lte=2).select_related("competency")[:1]:
                DevelopmentGoal.objects.get_or_create(employee=ap.employee, appraisal=ap, competency=cr.competency,
                                                      defaults={"title": f"Develop: {cr.competency.name}",
                                                                "actions": ap.development_needs,
                                                                "target_date": today + dt.timedelta(days=120),
                                                                "status": "in_progress"})
        # mentoring: the senior HR officer mentors the new HR officer
        hro = User.objects.get(username="hrofficer").employee
        newer = Employee.objects.filter(job_title=hro.job_title).exclude(pk=hro.pk).first()
        if newer:
            m = Mentorship.objects.create(mentor=hro, mentee=newer, objectives="Learn employee relations casework "
                                          "and payroll inputs.", start_date=today - dt.timedelta(days=60))
            MentoringSession.objects.create(mentorship=m, date=today - dt.timedelta(days=14),
                                            notes="Walked through a disciplinary case file.",
                                            next_steps="Shadow the next hearing.")
        self.stdout.write(f"Learning demo: {Enrollment.objects.count()} enrolments, compliance "
                          f"{lms.compliance_matrix()['compliance_percent']}%.")


    def _seed_exits(self, org, admin):
        """Employee relations cases, assets and exits (Phase 3). Idempotent."""
        from apps.assets import services as assets
        from apps.assets.models import Asset, AssetCategory
        from apps.employees.models import Employee
        from apps.offboarding import services as offb
        from apps.offboarding.models import ExitInterview, Separation
        from apps.relations import services as er
        from apps.relations.models import Case
        from apps.workflow import engine
        from apps.workflow.models import WorkflowTask

        if Case.objects.exists() or Asset.objects.exists() or not Employee.objects.exists():
            return
        User = get_user_model()
        today = dt.date.today()
        now = timezone.now()
        hro, hrd = User.objects.get(username="hrofficer"), User.objects.get(username="hrdirector")
        it = User.objects.filter(username="itsupport").first() or hrd
        nurses = list(Employee.objects.filter(job_title__name="Staff Nurse", status__in=["active", "probation"])
                      .exclude(user__username="employee"))
        demo = User.objects.get(username="employee").employee

        def approve(rtype):
            while (t := WorkflowTask.objects.filter(status="pending", instance__request_type=rtype).first()):
                engine.act(t, t.assignee, "approve", "OK")

        # ---- assets: laptops for office staff, access cards for everyone, scrubs for nurses
        cats = {c.code: c for c in AssetCategory.objects.all()}
        office = list(Employee.objects.filter(job_title__is_clinical=False, status__in=["active", "probation"])
                      .exclude(job_title__name="Porter"))
        for i, emp in enumerate(office):
            a = Asset.objects.create(tag=f"IT-{i + 1:04d}", category=cats["laptop"], description=random.choice(
                ["Dell Latitude 5440", "HP EliteBook 840", "Lenovo ThinkPad E14"]), serial_number=f"SN{730000 + i * 17}",
                replacement_value=D("7500"), purchase_date=today - dt.timedelta(days=random.randint(100, 900)))
            asg = assets.issue(it, emp, asset=a)
            if i % 3:
                assets.acknowledge(asg, emp.user) if emp.user_id else None
        for i in range(4):
            Asset.objects.create(tag=f"IT-{len(office) + i + 1:04d}", category=cats["laptop"], description="Dell Latitude 5440",
                                 serial_number=f"SN{740000 + i}", replacement_value=D("7500"))
        for i, emp in enumerate(Employee.objects.filter(status__in=["active", "probation"])):
            card = Asset.objects.create(tag=f"AC-{i + 1:04d}", category=cats["access_card"], description="Staff ID / access card",
                                        replacement_value=D("50"))
            assets.issue(hro, emp, asset=card)
        for emp in nurses[:6]:
            assets.issue(hro, emp, category=cats["uniform"], item="Scrubs (blue)", quantity=3)
        if nurses:
            lost = assets.issue(hro, nurses[0], category=cats["ppe"], item="Safety goggles")
            lost.notes = "Consumable PPE"
            lost.save(update_fields=["notes"])

        # ---- employee relations
        g = er.open_case(demo.user, {"case_type": "grievance", "title": "Unfair night-shift allocation",
                                     "description": "I have been rostered for nights for six consecutive weeks while "
                                                    "colleagues rotate monthly.", "severity": "medium"})
        er.assign(g, hrd, investigators=[hro], plan="Review 3 months of rosters; interview ward in-charge.")
        if len(nurses) >= 3:
            m = er.open_case(hro, {"case_type": "misconduct", "title": "Repeated lateness and absence from post",
                                   "description": "Late 9 times in October; left the ward unattended on 14/10.",
                                   "severity": "high", "policy_reference": "Code of conduct s.4.2"},
                             respondents=[nurses[1]])
            er.add_note(m, hro, "finding", "Clock records confirm 9 late arrivals; two witness statements obtained.")
            meet = er.schedule_meeting(m, hro, {"kind": "hearing", "scheduled_at": now + dt.timedelta(days=2),
                                                "venue": "HR meeting room", "attendees": "HR Officer, Nursing Officer"},
                                       [nurses[1]])
            meet.save()
            closed = er.open_case(hro, {"case_type": "policy_violation", "title": "Sharing of patient photos",
                                        "description": "Posted a patient photo in a WhatsApp group.",
                                        "severity": "high"}, respondents=[nurses[2]])
            h = er.schedule_meeting(closed, hro, {"kind": "hearing", "scheduled_at": now - dt.timedelta(days=20)},
                                    [nurses[2]])
            er.record_minutes(h, hro, "Employee admitted posting; removed it immediately; first offence.")
            er.decide(closed, hro, "written_warning", "Breach of patient confidentiality (Act 843); first offence.",
                      [{"employee": nurses[2], "action_type": "written_warning",
                        "details": "Breach of patient confidentiality by sharing a patient photograph."}])
            er.close(closed, hro, "Warning issued; data protection refresher assigned.")
        er.open_case(hro, {"case_type": "conflict", "title": "Dispute between lab staff over workload",
                           "description": "Recurring arguments about weekend cover.", "severity": "low"})

        # ---- exits: one completed last month, one in clearance, one awaiting approval
        accts = list(Employee.objects.filter(job_title__name="Accountant", status="active"))
        ksi = list(Employee.objects.filter(department__code="KSI_OPD", status="active"))
        if ksi:
            leaver = ksi[0]
            sep = Separation.objects.create(
                employee=leaver, exit_type="resignation", reason="travel", details="Relocating to the UK.",
                notice_date=today - dt.timedelta(days=60), last_working_day=today - dt.timedelta(days=30),
                notice_required_days=30, status="pending", submitted_by=hro, reference="EX-DEMO-0001")
            offb.approve(sep, hro)
            for a in assets.outstanding(leaver):
                assets.receive(a, hro, "good")
            ei = ExitInterview.objects.get(separation=sep)
            ei.ratings = {"Pay and benefits": 2, "Relationship with supervisor": 4, "Career growth and training": 3,
                          "Workload": 2, "Working conditions": 3, "Recognition": 2, "Team and colleagues": 5}
            ei.primary_reason, ei.would_recommend, ei.would_return = "travel", True, True
            ei.what_to_improve, ei.completed_at = "Night-shift allowance and staffing levels.", now - dt.timedelta(days=35)
            ei.save()
            for item in sep.clearance.all():
                item.status, item.cleared_by, item.cleared_at = "cleared", hro, now - dt.timedelta(days=28)
                item.save()
            offb.complete(sep, hro)
        if accts:
            sep2 = offb.initiate(accts[0].user or hro, accts[0], {
                "exit_type": "resignation", "reason": "better_pay", "details": "I have accepted an offer elsewhere.",
                "notice_date": today - dt.timedelta(days=10), "last_working_day": today + dt.timedelta(days=12)})
            approve("separation")
            sep2.refresh_from_db()
            for item in sep2.clearance.filter(owner__in=["supervisor", "finance"]):
                offb.clear(item, hrd, "Handover plan agreed" if item.owner == "supervisor" else "No balances")
        if len(accts) > 1 and accts[1].user_id:
            offb.initiate(accts[1].user, accts[1], {
                "exit_type": "resignation", "reason": "studies", "details": "Leaving for a master's programme.",
                "last_working_day": today + dt.timedelta(days=35)})
        self.stdout.write(f"Exits demo: {Case.objects.count()} ER cases, {Asset.objects.count()} assets, "
                          f"{Separation.objects.count()} exits.")


    def _seed_wellbeing(self, org, admin):
        """Engagement surveys, recognition, suggestions, events and health & safety (Phase 3). Idempotent."""
        from apps.employees.models import Employee
        from apps.engagement import services as eng
        from apps.engagement.models import ActionPlan, Event, Survey
        from apps.organization.models import Department
        from apps.rbac.models import Role, RoleAssignment
        from apps.safety import services as ohs
        from apps.safety.models import Inspection, RiskAssessment

        if Survey.objects.exists() or not Employee.objects.exists():
            return
        User = get_user_model()
        today = dt.date.today()
        now = timezone.now()
        hrd, hro = User.objects.get(username="hrdirector"), User.objects.get(username="hrofficer")

        def user(username, first, last, roles):
            u = User.objects.filter(username=username).first() or User.objects.create_user(
                username, f"{username}@shinelight.local", DEMO_PASSWORD, organization=org, first_name=first,
                last_name=last)
            for rc in roles:
                RoleAssignment.objects.get_or_create(user=u, role=Role.objects.get(code=rc))
            return u

        safety = user("safety", "Kwaku", "Darko", ["safety_officer"])
        ohdoc = user("ohdoctor", "Dr Adwoa", "Mensah", ["oh_professional"])
        staff = list(Employee.objects.filter(status__in=["active", "probation"]).select_related("user"))

        # ---- last quarter's pulse survey (closed, enough responses for results)
        questions = [
            {"key": "proud", "text": "I am proud to work for ShineLight", "type": "rating", "dimension": "engagement"},
            {"key": "recommend", "text": "I would recommend ShineLight as a great place to work", "type": "rating",
             "dimension": "engagement"},
            {"key": "manager", "text": "My supervisor treats me with respect", "type": "rating", "dimension": "management"},
            {"key": "workload", "text": "My workload is manageable", "type": "rating", "dimension": "workload"},
            {"key": "exhausted", "text": "I rarely feel exhausted at the end of my shift", "type": "rating",
             "dimension": "burnout"},
            {"key": "enps", "text": "How likely are you to recommend us as an employer (0-10)?", "type": "enps"},
            {"key": "improve", "text": "What one thing would most improve your work life?", "type": "text",
             "required": False}]
        past = Survey.objects.create(title=f"Q3 {today.year} staff pulse", kind="pulse", questions=questions,
                                     opens_on=today - dt.timedelta(days=60))
        eng.launch(past, hrd)
        comments = ["More staff on night shifts", "Fix the staff room air conditioning", "Clearer promotion criteria",
                    "Transport for late shifts", "", "Recognise good work more often", ""]
        for i, emp in enumerate(staff):
            if not emp.user_id or i % 5 == 4:
                continue
            ward = emp.department and emp.department.code == "WARD_A"
            eng.respond(past, emp.user, {
                "proud": random.choice([4, 4, 5, 3]), "recommend": random.choice([4, 3, 5, 4]),
                "manager": random.choice([4, 5, 3]), "workload": random.choice([2, 2, 3] if ward else [3, 4, 4]),
                "exhausted": random.choice([1, 2, 2, 3] if ward else [3, 4]), "enps": random.choice([9, 8, 7, 10, 6]),
                "improve": comments[i % len(comments)]})
        past.closes_on = today - dt.timedelta(days=45)
        past.save(update_fields=["closes_on"])
        eng.close(past)
        ward = Department.objects.filter(code="WARD_A").first()
        ns = User.objects.get(username="manager").employee
        ActionPlan.objects.create(survey=past, department=ward, issue="Workload and fatigue on Ward A night shifts",
                                  action="Recruit one additional nurse; cap consecutive night shifts at 4.",
                                  owner=ns, due_date=today + dt.timedelta(days=45), status="in_progress",
                                  progress_note="Requisition raised and approved; vacancy published.")
        # ---- open wellbeing check including the demo employee
        live = Survey.objects.create(title="Wellbeing check-in", kind="wellbeing", questions=questions[2:],
                                     closes_on=today + dt.timedelta(days=10),
                                     intro="Five quick questions. Your answers are anonymous.")
        eng.launch(live, hrd)
        # ---- recognition, suggestions, events
        pairs = [(0, 1, "patient_care", "Stayed after her shift to comfort a frightened patient's family."),
                 (2, 3, "teamwork", "Covered the lab bench during the outage without being asked."),
                 (1, 4, "extra_mile", "Re-organised the ward store so we find supplies in seconds.")]
        for g, r, v, msg in pairs:
            if len(staff) > max(g, r) and staff[g].user_id:
                eng.recognise(staff[g].user, staff[r], v, msg)
        demo = User.objects.get(username="employee")
        s1 = eng.suggest(demo, {"title": "Shuttle bus for night-shift staff", "category": "welfare",
                                "text": "A bus at 10pm and 7am from Circle and Madina would help staff get home safely."})
        s1.status, s1.response = "under_review", "Costing requested from two transport providers."
        s1.save()
        eng.suggest(hro, {"title": "Digital patient handover sheet", "category": "patient",
                          "text": "Replace paper handover with a tablet form."}, anonymous=True)
        Event.objects.create(title="Free health screening (BP, sugar, BMI)", kind="wellness",
                             starts_at=now + dt.timedelta(days=6), location="OPD conference room", capacity=60,
                             description="Run by the occupational health team. Results are confidential.")
        Event.objects.create(title="End-of-year staff durbar", kind="celebration", starts_at=now + dt.timedelta(days=50),
                             location="Hospital grounds", description="Long-service awards and music.")
        Event.objects.create(title="Confidential counselling sessions (EAP)", kind="eap",
                             starts_at=now + dt.timedelta(days=3), location="Wellness room, Admin block",
                             description="Book a private 30-minute slot with the counsellor.")

        # ---- health & safety
        nurses = [e for e in staff if e.job_title and e.job_title.name == "Staff Nurse"]
        reporter = demo
        exp = ohs.report(reporter, {"kind": "exposure", "severity": "minor",
                                    "occurred_at": now - dt.timedelta(days=12, hours=3), "location": "Ward A, bay 3",
                                    "department": ward, "description": "Needlestick injury while disposing of a "
                                    "used cannula; sharps bin overfilled.", "immediate_action": "Wound washed; "
                                    "reported to in-charge; sent to OPD for assessment."},
                          [reporter.employee] if reporter.employee else [])
        ohs.investigate(exp, safety, root_cause="Sharps bin above fill line; no bin at bedside.")
        ohs.add_action(safety, "Replace sharps bins at 3/4 full; add bedside bins on Ward A", hro,
                           today + dt.timedelta(days=7), incident=exp)
        fall = ohs.report(hro, {"kind": "injury", "severity": "serious", "occurred_at": now - dt.timedelta(days=30),
                                "location": "Main corridor", "description": "Porter slipped on a wet floor while "
                                "pushing a trolley; back injury.", "immediate_action": "First aid; X-ray."},
                          [e for e in staff if e.job_title and e.job_title.name == "Porter"][:1])
        ohs.investigate(fall, safety, root_cause="Floor mopped without wet-floor sign during busy period.",
                        lost_time_days=4, reported_to_authority_on=today - dt.timedelta(days=27))
        done = ohs.add_action(safety, "Mop corridors only with signs out; procure 10 extra signs", safety,
                              today - dt.timedelta(days=10), incident=fall)
        ohs.complete_action(done, safety, "Signs procured and cleaners briefed.")
        ohs.close_incident(fall, safety)
        for days, loc, desc in ((5, "Pharmacy store", "Box of IV fluids fell from top shelf; nobody hurt."),
                                (18, "Lab", "Centrifuge lid opened before stopping; caught in time.")):
            ohs.report(hro, {"kind": "near_miss", "occurred_at": now - dt.timedelta(days=days), "location": loc,
                             "description": desc})
        ohs.add_action(safety, "Fit shelf edge guards in pharmacy store", hro, today - dt.timedelta(days=3))
        for title, dep, hazard, l, s_, rl, rs, controls in [
                ("Sharps injuries", "WARD_A", "Needlestick from used sharps", 4, 4, 2, 4,
                 "Sharps bins at point of use; no recapping; Hep B vaccination; PEP protocol"),
                ("Manual handling of patients", "WARD_A", "Back injury when moving patients", 4, 3, 3, 3,
                 "Slide sheets; two-person lifts; annual training"),
                ("Biological samples", "LAB", "Exposure to infectious material", 3, 4, 2, 3,
                 "Biosafety cabinet; PPE; spill kits"),
                ("Violence from visitors", None, "Verbal and physical aggression at OPD", 3, 3, 3, 3,
                 "Security at OPD; de-escalation training (planned)")]:
            RiskAssessment.objects.create(title=title, department=Department.objects.filter(code=dep).first() if dep else None,
                                          hazard=hazard, likelihood=l, severity=s_, residual_likelihood=rl,
                                          residual_severity=rs, controls=controls, assessed_by=safety,
                                          review_date=today + dt.timedelta(days=random.choice([-5, 60, 120])))
        Inspection.objects.create(title="Monthly ward safety walk", department=ward, date=today - dt.timedelta(days=8),
                                  inspector=safety, findings="Two sharps bins overfilled; one extinguisher out of date.",
                                  checklist=[{"item": "Fire exits clear and signed", "ok": True},
                                             {"item": "Extinguishers in date", "ok": False},
                                             {"item": "Sharps bins below fill line", "ok": False},
                                             {"item": "Floors dry / signs used", "ok": True},
                                             {"item": "First-aid box stocked", "ok": True}])
        if nurses:
            ohs.add_oh_record(ohdoc, nurses[0], {
                "kind": "return_to_work", "date": today - dt.timedelta(days=2),
                "clinical_notes": "Recovering from wrist sprain; full grip expected in 2 weeks.",
                "fitness": "fit_restricted", "restrictions": "No lifting or turning patients",
                "valid_until": today + dt.timedelta(days=14), "review_date": today + dt.timedelta(days=14)})
        self.stdout.write(f"Wellbeing demo: surveys, recognition, events; safety incidents "
                          f"{ohs.stats()['incidents']} + near misses {ohs.stats()['near_misses']}.")


    def _seed_planning(self, org, admin):
        """Succession, talent review, career paths and a workforce plan (Phase 4). Idempotent."""
        from apps.employees.models import Employee
        from apps.learning.models import Course
        from apps.organization.models import Department, JobTitle, Position
        from apps.talent import services as tal
        from apps.talent.models import CareerPath, PlanLine, Scenario, SuccessionPlan, TalentProfile, WorkforcePlan

        if WorkforcePlan.objects.exists() or not Employee.objects.exists():
            return
        User = get_user_model()
        today = dt.date.today()
        hrd, mgr = User.objects.get(username="hrdirector"), User.objects.get(username="manager")
        titles = {t.name: t for t in JobTitle.objects.all()}

        def title(name):
            return titles.get(name)

        # career paths (published to everyone)
        ld = Course.objects.filter(code="LD-401").first()
        for frm, to, yrs, rating in (("Staff Nurse", "Nursing Officer (Ward In-charge)", 3, 4),
                                     ("Accountant", "Finance Manager", 4, 4), ("HR Officer", "Human Resource Manager", 4, 4)):
            if title(frm) and title(to):
                p, _ = CareerPath.objects.get_or_create(from_title=title(frm), to_title=title(to), defaults={
                    "min_years_in_role": D(yrs), "min_rating": rating,
                    "required_qualification": "Relevant professional licence / membership"})
                if ld:
                    p.required_courses.add(ld)
        # succession for critical positions
        hro_emp = User.objects.get(username="hrofficer").employee
        for pos in Position.objects.filter(is_critical=True, status="approved"):
            plan, _ = SuccessionPlan.objects.get_or_create(position=pos, defaults={
                "risk_of_loss": "medium", "impact_of_loss": "high"})
            if pos.job_title.name == "Human Resource Manager" and hro_emp:
                tal.add_successor(hrd, plan, hro_emp, "ready_now", "Lead the next salary review cycle.")
            if pos.job_title.name.startswith("Nursing Officer"):
                nurses = list(Employee.objects.filter(job_title__name="Staff Nurse", status="active")
                              .order_by("hire_date")[:2])
                for i, n in enumerate(nurses):
                    tal.add_successor(hrd, plan, n, "1_2_years" if i == 0 else "3_plus",
                                      "First-line supervisor programme; act as shift lead.", rank=i + 1)
                plan.risk_of_loss = "high"
                plan.knowledge_transfer = "Ward duty rota rules and IPC audit process are undocumented."
                plan.save()
        # talent review for the ward team (by the ward manager)
        crit = {"learning_agility": {"met": True, "evidence": "Picked up the new e-prescribing workflow quickly"},
                "leadership": {"met": True, "evidence": "Acts as shift lead on nights"},
                "aspiration": {"met": True, "evidence": "Asked to join the supervisor programme"}}
        period = f"{today.year} talent review"
        for i, emp in enumerate(Employee.objects.filter(supervisor=mgr.employee, status="active")[:8]):
            perf = tal.suggested_performance(emp) or 2
            pot = 3 if i == 0 else (2 if i % 3 else 1)
            c = crit if pot == 3 else ({"learning_agility": crit["learning_agility"]} if pot == 2 else {})
            tal.assess(mgr, emp, period, perf, pot, c, "Placement agreed at the ward talent review.",
                       "high" if i == 1 else "low")
        demo = User.objects.get(username="employee").employee
        TalentProfile.objects.get_or_create(employee=demo, defaults={
            "aspirations": "Become a ward in-charge within three years; interested in infection control.",
            "skills": ["Wound care", "IV cannulation", "Patient education"], "open_to_lateral_moves": True})
        # workforce plan
        plan = WorkforcePlan.objects.create(name=f"{today.year + 1} workforce plan", year=today.year + 1,
                                            horizon_years=3, notes="Ward A expansion to 30 beds.")
        ward, lab = Department.objects.filter(code="WARD_A").first(), Department.objects.filter(code="LAB").first()
        if ward and title("Staff Nurse"):
            PlanLine.objects.create(plan=plan, department=ward, job_title=title("Staff Nurse"), planned_headcount=10,
                                    workload_units=D("30"), workload_label="beds", target_ratio=D("0.33"),
                                    justification="Ministry guideline of one nurse per three beds across shifts.")
        if lab:
            PlanLine.objects.create(plan=plan, department=lab, planned_headcount=4,
                                    justification="Extended lab hours from January.")
        Scenario.objects.create(plan=plan, name="Expansion: +10% a year, 10% pay rise", growth_percent=D("10"),
                                salary_increase_percent=D("10"))
        Scenario.objects.create(plan=plan, name="Budget squeeze: hiring freeze", hiring_freeze=True,
                                salary_increase_percent=D("5"), budget_cap=D("500000"))
        self.stdout.write(f"Planning demo: {SuccessionPlan.objects.count()} succession plans, bench strength "
                          f"{tal.succession_risk()['bench_strength_percent']}%.")

    def _seed_reports(self, org, admin):
        """Shared report-builder definitions (Phase 4). Idempotent."""
        from apps.core.context import org_context
        from apps.reports.models import ReportDefinition

        hrd = get_user_model().objects.get(username="hrdirector")
        with org_context(org, hrd):
            for name, spec in (
                ("Headcount by department and gender", {"dataset": "employees", "group_by": ["department", "gender"],
                                                        "aggregates": [{"fn": "count"}],
                                                        "filters": [{"field": "status", "op": "in",
                                                                     "value": "active,probation,on_leave"}],
                                                        "chart": "none"}),
                ("Staff by tenure band", {"dataset": "employees", "group_by": ["tenure_band"],
                                          "aggregates": [{"fn": "count"}], "chart": "column",
                                          "filters": [{"field": "status", "op": "in",
                                                       "value": "active,probation,on_leave"}]}),
                ("Sick leave in the last 90 days", {"dataset": "leave", "group_by": ["department"],
                                                    "aggregates": [{"fn": "count"}, {"fn": "sum", "field": "days"}],
                                                    "filters": [{"field": "leave_type", "op": "contains",
                                                                 "value": "sick"},
                                                                {"field": "start_date", "op": "last_days",
                                                                 "value": "90"}],
                                                    "sort": "-sum_days", "chart": "bar"}),
                ("Contracts ending in the next 90 days", {"dataset": "employees",
                                                          "columns": ["staff_number", "name", "department",
                                                                      "job_title", "contract_end_date"],
                                                          "filters": [{"field": "contract_end_date", "op": "gte",
                                                                       "value": dt.date.today().isoformat()},
                                                                      {"field": "contract_end_date", "op": "lte",
                                                                       "value": (dt.date.today() + dt.timedelta(
                                                                           days=90)).isoformat()}],
                                                          "sort": "contract_end_date"}),
            ):
                ReportDefinition.objects.get_or_create(name=name, defaults={**spec, "visibility": "shared"})

    def _seed_platform(self, org):
        """Plans, a platform operator and a second small organization (multi-organization demo). Idempotent."""
        from apps.employees.models import Employee
        from apps.tenancy.models import Organization, Plan

        User = get_user_model()
        org.plan = Plan.objects.filter(code="healthcare").first()
        org.save(update_fields=["plan"])
        if not User.objects.filter(username="platform").exists():
            User.objects.create_user("platform", "platform@shinelight.local", DEMO_PASSWORD, organization=None,
                                     is_platform_admin=True, first_name="Platform", last_name="Operator")
        if Organization.objects.filter(code="accraclinic").exists():
            return
        clinic, clinic_admin = setup_organization("Accra Family Clinic", "accraclinic", "clinicadmin", DEMO_PASSWORD,
                                                  "admin@accraclinic.local", ["payroll", "sms"], require_mfa=False)
        clinic.plan = Plan.objects.filter(code="trial").first()
        clinic.status = "trial"
        clinic.trial_ends_at = dt.date.today() + dt.timedelta(days=21)
        clinic.save()
        from apps.employees.services import hire
        from apps.organization.models import Department, Grade, GradeStep, JobTitle

        with org_context(clinic, clinic_admin), transaction.atomic():
            dept = Department.objects.create(code="OPD", name="Outpatients")
            grade = Grade.objects.create(code="C1", name="Clinical", level=1, min_salary=D("3000"), max_salary=D("4500"))
            step = GradeStep.objects.create(grade=grade, step=1, basic_salary=D("3000"))
            title = JobTitle.objects.create(name="Clinic Nurse")
            for first, last, g in (("Efua", "Asante", "female"), ("Nii", "Lamptey", "male"), ("Adwoa", "Boakye", "female")):
                if not Employee.objects.filter(first_name=first, last_name=last).exists():
                    hire({"first_name": first, "last_name": last, "gender": g, "hire_date": dt.date(2024, 3, 1),
                          "department": dept, "job_title": title, "grade": grade, "grade_step": step,
                          "basic_salary": D("3000")}, allow_duplicate=True)
        self.stdout.write("Multi-organization demo: platform operator 'platform', second organization 'accraclinic'.")
