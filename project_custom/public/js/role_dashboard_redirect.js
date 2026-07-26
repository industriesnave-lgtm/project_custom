(() => {
        const redirectToNaveHome = () => {
                const path = window.location.pathname.replace(/\/+$/, "");

                if (
                        frappe.session.user !== "Guest" &&
                        (path === "/desk" || path === "/app")
                ) {
                        window.location.replace("/desk/nave-home");
                }
        };

        if (document.readyState === "loading") {
                document.addEventListener(
                        "DOMContentLoaded",
                        redirectToNaveHome
                );
        } else {
                redirectToNaveHome();
        }
})();
