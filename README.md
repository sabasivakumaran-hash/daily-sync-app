# Temple Sync - Income & Expense Application

A web application built with Python, Flask, and SQLite for managing daily transactions, categorizing financial activities, and generating reports for **Sri Ganesh Temple Society of British Columbia**.

---

## Key Features

* **Daily Activity Logging:** Fast transaction entry with session tracking (AM/PM), auto-calculated totals, and dynamic person name completion.
* **Financial Reports:** 
  * *Income vs. Expense Summary* with monthly breakdowns.
  * *Fiscal Year Analysis* tailored to the Jan 26 – Jan 25 fiscal cycle.
  * *Detailed Activity Matrix* with category grouping.
* **Interactive Dashboard:** Dynamic charts and Key Performance Indicators (KPIs) built for admin financial oversight.
* **Data Maintenance:** Full CRUD control over category and activity lookup tables.
* **Role-Based Access Control (RBAC):** Authenticated access using `Flask-Login` with distinct `admin` and `user` privileges.
* **Export Options:** Report views formatted for Excel, PDF, and direct printing.

---

## Tech Stack

* **Backend:** Python 3, Flask, Flask-Login, SQLite3, Werkzeug
* **Frontend:** Jinja2 Templates, Bootstrap 5, FontAwesome 6, Custom CSS/JS
* **Deployment:** Hosted on PythonAnywhere

---

## Project Structure

```text
daily-sync-app/
├── app.py                  # Main Flask application and routing logic
├── daily_sync.db           # SQLite database engine
├── requirements.txt        # Python package dependencies
├── README.md               # Project documentation
├── static/
│   ├── css/
│   │   └── style.css       # Custom application styling
│   └── js/
│       └── inactivity_timer.js # Client-side session management
└── templates/
    ├── base.html           # Core layout wrapper and navigation bar
    ├── login.html          # Authentication view
    ├── daily_activity.html # Transaction entry and activity logs
    ├── dashboard.html      # Financial KPI dashboard
    ├── reports.html        # Comprehensive financial reports
    ├── category_lookup.html# Category maintenance lookup table
    └── activity_lookup.html# Activity maintenance lookup table