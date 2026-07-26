import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


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


class CustomerFeedback(Document):
	def before_insert(self):
		if not self.submitted_on:
			self.submitted_on = now_datetime()

	def validate(self):
		self.validate_ratings()
		self.set_follow_up_status()

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
