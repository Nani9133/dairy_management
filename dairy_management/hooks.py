app_name = "dairy_management"
app_title = "Dairy Management"
app_publisher = "Vrich"
app_description = "Dairy D2C/B2B customer and delivery application"
app_email = "rajaboinasarath@gmail.com"
app_license = "MIT"

after_install = "dairy_management.setup.install.after_install"
after_migrate = "dairy_management.setup.install.after_migrate"

website_route_rules = [
    {
        "from_route": "/dairy-app",
        "to_route": "dairy-app",
    },
    {
        "from_route": "/dairy-app/<path:app_path>",
        "to_route": "dairy-app",
    },
]

app_include_css = [
    "/assets/dairy_management/css/dairy.css"
]

app_include_js = [
    "/assets/dairy_management/js/dairy_common.js"
]

doctype_js = {
    "Customer": "public/js/customer.js"
}
