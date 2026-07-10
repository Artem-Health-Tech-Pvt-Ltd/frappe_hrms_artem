// Redirect to BMC HRMS workspace on first /desk load
$(document).ready(function() {
    setTimeout(function() {
        const path = window.location.pathname;
        if (path === '/desk' || path === '/desk/' || path === '/') {
            window.location.replace('/desk/bmc-hrms');
        }
    }, 1500);
});