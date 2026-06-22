from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.permissions import copy_perms, get_all_perms


PERMISSION_FIELDS = (
	"permlevel", "if_owner", "select", "read", "write", "create", "delete", "submit",
	"cancel", "amend", "report", "export", "import", "share", "print", "email",
)
ACCESS_PARENT_TYPES = ("Page", "Report", "Workspace")


class PermissionManagerTool(Document):
	pass


def _require_system_manager() -> None:
	frappe.only_for("System Manager")


def _clean_role_name(value: str | None) -> str:
	return " ".join((value or "").strip().split())


def _effective_permissions(role: str) -> list[frappe._dict]:
	return list(get_all_perms(role) or [])


@frappe.whitelist()
def get_role_options() -> list[str]:
	_require_system_manager()
	return frappe.get_all("Role", filters={"disabled": 0}, pluck="name", order_by="name asc")


@frappe.whitelist()
def get_role_summary(role: str) -> dict:
	_require_system_manager()
	role = _clean_role_name(role)
	if not role or not frappe.db.exists("Role", role):
		frappe.throw(_("Please select a valid source role."))
	permissions = _effective_permissions(role)
	return {
		"role": role,
		"doctype_count": len({row.parent for row in permissions if row.get("parent")}),
		"permission_rows": len(permissions),
		"access_rules": frappe.db.count("Has Role", filters={"role": role, "parenttype": ["in", ACCESS_PARENT_TYPES]}),
	}


@frappe.whitelist()
def duplicate_role(source_role: str, new_role_name: str, copy_access_rules: int | str = 1) -> dict:
	_require_system_manager()
	source_role = _clean_role_name(source_role)
	new_role_name = _clean_role_name(new_role_name)
	if not source_role or not frappe.db.exists("Role", source_role):
		frappe.throw(_("Please select a valid source role."))
	if not new_role_name:
		frappe.throw(_("Please enter the new role name."))
	if source_role.casefold() == new_role_name.casefold():
		frappe.throw(_("The new role name must be different from the source role."))
	if frappe.db.exists("Role", new_role_name):
		frappe.throw(_("A role named {0} already exists.").format(frappe.bold(new_role_name)))

	source = frappe.get_doc("Role", source_role)
	new_role = frappe.get_doc({
		"doctype": "Role", "role_name": new_role_name, "desk_access": source.desk_access,
		"two_factor_auth": source.two_factor_auth, "restrict_to_domain": source.restrict_to_domain,
		"home_page": source.home_page, "disabled": 0, "is_custom": 1,
	}).insert(ignore_permissions=True)

	prepared_doctypes: set[str] = set()
	permission_count = 0
	for permission in _effective_permissions(source_role):
		parent = permission.get("parent")
		if not parent:
			continue
		if parent not in prepared_doctypes:
			if not frappe.db.exists("Custom DocPerm", {"parent": parent}):
				copy_perms(parent)
			prepared_doctypes.add(parent)
		values = {field: permission.get(field) or 0 for field in PERMISSION_FIELDS}
		values.update({"doctype": "Custom DocPerm", "parent": parent, "role": new_role.name})
		frappe.get_doc(values).insert(ignore_permissions=True)
		permission_count += 1

	access_count = 0
	if frappe.utils.cint(copy_access_rules):
		rows = frappe.get_all("Has Role", filters={"role": source_role, "parenttype": ["in", ACCESS_PARENT_TYPES]}, fields=["parent", "parenttype", "parentfield"])
		for row in rows:
			filters = {"parent": row.parent, "parenttype": row.parenttype, "parentfield": row.parentfield, "role": new_role.name}
			if frappe.db.exists("Has Role", filters):
				continue
			child = frappe.new_doc("Has Role")
			child.update(filters)
			child.set_new_name()
			child.db_insert()
			access_count += 1

	for doctype in prepared_doctypes:
		frappe.clear_cache(doctype=doctype)
	frappe.clear_cache()
	return {"role": new_role.name, "doctype_count": len(prepared_doctypes), "permission_rows": permission_count, "access_rules": access_count}
