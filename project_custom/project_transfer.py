import frappe


def scan_project_links(project):
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
