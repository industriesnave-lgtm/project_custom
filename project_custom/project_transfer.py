import json

import frappe
from frappe.model.rename_doc import get_dynamic_link_map, get_link_fields
from frappe.utils import now_datetime


def _require_system_manager():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            "Only System Manager can perform Project transfers."
        )


def _validate_projects(source_project, target_project):
    if source_project == target_project:
        frappe.throw(
            "Source and target Project cannot be the same."
        )

    if not frappe.db.exists("Project", source_project):
        frappe.throw(
            f"Source Project not found: {source_project}"
        )

    if not frappe.db.exists("Project", target_project):
        frappe.throw(
            f"Target Project not found: {target_project}"
        )

    target_status = frappe.db.get_value(
        "Project",
        target_project,
        "status",
    )

    if target_status != "Open":
        frappe.throw(
            f"Target Project must be Open. "
            f"Current status: {target_status}"
        )


def _transfer_confirmation(
    source_project,
    target_project,
    expected_count,
):
    return (
        f"TRANSFER {source_project} TO "
        f"{target_project} COUNT {expected_count}"
    )


def _direct_link_plan(source_project, target_project):
    results = []

    for field in get_link_fields("Project"):
        doctype = field["parent"]
        fieldname = field["fieldname"]
        issingle = bool(field.get("issingle"))

        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            continue

        if meta.is_virtual:
            continue

        if issingle:
            try:
                values = frappe.db.get_singles_dict(doctype)
            except Exception:
                continue

            if values.get(fieldname) == source_project:
                results.append({
                    "link_type": "direct_single",
                    "doctype": doctype,
                    "fieldname": fieldname,
                    "name": doctype,
                    "is_child": False,
                    "is_single": True,
                    "docstatus": None,
                    "source_project": source_project,
                    "target_project": target_project,
                })

            continue

        if not frappe.db.table_exists(doctype):
            continue

        table = f"tab{doctype}"

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
                "link_type": "direct",
                "doctype": doctype,
                "fieldname": fieldname,
                "name": record.get("name"),
                "is_child": bool(meta.istable),
                "is_single": False,
                "docstatus": record.get("docstatus"),
                "source_project": source_project,
                "target_project": target_project,
            }

            if meta.istable:
                item.update({
                    "parent": record.get("parent"),
                    "parenttype": record.get("parenttype"),
                    "parentfield": record.get("parentfield"),
                })
            else:
                item["status"] = record.get("status")

            results.append(item)

    return results


def _dynamic_link_plan(source_project, target_project):
    results = []

    dynamic_fields = get_dynamic_link_map().get(
        "Project",
        [],
    )

    for df in dynamic_fields:
        doctype = df.parent
        fieldname = df.fieldname
        type_field = df.options

        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            continue

        if meta.is_virtual:
            continue

        if meta.issingle:
            try:
                values = frappe.db.get_singles_dict(doctype)
            except Exception:
                continue

            if (
                values.get(type_field) == "Project"
                and values.get(fieldname) == source_project
            ):
                results.append({
                    "link_type": "dynamic_single",
                    "doctype": doctype,
                    "fieldname": fieldname,
                    "dynamic_type_field": type_field,
                    "name": doctype,
                    "is_child": False,
                    "is_single": True,
                    "docstatus": None,
                    "source_project": source_project,
                    "target_project": target_project,
                })

            continue

        if not frappe.db.table_exists(doctype):
            continue

        table = f"tab{doctype}"

        try:
            rows = frappe.db.sql(
                f"""
                SELECT *
                FROM `{table}`
                WHERE `{type_field}` = %s
                  AND `{fieldname}` = %s
                """,
                ("Project", source_project),
                as_dict=True,
            )
        except Exception:
            continue

        for record in rows:
            item = {
                "link_type": "dynamic",
                "doctype": doctype,
                "fieldname": fieldname,
                "dynamic_type_field": type_field,
                "name": record.get("name"),
                "is_child": bool(meta.istable),
                "is_single": False,
                "docstatus": record.get("docstatus"),
                "source_project": source_project,
                "target_project": target_project,
            }

            if meta.istable:
                item.update({
                    "parent": record.get("parent"),
                    "parenttype": record.get("parenttype"),
                    "parentfield": record.get("parentfield"),
                })
            else:
                item["status"] = record.get("status")

            results.append(item)

    return results


