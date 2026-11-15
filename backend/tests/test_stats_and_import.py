"""Stats, CSV export and CSV import against the real database."""
import csv
import io
from datetime import date, timedelta

from .conftest import register_and_login
from .test_applications import create


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def test_stats_use_status_history(client, auth_headers):
    a = create(client, auth_headers, company="A")
    b = create(client, auth_headers, company="B")
    create(client, auth_headers, company="C")
    create(client, auth_headers, company="D", status="Interview")

    # A went to interview, then was rejected: it still counts as "interviewed".
    client.patch(f"/applications/{a['id']}", json={"status": "Interview"}, headers=auth_headers)
    client.patch(f"/applications/{a['id']}", json={"status": "Rejected"}, headers=auth_headers)
    # B got straight to an offer.
    client.patch(f"/applications/{b['id']}", json={"status": "Offer"}, headers=auth_headers)

    stats = client.get("/applications/stats", headers=auth_headers).json()
    assert stats["total"] == 4
    assert stats["by_status"] == {"Applied": 1, "Interview": 1, "Offer": 1, "Rejected": 1}
    assert (stats["responded"], stats["interviewed"], stats["offers"]) == (3, 3, 1)
    assert stats["response_rate"] == 0.75 and stats["offer_rate"] == 0.25


def test_saving_the_same_status_does_not_add_history(client, auth_headers, admin_conn):
    app = create(client, auth_headers)
    client.patch(f"/applications/{app['id']}", json={"status": "Applied", "notes": "still waiting"},
                 headers=auth_headers)
    count = admin_conn.execute("SELECT count(*) FROM jobtracker_status_events").fetchone()[0]
    assert count == 1


def test_weekly_counts_include_empty_weeks(client, auth_headers):
    today = date.today()
    create(client, auth_headers, applied_on=today.isoformat())
    create(client, auth_headers, applied_on=today.isoformat())
    create(client, auth_headers, applied_on=(today - timedelta(weeks=2)).isoformat())
    create(client, auth_headers, applied_on=(today - timedelta(weeks=30)).isoformat())  # outside the window

    weekly = client.get("/applications/stats", headers=auth_headers).json()["weekly"]
    assert len(weekly) == 12
    assert weekly[-1] == {"week_start": monday(today).isoformat(), "count": 2}
    assert weekly[-3]["count"] == 1 and weekly[-2]["count"] == 0
    assert sum(w["count"] for w in weekly) == 3


def test_stats_for_a_new_user_are_zero(client, auth_headers):
    stats = client.get("/applications/stats", headers=auth_headers).json()
    assert stats["total"] == 0 and stats["response_rate"] == 0
    assert all(w["count"] == 0 for w in stats["weekly"])


def test_applied_on_defaults_to_today_and_cannot_be_future(client, auth_headers):
    assert create(client, auth_headers)["applied_on"] == date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    res = client.post("/applications", json={"company": "X", "role": "Y", "applied_on": tomorrow},
                      headers=auth_headers)
    assert res.status_code == 422


def test_export_is_csv_of_only_your_applications(client, auth_headers):
    create(client, auth_headers, company="Mine")
    other = register_and_login(client, email="someone@example.com")
    create(client, other, company="Theirs")

    res = client.get("/applications/export", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert [r["company"] for r in rows] == ["Mine"]


def test_import_then_export_round_trip(client, auth_headers):
    text = ("company,role,status,applied_on,follow_up_date,url,notes\n"
            "Acme,Dev,Interview,2026-09-01,,https://acme.example,Recruiter called\n"
            "Globex,QA,,,,,\n")
    res = client.post("/applications/import", json={"csv": text}, headers=auth_headers)
    assert res.status_code == 201 and res.json() == {"imported": 2}

    items = client.get("/applications", headers=auth_headers).json()["items"]
    assert {i["company"]: i["status"] for i in items} == {"Acme": "Interview", "Globex": "Applied"}
    stats = client.get("/applications/stats", headers=auth_headers).json()
    assert stats["interviewed"] == 1  # imported status is recorded in history

    exported = client.get("/applications/export", headers=auth_headers).text
    assert "Acme,Dev,Interview,2026-09-01,,https://acme.example,Recruiter called" in exported


def test_import_with_errors_saves_nothing(client, auth_headers):
    text = "company,role,status\nAcme,Dev,Applied\nGlobex,,Applied\nInitech,PM,Maybe\n"
    res = client.post("/applications/import", json={"csv": text}, headers=auth_headers)
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert [d["field"] for d in error["details"]] == ["row 3", "row 4"]
    assert "nothing was imported" in error["message"]
    assert client.get("/applications", headers=auth_headers).json()["items"] == []


def test_import_requires_login_and_valid_body(client, auth_headers):
    assert client.post("/applications/import", json={"csv": "company,role\nA,B\n"}).status_code == 401
    assert client.post("/applications/import", json={"csv": ""}, headers=auth_headers).status_code == 422
    assert client.post("/applications/import", json={"file": "x"}, headers=auth_headers).status_code == 422


def test_stats_and_export_require_login(client):
    assert client.get("/applications/stats").status_code == 401
    assert client.get("/applications/export").status_code == 401
