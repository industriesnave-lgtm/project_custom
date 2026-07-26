import re

import frappe
from frappe.model.document import Document
from frappe.utils import escape_html, flt, now_datetime


RATING_FIELDS = (
	"work_quality",
	"safety_compliance",
	"communication",
	"timely_completion",
	"team_behaviour",
	"overall_rating",
)


def rating_to_stars(value):
	value = flt(value)

	if 0 < value <= 1:
		return value * 5

	return value


def get_notification_recipients(settings):
	raw_recipients = settings.notification_recipients or ""

	return [
		email.strip()
		for email in re.split(r"[,;\n]+", raw_recipients)
		if email.strip()
	]


class CustomerFeedback(Document):
	def before_insert(self):
		if not self.submitted_on:
			self.submitted_on = now_datetime()

	def validate(self):
		self.validate_ratings()
		self.set_follow_up_status()

	def after_insert(self):
		if self.follow_up_status in ("Urgent", "Review Required"):
			self.send_follow_up_notification()
			self.create_follow_up_assignment()

	def validate_ratings(self):
		for fieldname in RATING_FIELDS:
			stars = rating_to_stars(self.get(fieldname))

			if stars < 1 or stars > 5:
				label = self.meta.get_label(fieldname)
				frappe.throw(f"{label} must be between 1 and 5 stars.")

	def set_follow_up_status(self):
		overall_stars = rating_to_stars(self.overall_rating)

		if overall_stars >= 4:
			self.follow_up_status = "Positive"
		elif overall_stars >= 3:
			self.follow_up_status = "Review Required"
		else:
			self.follow_up_status = "Urgent"

	def send_follow_up_notification(self):
		settings = frappe.get_single("Customer Feedback Settings")
		recipients = get_notification_recipients(settings)

		if not recipients:
			return

		overall_stars = rating_to_stars(self.overall_rating)
		subject = (
			f"{self.follow_up_status}: Customer Feedback "
			f"from {self.customer_company}"
		)

		message = f"""
			<h3>{escape_html(subject)}</h3>
			<p><strong>Contact Person:</strong>
				{escape_html(self.contact_person or "")}
			</p>
			<p><strong>Project / Site:</strong>
				{escape_html(self.project_site or "")}
			</p>
			<p><strong>Service Type:</strong>
				{escape_html(self.service_type or "")}
			</p>
			<p><strong>Overall Rating:</strong>
				{overall_stars:.0f} / 5
			</p>
			<p><strong>Feedback:</strong><br>
				{escape_html(self.feedback or "")}
			</p>
			<p>
				<a href="{frappe.utils.get_url_to_form(self.doctype, self.name)}">
					Open Feedback Record
				</a>
			</p>
		"""

		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			delayed=True,
		)

	def create_follow_up_assignment(self):
		settings = frappe.get_single("Customer Feedback Settings")
		assignee = settings.follow_up_assignee

		if not assignee:
			return

		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": assignee,
				"description": (
					f"{self.follow_up_status}: Follow up with "
					f"{self.customer_company}"
				),
				"reference_type": self.doctype,
				"reference_name": self.name,
				"priority": (
					"High"
					if self.follow_up_status == "Urgent"
					else "Medium"
				),
				"status": "Open",
			}
		).insert(ignore_permissions=True)