@frappe.whitelist()
def scan_project_links(project):
    _require_system_manager()

    if not frappe.db.exists("Project", project):
        frappe.throw(
            f"Project not found: {project}"
        )

    direct = _direct_link_plan(project, project)
    dynamic = _dynamic_link_plan(project, project)

    summary = {}

    for row in direct + dynamic:
        key = (
            row["link_type"],
            row["doctype"],
            row["fieldname"],
        )

        if key not in summary:
            summary[key] = {
                "link_type": row["link_type"],
                "doctype": row["doctype"],
                "fieldname": row["fieldname"],
                "count": 0,
            }

        summary[key]["count"] += 1

    return sorted(
        summary.values(),
        key=lambda x: (
            x["doctype"],
            x["fieldname"],
            x["link_type"],
        ),
    )


@frappe.whitelist()
def plan_project_transfer(
    source_project,
    target_project,
):
    _require_system_manager()
    _validate_projects(
        source_project,
        target_project,
    )

    results = (
        _direct_link_plan(
            source_project,
            target_project,
        )
        + _dynamic_link_plan(
            source_project,
            target_project,
        )
    )

    return sorted(
        results,
        key=lambda x: (
            x.get("link_type") or "",
            x.get("doctype") or "",
            x.get("parent") or "",
            x.get("name") or "",
            x.get("fieldname") or "",
        ),
    )


def _update_direct_group(
    doctype,
    fieldname,
    names,
    source_project,
    target_project,
):
    names = list(dict.fromkeys(names))

    if not names:
        return 0

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
            f"Unsafe direct field detected: "
            f"{doctype}.{fieldname}"
        )

    table = f"tab{doctype}"
    placeholders = ", ".join(["%s"] * len(names))

    frappe.db.sql(
        f"""
        UPDATE `{table}`
        SET `{fieldname}` = %s
        WHERE `{fieldname}` = %s
          AND `name` IN ({placeholders})
        """,
        [
            target_project,
            source_project,
            *names,
        ],
    )

    changed = frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `{table}`
        WHERE `{fieldname}` = %s
          AND `name` IN ({placeholders})
        """,
        [
            target_project,
            *names,
        ],
    )[0][0]

    if changed != len(names):
        frappe.throw(
            f"Verification failed for "
            f"{doctype}.{fieldname}: "
            f"expected {len(names)}, found {changed}"
        )

    return changed


def _update_dynamic_group(
    doctype,
    fieldname,
    type_field,
    names,
    source_project,
    target_project,
):
    names = list(dict.fromkeys(names))

    if not names:
        return 0

    if not frappe.db.table_exists(doctype):
        frappe.throw(
            f"Table disappeared during transfer: {doctype}"
        )

    meta = frappe.get_meta(doctype)
    value_df = meta.get_field(fieldname)
    type_df = meta.get_field(type_field)

    if (
        not value_df
        or value_df.fieldtype != "Dynamic Link"
        or value_df.options != type_field
    ):
        frappe.throw(
            f"Unsafe Dynamic Link field detected: "
            f"{doctype}.{fieldname}"
        )

    if not type_df:
        frappe.throw(
            f"Dynamic Link type field missing: "
            f"{doctype}.{type_field}"
        )

    table = f"tab{doctype}"
    placeholders = ", ".join(["%s"] * len(names))

    frappe.db.sql(
        f"""
        UPDATE `{table}`
        SET `{fieldname}` = %s
        WHERE `{type_field}` = %s
          AND `{fieldname}` = %s
          AND `name` IN ({placeholders})
        """,
        [
            target_project,
            "Project",
            source_project,
            *names,
        ],
    )

    changed = frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `{table}`
        WHERE `{type_field}` = %s
          AND `{fieldname}` = %s
          AND `name` IN ({placeholders})
        """,
        [
            "Project",
            target_project,
            *names,
        ],
    )[0][0]

    if changed != len(names):
        frappe.throw(
            f"Dynamic Link verification failed for "
            f"{doctype}.{fieldname}: "
            f"expected {len(names)}, found {changed}"
        )

    return changed


