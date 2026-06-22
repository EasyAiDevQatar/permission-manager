frappe.ui.form.on("Permission Manager Tool", {
	async refresh(frm) {
		frm.disable_save();
		frm.page.set_title(__("Permission Manager"));
		frm.set_intro(
			__("Duplicate an existing role with its complete effective permission matrix."),
			"orange"
		);
		const response = await frappe.call({
			method: "permission_manager.permission_manager.doctype.permission_manager_tool.permission_manager_tool.get_role_options",
		});
		frm.set_df_property("source_role", "options", ["", ...(response.message || [])]);
		frm.set_df_property("target_role", "options", ["", ...(response.message || [])]);
		frm.refresh_field("source_role");
		frm.refresh_field("target_role");
		frm.trigger("render_summary");
	},

	async source_role(frm) {
		await frm.trigger("render_summary");
	},

	async render_summary(frm) {
		const wrapper = frm.fields_dict.summary?.$wrapper;
		if (!wrapper) return;
		if (!frm.doc.source_role) {
			wrapper.html('<div class="permission-manager-empty">Select a source role to preview its permissions.</div>');
			return;
		}

		wrapper.html('<div class="permission-manager-loading">Loading permission summary...</div>');
		try {
			const response = await frappe.call({
				method: "permission_manager.permission_manager.doctype.permission_manager_tool.permission_manager_tool.get_role_summary",
				args: { role: frm.doc.source_role },
			});
			const data = response.message || {};
			wrapper.html(`
				<div class="permission-manager-summary">
					<div><strong>${frappe.utils.escape_html(String(data.doctype_count || 0))}</strong><span>DocTypes</span></div>
					<div><strong>${frappe.utils.escape_html(String(data.permission_rows || 0))}</strong><span>Permission Rules</span></div>
					<div><strong>${frappe.utils.escape_html(String(data.access_rules || 0))}</strong><span>Page & Report Rules</span></div>
				</div>`);
		} catch (error) {
			wrapper.html('<div class="permission-manager-empty">Unable to load the role summary.</div>');
		}
	},

	duplicate_role(frm) {
		if (!frm.doc.source_role || !frm.doc.new_role_name) {
			frappe.msgprint(__("Please select a source role and enter the new role name."));
			return;
		}

		frappe.confirm(
			__("Create role <b>{0}</b> with all permissions from <b>{1}</b>?", [
				frappe.utils.escape_html(frm.doc.new_role_name),
				frappe.utils.escape_html(frm.doc.source_role),
			]),
			async () => {
				const response = await frappe.call({
					method: "permission_manager.permission_manager.doctype.permission_manager_tool.permission_manager_tool.duplicate_role",
					args: {
						source_role: frm.doc.source_role,
						new_role_name: frm.doc.new_role_name,
						copy_access_rules: frm.doc.copy_access_rules,
					},
					freeze: true,
					freeze_message: __("Duplicating role permissions..."),
				});
				const data = response.message || {};
				frappe.msgprint({
					title: __("Role Created"),
					indicator: "green",
					message: __("Role <b>{0}</b> was created with {1} permission rules across {2} DocTypes.", [
						frappe.utils.escape_html(data.role || frm.doc.new_role_name),
						data.permission_rows || 0,
						data.doctype_count || 0,
					]),
				});
				frm.set_value("new_role_name", "");
			},
		);
	},

	apply_bulk_permissions(frm) {
		const doctypes = (frm.doc.selected_doctypes || []).map((row) => row.document_type).filter(Boolean);
		const rights = [
			"select", "read", "write", "create", "delete", "submit", "cancel", "amend",
			"report", "export", "import", "share", "print", "email",
		].filter((right) => frm.doc[`allow_${right}`]);

		if (!frm.doc.target_role || !doctypes.length || !rights.length) {
			frappe.msgprint(__("Select a target role, one or more Document Types, and at least one permission."));
			return;
		}

		frappe.confirm(
			__("Apply {0} permissions to {1} Document Types for role <b>{2}</b>?", [
				rights.length,
				doctypes.length,
				frappe.utils.escape_html(frm.doc.target_role),
			]),
			async () => {
				const response = await frappe.call({
					method: "permission_manager.permission_manager.doctype.permission_manager_tool.permission_manager_tool.apply_bulk_permissions",
					args: {
						role: frm.doc.target_role,
						doctypes,
						permissions: rights,
						replace_existing: frm.doc.replace_existing,
					},
					freeze: true,
					freeze_message: __("Applying permissions..."),
				});
				const data = response.message || {};
				frappe.msgprint({
					title: __("Permissions Applied"),
					indicator: "green",
					message: __("Updated {0} Document Types for role <b>{1}</b>.", [
						data.doctype_count || 0,
						frappe.utils.escape_html(data.role || frm.doc.target_role),
					]),
				});
				frm.clear_table("selected_doctypes");
				frm.refresh_field("selected_doctypes");
			},
		);
	},
});
