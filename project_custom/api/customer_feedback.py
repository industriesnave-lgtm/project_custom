import re

import frappe
from frappe.utils import (
	add_to_date,
	cint,
	flt,
	now_datetime,
	strip_html_tags,
	validate_email_address,
)


SERVICE_TYPES = {
	"Electrical Works",
	"Civil Works",
	"Fabrication Works",
	"Manpower Supply",
	"Machinery Rental",
	"Material Supply",
	"Project Execution",
	"Other",
}

RATING_FIELDS = (
	"work_quality",
	"safety_compliance",
	"communication",
	"timely_completion",
	"team_behaviour",
	"overall_rating",
)


def clean_text(value, max_length=500):
	value = strip_html_tags(str(value or "")).strip()
	return value[:max_length]


def get_request_ip():
	return getattr(frappe.local, "request_ip", None) or "Unknown"


def check_rate_limit(ip_address, hourly_limit):
	key = f"customer_feedback_rate:{ip_address}"
	count = cint(frappe.cache.get_value(key))

	if count >= hourly_limit:
		frappe.throw(
			"Too many feedback submissions. Please try again later.",
			frappe.RateLimitExceededError,
		)

	frappe.cache.set_value(key, count + 1, expires_in_sec=3600)


def check_duplicate(payload, duplicate_window):
	if duplicate_window <= 0:
		return

	existing = frappe.db.exists(
		"Customer Feedback",
		{
			"customer_company": payload["customer_company"],
			"contact_person": payload["contact_person"],
			"overall_rating": payload["overall_rating"],
			"feedback": payload["feedback"],
			"creation": [
				">=",
				add_to_date(now_datetime(), minutes=-duplicate_window),
			],
		},
	)

	if existing:
		frappe.throw("This feedback was already submitted recently.")


def validate_payload(payload):
	customer_company = clean_text(payload.get("customer_company"), 140)
	contact_person = clean_text(payload.get("contact_person"), 140)
	service_type = clean_text(payload.get("service_type"), 140)
	feedback = clean_text(payload.get("feedback"), 2000)

	if not customer_company:
		frappe.throw("Customer / Company Name is required.")

	if not contact_person:
		frappe.throw("Contact Person is required.")

	if service_type not in SERVICE_TYPES:
		frappe.throw("Please select a valid Service Type.")

	if not feedback:
		frappe.throw("Feedback is required.")

	email = clean_text(payload.get("email"), 140)
	if email:
		validate_email_address(email, throw=True)

	mobile_number = clean_text(payload.get("mobile_number"), 30)
	if mobile_number and not re.fullmatch(r"[0-9+\-()\s]{7,30}", mobile_number):
		frappe.throw("Please enter a valid Mobile Number.")

	result = {
		"customer_company": customer_company,
		"contact_person": contact_person,
		"mobile_number": mobile_number,
		"email": email,
		"project_site": clean_text(payload.get("project_site"), 140),
		"service_type": service_type,
		"feedback": feedback,
		"testimonial_permission": cint(
			payload.get("testimonial_permission")
		),
	}

	for fieldname in RATING_FIELDS:
		stars = flt(payload.get(fieldname))

		if stars < 1 or stars > 5:
			frappe.throw("Every rating must be between 1 and 5 stars.")

		# Frappe Rating fields store five-star values internally from 0 to 1.
		result[fieldname] = stars / 5

	return result


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_feedback(data=None):
	settings = frappe.get_single("Customer Feedback Settings")

	if not settings.portal_enabled:
		frappe.throw("The feedback portal is currently unavailable.")

	payload = frappe.parse_json(data) if isinstance(data, str) else (data or {})

	# Honeypot: real customers never fill this hidden field.
	if payload.get("company_website"):
		return {"ok": True}

	form_started_at = flt(payload.get("form_started_at"))
	if not form_started_at or (frappe.utils.now_datetime().timestamp() - form_started_at) < 3:
		frappe.throw("Please take a moment to complete the feedback form.")

	ip_address = get_request_ip()
	hourly_limit = max(cint(settings.hourly_submission_limit), 1)
	duplicate_window = max(cint(settings.duplicate_window_minutes), 0)

	check_rate_limit(ip_address, hourly_limit)

	clean_payload = validate_payload(payload)
	check_duplicate(clean_payload, duplicate_window)

	doc = frappe.get_doc(
		{
			"doctype": "Customer Feedback",
			**clean_payload,
			"google_review_status": "Pending",
			"submitted_on": now_datetime(),
			"ip_address": ip_address,
			"user_agent": clean_text(
				frappe.get_request_header("User-Agent"),
				500,
			),
		}
	)

	doc.insert(ignore_permissions=True)

	return {
		"ok": True,
		"name": doc.name,
		"follow_up_status": doc.follow_up_status,
		"google_review_url": (
			(settings.google_review_url or "")
			if doc.follow_up_status == "Positive"
			else ""
		),
		"feedback": doc.feedback,
	}
