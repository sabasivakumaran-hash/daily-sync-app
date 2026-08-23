import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, request, current_app
from flask_login import login_required

from helpers import role_required, parse_date_components

dynamic_bp = Blueprint('dynamic', __name__)

def get_db():
    """Obtain SQLite database connection factory using application configuration."""
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    if current_app.config.get('SQLITE_FOREIGN_KEYS'):
        conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@dynamic_bp.route('/reports')
@login_required
@role_required('admin')
def reports_page():
    conn = get_db()
    current_year_str = datetime.now().strftime('%Y')

    # Default report parameter set to 'income_expense'
    selected_report = request.args.get('report_type', 'income_expense')

    # Retrieve available transaction years for selectors
    years_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL AND txn_date != ''
        ORDER BY year DESC
    """).fetchall()
    available_years = [r['year'] for r in years_rows if r['year']]
    if current_year_str not in available_years:
        available_years.insert(0, current_year_str)

    # Resolve date boundaries
    selected_year = request.args.get('fiscal_year', request.args.get('year'))
    if not selected_year:
        selected_year = available_years[0] if available_years else current_year_str

    start_date_raw = request.args.get('start_date')
    end_date_raw = request.args.get('end_date')

    start_date = parse_date_components(start_date_raw) or f"{selected_year}-01-01"
    end_date = parse_date_components(end_date_raw) or f"{selected_year}-12-31"

    # Compute dynamic month buckets ('YYYY-MM' key and 'Mon YY' label)
    try:
        dt_start = datetime.strptime(start_date, '%Y-%m-%d').replace(day=1)
        dt_end = datetime.strptime(end_date, '%Y-%m-%d').replace(day=1)
    except ValueError:
        dt_start = datetime.strptime(f"{selected_year}-01-01", '%Y-%m-%d')
        dt_end = datetime.strptime(f"{selected_year}-12-31", '%Y-%m-%d')

    month_buckets = []
    curr = dt_start
    while curr <= dt_end:
        month_buckets.append({
            'key': curr.strftime('%Y-%m'),
            'label': curr.strftime('%b %y')
        })
        curr += relativedelta(months=1)

    # Data structures for Income & Expense and Fiscal Reports
    income_categories, expense_categories = {}, {}
    income_monthly_totals = {mb['key']: 0.0 for mb in month_buckets}
    expense_monthly_totals = {mb['key']: 0.0 for mb in month_buckets}
    net_monthly_surplus = {mb['key']: 0.0 for mb in month_buckets}
    total_income_period = 0.0
    total_expense_period = 0.0

    if selected_report in ['income_expense', 'fiscal_report']:
        cat_rows = conn.execute("""
            SELECT 
                c.category_name,
                CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income,
                strftime('%Y-%m', t.txn_date) as ym_key,
                SUM(t.total_amount) as total_amount
            FROM daily_activity t
            JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
            WHERE t.is_active = 1 AND t.txn_date BETWEEN ? AND ?
            GROUP BY c.category_name, is_income, ym_key
            ORDER BY c.category_name ASC
        """, (start_date, end_date)).fetchall()

        for r in cat_rows:
            cat = r['category_name'] if r['category_name'] else 'UNASSIGNED'
            is_inc = int(r['is_income'])
            ym_key = r['ym_key']
            amt = float(r['total_amount']) if r['total_amount'] else 0.0

            if ym_key not in [mb['key'] for mb in month_buckets]:
                continue

            target_dict = expense_categories if is_inc == 0 else income_categories
            if cat not in target_dict:
                target_dict[cat] = {mb['key']: 0.0 for mb in month_buckets}
                target_dict[cat]['total'] = 0.0

            target_dict[cat][ym_key] += amt
            target_dict[cat]['total'] += amt

            if is_inc == 0:
                expense_monthly_totals[ym_key] += amt
                total_expense_period += amt
            else:
                income_monthly_totals[ym_key] += amt
                total_income_period += amt

        for mb in month_buckets:
            k = mb['key']
            net_monthly_surplus[k] = income_monthly_totals[k] - expense_monthly_totals[k]

    # Data structures for Activity Summary Report
    act_summary_list = []
    act_map = {}
    cat_subtotals = {}
    grand_totals = {
        'INCOME': {mb['key']: 0.0 for mb in month_buckets},
        'EXPENSE': {mb['key']: 0.0 for mb in month_buckets},
        'NET': {mb['key']: 0.0 for mb in month_buckets}
    }
    grand_totals['INCOME']['total'] = 0.0
    grand_totals['EXPENSE']['total'] = 0.0
    grand_totals['NET']['total'] = 0.0

    if selected_report == 'activity_summary':
        activity_rows = conn.execute("""
            SELECT 
                a.activity_name,
                c.category_name,
                CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income,
                strftime('%Y-%m', t.txn_date) as ym_key,
                SUM(t.total_amount) as total_amount
            FROM daily_activity t
            JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
            WHERE t.is_active = 1 AND t.txn_date BETWEEN ? AND ?
            GROUP BY a.activity_name, c.category_name, is_income, ym_key
            ORDER BY a.activity_name ASC, c.category_name ASC
        """, (start_date, end_date)).fetchall()

        for r in activity_rows:
            act = r['activity_name']
            cat = r['category_name'] if r['category_name'] else 'UNASSIGNED'
            is_inc = int(r['is_income'])
            ym_key = r['ym_key']
            amt = float(r['total_amount']) if r['total_amount'] else 0.0

            if ym_key not in [mb['key'] for mb in month_buckets]:
                continue

            key = (act, cat)
            if key not in act_map:
                row_obj = {
                    'activity_name': act,
                    'category_name': cat,
                    'is_income': is_inc,
                    'months': {mb['key']: 0.0 for mb in month_buckets},
                    'total': 0.0
                }
                act_map[key] = row_obj
                act_summary_list.append(row_obj)

            act_map[key]['months'][ym_key] += amt
            act_map[key]['total'] += amt

            if cat not in cat_subtotals:
                cat_subtotals[cat] = {
                    'NET': {mb['key']: 0.0 for mb in month_buckets},
                    'total': 0.0
                }

            net_amt = amt if is_inc == 1 else -amt
            cat_subtotals[cat]['NET'][ym_key] += net_amt
            cat_subtotals[cat]['total'] += net_amt

            t_type = 'INCOME' if is_inc == 1 else 'EXPENSE'
            grand_totals[t_type][ym_key] += amt
            grand_totals[t_type]['total'] += amt
            grand_totals['NET'][ym_key] += net_amt
            grand_totals['NET']['total'] += net_amt

    conn.close()

    return render_template(
        'reports.html',
        selected_report=selected_report,
        selected_year=selected_year,
        available_years=available_years,
        start_date=start_date,
        end_date=end_date,
        month_buckets=month_buckets,
        income_categories=income_categories,
        expense_categories=expense_categories,
        income_monthly_totals=income_monthly_totals,
        expense_monthly_totals=expense_monthly_totals,
        net_monthly_surplus=net_monthly_surplus,
        total_income_period=total_income_period,
        total_expense_period=total_expense_period,
        net_surplus_period=(total_income_period - total_expense_period),
        act_matrix=act_summary_list,
        cat_subtotals=cat_subtotals,
        grand_totals=grand_totals
    )