---
project: employee-hr
type: guide
status: active
created: 2026-02-21
updated: 2026-02-21
---

# Appsmith HR Portal — Setup Guide

**API base URL:** `https://moonwalk-employee-hr-production.up.railway.app`
**Auth header:** `X-API-Key: bUgFGdJpaBTks8VFwNQ2_mf64AN9zMsj7NJad6bGEZU`
**Interactive docs:** `https://moonwalk-employee-hr-production.up.railway.app/docs`

---

## 1. Create the App

1. Log in at https://app.appsmith.com
2. Open the **Moonwalk** workspace
3. Create new app: **HR Portal**

---

## 2. Add API Datasource

Datasources → + New Datasource → REST API:

| Field | Value |
|-------|-------|
| Name | `HRApi` |
| URL | `https://moonwalk-employee-hr-production.up.railway.app` |
| Header | `X-API-Key` = `bUgFGdJpaBTks8VFwNQ2_mf64AN9zMsj7NJad6bGEZU` |

Save & Test → should return `200 OK` against `/health`.

---

## 3. Create Queries

### `GetEmployees`
- Datasource: `HRApi`
- Method: GET
- Path: `/employees`
- Run on page load: Yes

### `GetEmployee`
- Method: GET
- Path: `/employees/{{EmployeeTable.selectedRow.employee_id}}`

### `ExportCSV`
- Method: GET
- Path: `/export/csv`
- On success: download file

### `IngestPDF`
- Method: POST
- Path: `/ingest`
- Body type: FORM_DATA
- Key: `file`, Value: `{{FilePicker.files[0]}}`, Type: File
- On success: `GetEmployees.run()`

---

## 4. Page Layout

### Header bar
- Text widget: **HR Portal** (heading style)
- Text widget: `{{GetEmployees.data.length}} employees` (secondary)

---

### Employee Table

Full-width Table widget (`EmployeeTable`):
- Data: `{{GetEmployees.data}}`
- Visible columns:

| Column | Display name | Format |
|--------|-------------|--------|
| `employee_id` | ID | Text |
| `full_name` | Name | Text |
| `job_title` | Job Title | Text |
| `nationality` | Nationality | Text |
| `base_salary` | Base Salary (AED) | Number |
| `contract_expiry_date` | Contract Expiry | Date (YYYY-MM-DD) |
| `days_until_expiry` | Days Left | Number — see computed column below |
| `insurance_status` | Insurance | Text |

**Computed column — Days Left row colour:**
In table column settings for `contract_expiry_date`, set Cell Background:
```js
{{
  (() => {
    const expiry = currentRow.contract_expiry_date;
    if (!expiry) return "transparent";
    const days = (new Date(expiry) - new Date()) / 86400000;
    if (days < 0)   return "#FFCDD2";  // red   — expired
    if (days < 30)  return "#FFE082";  // amber — expiring soon
    return "transparent";
  })()
}}
```

Row click → trigger `GetEmployee.run()` to populate the detail panel.

---

### Action bar (above table)

| Widget | Type | Action |
|--------|------|--------|
| File Picker (`FilePicker`) | FilePicker | Accept `.pdf` only |
| **Upload Contract** button | Button (primary) | `IngestPDF.run()` |
| **Download CSV** button | Button (secondary) | `ExportCSV.run()` |
| Refresh icon button | Icon Button | `GetEmployees.run()` |

---

### Employee Detail Panel (right side drawer or modal)

Bind to `GetEmployee.data`. Show on row click via `showModal('EmployeeModal')`.

**Modal: `EmployeeModal`**

Tab 1 — Personal:

| Field | Bound to |
|-------|---------|
| Employee ID | `{{GetEmployee.data.employee_id}}` |
| Full Name | `{{GetEmployee.data.full_name}}` |
| Nationality | `{{GetEmployee.data.nationality}}` |
| Date of Birth | `{{GetEmployee.data.date_of_birth}}` |
| Passport Number | `{{GetEmployee.data.passport_number}}` |
| Job Title | `{{GetEmployee.data.job_title}}` |

Tab 2 — Contract & Salary:

| Field | Bound to |
|-------|---------|
| Base Salary (AED) | `{{GetEmployee.data.base_salary}}` |
| Total Salary (AED) | `{{GetEmployee.data.total_salary}}` |
| Contract Start | `{{GetEmployee.data.contract_start_date}}` |
| Contract Expiry | `{{GetEmployee.data.contract_expiry_date}}` |
| Insurance Status | `{{GetEmployee.data.insurance_status ?? "Not set"}}` |
| MOHRE Transaction No | `{{GetEmployee.data.mohre_transaction_no}}` |

Tab 3 — Ingest Metadata:

| Field | Bound to |
|-------|---------|
| Source File | `{{GetEmployee.data.source_file}}` |
| Confidence Score | `{{GetEmployee.data.confidence_score}}` |
| Ingested At | `{{GetEmployee.data.ingested_at}}` |

Modal footer: **Close** button → `closeModal('EmployeeModal')`

---

## 5. Ingest Error Handling

The `IngestPDF` query returns HTTP 422 when confidence is below 0.95.
Show an alert on failure:

On `IngestPDF` → onError:
```js
showAlert("Parse failed: " + JSON.stringify(this.error.message), "error");
```

On success:
```js
showAlert("Ingested: " + IngestPDF.data.employee_id, "success");
GetEmployees.run();
```

---

## 6. API Reference

| Endpoint | Method | Auth | Notes |
|----------|--------|------|-------|
| `/health` | GET | None | Health probe |
| `/employees` | GET | Key | List all |
| `/employees/{id}` | GET | Key | Single record by EID |
| `/ingest` | POST | Key | Multipart PDF upload; 422 on low confidence |
| `/export/csv` | GET | Key | Download `employees.csv` with expiry columns |
