"""All SQL lives here. Every query is parameterised, and every application query
includes user_id, so a user can never read or change another user's rows."""
from psycopg import Connection, sql

APPLICATION_COLUMNS = "id, company, role, url, status, follow_up_date, applied_on, notes, created_at, updated_at"

# Whitelist of columns PATCH may change. Column names come from this fixed set,
# never from the request, and values are always passed as parameters.
UPDATABLE_COLUMNS = {"company", "role", "url", "status", "follow_up_date", "applied_on", "notes"}


# ---------- Users ----------

def create_user(conn: Connection, email: str, password_hash: str) -> dict:
    return conn.execute(
        "INSERT INTO jobtracker_users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
        (email, password_hash),
    ).fetchone()


def get_user_by_email(conn: Connection, email: str) -> dict | None:
    return conn.execute(
        "SELECT id, email, password_hash FROM jobtracker_users WHERE email = %s", (email,)
    ).fetchone()


def get_user_by_id(conn: Connection, user_id: int) -> dict | None:
    return conn.execute("SELECT id, email FROM jobtracker_users WHERE id = %s", (user_id,)).fetchone()


# ---------- Applications ----------

def list_applications(conn: Connection, user_id: int, status: str | None) -> list[dict]:
    query = f"SELECT {APPLICATION_COLUMNS} FROM jobtracker_applications WHERE user_id = %s"
    params: list = [user_id]
    if status is not None:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY follow_up_date ASC NULLS LAST, created_at DESC, id DESC"
    return conn.execute(query, params).fetchall()


def get_application(conn: Connection, user_id: int, application_id: int) -> dict | None:
    return conn.execute(
        f"SELECT {APPLICATION_COLUMNS} FROM jobtracker_applications WHERE id = %s AND user_id = %s",
        (application_id, user_id),
    ).fetchone()


def create_application(conn: Connection, user_id: int, data: dict) -> dict:
    # Two statements (the row and its first history event) must succeed together.
    with conn.transaction():
        return _insert_application(conn, user_id, data)


def _insert_application(conn: Connection, user_id: int, data: dict) -> dict:
    row = conn.execute(
        f"""INSERT INTO jobtracker_applications
                (user_id, company, role, url, status, follow_up_date, applied_on, notes)
            VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, CURRENT_DATE), %s)
            RETURNING {APPLICATION_COLUMNS}""",
        (user_id, data["company"], data["role"], data["url"], data["status"],
         data["follow_up_date"], data.get("applied_on"), data["notes"]),
    ).fetchone()
    record_status(conn, row["id"], row["status"])
    return row


def record_status(conn: Connection, application_id: int, status: str) -> None:
    conn.execute(
        "INSERT INTO jobtracker_status_events (application_id, status) VALUES (%s, %s)",
        (application_id, status),
    )


def update_application(conn: Connection, user_id: int, application_id: int, changes: dict) -> dict | None:
    columns = [c for c in changes if c in UPDATABLE_COLUMNS]
    assignments = [sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns]
    assignments.append(sql.SQL("updated_at = now()"))
    query = sql.SQL(
        "UPDATE jobtracker_applications SET {} WHERE id = %s AND user_id = %s RETURNING "
        + APPLICATION_COLUMNS
    ).format(sql.SQL(", ").join(assignments))
    params = [changes[c] for c in columns] + [application_id, user_id]
    if "status" not in columns:
        return conn.execute(query, params).fetchone()

    # Lock the row and read the old status first, so history only records real
    # changes. All three statements run in one transaction.
    with conn.transaction():
        old = conn.execute(
            "SELECT status FROM jobtracker_applications WHERE id = %s AND user_id = %s FOR UPDATE",
            (application_id, user_id),
        ).fetchone()
        if old is None:
            return None
        row = conn.execute(query, params).fetchone()
        if old["status"] != row["status"]:
            record_status(conn, application_id, row["status"])
        return row


def import_applications(conn: Connection, user_id: int, rows: list[dict]) -> int:
    """Insert every row, or none of them."""
    with conn.transaction():
        for data in rows:
            _insert_application(conn, user_id, data)
    return len(rows)


def get_stats(conn: Connection, user_id: int, weeks: int) -> dict:
    """Counts for the stats page. "Ever reached" comes from the status history."""
    counts = conn.execute(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE status = 'Applied')   AS applied,
                  count(*) FILTER (WHERE status = 'Interview') AS interview,
                  count(*) FILTER (WHERE status = 'Offer')     AS offer,
                  count(*) FILTER (WHERE status = 'Rejected')  AS rejected,
                  count(*) FILTER (WHERE EXISTS (
                      SELECT 1 FROM jobtracker_status_events e
                      WHERE e.application_id = a.id AND e.status <> 'Applied')) AS responded,
                  count(*) FILTER (WHERE EXISTS (
                      SELECT 1 FROM jobtracker_status_events e
                      WHERE e.application_id = a.id AND e.status IN ('Interview', 'Offer'))) AS interviewed,
                  count(*) FILTER (WHERE EXISTS (
                      SELECT 1 FROM jobtracker_status_events e
                      WHERE e.application_id = a.id AND e.status = 'Offer')) AS offers
           FROM jobtracker_applications a
           WHERE a.user_id = %s""",
        (user_id,),
    ).fetchone()
    weekly = conn.execute(
        """SELECT w.week_start::date AS week_start, count(a.id) AS count
           FROM generate_series(
                    date_trunc('week', CURRENT_DATE) - make_interval(weeks => %(weeks)s - 1),
                    date_trunc('week', CURRENT_DATE),
                    interval '1 week') AS w(week_start)
           LEFT JOIN jobtracker_applications a
                  ON a.user_id = %(user_id)s
                 AND date_trunc('week', a.applied_on) = w.week_start
           GROUP BY w.week_start
           ORDER BY w.week_start""",
        {"user_id": user_id, "weeks": weeks},
    ).fetchall()
    return {**counts, "weekly": weekly}


def all_applications_for_export(conn: Connection, user_id: int) -> list[dict]:
    return conn.execute(
        f"SELECT {APPLICATION_COLUMNS} FROM jobtracker_applications WHERE user_id = %s "
        "ORDER BY applied_on, id",
        (user_id,),
    ).fetchall()


def delete_application(conn: Connection, user_id: int, application_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM jobtracker_applications WHERE id = %s AND user_id = %s", (application_id, user_id)
    )
    return cur.rowcount == 1
