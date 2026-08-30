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

            if not frappe.db.table_exists(doctype):
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

        if not frappe.db.table_exists(doctype):
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


def _require_system_manager():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Manager can perform Project transfers.")


def _transfer_confirmation(source_project, target_project):
    return f"TRANSFER {source_project} TO {target_project}"


@frappe.whitelist(methods=["POST"])
def execute_project_transfer(
    source_project,
    target_project,
    confirmation,
):
    """
    Move every direct Link-to-Project reference from source_project
    to target_project.

    IMPORTANT:
    - POST only
    - System Manager only
    - Exact confirmation required
    - Uses one database transaction
    - Rolls back on any failure
    - Creates an audit JSON File containing every affected row
    """

    import json
    from frappe.utils import now_datetime

    _require_system_manager()

    if source_project == target_project:
        frappe.throw("Source and target Project cannot be the same.")

    if not frappe.db.exists("Project", source_project):
        frappe.throw(f"Source Project not found: {source_project}")

    if not frappe.db.exists("Project", target_project):
        frappe.throw(f"Target Project not found: {target_project}")

    expected_confirmation = _transfer_confirmation(
        source_project,
        target_project,
    )

    if confirmation != expected_confirmation:
        frappe.throw(
            "Invalid confirmation. Expected: "
            + expected_confirmation
        )

    # Rebuild the plan immediately before execution.
    plan = plan_project_transfer(
        source_project=source_project,
        target_project=target_project,
    )

    if not plan:
        return {
            "success": True,
            "message": "No Project links found to transfer.",
            "source_project": source_project,
            "target_project": target_project,
            "updated_rows": 0,
        }

    savepoint = "project_transfer_before_updates"
    frappe.db.savepoint(savepoint)

    audit = {
        "source_project": source_project,
        "target_project": target_project,
        "confirmation": confirmation,
        "executed_by": frappe.session.user,
        "executed_at": str(now_datetime()),
        "planned_rows": len(plan),
        "records": plan,
    }

    try:
        # Group rows by DocType + field so each table is updated once.
        groups = {}

        for row in plan:
            key = (
                row["doctype"],
                row["fieldname"],
            )

            groups.setdefault(key, []).append(row["name"])

        updated_rows = 0
        update_summary = []

        for (doctype, fieldname), names in groups.items():
            if not names:
                continue

            if not frappe.db.table_exists(doctype):
                frappe.throw(
                    f"Table disappeared during transfer: {doctype}"
                )

            meta = frappe.get_meta(doctype)
            field = meta.get_field(fieldname)

            if not field:
                frappe.throw(
                    f"Field disappeared during transfer: "
                    f"{doctype}.{fieldname}"
                )

            if (
                field.fieldtype != "Link"
                or field.options != "Project"
            ):
                frappe.throw(
                    f"Unsafe field detected: "
                    f"{doctype}.{fieldname}"
                )

            table = f"tab{doctype}"

            placeholders = ", ".join(["%s"] * len(names))

            params = [
                target_project,
                source_project,
                *names,
            ]

            frappe.db.sql(
                f"""
                UPDATE `{table}`
                SET `{fieldname}` = %s
                WHERE `{fieldname}` = %s
                  AND `name` IN ({placeholders})
                """,
                params,
            )

            changed = frappe.db.sql(
                f"""
                SELECT COUNT(*)
                FROM `{table}`
                WHERE `{fieldname}` = %s
                  AND `name` IN ({placeholders})
                """,
                [target_project, *names],
            )[0][0]

            if changed != len(names):
                frappe.throw(
                    f"Verification failed for "
                    f"{doctype}.{fieldname}: "
                    f"expected {len(names)}, found {changed}"
                )

            updated_rows += changed

            update_summary.append({
                "doctype": doctype,
                "fieldname": fieldname,
                "updated": changed,
            })

        # Final verification: source Project must have no remaining
        # direct Link-to-Project references.
        remaining = plan_project_transfer(
            source_project=source_project,
            target_project=target_project,
        )

        if remaining:
            frappe.throw(
                f"Transfer verification failed. "
                f"{len(remaining)} Project link(s) still point to "
                f"{source_project}."
            )

        audit["updated_rows"] = updated_rows
        audit["update_summary"] = update_summary
        audit["verification_remaining"] = 0
        audit["success"] = True

        timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")

        audit_file = frappe.get_doc({
            "doctype": "File",
            "file_name": (
                f"project-transfer-"
                f"{source_project}-to-{target_project}-"
                f"{timestamp}.json"
            ),
            "is_private": 1,
            "content": json.dumps(
                audit,
                indent=2,
                default=str,
            ),
        })

        audit_file.insert(ignore_permissions=True)

        return {
            "success": True,
            "source_project": source_project,
            "target_project": target_project,
            "planned_rows": len(plan),
            "updated_rows": updated_rows,
            "remaining_links": 0,
            "audit_file": audit_file.file_url,
            "summary": update_summary,
        }

    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
