from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import sqlite3

from database import get_connection, create_tables
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_roles,
)

app = FastAPI(
    title="Helpdesk / IT Support Ticketing System",
    description="Helpdesk system using Python, FastAPI and SQLite3",
    version="1.0"
)

create_tables()
security = HTTPBearer()

SLA_HOURS = {
    "LOW": 24,
    "MEDIUM": 8,
    "HIGH": 4,
    "CRITICAL": 2,
}

VALID_STATUSES = [
    "OPEN",
    "ASSIGNED",
    "IN_PROGRESS",
    "WAITING_FOR_USER",
    "RESOLVED",
    "CLOSED",
]

VALID_ROLES = ["USER", "ENGINEER", "ADMIN"]

STATUS_TRANSITIONS = {
    "OPEN": ["ASSIGNED"],
    "ASSIGNED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["WAITING_FOR_USER", "RESOLVED"],
    "WAITING_FOR_USER": ["IN_PROGRESS"],
    "RESOLVED": ["CLOSED"],
    "CLOSED": [],
}


# -------------------- SCHEMAS --------------------

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "USER"


class LoginRequest(BaseModel):
    email: str
    password: str


class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TicketCreate(BaseModel):
    title: str
    description: str
    category_id: int
    priority: str = "MEDIUM"


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None


class AssignEngineer(BaseModel):
    engineer_id: int


class StatusUpdate(BaseModel):
    status: str


class CommentCreate(BaseModel):
    comment: str


class CreateUser(BaseModel):
    name: str
    email: str
    password: str
    role: str = "USER"


# -------------------- HELPERS --------------------

