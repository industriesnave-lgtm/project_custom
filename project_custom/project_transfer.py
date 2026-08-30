import frappe


@frappe.whitelist()
def scan_project_links(project):
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Manager can scan project links.")

    if not frappe.db.exists("Project", project):
        frappe.throw(f"Project not found: {project}")

    results = []

    doctypes = frappe.get_all(
        "DocType",
        filters={
            "istable": 0,
            "issingle": 0,
        },
        fields=["name", "is_virtual"],
    )

    for row in doctypes:
        if row.get("is_virtual"):
            continue

        doctype = row["name"]

        try:
            meta = frappe.get_meta(doctype)

            project_fields = [
                df.fieldname
                for df in meta.fields
                if (
                    df.fieldtype == "Link"
                    and df.options == "Project"
                    and df.fieldname
                )
            ]

            if not project_fields:
                continue

            table = f"tab{doctype}"

            if not frappe.db.table_exists(table):
                continue

            for fieldname in project_fields:
                try:
                    count = frappe.db.sql(
                        f"""
                        SELECT COUNT(*)
                        FROM `{table}`
                        WHERE `{fieldname}` = %s
                        """,
                        (project,),
                    )[0][0]
                except Exception:
                    continue

                if count:
                    results.append({
                        "doctype": doctype,
                        "fieldname": fieldname,
                        "count": count,
                    })

        except Exception:
            continue

    return sorted(
        results,
        key=lambda x: (x["doctype"], x["fieldname"]),
    )


@frappe.whitelist()
def plan_project_transfer(source_project, target_project):
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Manager can plan project transfers.")

    if source_project == target_project:
        frappe.throw("Source and target Project cannot be the same.")

    if not frappe.db.exists("Project", source_project):
        frappe.throw(f"Source Project not found: {source_project}")

    if not frappe.db.exists("Project", target_project):
        frappe.throw(f"Target Project not found: {target_project}")

    results = []

    doctypes = frappe.get_all(
        "DocType",
        fields=["name", "istable", "issingle", "is_virtual"],
    )

    for row in doctypes:
        if row.get("is_virtual") or row.get("issingle"):
            continue

        doctype = row["name"]

        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            continue

        project_fields = [
            df.fieldname
            for df in meta.fields
            if (
                df.fieldtype == "Link"
                and df.options == "Project"
                and df.fieldname
            )
        ]

        if not project_fields:
            continue

        table = f"tab{doctype}"

        if not frappe.db.table_exists(table):
            continue

        for fieldname in project_fields:
            try:
                rows = frappe.db.sql(
                    f"""
                    SELECT *
                    FROM `{table}`
                    WHERE `{fieldname}` = %s
                    """,
                    (source_project,),
                    as_dict=True,
                )
            except Exception:
                continue

            for record in rows:
                item = {
                    "doctype": doctype,
                    "fieldname": fieldname,
                    "name": record.get("name"),
                    "is_child": bool(row.get("istable")),
                    "docstatus": record.get("docstatus"),
                    "source_project": source_project,
                    "target_project": target_project,
                }

                if row.get("istable"):
                    item.update({
                        "parent": record.get("parent"),
                        "parenttype": record.get("parenttype"),
                        "parentfield": record.get("parentfield"),
                    })
                else:
                    item["status"] = record.get("status")

                results.append(item)

    return sorted(
        results,
        key=lambda x: (
            x.get("doctype") or "",
            x.get("parent") or "",
            x.get("name") or "",
        ),
    )
