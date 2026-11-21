
import requests
import streamlit as st

# -------------------- CONFIGURATION --------------------

st.set_page_config(
    page_title="Helpdesk Ticketing System",
    page_icon="🎫",
    layout="wide",
)

DEFAULT_API_URL = "http://127.0.0.1:8000"

if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None


# -------------------- API HELPER --------------------

def api_request(method, endpoint, data=None, params=None):
    """Send a request to the FastAPI backend."""
    base_url = st.session_state.get(
        "api_url", DEFAULT_API_URL
    ).rstrip("/")

    headers = {}
    if st.session_state.token:
        headers["Authorization"] = (
            f"Bearer {st.session_state.token}"
        )

    try:
        response = requests.request(
            method=method,
            url=f"{base_url}{endpoint}",
            json=data,
            params=params,
            headers=headers,
            timeout=10,
        )

        try:
            result = response.json()
        except ValueError:
            result = response.text

        if response.ok:
            return True, result

        detail = (
            result.get("detail", result)
            if isinstance(result, dict)
            else result
        )
        return False, f"HTTP {response.status_code}: {detail}"

    except requests.exceptions.ConnectionError:
        return False, (
            "Cannot connect to FastAPI. Start the backend using "
            "'uvicorn main:app --reload'."
        )
    except requests.exceptions.Timeout:
        return False, "The API request timed out."
    except requests.exceptions.RequestException as exc:
        return False, str(exc)


def show_result(success, result):
    if success:
        st.success("Request completed successfully.")
        if result is not None:
            st.json(result)
    else:
        st.error(str(result))


def get_categories():
    ok, data = api_request("GET", "/categories")
    if ok and isinstance(data, list):
        return data
    if not ok:
        st.error(str(data))
    return []


# -------------------- HEADER --------------------

st.title("🎫 Helpdesk IT Support System")
st.caption(
    "Manage support tickets, engineers, priorities, comments and SLAs."
)

with st.sidebar:
    st.header("Configuration")
    st.text_input(
        "FastAPI Base URL",
        value=st.session_state.get("api_url", DEFAULT_API_URL),
        key="api_url",
        help="Example: http://127.0.0.1:8000",
    )
    st.markdown("---")


# -------------------- LOGIN / REGISTRATION --------------------

if not st.session_state.token:
    login_tab, register_tab = st.tabs(
        ["🔐 Login", "📝 Register"]
    )

    with login_tab:
        st.subheader("Login to your account")

        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input(
                "Password", type="password"
            )
            login_clicked = st.form_submit_button(
                "Login", type="primary"
            )

        if login_clicked:
            ok, result = api_request(
                "POST",
                "/auth/login",
                {
                    "email": email.strip(),
                    "password": password,
                },
            )

            if ok and isinstance(result, dict):
                st.session_state.token = result["access_token"]

                # Get the logged-in user's actual profile.
                profile_ok, profile = api_request(
                    "GET", "/auth/me"
                )

                if profile_ok:
                    st.session_state.user = profile
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.session_state.token = None
                    st.error(str(profile))
            else:
                st.error(str(result))

    with register_tab:
        st.subheader("Create a user account")
        st.info(
            "Public registration creates a USER account. "
            "Admin and engineer accounts should be created "
            "through an authorized admin account."
        )

        with st.form("register_form"):
            reg_name = st.text_input("Full name")
            reg_email = st.text_input("Registration email")
            reg_password = st.text_input(
                "Password (minimum 6 characters)",
                type="password",
            )
            register_clicked = st.form_submit_button(
                "Register"
            )

        if register_clicked:
            if not reg_name.strip() or not reg_email.strip():
                st.warning("Enter your name and email.")
            elif len(reg_password) < 6:
                st.warning(
                    "Password must contain at least 6 characters."
                )
            else:
                ok, result = api_request(
                    "POST",
                    "/auth/register",
                    {
                        "name": reg_name.strip(),
                        "email": reg_email.strip(),
                        "password": reg_password,
                        "role": "USER",
                    },
                )
                show_result(ok, result)

    st.stop()


