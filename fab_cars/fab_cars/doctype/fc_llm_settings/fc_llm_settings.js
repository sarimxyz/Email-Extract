// Copyright (c) 2026, fab_cars and contributors
// For license information, please see license.txt

frappe.ui.form.on("FC LLM Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Configure your LLM provider and API keys here (stored encrypted). " +
					"These settings are used by the app at runtime."
			)
		);
	},
});
