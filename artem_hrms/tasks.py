import frappe
from frappe.utils import getdate, add_days, today
from datetime import datetime, timedelta

def calculate_worked_hours(checkins):
    """
    Calculates total worked hours from a chronological list of checkin logs.
    Considers only the first 'IN' and the last 'OUT' log types for the day.
    """
    in_times = [log.time for log in checkins if log.log_type == "IN"]
    out_times = [log.time for log in checkins if log.log_type == "OUT"]

    if not in_times or not out_times:
        return 0.0

    first_in_time = in_times[0]
    last_out_time = out_times[-1]

    diff = (last_out_time - first_in_time).total_seconds() / 3600.0
    if diff > 0:
        return round(diff, 2)
    return 0.0


def format_hhmm(minutes):
    if minutes is None or minutes < 0:
        return ""
    total = int(minutes)
    return f"{total // 60:02d}:{total % 60:02d}"


def minutes_between(later, earlier):
    diff = (later - earlier).total_seconds() / 60.0
    return int(round(diff))


def get_long_duration_shift_names():
    """
    Shift Types whose effective duration is effectively 24 hours.
    These are skipped when computing late arrival / early out minutes.
    A shift counts as a long-rotation when end_time is on or before start_time
    (covers both 00:00 - 23:59 anchors and shifts that wrap midnight such as
    22:00 - 06:00) so only true day-long rotations are excluded.
    """
    shifts = frappe.get_all("Shift Type", fields=["name", "start_time", "end_time"])
    long_set = set()
    for s in shifts:
        start, end = s.start_time, s.end_time
        if start is None or end is None:
            continue
        if end <= start:
            long_set.add(s.name)
    return long_set


def resolve_employee_shift_for_date(employee, target_date):
    """
    Returns the shift name applicable for this employee on this date.
    1. Active Shift Assignment on that date wins.
    2. Falls back to Employee.default_shift.
    """
    assignment = frappe.db.sql(
        """
        SELECT shift_type
        FROM `tabShift Assignment`
        WHERE employee = %(emp)s
          AND docstatus = 1
          AND status = 'Active'
          AND start_date <= %(date)s
          AND (end_date IS NULL OR end_date >= %(date)s)
        ORDER BY start_date DESC
        LIMIT 1
        """,
        {"emp": employee, "date": target_date},
        as_dict=True,
    )
    if assignment:
        return assignment[0].shift_type

    default_shift = frappe.db.get_value("Employee", employee, "default_shift")
    return default_shift or None


def get_shift_times_for_date(target_date, employee):
    """
    Returns (shift_name, start_time, end_time) for the employee on target_date,
    or (None, None, None) when no shift can be resolved.
    `start_time` / `end_time` are `datetime.time` instances matching the
    Shift Type definition.
    """
    name = resolve_employee_shift_for_date(employee, target_date)
    if not name:
        return None, None, None
    row = frappe.db.get_value(
        "Shift Type", name, ["start_time", "end_time"], as_dict=True
    )
    if not row:
        return name, None, None
    return name, row.start_time, row.end_time


def get_shift_grace_fields(shift_name):
    """
    Returns the grace/window fields from the Shift Type that the
    late_arrival / early_out logic honours. All values are minutes.
    Missing values fall back to safe defaults (0 disables the buffer).
    """
    fields = [
        "begin_check_in_before_shift_start_time",
        "late_entry_grace_period",
        "early_exit_grace_period",
    ]
    if not shift_name:
        return {"early_in_window": 0, "late_grace": 0, "early_exit_grace": 0}
    row = frappe.db.get_value("Shift Type", shift_name, fields, as_dict=True) or {}
    return {
        "early_in_window": int(row.get("begin_check_in_before_shift_start_time") or 0),
        "late_grace": int(row.get("late_entry_grace_period") or 0),
        "early_exit_grace": int(row.get("early_exit_grace_period") or 0),
    }


def _shift_window(start_time, end_time, target_date):
    """Returns (shift_start_dt, shift_end_dt) for the day. End rolls to next
    day when the shift crosses midnight (end_time <= start_time).
    """
    shift_start_dt = datetime.combine(target_date, start_time)
    shift_end_dt = datetime.combine(target_date, end_time)
    if end_time <= start_time:
        shift_end_dt += timedelta(days=1)
    return shift_start_dt, shift_end_dt


