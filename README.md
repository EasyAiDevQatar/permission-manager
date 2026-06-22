# Permission Manager

An installable Frappe/ERPNext v15 app for safely duplicating a role with its complete effective permission matrix.

## Features

- System Manager-only access.
- Copies Role desk, domain, home-page, and two-factor settings.
- Copies effective DocType permissions into Custom DocPerm safely.
- Preserves existing standard permissions when customization is required.
- Optionally copies Page, Report, and Workspace access rules.
- Shows DocType and permission totals before duplication.
- Supports English and Arabic role labels.
- Keeps Frappe's core Role Permissions Manager page unchanged.

## Install

```bash
bench get-app https://github.com/EasyAiDevQatar/permission-manager.git
bench --site your-site install-app permission_manager
bench --site your-site migrate
```

Open `/app/permission-manager-tool` after installation.
