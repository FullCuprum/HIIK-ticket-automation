"""End-to-end integration checks against a running API instance."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date

import httpx

BASE_URL = "http://localhost:8000"
TIMEOUT = 30.0


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class IntegrationReport:
    results: list[TestResult] = field(default_factory=list)

    def ok(self, name: str, detail: str = "") -> None:
        self.results.append(TestResult(name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append(TestResult(name, False, detail))

    @property
    def passed(self) -> int:
        return sum(1 for item in self.results if item.passed)

    @property
    def failed(self) -> int:
        return sum(1 for item in self.results if not item.passed)


def login(client: httpx.Client, username: str, password: str) -> dict:
    response = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def run_integration_tests() -> IntegrationReport:
    report = IntegrationReport()
    unique = int(time.time())
    ticket_text = (
        f"[integration-{unique}] Срочно! Не работает интернет в ауд. 214 "
        "первого корпуса, пользователи не могут выйти в сеть."
    )

    with httpx.Client(timeout=TIMEOUT) as client:
        # Infrastructure
        try:
            health = client.get(f"{BASE_URL}/health")
            if health.status_code == 200 and health.json().get("status") == "ok":
                report.ok("Health check", health.text)
            else:
                report.fail("Health check", f"Unexpected response: {health.status_code} {health.text}")
                return report
        except httpx.HTTPError as exc:
            report.fail("Health check", str(exc))
            return report

        try:
            frontend = client.get(f"{BASE_URL}/frontend/index.html")
            if frontend.status_code == 200 and "html" in frontend.headers.get("content-type", ""):
                report.ok("Frontend static", f"{len(frontend.text)} bytes")
            else:
                report.fail("Frontend static", f"status={frontend.status_code}")
        except httpx.HTTPError as exc:
            report.fail("Frontend static", str(exc))

        # Auth
        try:
            bad = client.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "wrong"})
            if bad.status_code == 401:
                report.ok("Auth rejects invalid credentials")
            else:
                report.fail("Auth rejects invalid credentials", f"status={bad.status_code}")
        except httpx.HTTPError as exc:
            report.fail("Auth rejects invalid credentials", str(exc))

        tokens: dict[str, str] = {}
        for username, password in [("admin", "admin"), ("user", "user"), ("employee", "employee")]:
            try:
                data = login(client, username, password)
                if data.get("access_token") and data.get("role"):
                    tokens[username] = data["access_token"]
                    report.ok(f"Login as {username}", f"role={data['role']}")
                else:
                    report.fail(f"Login as {username}", json.dumps(data, ensure_ascii=False))
            except httpx.HTTPError as exc:
                report.fail(f"Login as {username}", str(exc))

        if "user" not in tokens:
            report.fail("Ticket flow", "Skipped: user token unavailable")
            return report

        user_headers = auth_headers(tokens["user"])
        admin_headers = auth_headers(tokens.get("admin", ""))
        employee_headers = auth_headers(tokens.get("employee", ""))

        # Unauthorized journal
        try:
            resp = client.get(f"{BASE_URL}/tickets/journal")
            if resp.status_code == 401:
                report.ok("Journal requires auth")
            else:
                report.fail("Journal requires auth", f"status={resp.status_code}")
        except httpx.HTTPError as exc:
            report.fail("Journal requires auth", str(exc))

        # Buildings
        try:
            resp = client.get(f"{BASE_URL}/tickets/buildings")
            data = resp.json()
            if resp.status_code == 200 and "corpus_1" in data:
                report.ok("Buildings list", f"{len(data)} buildings")
            else:
                report.fail("Buildings list", resp.text)
        except httpx.HTTPError as exc:
            report.fail("Buildings list", str(exc))

        # Preview
        extracted: dict = {}
        try:
            preview = client.post(f"{BASE_URL}/tickets/preview", json={"raw_text": ticket_text})
            preview_data = preview.json()
            if preview.status_code == 200:
                extracted = preview_data.get("extracted", {})
                report.ok(
                    "Ticket preview",
                    f"missing={preview_data.get('missing_fields', [])}, "
                    f"building={extracted.get('building')}, type={extracted.get('ticket_type')}",
                )
            else:
                report.fail("Ticket preview", preview.text)
        except httpx.HTTPError as exc:
            report.fail("Ticket preview", str(exc))

        # Create ticket (full lifecycle)
        ticket_id: int | None = None
        approval_id: int | None = None
        try:
            create = client.post(
                f"{BASE_URL}/tickets/",
                headers=user_headers,
                json={"raw_text": ticket_text, "extracted": extracted},
            )
            ticket = create.json()
            ticket_id = ticket.get("id")
            status = ticket.get("status")
            if create.status_code == 200 and ticket_id and status in {"scheduled", "ready_for_scheduling"}:
                report.ok("Create ticket", f"id={ticket_id}, status={status}")
            elif create.status_code == 200 and status == "need_clarification":
                report.fail("Create ticket", f"Unexpected clarification required: {ticket.get('missing_fields')}")
            else:
                report.fail("Create ticket", create.text)
        except httpx.HTTPError as exc:
            report.fail("Create ticket", str(exc))

        # Journal visibility
        today = date.today().isoformat()
        try:
            user_journal = client.get(
                f"{BASE_URL}/tickets/journal",
                headers=user_headers,
                params={"date_from": today, "date_to": today},
            )
            user_items = user_journal.json()
            if user_journal.status_code == 200 and any(item.get("id") == ticket_id for item in user_items):
                report.ok("User journal contains created ticket", f"items={len(user_items)}")
            else:
                report.fail(
                    "User journal contains created ticket",
                    f"status={user_journal.status_code}, found={len(user_items) if user_journal.status_code == 200 else 'n/a'}",
                )
        except httpx.HTTPError as exc:
            report.fail("User journal contains created ticket", str(exc))

        if tokens.get("admin"):
            try:
                admin_journal = client.get(
                    f"{BASE_URL}/tickets/journal",
                    headers=admin_headers,
                    params={"date_from": today, "date_to": today},
                )
                admin_items = admin_journal.json()
                if admin_journal.status_code == 200 and any(item.get("id") == ticket_id for item in admin_items):
                    report.ok("Admin journal contains created ticket", f"items={len(admin_items)}")
                else:
                    report.fail("Admin journal contains created ticket", admin_journal.text[:200])
            except httpx.HTTPError as exc:
                report.fail("Admin journal contains created ticket", str(exc))

            try:
                authors = client.get(f"{BASE_URL}/tickets/journal/authors", headers=admin_headers)
                if authors.status_code == 200 and "user" in authors.json():
                    report.ok("Journal authors (admin)")
                else:
                    report.fail("Journal authors (admin)", authors.text)
            except httpx.HTTPError as exc:
                report.fail("Journal authors (admin)", str(exc))

            try:
                employees = client.get(f"{BASE_URL}/employees/", headers=admin_headers)
                emp_data = employees.json()
                if employees.status_code == 200 and emp_data.get("items"):
                    report.ok("Employees list (admin)", f"count={len(emp_data['items'])}")
                else:
                    report.fail("Employees list (admin)", employees.text[:200])
            except httpx.HTTPError as exc:
                report.fail("Employees list (admin)", str(exc))

        # Approvals & schedule
        try:
            approvals = client.get(f"{BASE_URL}/schedule/approvals")
            pending = approvals.json()
            if approvals.status_code == 200:
                match = next((item for item in pending if item.get("ticket_id") == ticket_id), None)
                if match:
                    approval_id = match.get("id")
                    executors = match.get("employee_names") or []
                    report.ok(
                        "Pending approval created",
                        f"approval_id={approval_id}, executors={executors}",
                    )
                else:
                    report.fail("Pending approval created", f"ticket_id={ticket_id} not in {len(pending)} pending")
            else:
                report.fail("Pending approval created", approvals.text)
        except httpx.HTTPError as exc:
            report.fail("Pending approval created", str(exc))

        if approval_id:
            try:
                denied = client.post(
                    f"{BASE_URL}/schedule/approvals/{approval_id}/approve",
                    json={"manager_comment": "Should be denied"},
                )
                if denied.status_code == 401:
                    report.ok("Approve requires admin auth")
                else:
                    report.fail("Approve requires admin auth", f"status={denied.status_code}")
            except httpx.HTTPError as exc:
                report.fail("Approve requires admin auth", str(exc))

            if tokens.get("admin"):
                try:
                    approve = client.post(
                        f"{BASE_URL}/schedule/approvals/{approval_id}/approve",
                        headers=admin_headers,
                        json={"manager_comment": "Integration test approval"},
                    )
                    if approve.status_code == 200:
                        report.ok("Approve schedule proposal (admin)")
                    else:
                        report.fail("Approve schedule proposal (admin)", approve.text)
                except httpx.HTTPError as exc:
                    report.fail("Approve schedule proposal (admin)", str(exc))

        try:
            schedule = client.get(f"{BASE_URL}/schedule/current", headers=user_headers)
            items = schedule.json()
            if schedule.status_code == 200:
                found = any(item.get("ticket_id") == ticket_id for item in items)
                report.ok("Current schedule", f"items={len(items)}, ticket_visible={found}")
            else:
                report.fail("Current schedule", schedule.text)
        except httpx.HTTPError as exc:
            report.fail("Current schedule", str(exc))

        if tokens.get("employee"):
            try:
                emp_journal = client.get(
                    f"{BASE_URL}/tickets/journal",
                    headers=employee_headers,
                    params={"date_from": today, "date_to": today},
                )
                if emp_journal.status_code == 200:
                    report.ok("Employee journal accessible", f"items={len(emp_journal.json())}")
                else:
                    report.fail("Employee journal accessible", emp_journal.text)
            except httpx.HTTPError as exc:
                report.fail("Employee journal accessible", str(exc))

        # RBAC: employee cannot access admin employees
        if tokens.get("employee"):
            try:
                denied = client.get(f"{BASE_URL}/employees/", headers=employee_headers)
                if denied.status_code == 403:
                    report.ok("RBAC blocks employee from admin employees API")
                else:
                    report.fail("RBAC blocks employee from admin employees API", f"status={denied.status_code}")
            except httpx.HTTPError as exc:
                report.fail("RBAC blocks employee from admin employees API", str(exc))

    return report


def main() -> int:
    report = run_integration_tests()
    print("=" * 60)
    print("INTEGRATION TEST REPORT")
    print("=" * 60)
    for item in report.results:
        status = "PASS" if item.passed else "FAIL"
        line = f"[{status}] {item.name}"
        if item.detail:
            line += f" — {item.detail}"
        print(line)
    print("-" * 60)
    print(f"Total: {len(report.results)}, passed: {report.passed}, failed: {report.failed}")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
