import frappe
from frappe.utils import getdate, add_days, today
from datetime import datetime

def calculate_worked_hours(checkins):
	"""
	Calculates total worked hours from a chronological list of checkin logs.
	Pairs consecutive 'IN' and 'OUT' log types.
	"""
	total_hours = 0.0
	last_in_time = None

	for log in checkins:
		if log.log_type == "IN":
			last_in_time = log.time
		elif log.log_type == "OUT" and last_in_time:
			diff = (log.time - last_in_time).total_seconds() / 3600.0
			if diff > 0:
				total_hours += diff
			last_in_time = None

	return round(total_hours, 2)

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
		SELECT name, company, employee_name 
		FROM `tabEmployee` 
		WHERE status = 'Active' 
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

	# 4. Process each employee
	count = 0
	for emp in employees:
		try:
			emp_checkins = checkins_by_employee.get(emp.name, [])
			
			if not emp_checkins:
				target_status = "Absent"
				worked_hours = 0.0
			else:
				# Check log types
				has_in = any(c.log_type == "IN" for c in emp_checkins)
				has_out = any(c.log_type == "OUT" for c in emp_checkins)

				if has_in:
					if not has_out:
						# If IN is there but OUT is not there, mark Present
						target_status = "Present"
						worked_hours = 0.0
					else:
						worked_hours = calculate_worked_hours(emp_checkins)
						if worked_hours > 3.5:
							target_status = "Present"
						else:
							target_status = "Half Day"
				else:
					# Checkins exist, but no "IN" log_type. Default to Half Day.
					worked_hours = 0.0
					target_status = "Half Day"

			# 5. Create or Update Attendance
			attendance = existing_dict.get(emp.name)
			if attendance:
				# If existing, check if status or working_hours has changed
				if (attendance.status != target_status or 
					abs(float(attendance.working_hours or 0) - float(worked_hours)) > 0.01):
					
					# Update directly in database to avoid docstatus blocks
					frappe.db.set_value("Attendance", attendance.name, {
						"status": target_status,
						"working_hours": worked_hours
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
