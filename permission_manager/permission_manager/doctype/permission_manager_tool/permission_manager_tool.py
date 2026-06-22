from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.permissions import copy_perms, get_all_perms


PERMISSION_FIELDS = (
	"permlevel",
	"if_owner",
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
)

ACCESS_PARENT_TYPES = ("Page", "Report", "Workspace")
RIGHT_FIELDS = tuple(field for field in PERMISSION_FIELDS if field not in ("permlevel", "if_owner"))


class PermissionManagerTool(Document):
	pass


def _require_system_manager() -> None:
	frappe.only_for("System Manager")


def _clean_role_name(value: str | None) -> str:
	return " ".join((value or "").strip().split())


def _effective_permissions(role: str) -> list[frappe._dict]:
	return list(get_all_perms(role) or [])


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_roles(doctype, txt, searchfield, start, page_len, filters):
	_require_system_manager()
	return frappe.db.sql(
		"""
		select name, case when desk_access = 1 then 'Desk Access' else 'Portal Only' end
		from `tabRole`
		where disabled = 0 and name like %(txt)s
		order by name
		limit %(start)s, %(page_len)s
		""",
		{"txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


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
	doctypes = {row.parent for row in permissions if row.get("parent")}
	access_rules = frappe.db.count(
		"Has Role",
		filters={"role": role, "parenttype": ["in", ACCESS_PARENT_TYPES]},
	)
	return {
		"role": role,
		"doctype_count": len(doctypes),
		"permission_rows": len(permissions),
		"access_rules": access_rules,
	}


def _as_list(value) -> list:
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return list(value or [])


@frappe.whitelist()
def apply_bulk_permissions(
	role: str,
	doctypes,
	permissions,
	replace_existing: int | str = 0,
) -> dict:
	_require_system_manager()
	role = _clean_role_name(role)
	if not role or not frappe.db.exists("Role", role):
		frappe.throw(_("Please select a valid target role."))

	selected_doctypes = list(dict.fromkeys(str(value).strip() for value in _as_list(doctypes) if value))
	selected_permissions = [value for value in _as_list(permissions) if value in RIGHT_FIELDS]
	if not selected_doctypes:
		frappe.throw(_("Please select at least one Document Type."))
	if not selected_permissions:
		frappe.throw(_("Please select at least one permission."))

	valid_doctypes = set(
		frappe.get_all(
			"DocType",
			filters={"name": ["in", selected_doctypes], "istable": 0},
			pluck="name",
		)
	)
	invalid_doctypes = [doctype for doctype in selected_doctypes if doctype not in valid_doctypes]
	if invalid_doctypes:
		frappe.throw(_("Invalid Document Types: {0}").format(", ".join(invalid_doctypes)))

	created = 0
	updated = 0
	for doctype in selected_doctypes:
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype}):
			copy_perms(doctype)

		permission_name = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
			"name",
		)
		if permission_name:
			permission_doc = frappe.get_doc("Custom DocPerm", permission_name)
			updated += 1
		else:
			permission_doc = frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": doctype,
					"role": role,
					"permlevel": 0,
					"if_owner": 0,
				}
			)
			created += 1

		if frappe.utils.cint(replace_existing):
			for right in RIGHT_FIELDS:
				permission_doc.set(right, 0)
		for right in selected_permissions:
			permission_doc.set(right, 1)

		if permission_doc.is_new():
			permission_doc.insert(ignore_permissions=True)
		else:
			permission_doc.save(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)

	frappe.clear_cache()
	return {
		"role": role,
		"doctype_count": len(selected_doctypes),
		"permissions": selected_permissions,
		"created": created,
		"updated": updated,
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
	new_role = frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": new_role_name,
			"desk_access": source.desk_access,
			"two_factor_auth": source.two_factor_auth,
			"restrict_to_domain": source.restrict_to_domain,
			"home_page": source.home_page,
			"disabled": 0,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)

	permissions = _effective_permissions(source_role)
	prepared_doctypes: set[str] = set()
	permission_count = 0
	for permission in permissions:
		parent = permission.get("parent")
		if not parent:
			continue

		# Once a DocType has any Custom DocPerm rows, Frappe uses those rows for
		# every role. Copy standard rows first so existing roles keep their access.
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
		access_rows = frappe.get_all(
			"Has Role",
			filters={"role": source_role, "parenttype": ["in", ACCESS_PARENT_TYPES]},
			fields=["parent", "parenttype", "parentfield"],
		)
		for row in access_rows:
			if frappe.db.exists(
				"Has Role",
				{
					"parent": row.parent,
					"parenttype": row.parenttype,
					"parentfield": row.parentfield,
					"role": new_role.name,
				},
			):
				continue
			child = frappe.new_doc("Has Role")
			child.update(
				{
					"parent": row.parent,
					"parenttype": row.parenttype,
					"parentfield": row.parentfield,
					"role": new_role.name,
				}
			)
			child.set_new_name()
			child.db_insert()
			access_count += 1

	for doctype in prepared_doctypes:
		frappe.clear_cache(doctype=doctype)
	frappe.clear_cache()

	return {
		"role": new_role.name,
		"doctype_count": len(prepared_doctypes),
		"permission_rows": permission_count,
		"access_rules": access_count,
	}
