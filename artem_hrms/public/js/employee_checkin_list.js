frappe.listview_settings['Employee Checkin'] = {
    onload: function(listview) {
        if (listview.page && listview.page.fields_dict) {
            // Remove 'ID' search input
            if (listview.page.fields_dict.name && listview.page.fields_dict.name.$wrapper) {
                listview.page.fields_dict.name.$wrapper.remove();
            }
            // Remove 'Employee Name' search input
            if (listview.page.fields_dict.employee_name && listview.page.fields_dict.employee_name.$wrapper) {
                listview.page.fields_dict.employee_name.$wrapper.remove();
            }
        }
    }
};