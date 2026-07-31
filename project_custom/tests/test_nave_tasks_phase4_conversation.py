"""Phase A/B conversation and Director permission tests."""

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
	frappe.session = types.SimpleNamespace(user="Guest")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.flags = types.SimpleNamespace(in_migrate=False, in_install=False, in_patch=False)

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: []
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
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
	frappe.utils.nowdate = lambda: "2026-07-29"
	frappe.utils.now_datetime = lambda: "2026-07-29 12:00:00"
	frappe.utils.add_days = lambda d, n: d
	frappe.utils.getdate = lambda d: d
	frappe.utils.time_diff_in_seconds = lambda a, b: 0

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

from project_custom.nave_task_ui import (  # noqa: E402
	allowed_composer_types,
	css_class_for_update_type,
)
from project_custom.nave_task_utils import (  # noqa: E402
	INTERNAL_NOTE_TYPE,
	build_task_permission_condition,
	can_access_internal_notes,
	format_field_change_message,
	get_display_role,
	user_can_access_task,
	values_differ,
)


class TestDirectorPermissions(unittest.TestCase):
	def test_director_can_see_all_tasks(self):
		self.assertTrue(
			user_can_access_task(
				user="director@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_director=True,
				is_manager=False,
				user_department="HR",
			)
		)

	def test_director_query_condition_unrestricted(self):
		sql = build_task_permission_condition(
			"director@example.com",
			is_admin=False,
			is_director=True,
			is_manager=False,
			department=None,
			escape=lambda v: f"'{v}'",
		)
		self.assertEqual(sql, "")


class TestInternalNotes(unittest.TestCase):
	def test_employee_cannot_create_or_read_internal_note(self):
		self.assertFalse(
			can_access_internal_notes(
				is_admin=False,
				is_director=False,
				is_manager=False,
			)
		)
		types = allowed_composer_types(
			is_admin=False,
			is_director=False,
			is_manager=False,
		)
		self.assertNotIn(INTERNAL_NOTE_TYPE, types)

	def test_manager_can_create_and_read_internal_note(self):
		self.assertTrue(
			can_access_internal_notes(
				is_admin=False,
				is_director=False,
				is_manager=True,
			)
		)
		types = allowed_composer_types(
			is_admin=False,
			is_director=False,
			is_manager=True,
		)
		self.assertIn(INTERNAL_NOTE_TYPE, types)

	def test_director_can_access_internal_notes(self):
		self.assertTrue(
			can_access_internal_notes(
				is_admin=False,
				is_director=True,
				is_manager=False,
			)
		)


class TestFieldChangeLogging(unittest.TestCase):
	def test_due_date_change_message(self):
		msg = format_field_change_message("due_date", "2026-07-01", "2026-07-15")
		self.assertIn("Due Date", msg)
		self.assertIn("2026-07-01", msg)
		self.assertIn("2026-07-15", msg)

	def test_priority_change_message(self):
		msg = format_field_change_message("priority", "Low", "High")
		self.assertIn("Priority", msg)

	def test_values_differ_helpers(self):
		self.assertTrue(values_differ("Low", "High", fieldname="priority"))
		self.assertFalse(values_differ("High", "High", fieldname="priority"))
		self.assertTrue(values_differ(10, 20, fieldname="progress"))
		self.assertFalse(values_differ(10, 10.0, fieldname="progress"))

	def test_exactly_one_system_update_per_field_change(self):
		"""Simulate one System message per changed tracked field (no duplicates)."""
		before = {
			"due_date": "2026-07-01",
			"priority": "Low",
			"status": "Open",
			"progress": 0,
			"assigned_to": "emp@example.com",
		}
		after = {
			"due_date": "2026-07-15",
			"priority": "High",
			"status": "Open",
			"progress": 0,
			"assigned_to": "emp@example.com",
		}
		messages = []
		for fieldname in ("assigned_to", "status", "progress", "priority", "due_date"):
			if values_differ(before[fieldname], after[fieldname], fieldname=fieldname):
				messages.append(
					format_field_change_message(
						fieldname,
						before[fieldname],
						after[fieldname],
					)
				)

		due_msgs = [m for m in messages if "Due Date" in m]
		priority_msgs = [m for m in messages if "Priority" in m]
		self.assertEqual(len(due_msgs), 1)
		self.assertEqual(len(priority_msgs), 1)
		self.assertEqual(len(messages), 2)


