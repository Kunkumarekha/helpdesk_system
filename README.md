# Helpdesk / IT Support Ticketing System

A beginner-friendly industry-style Helpdesk API using only:

- Python
- FastAPI
- SQLite3
- Uvicorn
- Python standard library for authentication

No SQLAlchemy, Alembic, PyJWT, bcrypt or other third-party database/authentication libraries.

## Project Structure

```text
helpdesk_system/
├── main.py
├── database.py
├── auth.py
├── requirements.txt
├── README.md
└── helpdesk.db
```

`helpdesk.db` is created automatically when the application starts.

## Features

- User registration and login
- Password hashing using Python standard library PBKDF2-HMAC
- JWT-compatible HS256 bearer access tokens implemented with Python standard library
- Role-based access control
- Roles: USER, ENGINEER, ADMIN
- Ticket creation
- Ticket filtering
- Engineer assignment
- Ticket status workflow
- SLA calculation
- SLA breach checking
- Ticket comments
- Notifications
- Audit logs
- SQLite foreign keys
- Swagger documentation
- ReDoc documentation

## Ticket Workflow

```text
OPEN
  ↓
ASSIGNED
  ↓
IN_PROGRESS
  ↓
WAITING_FOR_USER
  ↓
IN_PROGRESS
  ↓
RESOLVED
  ↓
CLOSED
```

## SLA

```text
LOW       = 24 hours
MEDIUM    = 8 hours
HIGH      = 4 hours
CRITICAL  = 2 hours
```

## Run

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Install:

```powershell
pip install -r requirements.txt
```

Start:

```powershell
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## First user

Use:

```text
POST /auth/register
```

For initial testing you can register an ADMIN:

```json
{
  "name": "Admin",
  "email": "admin@example.com",
  "password": "Admin@123",
  "role": "ADMIN"
}
```

Then login using:

```text
POST /auth/login
```

Copy the returned `access_token`.

In Swagger click **Authorize** and enter:

```text
Bearer YOUR_TOKEN
```

Then use the protected APIs.

## Important security note

The `SECRET_KEY` in `auth.py` is for learning/demo use. Change it before using the project in a real deployment.

Also, for a production system, use a well-tested JWT/authentication library rather than maintaining cryptographic code yourself.
