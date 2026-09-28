frappe.ui.form.on('Customer',{refresh(frm){['custom_wallet_balance','custom_customer_id'].forEach(f=>{if(frm.fields_dict[f])frm.set_df_property(f,'read_only',1)})}});