def get_ticket(ticket_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    ticket = cur.fetchone()
    conn.close()
    return ticket


def add_audit_log(user_id, action, entity, entity_id, old_value=None, new_value=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audit_logs
        (user_id, action, entity, entity_id, old_value, new_value, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            action,
            entity,
            entity_id,
            old_value,
            new_value,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def create_notification(user_id, ticket_id, message):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO notifications
        (user_id, ticket_id, message, is_read, created_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (user_id, ticket_id, message, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# -------------------- HOME --------------------

@app.get("/")
def home():
    return {"message": "Helpdesk API is running"}


# -------------------- AUTH --------------------

@app.post("/auth/register")
def register(data: RegisterRequest):
    role = data.role.upper()

    if role not in VALID_ROLES:
        raise HTTPException(400, "Role must be USER, ENGINEER or ADMIN")

    if len(data.password) < 6:
        raise HTTPException(400, "Password must contain at least 6 characters")

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                data.name,
                data.email.lower(),
                hash_password(data.password),
                role,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Email already exists")

    conn.close()

    return {
        "message": "Registration successful",
        "user_id": user_id,
        "role": role,
    }


@app.post("/auth/login")
def login(data: LoginRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE email = ?",
        (data.email.lower(),)
    )
    user = cur.fetchone()
    conn.close()

    if not user or not user["is_active"]:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(
        {
            "sub": str(user["id"]),
            "role": user["role"],
            "email": user["email"],
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user["id"],
        "role": user["role"],
    }


@app.get("/auth/me")
def me(current_user=Depends(get_current_user)):
    return current_user


# -------------------- USERS --------------------

@app.post("/users")
def create_user(
    data: CreateUser,
    current_user=Depends(require_roles("ADMIN"))
):
    role = data.role.upper()

    if role not in VALID_ROLES:
        raise HTTPException(400, "Invalid role")

    if len(data.password) < 6:
        raise HTTPException(400, "Password must contain at least 6 characters")

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO users
            (name, email, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                data.name,
                data.email.lower(),
                hash_password(data.password),
                role,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Email already exists")

    conn.close()

    add_audit_log(
        current_user["id"], "CREATE", "user", user_id,
        None, f"role={role}"
    )

    return {"message": "User created successfully", "user_id": user_id}


@app.get("/users")
def get_users(current_user=Depends(require_roles("ADMIN"))):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, email, role, is_active, created_at FROM users ORDER BY id"
    )
    users = [dict(row) for row in cur.fetchall()]
    conn.close()
    return users


# -------------------- CATEGORIES --------------------

@app.post("/categories")
def create_category(
    data: CategoryCreate,
    current_user=Depends(require_roles("ADMIN"))
):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO ticket_categories (name, description)
            VALUES (?, ?)
            """,
            (data.name, data.description),
        )
        conn.commit()
        category_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Category already exists")

    conn.close()

    add_audit_log(
        current_user["id"], "CREATE", "category", category_id,
        None, data.name
    )

    return {"message": "Category created successfully", "category_id": category_id}


@app.get("/categories")
def get_categories(current_user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ticket_categories ORDER BY id")
    categories = [dict(row) for row in cur.fetchall()]
    conn.close()
    return categories


# -------------------- TICKETS --------------------

@app.post("/tickets")
def create_ticket(
    data: TicketCreate,
    current_user=Depends(require_roles("USER", "ADMIN"))
):
    priority = data.priority.upper()

    if priority not in SLA_HOURS:
        raise HTTPException(
            400, "Priority must be LOW, MEDIUM, HIGH or CRITICAL"
        )

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM ticket_categories WHERE id = ?",
        (data.category_id,)
    )
    if not cur.fetchone():
        conn.close()
        raise HTTPException(404, "Category not found")

    created_at = datetime.now()
    deadline = created_at + timedelta(hours=SLA_HOURS[priority])

    cur.execute(
        """
        INSERT INTO tickets
        (title, description, category_id, created_by, assigned_to,
         priority, status, sla_deadline, sla_breached, created_at, updated_at)
        VALUES (?, ?, ?, ?, NULL, ?, 'OPEN', ?, 0, ?, ?)
        """,
        (
            data.title,
            data.description,
            data.category_id,
            current_user["id"],
            priority,
            deadline.isoformat(),
            created_at.isoformat(),
            created_at.isoformat(),
        ),
    )

    conn.commit()
    ticket_id = cur.lastrowid
    conn.close()

    add_audit_log(
        current_user["id"], "CREATE", "ticket", ticket_id,
        None, f"status=OPEN, priority={priority}"
    )

    return {
        "message": "Ticket created successfully",
        "ticket_id": ticket_id,
        "status": "OPEN",
        "priority": priority,
        "sla_deadline": deadline.isoformat(),
    }


@app.get("/tickets")
def get_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user=Depends(get_current_user)
):
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT
            t.*,
            u.name AS creator_name,
            e.name AS engineer_name,
            c.name AS category_name
        FROM tickets t
        JOIN users u ON t.created_by = u.id
        LEFT JOIN users e ON t.assigned_to = e.id
        JOIN ticket_categories c ON t.category_id = c.id
        WHERE 1=1
    """
    values = []

    if current_user["role"] == "USER":
        query += " AND t.created_by = ?"
        values.append(current_user["id"])
    elif current_user["role"] == "ENGINEER":
        query += " AND t.assigned_to = ?"
        values.append(current_user["id"])

    if status:
        status = status.upper()
        if status not in VALID_STATUSES:
            conn.close()
            raise HTTPException(400, "Invalid status")
        query += " AND t.status = ?"
        values.append(status)

    if priority:
        priority = priority.upper()
        if priority not in SLA_HOURS:
            conn.close()
            raise HTTPException(400, "Invalid priority")
        query += " AND t.priority = ?"
        values.append(priority)

    query += " ORDER BY t.id DESC"

    cur.execute(query, values)
    tickets = [dict(row) for row in cur.fetchall()]
    conn.close()

    return tickets


@app.get("/tickets/{ticket_id}")
def get_single_ticket(
    ticket_id: int,
    current_user=Depends(get_current_user)
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if current_user["role"] == "USER" and ticket["created_by"] != current_user["id"]:
        raise HTTPException(403, "You can only view your own tickets")

    if current_user["role"] == "ENGINEER" and ticket["assigned_to"] != current_user["id"]:
        raise HTTPException(403, "You can only view tickets assigned to you")

    return dict(ticket)


@app.put("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    current_user=Depends(require_roles("USER", "ENGINEER", "ADMIN"))
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if current_user["role"] == "USER" and ticket["created_by"] != current_user["id"]:
        raise HTTPException(403, "You can only update your own tickets")

    if current_user["role"] == "ENGINEER" and ticket["assigned_to"] != current_user["id"]:
        raise HTTPException(403, "You can only update assigned tickets")

    title = data.title if data.title is not None else ticket["title"]
    description = (
        data.description
        if data.description is not None
        else ticket["description"]
    )
    priority = (
        data.priority.upper()
        if data.priority is not None
        else ticket["priority"]
    )

    if priority not in SLA_HOURS:
        raise HTTPException(400, "Invalid priority")

    conn = get_connection()
    cur = conn.cursor()

    # Recalculate SLA when priority changes.
    deadline = datetime.fromisoformat(ticket["sla_deadline"])
    if priority != ticket["priority"]:
        deadline = datetime.now() + timedelta(hours=SLA_HOURS[priority])

    cur.execute(
        """
        UPDATE tickets
        SET title = ?, description = ?, priority = ?,
            sla_deadline = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            title,
            description,
            priority,
            deadline.isoformat(),
            datetime.now().isoformat(),
            ticket_id,
        ),
    )
    conn.commit()
    conn.close()

    add_audit_log(
        current_user["id"], "UPDATE", "ticket", ticket_id,
        f"priority={ticket['priority']}",
        f"priority={priority}"
    )

    return {"message": "Ticket updated successfully"}


# -------------------- ASSIGNMENT --------------------

@app.patch("/tickets/{ticket_id}/assign")
def assign_engineer(
    ticket_id: int,
    data: AssignEngineer,
    current_user=Depends(require_roles("ADMIN"))
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, role FROM users WHERE id = ? AND is_active = 1",
        (data.engineer_id,)
    )
    engineer = cur.fetchone()

    if not engineer:
        conn.close()
        raise HTTPException(404, "Engineer not found")

    if engineer["role"] != "ENGINEER":
        conn.close()
        raise HTTPException(400, "Selected user is not an engineer")

    old_status = ticket["status"]

    if "ASSIGNED" not in STATUS_TRANSITIONS.get(old_status, []):
        conn.close()
        raise HTTPException(
            400,
            f"Cannot assign a ticket from status {old_status}"
        )

    now = datetime.now().isoformat()

    cur.execute(
        """
        UPDATE tickets
        SET assigned_to = ?, status = 'ASSIGNED', updated_at = ?
        WHERE id = ?
        """,
        (data.engineer_id, now, ticket_id),
    )

    cur.execute(
        """
        INSERT INTO notifications
        (user_id, ticket_id, message, is_read, created_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (
            data.engineer_id,
            ticket_id,
            f"Ticket #{ticket_id} has been assigned to you",
            now,
        ),
    )

    conn.commit()
    conn.close()

    add_audit_log(
        current_user["id"], "ASSIGN", "ticket", ticket_id,
        f"assigned_to={ticket['assigned_to']}",
        f"assigned_to={data.engineer_id}"
    )

    return {
        "message": "Engineer assigned successfully",
        "ticket_id": ticket_id,
        "engineer_id": data.engineer_id,
        "status": "ASSIGNED",
    }


# -------------------- STATUS --------------------

@app.patch("/tickets/{ticket_id}/status")
def update_status(
    ticket_id: int,
    data: StatusUpdate,
    current_user=Depends(require_roles("ENGINEER", "ADMIN"))
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if current_user["role"] == "ENGINEER" and ticket["assigned_to"] != current_user["id"]:
        raise HTTPException(403, "Ticket is not assigned to you")

    new_status = data.status.upper()

    if new_status not in VALID_STATUSES:
        raise HTTPException(400, "Invalid ticket status")

    old_status = ticket["status"]

    if new_status not in STATUS_TRANSITIONS.get(old_status, []):
        raise HTTPException(
            400,
            f"Invalid transition: {old_status} -> {new_status}"
        )

    resolved_at = ticket["resolved_at"]
    closed_at = ticket["closed_at"]

    if new_status == "RESOLVED":
        resolved_at = datetime.now().isoformat()

    if new_status == "CLOSED":
        closed_at = datetime.now().isoformat()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE tickets
        SET status = ?, resolved_at = ?, closed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            new_status,
            resolved_at,
            closed_at,
            datetime.now().isoformat(),
            ticket_id,
        ),
    )

    conn.commit()
    conn.close()

    add_audit_log(
        current_user["id"], "STATUS_CHANGE", "ticket", ticket_id,
        old_status, new_status
    )

    return {
        "message": "Ticket status updated",
        "ticket_id": ticket_id,
        "status": new_status,
    }


# -------------------- COMMENTS --------------------

@app.post("/tickets/{ticket_id}/comments")
def add_comment(
    ticket_id: int,
    data: CommentCreate,
    current_user=Depends(require_roles("USER", "ENGINEER", "ADMIN"))
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if current_user["role"] == "USER" and ticket["created_by"] != current_user["id"]:
        raise HTTPException(403, "You can only comment on your own tickets")

    if current_user["role"] == "ENGINEER" and ticket["assigned_to"] != current_user["id"]:
        raise HTTPException(403, "You can only comment on assigned tickets")

    if not data.comment.strip():
        raise HTTPException(400, "Comment cannot be empty")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO ticket_comments
        (ticket_id, user_id, comment, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            ticket_id,
            current_user["id"],
            data.comment,
            datetime.now().isoformat(),
        ),
    )

    comment_id = cur.lastrowid
    conn.commit()
    conn.close()

    add_audit_log(
        current_user["id"], "COMMENT", "ticket", ticket_id,
        None, data.comment
    )

    return {
        "message": "Comment added successfully",
        "comment_id": comment_id,
    }


@app.get("/tickets/{ticket_id}/comments")
def get_comments(
    ticket_id: int,
    current_user=Depends(get_current_user)
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if current_user["role"] == "USER" and ticket["created_by"] != current_user["id"]:
        raise HTTPException(403, "Access denied")

    if current_user["role"] == "ENGINEER" and ticket["assigned_to"] != current_user["id"]:
        raise HTTPException(403, "Access denied")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            tc.id,
            tc.ticket_id,
            tc.user_id,
            u.name AS user_name,
            tc.comment,
            tc.created_at
        FROM ticket_comments tc
        JOIN users u ON tc.user_id = u.id
        WHERE tc.ticket_id = ?
        ORDER BY tc.id
        """,
        (ticket_id,),
    )

    comments = [dict(row) for row in cur.fetchall()]
    conn.close()

    return comments


# -------------------- SLA --------------------

@app.get("/tickets/{ticket_id}/sla")
def check_sla(
    ticket_id: int,
    current_user=Depends(get_current_user)
):
    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    deadline = datetime.fromisoformat(ticket["sla_deadline"])
    breached = (
        datetime.now() > deadline
        and ticket["status"] not in ["RESOLVED", "CLOSED"]
    )

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tickets SET sla_breached = ? WHERE id = ?",
        (1 if breached else 0, ticket_id),
    )
    conn.commit()
    conn.close()

    return {
        "ticket_id": ticket_id,
        "sla_status": "BREACHED" if breached else "ON_TIME",
        "deadline": ticket["sla_deadline"],
    }


# -------------------- NOTIFICATIONS --------------------

@app.get("/notifications")
def get_notifications(current_user=Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (current_user["id"],),
    )

    notifications = [dict(row) for row in cur.fetchall()]
    conn.close()
    return notifications


@app.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user=Depends(get_current_user)
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM notifications WHERE id = ?",
        (notification_id,),
    )
    notification = cur.fetchone()

    if not notification:
        conn.close()
        raise HTTPException(404, "Notification not found")

    if notification["user_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(403, "Access denied")

    cur.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ?",
        (notification_id,),
    )

    conn.commit()
    conn.close()

    return {"message": "Notification marked as read"}


# -------------------- AUDIT LOGS --------------------

@app.get("/audit-logs")
def get_audit_logs(current_user=Depends(require_roles("ADMIN"))):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            a.*,
            u.name AS user_name
        FROM audit_logs a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
        """
    )

    logs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return logs
