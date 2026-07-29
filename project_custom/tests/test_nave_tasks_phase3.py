"""Phase 3 NAVE Tasks recurrence tests (pure helpers + mocked generation rules)."""

from __future__ import annotations

import sys
import types
import unittest
from datetime import date
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
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: ["System Manager"]
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
	frappe.get_all = MagicMock(return_value=[])
	frappe.get_list = MagicMock(return_value=[])
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *x, **y: None)
	frappe.log_error = MagicMock()
	frappe.get_traceback = lambda: "traceback"

	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v: float(v or 0)
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.getdate = lambda d: d
	utils.add_days = lambda d, n: d
	frappe.utils = utils

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		pass

	document.Document = Document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return frappe


_install_fake_frappe()

from project_custom.nave_task_recurrence import (  # noqa: E402
	add_months,
	add_years,
	build_generated_subject,
	calculate_due_date,
	next_occurrence_date,
	normalize_support_required,
	should_stop_recurrence,
	validate_recurrence_config,
)
from project_custom.nave_task_utils import user_can_manage_task  # noqa: E402


class TestDateCalculations(unittest.TestCase):
	def test_daily(self):
		self.assertEqual(
			next_occurrence_date("Daily", date(2026, 7, 29)),
			date(2026, 7, 30),
		)

	def test_weekly(self):
		self.assertEqual(
			next_occurrence_date("Weekly", date(2026, 7, 29)),
			date(2026, 8, 5),
		)

	def test_monthly(self):
		self.assertEqual(
			next_occurrence_date("Monthly", date(2026, 1, 15)),
			date(2026, 2, 15),
		)

	def test_month_end_handling(self):
		self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
		self.assertEqual(add_months(date(2024, 1, 31), 1), date(2024, 2, 29))

	def test_yearly(self):
		self.assertEqual(
			next_occurrence_date("Yearly", date(2026, 7, 29)),
			date(2027, 7, 29),
		)

	def test_leap_year_handling(self):
		self.assertEqual(add_years(date(2024, 2, 29), 1), date(2025, 2, 28))
		self.assertEqual(add_years(date(2024, 2, 29), 4), date(2028, 2, 29))

	def test_due_date_calculation(self):
		self.assertEqual(calculate_due_date(date(2026, 7, 29), 3), date(2026, 8, 1))
		self.assertEqual(calculate_due_date(date(2026, 7, 29), 0), date(2026, 7, 29))


class TestStopConditions(unittest.TestCase):
	def test_end_date_stop(self):
		self.assertTrue(
			should_stop_recurrence(
				is_recurring=1,
				recurrence_active=1,
				status="Open",
				recurrence_end_date="2026-07-01",
				occurrence=date(2026, 7, 29),
			)
		)

	def test_disabled_stop(self):
		self.assertTrue(
			should_stop_recurrence(
				is_recurring=1,
				recurrence_active=0,
				status="Open",
				recurrence_end_date=None,
				occurrence=date(2026, 7, 29),
			)
		)

	def test_closed_cancelled_stop(self):
		self.assertTrue(
			should_stop_recurrence(
				is_recurring=1,
				recurrence_active=1,
				status="Closed",
				recurrence_end_date=None,
				occurrence=date(2026, 7, 29),
			)
		)
		self.assertTrue(
			should_stop_recurrence(
				is_recurring=1,
				recurrence_active=1,
				status="Cancelled",
				recurrence_end_date=None,
				occurrence=date(2026, 7, 29),
			)
		)

	def test_active_continues(self):
		self.assertFalse(
			should_stop_recurrence(
				is_recurring=1,
				recurrence_active=1,
				status="Open",
				recurrence_end_date="2026-12-31",
				occurrence=date(2026, 7, 29),
			)
		)


class TestValidationAndCompatibility(unittest.TestCase):
	def test_existing_non_recurring_compatible(self):
		self.assertEqual(validate_recurrence_config({"is_recurring": 0}), [])

	def test_generated_instance_cannot_be_template(self):
		errors = validate_recurrence_config(
			{
				"is_recurring": 1,
				"generated_from": "NT-2026-00001",
				"recurrence_frequency": "Daily",
				"recurrence_start_date": "2026-07-01",
			}
		)
		self.assertTrue(any("Generated" in e for e in errors))

	def test_frequency_and_start_required(self):
		errors = validate_recurrence_config({"is_recurring": 1})
		self.assertTrue(any("Frequency" in e for e in errors))
		self.assertTrue(any("Start Date" in e for e in errors))

	def test_support_required_compatibility(self):
		self.assertEqual(normalize_support_required(1), "Yes")
		self.assertEqual(normalize_support_required("1"), "Yes")
		self.assertEqual(normalize_support_required(0), "")
		self.assertEqual(normalize_support_required("Need help"), "Need help")


