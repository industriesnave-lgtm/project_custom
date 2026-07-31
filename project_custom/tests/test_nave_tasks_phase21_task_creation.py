"""Phase 5.1 — dashboard task creation for office staff."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="staff@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.flags = types.SimpleNamespace(in_migrate=False)

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: ["Employee"]
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
		get_single_value=MagicMock(return_value="Nave Industries"),
		exists=MagicMock(return_value=False),
		set_value=MagicMock(),
		sql=MagicMock(return_value=((0,),)),
		has_column=MagicMock(return_value=True),
		table_exists=MagicMock(return_value=True),
	)
	frappe.get_doc = MagicMock()
	frappe.get_list = MagicMock(return_value=[])
	frappe.get_all = MagicMock(return_value=[])
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.utils = types.ModuleType("frappe.utils")
	frappe.utils.cint = lambda v: int(float(v or 0))
	frappe.utils.flt = lambda v: float(v or 0)
	frappe.utils.nowdate = lambda: "2026-07-31"
	frappe.utils.now_datetime = lambda: "2026-07-31 21:00:00"
	frappe.utils.add_days = lambda d, n: d
	frappe.utils.getdate = lambda d: d

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		pass

	document.Document = Document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = frappe.utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return frappe


_install_fake_frappe()

from project_custom.nave_task_utils import (  # noqa: E402
	build_task_permission_condition,
	is_restricted_department,
	user_can_access_task,
)


class TestRestrictedDepartmentHelpers(unittest.TestCase):
	def test_exact_restricted_names_only(self):
		self.assertTrue(is_restricted_department("HR"))
		self.assertTrue(is_restricted_department("Human Resources"))
		self.assertTrue(is_restricted_department("Accounts"))
		self.assertTrue(is_restricted_department("Finance"))
		# No substring / keyword heuristics.
		self.assertFalse(is_restricted_department("Finance Team"))
		self.assertFalse(is_restricted_department("hr"))
		self.assertFalse(is_restricted_department("Sales"))
		self.assertFalse(is_restricted_department(""))
		self.assertFalse(is_restricted_department(None))


class TestParticipantVisibility(unittest.TestCase):
	def test_participant_can_access_non_restricted(self):
		self.assertTrue(
			user_can_access_task(
				user="viewer@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Ops",
				is_participant=True,
			)
		)

	def test_participant_cannot_unlock_restricted_department(self):
		self.assertFalse(
			user_can_access_task(
				user="viewer@example.com",
				assigned_to="hr.owner@example.com",
				owner="hr.owner@example.com",
				assigned_by="hr.owner@example.com",
				department="HR",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
				is_participant=True,
			)
		)

	def test_query_participant_excludes_restricted_departments(self):
		sql = build_task_permission_condition(
			"staff@example.com",
			is_admin=False,
			is_director=False,
			is_manager=False,
			department="Sales",
			escape=lambda v: f"'{v}'",
		)
		self.assertIn("tabNAVE Task Update", sql)
		self.assertIn("update_by", sql)
		self.assertIn("NOT IN", sql)
		self.assertIn("'HR'", sql)
		self.assertIn("'Finance'", sql)


class TestCreateTaskApi(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		import importlib

		import project_custom.api.nave_task as api

		importlib.reload(api)
		self.api = api
		self.frappe.session.user = "staff@example.com"
		self.frappe.get_roles = lambda user=None: {
			"staff@example.com": ["Employee"],
			"peer@example.com": ["Employee"],
			"hr.user@example.com": ["Employee"],
			"disabled@example.com": ["Employee"],
			"outsider@example.com": ["Website User"],
		}.get(user or self.frappe.session.user, ["Employee"])

	def _mock_assignee_lookups(
		self,
		*,
		assignee="peer@example.com",
		enabled=1,
		user_type="System User",
		assignee_dept="Sales",
		assignee_company="Nave Industries",
		actor_dept="Sales",
		actor_company="Nave Industries",
	):
		def get_value(doctype, name=None, fieldname=None, as_dict=False, **kwargs):
			filters = name if isinstance(name, dict) else None
			if doctype == "User":
				return types.SimpleNamespace(
					name=assignee if not isinstance(name, str) else name,
					enabled=enabled,
					user_type=user_type,
				)
			if doctype == "Employee":
				user_id = None
				if filters:
					user_id = filters.get("user_id")
				if user_id == "staff@example.com":
					row = types.SimpleNamespace(
						name="EMP-STAFF",
						department=actor_dept,
						company=actor_company,
						employee_name="Staff",
					)
				elif user_id == assignee or user_id == "peer@example.com":
					row = types.SimpleNamespace(
						name="EMP-PEER",
						department=assignee_dept,
						company=assignee_company,
						employee_name="Peer",
					)
				elif user_id == "hr.user@example.com":
					row = types.SimpleNamespace(
						name="EMP-HR",
						department="HR",
						company=assignee_company,
						employee_name="HR User",
					)
				else:
					row = None
				return row
			if doctype == "Project":
				return assignee_company
			return None

		self.frappe.db.get_value = MagicMock(side_effect=get_value)
		self.frappe.db.has_column = MagicMock(return_value=True)

	def test_staff_can_create_and_assign_to_office_peer(self):
		self._mock_assignee_lookups()
		created = types.SimpleNamespace(
			name="NT-2026-01001",
			subject="Prepare report",
			assigned_to="peer@example.com",
			status="Open",
			progress=0,
			as_dict=lambda: {
				"name": "NT-2026-01001",
				"subject": "Prepare report",
				"assigned_to": "peer@example.com",
				"status": "Open",
				"progress": 0,
			},
			insert=MagicMock(),
		)
		doc_factory = MagicMock(return_value=created)
		self.frappe.get_doc = doc_factory
		with (
			patch.object(self.api, "_create_history_entry", return_value=None),
			patch.object(self.api, "get_user_full_name", return_value="Staff"),
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", return_value=False),
			patch.object(self.api, "serialize_task", return_value={"name": "NT-2026-01001"}),
		):
			result = self.api.create_task(
				subject="Prepare report",
				assigned_to="peer@example.com",
				priority="High",
				due_date="2026-08-05",
				description="Need summary",
			)
		self.assertTrue(result["ok"])
		self.assertEqual(result["task"], "NT-2026-01001")
		created.insert.assert_called_once()
		payload = doc_factory.call_args.args[0]
		self.assertEqual(payload["assigned_by"], "staff@example.com")
		self.assertEqual(payload["assigned_to"], "peer@example.com")

	def test_cannot_assign_disabled_user(self):
		self._mock_assignee_lookups(assignee="disabled@example.com", enabled=0)
		with (
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", return_value=False),
		):
			with self.assertRaises(self.frappe.ValidationError):
				self.api.create_task(
					subject="X",
					assigned_to="disabled@example.com",
					priority="Medium",
					due_date="2026-08-05",
				)

	def test_cannot_assign_restricted_hr_department(self):
		self._mock_assignee_lookups(
			assignee="hr.user@example.com",
			assignee_dept="HR",
		)
		with (
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", return_value=False),
		):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.create_task(
					subject="Payroll check",
					assigned_to="hr.user@example.com",
					priority="Medium",
					due_date="2026-08-05",
				)

	def test_cannot_cross_company_assign(self):
		self._mock_assignee_lookups(
			assignee_company="Other Co",
			actor_company="Nave Industries",
		)
		with (
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", return_value=False),
		):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.create_task(
					subject="Cross",
					assigned_to="peer@example.com",
					priority="Low",
					due_date="2026-08-05",
				)

	def test_creator_and_assignee_visibility_helpers(self):
		self.assertTrue(
			user_can_access_task(
				user="staff@example.com",
				assigned_to="peer@example.com",
				owner="staff@example.com",
				assigned_by="staff@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)
		self.assertTrue(
			user_can_access_task(
				user="peer@example.com",
				assigned_to="peer@example.com",
				owner="staff@example.com",
				assigned_by="staff@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)
		self.assertFalse(
			user_can_access_task(
				user="stranger@example.com",
				assigned_to="peer@example.com",
				owner="staff@example.com",
				assigned_by="staff@example.com",
				department="HR",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)
		self.assertTrue(
			user_can_access_task(
				user="admin@example.com",
				assigned_to="peer@example.com",
				owner="staff@example.com",
				assigned_by="staff@example.com",
				department="HR",
				is_admin=True,
				is_manager=False,
				user_department=None,
			)
		)


class TestCreateTaskUiAssets(unittest.TestCase):
	def test_new_task_button_and_api(self):
		js = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "page"
			/ "nave_tasks"
			/ "nave_tasks.js"
		).read_text()
		self.assertIn("nt-new-task", js)
		self.assertIn("open_new_task_dialog", js)
		self.assertIn("project_custom.api.nave_task.create_task", js)
		self.assertIn("Assign To", js)
		self.assertIn("Due Date", js)


if __name__ == "__main__":
	unittest.main()