# -------------------- LOGGED-IN USER --------------------

user = st.session_state.user or {}
role = user.get("role", "USER")
user_name = user.get("name", "User")

with st.sidebar:
    st.success(f"Logged in: {user_name}")
    st.write(f"**Role:** {role}")

    if st.button("Logout", use_container_width=True):
        st.session_state.token = None
        st.session_state.user = None
        st.rerun()

    st.markdown("---")

    pages = [
        "Dashboard",
        "View Tickets",
        "Create Ticket",
        "Update Ticket",
        "Comments & SLA",
        "Notifications",
    ]

    if role == "ADMIN":
        pages += [
            "Manage Users",
            "Manage Categories",
            "Audit Logs",
        ]

    page = st.radio("Navigation", pages)


# -------------------- DASHBOARD --------------------

if page == "Dashboard":
    st.header("📊 Dashboard")

    ok, tickets = api_request("GET", "/tickets")

    if ok and isinstance(tickets, list):
        total = len(tickets)
        open_count = sum(
            t.get("status") == "OPEN" for t in tickets
        )
        progress_count = sum(
            t.get("status") == "IN_PROGRESS"
            for t in tickets
        )
        resolved_count = sum(
            t.get("status") in ["RESOLVED", "CLOSED"]
            for t in tickets
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Tickets", total)
        c2.metric("Open", open_count)
        c3.metric("In Progress", progress_count)
        c4.metric("Resolved / Closed", resolved_count)

        st.subheader("Recent Tickets")
        if tickets:
            st.dataframe(
                tickets[:10],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No tickets available yet.")
    else:
        st.error(str(tickets))


# -------------------- VIEW TICKETS --------------------

elif page == "View Tickets":
    st.header("📋 View Tickets")

    c1, c2 = st.columns(2)
    with c1:
        status_filter = st.selectbox(
            "Filter by status",
            [
                "All",
                "OPEN",
                "ASSIGNED",
                "IN_PROGRESS",
                "WAITING_FOR_USER",
                "RESOLVED",
                "CLOSED",
            ],
        )
    with c2:
        priority_filter = st.selectbox(
            "Filter by priority",
            ["All", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
        )

    params = {}
    if status_filter != "All":
        params["status"] = status_filter
    if priority_filter != "All":
        params["priority"] = priority_filter

    if st.button("Refresh Tickets"):
        st.rerun()

    ok, tickets = api_request(
        "GET", "/tickets", params=params
    )

    if ok and isinstance(tickets, list):
        if tickets:
            st.dataframe(
                tickets,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No tickets match these filters.")

        st.subheader("View One Ticket")
        ticket_id = st.number_input(
            "Ticket ID",
            min_value=1,
            step=1,
            key="view_ticket_id",
        )

        if st.button("Get Ticket Details"):
            detail_ok, detail = api_request(
                "GET", f"/tickets/{int(ticket_id)}"
            )
            show_result(detail_ok, detail)
    else:
        st.error(str(tickets))


# -------------------- CREATE TICKET --------------------

elif page == "Create Ticket":
    st.header("➕ Create Support Ticket")

    if role not in ["USER", "ADMIN"]:
        st.warning(
            "Your role cannot create tickets through this API."
        )
    else:
        categories = get_categories()

        if not categories:
            st.info(
                "No categories found. Ask an admin to create "
                "a category first."
            )
        else:
            category_map = {
                f'{c["name"]} (ID: {c["id"]})': c["id"]
                for c in categories
            }

            with st.form("create_ticket_form"):
                title = st.text_input(
                    "Ticket title",
                    placeholder="Laptop is not starting",
                )
                description = st.text_area(
                    "Describe the issue"
                )
                category_label = st.selectbox(
                    "Category", list(category_map.keys())
                )
                priority = st.selectbox(
                    "Priority",
                    ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    index=1,
                )
                create_clicked = st.form_submit_button(
                    "Create Ticket",
                    type="primary",
                )

            if create_clicked:
                if not title.strip() or not description.strip():
                    st.warning(
                        "Title and description are required."
                    )
                else:
                    ok, result = api_request(
                        "POST",
                        "/tickets",
                        {
                            "title": title.strip(),
                            "description": description.strip(),
                            "category_id": category_map[
                                category_label
                            ],
                            "priority": priority,
                        },
                    )
                    show_result(ok, result)


# -------------------- UPDATE / ASSIGN / STATUS --------------------

elif page == "Update Ticket":
    st.header("🛠️ Update and Manage Tickets")

    ticket_id = st.number_input(
        "Ticket ID",
        min_value=1,
        step=1,
        key="manage_ticket_id",
    )

    st.subheader("Update Ticket Details — PUT")

    with st.form("update_ticket_form"):
        new_title = st.text_input("New title (optional)")
        new_description = st.text_area(
            "New description (optional)"
        )
        new_priority = st.selectbox(
            "Priority",
            ["Keep existing", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
        )
        update_clicked = st.form_submit_button(
            "Update Ticket"
        )

    if update_clicked:
        payload = {}
        if new_title.strip():
            payload["title"] = new_title.strip()
        if new_description.strip():
            payload["description"] = new_description.strip()
        if new_priority != "Keep existing":
            payload["priority"] = new_priority

        if not payload:
            st.warning("Enter at least one field to update.")
        else:
            ok, result = api_request(
                "PUT",
                f"/tickets/{int(ticket_id)}",
                payload,
            )
            show_result(ok, result)

    st.markdown("---")
    st.subheader("Change Ticket Status — PATCH")

    status_options = [
        "ASSIGNED",
        "IN_PROGRESS",
        "WAITING_FOR_USER",
        "RESOLVED",
        "CLOSED",
    ]

    with st.form("status_form"):
        new_status = st.selectbox(
            "New status", status_options
        )
        status_clicked = st.form_submit_button(
            "Update Status"
        )

    if status_clicked:
        ok, result = api_request(
            "PATCH",
            f"/tickets/{int(ticket_id)}/status",
            {"status": new_status},
        )
        show_result(ok, result)

    if role == "ADMIN":
        st.markdown("---")
        st.subheader("Assign Engineer — PATCH")

        ok, users = api_request("GET", "/users")

        if ok and isinstance(users, list):
            engineers = [
                u for u in users
                if u.get("role") == "ENGINEER"
                and u.get("is_active")
            ]

            if engineers:
                engineer_map = {
                    f'{e["name"]} (ID: {e["id"]})': e["id"]
                    for e in engineers
                }

                with st.form("assign_form"):
                    engineer_label = st.selectbox(
                        "Select engineer",
                        list(engineer_map.keys()),
                    )
                    assign_clicked = st.form_submit_button(
                        "Assign Ticket"
                    )

                if assign_clicked:
                    ok, result = api_request(
                        "PATCH",
                        f"/tickets/{int(ticket_id)}/assign",
                        {
                            "engineer_id": engineer_map[
                                engineer_label
                            ]
                        },
                    )
                    show_result(ok, result)
            else:
                st.info(
                    "No active engineers found. Create an "
                    "ENGINEER account under Manage Users."
                )
        else:
            st.error(str(users))


# -------------------- COMMENTS AND SLA --------------------

elif page == "Comments & SLA":
    st.header("💬 Comments and SLA")

    ticket_id = st.number_input(
        "Ticket ID",
        min_value=1,
        step=1,
        key="comment_ticket_id",
    )

    st.subheader("Add Comment — POST")

    with st.form("comment_form"):
        comment = st.text_area("Write a comment")
        comment_clicked = st.form_submit_button(
            "Add Comment"
        )

    if comment_clicked:
        if not comment.strip():
            st.warning("Comment cannot be empty.")
        else:
            ok, result = api_request(
                "POST",
                f"/tickets/{int(ticket_id)}/comments",
                {"comment": comment.strip()},
            )
            show_result(ok, result)

    st.subheader("View Comments — GET")

    if st.button("Load Comments"):
        ok, result = api_request(
            "GET", f"/tickets/{int(ticket_id)}/comments"
        )
        if ok:
            if result:
                st.dataframe(
                    result,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No comments yet.")
        else:
            st.error(str(result))

    st.subheader("Check SLA — GET")

    if st.button("Check SLA"):
        ok, result = api_request(
            "GET", f"/tickets/{int(ticket_id)}/sla"
        )
        show_result(ok, result)


# -------------------- NOTIFICATIONS --------------------

elif page == "Notifications":
    st.header("🔔 Notifications")

    ok, notifications = api_request(
        "GET", "/notifications"
    )

    if ok and isinstance(notifications, list):
        if not notifications:
            st.info("You have no notifications.")
        else:
            st.dataframe(
                notifications,
                use_container_width=True,
                hide_index=True,
            )

            unread = [
                n for n in notifications
                if not n.get("is_read")
            ]

            if unread:
                notification_map = {
                    (
                        f'ID {n["id"]}: {n.get("message", "")}'
                    ): n["id"]
                    for n in unread
                }

                selected = st.selectbox(
                    "Select unread notification",
                    list(notification_map.keys()),
                )

                if st.button("Mark as Read"):
                    notification_id = notification_map[selected]
                    ok, result = api_request(
                        "PATCH",
                        f"/notifications/{notification_id}/read",
                    )
                    show_result(ok, result)
                    if ok:
                        st.rerun()
    else:
        st.error(str(notifications))


# -------------------- ADMIN: USERS --------------------

elif page == "Manage Users" and role == "ADMIN":
    st.header("👥 Manage Users")

    with st.form("create_user_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        password = st.text_input(
            "Temporary password", type="password"
        )
        new_role = st.selectbox(
            "Role", ["USER", "ENGINEER", "ADMIN"]
        )
        create_user_clicked = st.form_submit_button(
            "Create User"
        )

    if create_user_clicked:
        if not name.strip() or not email.strip():
            st.warning("Name and email are required.")
        elif len(password) < 6:
            st.warning("Password must have at least 6 characters.")
        else:
            ok, result = api_request(
                "POST",
                "/users",
                {
                    "name": name.strip(),
                    "email": email.strip(),
                    "password": password,
                    "role": new_role,
                },
            )
            show_result(ok, result)

    st.subheader("All Users")

    if st.button("Load Users"):
        ok, result = api_request("GET", "/users")
        if ok:
            st.dataframe(
                result,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.error(str(result))


# -------------------- ADMIN: CATEGORIES --------------------

elif page == "Manage Categories" and role == "ADMIN":
    st.header("🗂️ Manage Categories")

    with st.form("category_form"):
        category_name = st.text_input("Category name")
        category_description = st.text_area(
            "Description (optional)"
        )
        category_clicked = st.form_submit_button(
            "Create Category"
        )

    if category_clicked:
        if not category_name.strip():
            st.warning("Category name is required.")
        else:
            ok, result = api_request(
                "POST",
                "/categories",
                {
                    "name": category_name.strip(),
                    "description": (
                        category_description.strip() or None
                    ),
                },
            )
            show_result(ok, result)

    st.subheader("Existing Categories")

    if st.button("Load Categories"):
        ok, result = api_request("GET", "/categories")
        if ok:
            st.dataframe(
                result,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.error(str(result))


# -------------------- ADMIN: AUDIT LOGS --------------------

elif page == "Audit Logs" and role == "ADMIN":
    st.header("🧾 Audit Logs")

    if st.button("Load Audit Logs"):
        ok, result = api_request("GET", "/audit-logs")
        if ok:
            if result:
                st.dataframe(
                    result,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No audit logs available.")
        else:
            st.error(str(result))


# -------------------- FALLBACK --------------------

else:
    st.warning(
        "This page is not available for your current role."
    )
