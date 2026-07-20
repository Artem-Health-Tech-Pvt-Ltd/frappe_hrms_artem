from erpnext.setup.doctype.department.department import Department

class CustomDepartment(Department):
	def autoname(self):
		self.name = self.department_name

	def before_rename(self, old, new, merge=False):
		return new