class TestTimelineEnrichment(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		import importlib

		import project_custom.api.nave_task as api

		importlib.reload(api)
		self.api = api

	def test_timeline_returns_sender_full_name_and_display_role(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		task = types.SimpleNamespace(
			name="NT-2026-00001",
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			status="Working",
			progress=20,
			as_dict=lambda: {
				"name": "NT-2026-00001",
				"subject": "Test",
				"description": "Desc",
				"status": "Working",
				"progress": 20,
				"assigned_to": "emp@example.com",
				"owner": "creator@example.com",
				"assigned_by": "creator@example.com",
			},
		)
		row = {
			"name": "NTU-1",
			"task": "NT-2026-00001",
			"update_by": "mgr@example.com",
			"employee": "HR-EMP-001",
			"updated_on": "2026-07-29 10:00:00",
			"update_type": "Reply",
			"status": "Working",
			"progress": 20,
			"update_text": "Please prioritize",
			"pending_reason": "",
			"support_required": "",
			"attachment": None,
			"creation": "2026-07-29 10:00:00",
		}

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "user_can_see_internal_notes", return_value=True),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.frappe, "get_list", return_value=[row]),
			patch.object(self.api, "get_user_full_name", return_value="Manager Person"),
			patch.object(
				self.frappe.db,
				"get_value",
				side_effect=lambda *a, **k: "Manager Emp" if a and a[0] == "Employee" else None,
			),
			patch.object(self.api, "is_task_manager", return_value=True),
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
		):
			result = self.api.get_task_timeline("NT-2026-00001")

		item = result["timeline"][0]
		self.assertEqual(item["sender_full_name"], "Manager Person")
		self.assertEqual(item["display_role"], "Manager")
		self.assertEqual(item["sender_user_id"], "mgr@example.com")

	def test_employee_timeline_excludes_internal_notes(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = types.SimpleNamespace(
			name="NT-2026-00001",
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			status="Working",
			progress=20,
			as_dict=lambda: {"name": "NT-2026-00001", "subject": "T", "description": ""},
		)
		rows = [
			{
				"name": "NTU-1",
				"update_by": "mgr@example.com",
				"employee": None,
				"updated_on": "2026-07-29 10:00:00",
				"update_type": "Internal Note",
				"status": "Working",
				"progress": 20,
				"update_text": "secret",
				"creation": "2026-07-29 10:00:00",
			},
			{
				"name": "NTU-2",
				"update_by": "emp@example.com",
				"employee": None,
				"updated_on": "2026-07-29 11:00:00",
				"update_type": "Reply",
				"status": "Working",
				"progress": 20,
				"update_text": "visible",
				"creation": "2026-07-29 11:00:00",
			},
		]

		captured = {}

		def fake_get_list(*args, **kwargs):
			captured["filters"] = kwargs.get("filters")
			# Simulate DB already filtered by != Internal Note
			return [r for r in rows if r["update_type"] != "Internal Note"]

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "user_can_see_internal_notes", return_value=False),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.frappe, "get_list", side_effect=fake_get_list),
			patch.object(self.api, "get_user_full_name", return_value="Emp"),
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", return_value=False),
		):
			result = self.api.get_task_timeline("NT-2026-00001")

		self.assertEqual(len(result["timeline"]), 1)
		self.assertEqual(result["timeline"][0]["update_type"], "Reply")
		self.assertEqual(captured["filters"].get("update_type"), ["!=", "Internal Note"])

	def test_employee_cannot_post_internal_note(self):
		self.frappe.session.user = "emp@example.com"
		task = types.SimpleNamespace(
			name="NT-2026-00001",
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			status="Open",
			progress=0,
		)
		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "user_can_see_internal_notes", return_value=False),
		):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.post_task_message(
					"NT-2026-00001",
					"secret",
					update_type="Internal Note",
				)

	def test_viewer_cannot_post_progress_update_without_permission(self):
		"""P2: Progress Update must not silently succeed for non-assignees."""
		self.frappe.session.user = "creator@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = types.SimpleNamespace(
			name="NT-2026-00001",
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			status="Working",
			progress=20,
			due_date="2026-08-01",
			db_set=MagicMock(),
		)
		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "can_submit_progress_on_task", return_value=False),
			patch.object(self.api, "get_user_department", return_value="Sales"),
		):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.post_task_message(
					"NT-2026-00001",
					"Looks done",
					update_type="Progress Update",
					status="Completed",
					progress=100,
				)

	def test_display_role_and_css_helpers(self):
		self.assertEqual(
			get_display_role(
				is_admin=False,
				is_director=True,
				is_manager=False,
			),
			"Director",
		)
		self.assertEqual(css_class_for_update_type("Internal Note"), "nt-type-internal")
		self.assertEqual(css_class_for_update_type("Manager Instruction"), "nt-type-manager")


