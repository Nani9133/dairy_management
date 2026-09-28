import frappe

def ensure_roles():
    for role in ['Dairy Customer','Dairy Delivery Partner','Dairy Operations Manager']:
        if not frappe.db.exists('Role', role):
            frappe.get_doc({'doctype':'Role','role_name':role,'desk_access':0}).insert(ignore_permissions=True)

def customer_fields():
    fields=[
      ('custom_customer_id','Customer ID','Data',None,1),('custom_phone_number','Phone Number','Data',None,0),
      ('custom_wallet_balance','Wallet Balance','Currency',None,0),('custom_latitude','Latitude','Float',None,0),
      ('custom_longitude','Longitude','Float',None,0),('custom_status','Status','Select','Active\\nInactive\\nBlocked',0),
      ('custom_route','Route','Link','Dairy Route',0),('custom_area','Area','Link','Area',0),('custom_zone','Zone','Link','Zone',0),
      ('custom_vehicle_name','Vehicle Name','Link','Vehicle',0),('custom_house_image','House Image','Attach Image',None,0),
      ('custom_delivery_address','Delivery Address','Small Text',None,0),('custom_user','Customer User','Link','User',0)]
    for fn,label,ft,options,reqd in fields:
        if not frappe.db.exists('Custom Field',{'dt':'Customer','fieldname':fn}):
            frappe.get_doc({'doctype':'Custom Field','dt':'Customer','fieldname':fn,'label':label,'fieldtype':ft,'options':options,'reqd':reqd,'insert_after':'customer_name'}).insert(ignore_permissions=True)
    frappe.db.commit()

def after_install(): ensure_roles(); customer_fields()
def after_migrate(): ensure_roles(); customer_fields()
