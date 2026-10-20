"""Demo data for evaluation and training. NEVER run against production.

Demo logins (all share DEMO_PASSWORD below; MFA disabled for the demo org):
  admin, hrdirector, hrofficer, payroll, approver, manager, employee, auditor
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
                                        "admin@shinelight.local", ["payroll", "hospital", "sms", "geofence"],
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
