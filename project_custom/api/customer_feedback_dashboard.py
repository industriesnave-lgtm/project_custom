from collections import Counter, defaultdict

import frappe
from frappe.utils import flt, getdate


def rating_to_stars(value):
	value = flt(value)

	if 0 < value <= 1:
		return value * 5

	return value


def require_dashboard_access():
	roles = frappe.get_roles(frappe.session.user)

	if (
		frappe.session.user != "Administrator"
		and "System Manager" not in roles
	):
		frappe.throw(
			"Only System Manager can access this dashboard.",
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_dashboard_data():
	require_dashboard_access()

	records = frappe.get_all(
		"Customer Feedback",
		fields=[
			"name",
			"customer_company",
			"contact_person",
			"project_site",
			"service_type",
			"overall_rating",
			"feedback",
			"testimonial_permission",
			"google_review_status",
			"follow_up_status",
			"submitted_on",
			"creation",
		],
		order_by="submitted_on desc, creation desc",
		limit_page_length=0,
	)

	total_feedback = len(records)
	ratings = [rating_to_stars(row.overall_rating) for row in records]
	average_rating = (
		sum(ratings) / total_feedback if total_feedback else 0
	)

	positive_count = sum(
		1 for row in records if row.follow_up_status == "Positive"
	)
	positive_percent = (
		(positive_count / total_feedback) * 100
		if total_feedback
		else 0
	)

	low_rating_count = sum(
		1 for row in records if rating_to_stars(row.overall_rating) <= 2
	)

	google_review_pending = sum(
		1
		for row in records
		if row.google_review_status == "Pending"
	)

	service_counts = Counter(
		row.service_type or "Not Specified" for row in records
	)

	project_counts = Counter(
		row.project_site or "Not Specified" for row in records
	)

	monthly = defaultdict(
		lambda: {"count": 0, "rating_total": 0}
	)

	for row in records:
		date_value = row.submitted_on or row.creation

		if not date_value:
			continue

		month_key = getdate(date_value).strftime("%Y-%m")
		monthly[month_key]["count"] += 1
		monthly[month_key]["rating_total"] += rating_to_stars(
			row.overall_rating
		)

	monthly_trend = []

	for month_key in sorted(monthly.keys())[-12:]:
		values = monthly[month_key]
		monthly_trend.append(
			{
				"month": month_key,
				"count": values["count"],
				"average_rating": round(
					values["rating_total"] / values["count"],
					2,
				),
			}
		)

	recent_feedback = []

	for row in records[:10]:
		recent_feedback.append(
			{
				"name": row.name,
				"customer_company": row.customer_company,
				"project_site": row.project_site,
				"service_type": row.service_type,
				"overall_rating": round(
					rating_to_stars(row.overall_rating),
					1,
				),
				"feedback": row.feedback,
				"follow_up_status": row.follow_up_status,
				"google_review_status": row.google_review_status,
				"submitted_on": row.submitted_on,
			}
		)

	return {
		"total_feedback": total_feedback,
		"average_rating": round(average_rating, 2),
		"positive_feedback_percent": round(positive_percent, 1),
		"low_rating_count": low_rating_count,
		"google_review_pending": google_review_pending,
		"service_breakdown": [
			{"label": label, "value": value}
			for label, value in service_counts.most_common()
		],
		"project_breakdown": [
			{"label": label, "value": value}
			for label, value in project_counts.most_common(10)
		],
		"monthly_trend": monthly_trend,
		"recent_feedback": recent_feedback,
	}	
