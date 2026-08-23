from datetime import datetime
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

# ---------------------------------------------------------
# RBAC DECORATOR HELPERS
# ---------------------------------------------------------
def role_required(role_name):
    """Decorator to enforce specific role permissions on routes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role_name:
                flash('Unauthorized access privileges required.', 'danger')
                return redirect(url_for('daily_activity_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator to enforce admin access on sensitive routes."""
    return role_required('admin')(f)

# ---------------------------------------------------------
# DATE PARSER HELPER
# ---------------------------------------------------------
def parse_date_components(date_str):
    """Normalizes incoming date strings (MM/DD/YYYY, M/D/YYYY, YYYY-MM-DD) into YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    try:
        if '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 3:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{y:04d}-{m:02d}-{d:02d}"
        elif '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, IndexError):
        pass
    return None

# ---------------------------------------------------------
# JINJA TEMPLATE FILTERS
# ---------------------------------------------------------
def format_currency(value):
    """Formats numerical values as CAD/USD currency."""
    if value is None:
        value = 0.0
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

def ui_date_filter(value):
    """Converts DB date (YYYY-MM-DD) to UI display date (MM/DD/YYYY)."""
    if not value:
        return ""
    try:
        if '-' in str(value):
            parts = str(value).split('-')
            if len(parts) == 3:
                return f"{int(parts[1]):02d}/{int(parts[2]):02d}/{parts[0]}"
    except (ValueError, IndexError):
        pass
    return str(value)

def format_date(value, fmt='%Y-%m-%d'):
    """Formats date objects or strings into custom display formats."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return value
    return value.strftime(fmt)

def badge_session_filter(value):
    """Renders Session Badge (1 = AM, 0 = PM)."""
    try:
        val = int(value) if value is not None else 1
    except (ValueError, TypeError):
        val = 1
    if val == 1:
        return '<span class="badge bg-light text-dark border">AM</span>'
    return '<span class="badge bg-light text-dark border">PM</span>'

def badge_type_filter(value):
    """Renders Transaction Type Badge (1 = Income, 0 = Expense)."""
    try:
        val = int(value) if value is not None else 1
    except (ValueError, TypeError):
        val = 1
        
    if val == 1:
        return '<span class="badge bg-success">INCOME</span>'
    return '<span class="badge bg-danger">EXPENSE</span>'

def badge_status_filter(value):
    """Renders Record Status Badge (1 = Active, 0 = Inactive)."""
    try:
        val = int(value) if value is not None else 1
    except (ValueError, TypeError):
        val = 1
        
    if val == 1:
        return '<span class="badge bg-success">Active</span>'
    return '<span class="badge bg-danger">Inactive</span>'