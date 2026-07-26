(() => {
	"use strict";

	const form = document.getElementById("customer-feedback-form");
	const formContainer = document.getElementById("feedback-form-container");
	const successPanel = document.getElementById("feedback-success");
	const errorBox = document.getElementById("feedback-error");
	const submitButton = form.querySelector(".feedback-submit");
	const submitLabel = form.querySelector(".submit-label");
	const submitLoading = form.querySelector(".submit-loading");
	const copyButton = document.getElementById("copy-feedback");
	const reviewButton = document.getElementById("google-review-button");
	const submittedFeedback = document.getElementById(
		"submitted-feedback-text"
	);

	const config = window.naveFeedbackConfig || {};
	let savedFeedback = "";

	function setError(message) {
		errorBox.textContent = message || "Unable to submit feedback.";
		errorBox.hidden = false;
		errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
	}

	function clearError() {
		errorBox.textContent = "";
		errorBox.hidden = true;
	}

	function setLoading(loading) {
		submitButton.disabled = loading;
		submitLabel.hidden = loading;
		submitLoading.hidden = !loading;
	}

	function initialiseRatings() {
		document.querySelectorAll(".rating-field").forEach((ratingField) => {
			const input = ratingField.querySelector('input[type="hidden"]');
			const valueLabel = ratingField.querySelector(".rating-value");
			const stars = Array.from(
				ratingField.querySelectorAll(".star-button")
			);

			stars.forEach((starButton) => {
				starButton.addEventListener("click", () => {
					const selectedValue = Number(starButton.dataset.value);
					input.value = selectedValue;
					valueLabel.textContent = `${selectedValue} / 5`;

					stars.forEach((star) => {
						const active =
							Number(star.dataset.value) <= selectedValue;

						star.classList.toggle("active", active);
						star.setAttribute(
							"aria-checked",
							active ? "true" : "false"
						);
					});
				});
			});
		});
	}

	function collectPayload() {
		const formData = new FormData(form);
		const payload = {};

		for (const [key, value] of formData.entries()) {
			payload[key] = typeof value === "string" ? value.trim() : value;
		}

		payload.testimonial_permission = form.elements
			.testimonial_permission.checked
			? 1
			: 0;

		payload.form_started_at = config.formStartedAt || Date.now() / 1000;

		return payload;
	}

	function validateRatings(payload) {
		const ratingFields = [
			"work_quality",
			"safety_compliance",
			"communication",
			"timely_completion",
			"team_behaviour",
			"overall_rating",
		];

		return ratingFields.every((fieldname) => {
			const value = Number(payload[fieldname]);
			return value >= 1 && value <= 5;
		});
	}

	function showSuccess(response, payload) {
		savedFeedback = response.feedback || payload.feedback || "";
		submittedFeedback.textContent = savedFeedback;

            const reviewUrl = response.google_review_url || "";

		if (reviewUrl) {
			reviewButton.href = reviewUrl;
			reviewButton.hidden = false; reviewButton.style.display = "";
		} else {
			reviewButton.hidden = true; reviewButton.style.display = "none";
		}

		formContainer.hidden = true;
		successPanel.hidden = false;
		successPanel.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	function extractError(error) {
		if (error && error._server_messages) {
			try {
				const messages = JSON.parse(error._server_messages);
				const lastMessage = JSON.parse(messages[messages.length - 1]);
				return lastMessage.message || lastMessage;
			} catch (parseError) {
				console.error(parseError);
			}
		}

		return (
			error?.message ||
			"Unable to submit feedback. Please try again."
		);
	}

	form.addEventListener("submit", (event) => {
		event.preventDefault();
		clearError();

		if (!form.checkValidity()) {
			form.reportValidity();
			return;
		}

		const payload = collectPayload();

		if (!validateRatings(payload)) {
			setError("Please provide all six ratings.");
			return;
		}

		setLoading(true);

		frappe.call({
			method: "project_custom.api.customer_feedback.submit_feedback",
			type: "POST",
			args: {
				data: JSON.stringify(payload),
			},
			callback: (response) => {
				setLoading(false);

				if (!response.message || !response.message.ok) {
					setError("Unable to submit feedback.");
					return;
				}

				showSuccess(response.message, payload);
			},
			error: (error) => {
				setLoading(false);
				setError(extractError(error));
			},
		});
	});

	copyButton.addEventListener("click", async () => {
		try {
			await navigator.clipboard.writeText(savedFeedback);
			copyButton.textContent = "Copied!";
			setTimeout(() => {
				copyButton.textContent = "Copy Feedback";
			}, 1800);
		} catch (error) {
			setError("Unable to copy feedback.");
		}
	});

	initialiseRatings();
})();
