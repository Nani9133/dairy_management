frappe.pages["dairy-route-planner"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "Route Planner",
        single_column: true
    });

    $(wrapper).find(".layout-main-section").html(`
        <div style="padding: 20px;">
            <h3>Route Planner</h3>
            <p>Route Planner page loaded successfully.</p>
        </div>
    `);
};
