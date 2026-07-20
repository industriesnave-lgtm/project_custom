from frappe import _


def get_project_dashboard(data):
    data["transactions"].append(
        {
            "label": _("Accounts"),
            "items": ["Journal Entry"],
        }
    )
    return data
