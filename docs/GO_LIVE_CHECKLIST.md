# Go-live checklist

## Statutory configuration (must be signed off by a qualified payroll professional)

- [ ] **PAYE bands** (Payroll → Setup → PAYE tax tables) match the current GRA monthly resident table. Use the built-in calculator to check a few figures against GRA examples, then tick **Verified**.
- [ ] **SSNIT** employee/employer rates, Tier 1/Tier 2 split and **maximum insurable earnings** match current SSNIT/NPRA guidance. Tick **Verified**.
- [ ] **Bonus tax** (rate and % of annual basic), **overtime tax** (qualifying income threshold, rates, % of basic) and the **non-resident rate** are current.
- [ ] **Personal reliefs** (marriage/responsibility, child education, aged dependant, professional training, old age, disability) are current, and employee claims are evidenced and approved.
- [ ] **Tier 2 trustee** and **Tier 3 provident fund** arrangements are recorded. Tier 3 percentages are set per employee.
- [ ] **Overtime multipliers, proration method and hours per month** reflect your collective agreement or conditions of service.
- [ ] **Leave entitlements** reflect the Labour Act, 2003 (Act 651) minimums and your conditions of service.
- [ ] **Public holidays** for the year are loaded. Add the Eid dates when they are gazetted.

## Parallel run

- [ ] Run at least **two months in parallel** with the current payroll. Reconcile every employee's gross, PAYE, SSNIT and net to the pesewa. Investigate every variance.
- [ ] The GL journal is mapped to your chart of accounts (Settings → GL accounts) and **balances**.
- [ ] The bank file format has been tested with your bank (upload a test file) and the MoMo provider.
- [ ] GRA PAYE schedule and SSNIT report columns match the current filing templates.

## Data migration

- [ ] Departments, grades/steps, job titles and positions are configured before importing employees.
- [ ] Employees imported with the Excel template (dry run until zero errors). Data quality dashboard shows ≥ 95% completeness.
- [ ] Opening leave balances posted (Leave → Balances & adjustments).
- [ ] Bank details are verified against bank letters by a second person.
- [ ] Outstanding loans recorded with their current balances.

## Access & security

- [ ] Every user has an individual account with the correct role and scope. The Payroll Officer and Payroll Approver are **different people**.
- [ ] MFA is enrolled for all sensitive roles. The demo organization and demo users are **not** present in production.
- [ ] `DEBUG=False`, strong `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` backed up, TLS on, `python manage.py check --deploy` is clean.
- [ ] Backups are scheduled and copied off-site, and a **test restore has been completed**.

## Data protection (Act 843)

- [ ] The organization is registered with the **Data Protection Commission** as a data controller (renew annually).
- [ ] Privacy notice issued to staff. Consent or the lawful basis is recorded where applicable (employee record → consents).
- [ ] Retention periods per document category are approved by legal/HR.
- [ ] A breach response procedure is documented (see OPERATIONS.md §7).

## People readiness

- [ ] Workflows reviewed with department heads; delegations set for planned absences.
- [ ] Training delivered: employees (ESS on mobile), managers (inbox, team, roster), HR, payroll.
- [ ] Policies uploaded and marked "requires acknowledgment".