class TestGeneratedTaskPayloadHelpers(unittest.TestCase):
	def test_subject_and_template_reference_helpers(self):
		subject = build_generated_subject("Site Inspection", date(2026, 7, 29), 3)
		self.assertIn("Site Inspection", subject)
		self.assertIn("2026-07-29", subject)
		self.assertIn("#3", subject)


class TestDuplicatePrevention(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		import importlib

		import project_custom.nave_task_generation as gen

		importlib.reload(gen)
		self.gen = gen

	def test_occurrence_already_generated(self):
		self.frappe.db.exists = MagicMock(return_value=True)
		self.assertTrue(
			self.gen.occurrence_already_generated("NT-TEMPLATE", date(2026, 7, 29))
		)

	def test_create_generated_task_skips_duplicate(self):
		self.frappe.db.exists = MagicMock(return_value=True)
		self.frappe.db.get_value = MagicMock(return_value="NT-EXISTING")
		template = types.SimpleNamespace(
			name="NT-TEMPLATE",
			is_recurring=1,
			recurrence_active=1,
			status="Open",
			recurrence_end_date=None,
			recurrence_due_after_days=2,
			subject="Daily Check",
			assigned_by="creator@example.com",
			owner="creator@example.com",
			get=lambda field: None,
		)
		result = self.gen.create_generated_task(template, date(2026, 7, 29))
		self.assertTrue(result["duplicate"])
		self.assertFalse(result["created"])
		self.assertEqual(result["task"], "NT-EXISTING")


class TestPermissionChecks(unittest.TestCase):
	def test_recurrence_manage_permission_creator(self):
		self.assertTrue(
			user_can_manage_task(
				user="creator@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)

	def test_recurrence_manage_denied_for_ordinary_assignee(self):
		self.assertFalse(
			user_can_manage_task(
				user="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)


class TestHooksAndAssets(unittest.TestCase):
	def test_scheduler_registers_combined_daily_job(self):
		text = (WORKSPACE / "project_custom" / "hooks.py").read_text()
		self.assertIn("run_daily_nave_task_jobs", text)

	def test_update_type_includes_recurrence_event(self):
		text = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "doctype"
			/ "nave_task_update"
			/ "nave_task_update.json"
		).read_text()
		self.assertIn("Recurrence Event", text)

	def test_recurrence_fields_present(self):
		text = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "doctype"
			/ "nave_task"
			/ "nave_task.json"
		).read_text()
		for field in (
			"is_recurring",
			"recurrence_frequency",
			"recurrence_start_date",
			"recurrence_end_date",
			"next_creation_date",
			"last_generated_date",
			"recurrence_due_after_days",
			"recurrence_active",
			"recurring_template",
			"generated_from",
			"recurrence_sequence",
			"recurrence_occurrence_date",
		):
			self.assertIn(field, text)

	def test_patches_registered(self):
		text = (WORKSPACE / "project_custom" / "patches.txt").read_text()
		self.assertIn("v1_5.ensure_nave_task_recurrence_defaults", text)
		self.assertIn("v1_5.normalize_support_required_values", text)

	def test_ui_wires_recurring_api(self):
		js = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "page"
			/ "nave_tasks"
			/ "nave_tasks.js"
		).read_text()
		self.assertIn("get_recurring_tasks", js)
		self.assertIn("generate_recurring_task_now", js)
		self.assertIn("View Generated Tasks", js)


class TestCreatorVisibilityConcept(unittest.TestCase):
	def test_generated_task_keeps_template_creator_for_visibility(self):
		from project_custom.nave_task_utils import user_can_access_task

		template_owner = "creator@example.com"
		self.assertTrue(
			user_can_access_task(
				user=template_owner,
				assigned_to="emp@example.com",
				owner=template_owner,
				assigned_by=template_owner,
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="HR",
			)
		)


if __name__ == "__main__":
	unittest.main()