@frappe.whitelist(methods=["POST"])
def execute_project_transfer(
    source_project,
    target_project,
    expected_count,
    confirmation,
):
    """
    Transfer Project references without deleting the source Project.

    Covers:
    - Direct Link -> Project
    - Dynamic Link -> Project
    - Single DocType direct links
    - Single DocType dynamic links

    Safety:
    - POST only
    - System Manager only
    - Target Project must be Open
    - Exact expected row count required
    - Exact confirmation required
    - One DB transaction
    - Rollback on failure
    - Final zero-link verification
    - Private audit JSON
    """

    _require_system_manager()
    _validate_projects(
        source_project,
        target_project,
    )

    try:
        expected_count = int(expected_count)
    except (TypeError, ValueError):
        frappe.throw(
            "expected_count must be an integer."
        )

    plan = plan_project_transfer(
        source_project=source_project,
        target_project=target_project,
    )

    actual_count = len(plan)

    if actual_count != expected_count:
        frappe.throw(
            f"Transfer plan changed. "
            f"Expected {expected_count} row(s), "
            f"but current plan has {actual_count}. "
            f"Run the dry-run again."
        )

    expected_confirmation = _transfer_confirmation(
        source_project,
        target_project,
        expected_count,
    )

    if confirmation != expected_confirmation:
        frappe.throw(
            "Invalid confirmation. Expected: "
            + expected_confirmation
        )

    if not plan:
        return {
            "success": True,
            "message": "No Project links found to transfer.",
            "source_project": source_project,
            "target_project": target_project,
            "planned_rows": 0,
            "updated_rows": 0,
            "remaining_links": 0,
        }

    savepoint = "project_transfer_before_updates"
    frappe.db.savepoint(savepoint)

    audit = {
        "source_project": source_project,
        "target_project": target_project,
        "confirmation": confirmation,
        "expected_count": expected_count,
        "executed_by": frappe.session.user,
        "executed_at": str(now_datetime()),
        "planned_rows": actual_count,
        "records": plan,
    }

    try:
        groups = {}

        for row in plan:
            key = (
                row["link_type"],
                row["doctype"],
                row["fieldname"],
                row.get("dynamic_type_field"),
            )

            groups.setdefault(key, []).append(row)

        updated_rows = 0
        update_summary = []

        for key, rows in groups.items():
            (
                link_type,
                doctype,
                fieldname,
                type_field,
            ) = key

            if link_type == "direct":
                changed = _update_direct_group(
                    doctype,
                    fieldname,
                    [r["name"] for r in rows],
                    source_project,
                    target_project,
                )

            elif link_type == "dynamic":
                changed = _update_dynamic_group(
                    doctype,
                    fieldname,
                    type_field,
                    [r["name"] for r in rows],
                    source_project,
                    target_project,
                )

            elif link_type == "direct_single":
                doc = frappe.get_doc(doctype)

                if doc.get(fieldname) != source_project:
                    frappe.throw(
                        f"Single value changed before transfer: "
                        f"{doctype}.{fieldname}"
                    )

                doc.set(fieldname, target_project)
                doc.flags.ignore_mandatory = True
                doc.flags.ignore_links = True
                doc.save(ignore_permissions=True)

                changed = 1

            elif link_type == "dynamic_single":
                values = frappe.db.get_singles_dict(
                    doctype
                )

                if (
                    values.get(type_field) != "Project"
                    or values.get(fieldname)
                    != source_project
                ):
                    frappe.throw(
                        f"Single Dynamic Link changed before "
                        f"transfer: {doctype}.{fieldname}"
                    )

                frappe.db.sql(
                    """
                    UPDATE `tabSingles`
                    SET `value` = %s
                    WHERE `doctype` = %s
                      AND `field` = %s
                      AND `value` = %s
                    """,
                    (
                        target_project,
                        doctype,
                        fieldname,
                        source_project,
                    ),
                )

                changed = 1

            else:
                frappe.throw(
                    f"Unknown link type: {link_type}"
                )

            updated_rows += changed

            update_summary.append({
                "link_type": link_type,
                "doctype": doctype,
                "fieldname": fieldname,
                "updated": changed,
            })

        remaining = plan_project_transfer(
            source_project=source_project,
            target_project=target_project,
        )

        if remaining:
            frappe.throw(
                f"Transfer verification failed. "
                f"{len(remaining)} Project link(s) still "
                f"point to {source_project}."
            )

        audit["updated_rows"] = updated_rows
        audit["update_summary"] = update_summary
        audit["verification_remaining"] = 0
        audit["success"] = True

        timestamp = now_datetime().strftime(
            "%Y%m%d-%H%M%S"
        )

        audit_file = frappe.get_doc({
            "doctype": "File",
            "file_name": (
                f"project-transfer-"
                f"{source_project}-to-"
                f"{target_project}-"
                f"{timestamp}.json"
            ),
            "is_private": 1,
            "content": json.dumps(
                audit,
                indent=2,
                default=str,
            ),
        })

        audit_file.insert(
            ignore_permissions=True
        )

        return {
            "success": True,
            "source_project": source_project,
            "target_project": target_project,
            "planned_rows": actual_count,
            "updated_rows": updated_rows,
            "remaining_links": 0,
            "audit_file": audit_file.file_url,
            "summary": update_summary,
        }

    except Exception:
        frappe.db.rollback(
            save_point=savepoint
        )
        raise