class TestDirectUpdateTypeGuards(unittest.TestCase):
	"""P1: privileged timeline types blocked on direct DocType inserts."""

	def setUp(self):
		self.frappe = _install_fake_frappe()
		import importlib

		import project_custom.project_custom.doctype.nave_task_update.nave_task_update as mod

		importlib.reload(mod)
		self.mod = mod

	def _doc(self, update_type, *, ignore_permissions=False):
		doc = self.mod.NAVETaskUpdate()
		doc.update_type = update_type
		doc.task = "NT-2026-00001"
		doc.status = "Working"
		doc.progress = 10
		doc.flags = types.SimpleNamespace(
			ignore_permissions=ignore_permissions,
			allow_privileged_nave_update_type=False,
		)
		return doc

	def test_employee_cannot_forge_system_update_type(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		doc = self._doc("System")
		with self.assertRaises(self.frappe.PermissionError):
			doc.validate_update_type_permission()

	def test_employee_cannot_forge_reassignment_or_close(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		for update_type in ("Reassignment", "Close", "Status Change", "Recurrence Event"):
			doc = self._doc(update_type)
			with self.assertRaises(self.frappe.PermissionError):
				doc.validate_update_type_permission()

	def test_employee_cannot_forge_manager_instruction(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		doc = self._doc("Manager Instruction")
		with self.assertRaises(self.frappe.PermissionError):
			doc.validate_update_type_permission()

	def test_trusted_insert_allows_system_type(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		doc = self._doc("System", ignore_permissions=True)
		doc.validate_update_type_permission()  # does not raise

	def test_employee_cannot_direct_insert_progress_without_assignment(self):
		self.frappe.session.user = "creator@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = types.SimpleNamespace(
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
		)
		doc = self._doc("Progress Update")
		with (
			patch.object(self.frappe.db, "get_value", return_value=task),
			patch(
				"project_custom.project_custom.doctype.nave_task_update.nave_task_update._employee_department",
				return_value="Sales",
			),
		):
			with self.assertRaises(self.frappe.PermissionError) as ctx:
				doc.validate_update_type_permission()
		self.assertIn("progress updates", str(ctx.exception).lower())


class TestAssetsAndPatches(unittest.TestCase):
	def test_director_patch_registered(self):
		text = (WORKSPACE / "project_custom" / "patches.txt").read_text()
		self.assertIn("v1_6.create_nave_task_director_role", text)

	def test_update_types_in_doctype(self):
		text = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "doctype"
			/ "nave_task_update"
			/ "nave_task_update.json"
		).read_text()
		for label in (
			"Clarification Required",
			"Completion Update",
			"Manager Instruction",
			"Internal Note",
		):
			self.assertIn(label, text)

	def test_ui_has_inline_composer(self):
		js = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "page"
			/ "nave_tasks"
			/ "nave_tasks.js"
		).read_text()
		self.assertIn("nt-composer", js)
		self.assertIn("post_task_message", js)
		self.assertIn("sender_full_name", js)


if __name__ == "__main__":
	unittest.main()