def compute_late_early(checkins, start_time, end_time, shift_name=None):
    """
    Option B: Dynamic duration balance.

    Returns ('HH:MM', 'HH:MM') for (late_arrival, early_out).
    Both values are empty strings when there is nothing to record.

    Rules:
      - Skip when the day's shift duration is >= 24 hours (handled by caller).
      - Late Arrival = max(0, first_in - shift_start_dt - late_grace).
        If first_in falls before the allowed early-in window, it is not
        counted as late (the value stays blank).
      - Early Out uses Option B logic: if the employee clocked in before or
        exactly at shift start, the expected clock-out moves to
        first_in + shift_duration (so they only owe their scheduled hours).
        Late arrivals don't get that slack — expected_end stays at
        shift_end_dt.  If the last OUT is still within early_exit_grace
        before the expected end, no early-out is recorded.
    """
    if not start_time or not end_time or not checkins:
        return "", ""

    in_logs = sorted(c.time for c in checkins if c.log_type == "IN")
    out_logs = sorted(c.time for c in checkins if c.log_type == "OUT")
    first_in = in_logs[0] if in_logs else None
    last_out = out_logs[-1] if out_logs else None
    if not first_in and not last_out:
        return "", ""

    target_date = (
        first_in.date() if first_in else last_out.date()
    )
    shift_start_dt, shift_end_dt = _shift_window(
        start_time, end_time, target_date
    )
    shift_duration = shift_end_dt - shift_start_dt

    grace = get_shift_grace_fields(shift_name)

    # --- Late Arrival ---
    late = ""
    if first_in:
        earliest_allowed = shift_start_dt - timedelta(
            minutes=grace["early_in_window"]
        )
        if first_in < earliest_allowed:
            # Outside the allowed pre-shift window — too early to count as
            # "on the way", so we don't mark a late arrival.
            late = ""
        elif first_in > shift_start_dt + timedelta(minutes=grace["late_grace"]):
            delta = first_in - (
                shift_start_dt + timedelta(minutes=grace["late_grace"])
            )
            late = format_hhmm(int(delta.total_seconds() // 60))

    # --- Early Out (Option B — dynamic) ---
    early = ""
    if last_out:
        if first_in and first_in <= shift_start_dt:
            # Arrived on-time (or early): give them back the time they
            # pre-poned the shift, so they only owe their scheduled duration.
            expected_end = first_in + shift_duration
        else:
            expected_end = shift_end_dt
        threshold = expected_end - timedelta(minutes=grace["early_exit_grace"])
        if last_out < threshold:
            delta = expected_end - last_out
            early = format_hhmm(int(delta.total_seconds() // 60))

    return late, early

def sync_attendance_for_date(target_date):
    """
    Main processing function for a single calendar date.
    Queries all active employees, calculates their attendance status based on checkin logs,
    and creates or updates Attendance records.
    """
    if isinstance(target_date, datetime):
        target_date = target_date.strftime("%Y-%m-%d")
    elif not isinstance(target_date, str):
        target_date = str(target_date)

    # 1. Fetch active employees on target_date
    employees = frappe.db.sql("""
        SELECT
            name,
            company,
            employee_name
        FROM `tabEmployee`
        WHERE status = 'Active'
        AND employment_type = 'Contract'
        AND date_of_joining IS NOT NULL
        AND date_of_joining <= %(date)s
        AND (relieving_date IS NULL OR relieving_date >= %(date)s)
    """, {"date": target_date}, as_dict=True)

    if not employees:
        return

    # 2. Fetch all checkins on target_date
    start_dt = f"{target_date} 00:00:00"
    end_dt = f"{target_date} 23:59:59"
    checkins = frappe.db.sql("""
        SELECT employee, time, log_type 
        FROM `tabEmployee Checkin` 
        WHERE time >= %(start)s AND time <= %(end)s
        ORDER BY time ASC
    """, {"start": start_dt, "end": end_dt}, as_dict=True)

    checkins_by_employee = {}
    for c in checkins:
        checkins_by_employee.setdefault(c.employee, []).append(c)

    # 3. Fetch existing attendances on target_date
    existing_attendances = frappe.db.sql("""
        SELECT name, employee, status, working_hours, docstatus 
        FROM `tabAttendance` 
        WHERE attendance_date = %(date)s
    """, {"date": target_date}, as_dict=True)
    existing_dict = {a.employee: a for a in existing_attendances}

    # 3b. Pre-compute shifts that span the whole day so we skip the
    # late-arrival / early-out marking for them.
    long_rotation_shifts = get_long_duration_shift_names()

    # 4. Process each employee
    count = 0
    for emp in employees:
        try:
            emp_checkins = checkins_by_employee.get(emp.name, [])
            
            # Extract presence of IN and OUT types
            has_in = any(c.log_type == "IN" for c in emp_checkins)
            has_out = any(c.log_type == "OUT" for c in emp_checkins)

            # Rule 1: No IN and No OUT
            if not has_in and not has_out:
                target_status = "Absent"
                worked_hours = 0.0
            
            # Rule 4: Both IN and OUT Found
            elif has_in and has_out:
                worked_hours = calculate_worked_hours(emp_checkins)
                if worked_hours > 3.5:
                    target_status = "Present"
                else:
                    target_status = "Half Day"
            
            # Rule 2 & 3: Only IN or Only OUT found
            else:
                target_status = "Half Day"
                worked_hours = 0.0

            # 4b. Late Arrival / Early Out (HH:MM) — skipped for 24h shifts
            # and when the employee has no punches to measure against.
            shift_name, shift_start, shift_end = get_shift_times_for_date(
                target_date, emp.name
            )
            if (
                shift_name not in long_rotation_shifts
                and (has_in or has_out)
                and shift_start
                and shift_end
            ):
                late_arrival, early_out = compute_late_early(
                    emp_checkins, shift_start, shift_end, shift_name=shift_name
                )
            else:
                late_arrival, early_out = "", ""

            # 5. Create or Update Attendance
            attendance = existing_dict.get(emp.name)
            if attendance:
                # If existing, check whether any field needs to change.
                if (attendance.status != target_status
                    or abs(float(attendance.working_hours or 0) - float(worked_hours)) > 0.01
                    or late_arrival
                    or early_out):

                    # Update directly in database to avoid docstatus blocks
                    frappe.db.set_value("Attendance", attendance.name, {
                        "status": target_status,
                        "working_hours": worked_hours,
                        "custom_late_arrival_minutes": late_arrival,
                        "custom_early_out_minutes": early_out,
                    }, update_modified=True)
                    frappe.clear_document_cache("Attendance", attendance.name)
            else:
                # Create a new attendance document
                att_doc = frappe.new_doc("Attendance")
                att_doc.employee = emp.name
                att_doc.employee_name = emp.employee_name
                att_doc.company = emp.company
                att_doc.attendance_date = target_date
                att_doc.status = target_status
                att_doc.working_hours = worked_hours
                att_doc.custom_late_arrival_minutes = late_arrival
                att_doc.custom_early_out_minutes = early_out
                att_doc.naming_series = "HR-ATT-.YYYY.-"
                att_doc.insert(ignore_permissions=True)
                att_doc.submit()

            count += 1
            if count % 200 == 0:
                frappe.db.commit()

        except Exception as e:
            frappe.log_error(
                title=f"Attendance Sync Failed for {emp.name} on {target_date}",
                message=frappe.get_traceback()
            )

@frappe.whitelist()
def get_sync_status():
    """
    Returns earliest check-in date, last successfully synced date, and a recommended default start date.
    """
    earliest = frappe.db.sql("SELECT MIN(time) FROM `tabEmployee Checkin`")[0][0]
    earliest_date = earliest.strftime("%Y-%m-%d") if earliest else today()

    last_synced = frappe.db.get_global("last_historical_attendance_sync_date")

    default_start = earliest_date
    if last_synced:
        default_start = add_days(last_synced, 1)
        if getdate(default_start) > getdate(today()):
            default_start = today()
    return {
        "earliest_date": earliest_date,
        "last_synced_date": last_synced,
        "default_start_date": default_start
    }

@frappe.whitelist()
def trigger_historical_attendance_sync(start_date=None, end_date=None):
    """
    Whitelisted method called from the "HR Settings" button.
    Starts the sequential background execution.
    """
    if not start_date:
        earliest = frappe.db.sql("SELECT MIN(time) FROM `tabEmployee Checkin`")[0][0]
        if earliest:
            start_date = earliest.strftime("%Y-%m-%d")
        else:
            start_date = today()

    if not end_date:
        end_date = today()

    frappe.enqueue(
        "artem_hrms.tasks.process_attendance_sequential",
        queue="long",
        start_date=start_date,
        end_date=end_date,
        current_date=start_date
    )
    return {"status": "success", "message": "Attendance sync task enqueued."}

@frappe.whitelist()
def stop_attendance_sync():
    """
    Sends a stop signal to the background sequential sync job.
    """
    frappe.db.set_global("stop_attendance_sync", "1")
    frappe.db.commit()
    return {"status": "success", "message": "Stop signal sent to the sync job."}

def process_attendance_sequential(start_date, end_date, current_date):
    """
    Sequentially processes attendance day by day using background queue enqueuing.
    Prevents system timeouts and memory exhaustion.
    Checks for stop signal before continuing.
    """
    if frappe.db.get_global("stop_attendance_sync") == "1":
        frappe.db.set_global("stop_attendance_sync", "0")
        frappe.db.commit()
        return

    if getdate(current_date) > getdate(end_date):
        return

    sync_attendance_for_date(current_date)
    
    # Record the last successfully completed date in the system globals
    frappe.db.set_global("last_historical_attendance_sync_date", str(current_date))
    frappe.db.commit()

    next_date = add_days(current_date, 1)
    if getdate(next_date) <= getdate(end_date):
        frappe.enqueue(
            "artem_hrms.tasks.process_attendance_sequential",
            queue="long",
            start_date=start_date,
            end_date=end_date,
            current_date=next_date
        )

def daily_attendance_sync():
    """
    Daily scheduler event task.
    Enqueues the actual sync job to the 'long' queue to prevent blocking the scheduler.
    """
    frappe.enqueue(
        "artem_hrms.tasks.run_daily_sync_background",
        queue="long"
    )

def run_daily_sync_background():
    """
    Runs the daily attendance synchronization for the last 3 days in the background.
    """
    today_date = today()
    for i in range(3, 0, -1):
        target_date = add_days(today_date, -i)
        sync_attendance_for_date(target_date)
        frappe.db.commit()