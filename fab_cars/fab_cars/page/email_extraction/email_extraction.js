frappe.pages["email-extraction"].on_page_load = function (wrapper) {
	// Frappe's Desk breadcrumbs for Pages are derived from the `Page.title`
	// field (DB). If that field is blank (not yet synced), ensure we still
	// show the correct label in the header.
	try {
		frappe.breadcrumbs.add({
			type: "Custom",
			label: "Email Extraction",
			route: frappe.get_route_str(),
		});
	} catch (e) {
		// Non-fatal: the page content will still render.
	}

	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Email Extraction",
		single_column: true,
	});

	// Create the dashboard layout
	create_dashboard(page);
};

// Dashboard pagination state.
// Uses Frappe's "list-paging-area" markup (same as ListView) and server-side paging via dashboard_api.
let dashboardState = {
	start: 0,
	page_length: 20,
	selected_page_count: 20,
	data: [],
	total_count: 0,
};

function create_dashboard(page) {
	// Defensive defaults: prevent the UI from rendering literal "undefined".
	let today = "";
	try {
		if (frappe.datetime && typeof frappe.datetime.get_today === "function") {
			today = frappe.datetime.get_today();
		}
	} catch (e) {
		// Keep today as "".
	}

	let fromDate = "";
	try {
		if (frappe.datetime && typeof frappe.datetime.add_months === "function" && today) {
			fromDate = frappe.datetime.add_months(today, -1);
		}
	} catch (e) {
		// Fall back to today below.
	}
	if (!fromDate) fromDate = today;

	let page_shell_start = `
		<style>
			.fc-extraction-shell{
				padding: 24px 20px;
				max-width: none;
				margin: 0;
				width: 100%;
				box-sizing: border-box;
			}
			.fc-extraction-card{
				background: #fff;
				border: 1px solid #eef1f5;
				border-radius: 12px;
				padding: 16px;
				box-shadow: 0 1px 0 rgba(16,24,40,.02);
			}
			.fc-extraction-table-wrap{
				background: #fff;
				border: 1px solid #eef1f5;
				border-radius: 12px;
				overflow: hidden;
			}
			.table-responsive{ overflow-x: auto; }
			#data_table{ margin: 0; table-layout: fixed; min-width: 1550px; }
			#data_table thead th{
				background: #f7f8fa;
				border-bottom: 1px solid #eef1f5 !important;
				font-weight: 600;
				font-size: 12px;
				color: #475467;
				letter-spacing: .01em;
			}
			#data_table thead th, #data_table tbody td{
				vertical-align: middle;
				padding: 12px 10px !important;
			}
			/* Fixed column widths keep the table readable (instead of squeezing everything). */
			#data_table th:nth-child(1), #data_table td:nth-child(1){ width: 170px; }
			#data_table th:nth-child(2), #data_table td:nth-child(2){ width: 240px; }
			#data_table th:nth-child(3), #data_table td:nth-child(3){ width: 140px; }
			#data_table th:nth-child(4), #data_table td:nth-child(4){ width: 240px; }
			#data_table th:nth-child(5), #data_table td:nth-child(5){ width: 190px; }
			#data_table th:nth-child(6), #data_table td:nth-child(6){ width: 130px; }
			#data_table th:nth-child(7), #data_table td:nth-child(7){ width: 120px; }
			#data_table th:nth-child(8), #data_table td:nth-child(8){ width: 160px; }
			#data_table th:nth-child(9), #data_table td:nth-child(9){ width: 260px; }
			#data_table tbody td{
				border-top: 1px solid #eef1f5;
				font-size: 13px;
				color: #101828;
			}
			#data_table tbody tr{
				transition: background-color 120ms ease;
			}
			#data_table tbody tr:hover{
				background-color: #fcfcfd;
			}
			.fc-cell-ellipsis{
				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}
			.fc-cell-clamp-2{
				display: -webkit-box;
				-webkit-line-clamp: 2;
				-webkit-box-orient: vertical;
				overflow: hidden;
			}
			.fc-extraction-badge{
				padding: 4px 10px !important;
				border-radius: 999px;
				font-size: 12px;
				font-weight: 600;
			}
			.fc-extraction-h4{
				margin: 0 0 10px 0;
				font-size: 14px;
				font-weight: 700;
				color: #344054;
			}
			.table{ width: 100% !important; }
			@media (max-width: 768px){
				.fc-extraction-shell{ padding: 14px 10px; }
				.dashboard-filters .col-md-3{ margin-bottom: 10px; }
				#data_table{ min-width: 1200px; }
				#data_table th:nth-child(1), #data_table td:nth-child(1){ width: 150px; }
				#data_table th:nth-child(2), #data_table td:nth-child(2){ width: 200px; }
				#data_table th:nth-child(3), #data_table td:nth-child(3){ width: 120px; }
				#data_table th:nth-child(4), #data_table td:nth-child(4){ width: 220px; }
				#data_table th:nth-child(5), #data_table td:nth-child(5){ width: 170px; }
				#data_table th:nth-child(6), #data_table td:nth-child(6){ width: 120px; }
				#data_table th:nth-child(7), #data_table td:nth-child(7){ width: 110px; }
				#data_table th:nth-child(8), #data_table td:nth-child(8){ width: 140px; }
				#data_table th:nth-child(9), #data_table td:nth-child(9){ width: 200px; }
			}
		</style>
		<div class="fc-extraction-shell">
	`;

	let page_shell_end = `</div>`;

	// Create filters section
	let filters_html = `
		<div class="dashboard-filters fc-extraction-card" style="margin-bottom: 16px;">
			<div class="row">
				<div class="col-md-3 col-sm-6 col-12">
					<label>From Date</label>
					<input type="date" class="form-control" id="from_date" value="${fromDate}">
				</div>
				<div class="col-md-3 col-sm-6 col-12">
					<label>To Date</label>
					<input type="date" class="form-control" id="to_date" value="${today}">
				</div>
				<div class="col-md-3 col-sm-6 col-12">
					<label>Trip Status</label>
					<select class="form-control" id="trip_status">
					<option value="">All</option>
					<option value="Pending">Pending</option>
					<option value="Needs Info">Needs Info</option>
					<option value="Successful">Successful</option>
					<option value="Failed">Failed</option>
					</select>
				</div>
				<div class="col-md-3 col-sm-6 col-12">
					<label>&nbsp;</label><br>
					<button class="btn btn-primary" onclick="refresh_dashboard()">Refresh</button>
				</div>
			</div>
		</div>
	`;

	// Create number cards section
	let number_cards_html = `
		<div class="number-cards" style="margin-bottom: 16px;">
			<div class="row" id="number_cards_container">
				<!-- Number cards will be loaded here -->
			</div>
		</div>
	`;

	// Create data table section
	let data_table_html = `
		<div class="data-table-section" style="margin-bottom: 8px;">
			<div class="fc-extraction-table-wrap">
				<div style="padding: 14px 14px 0 14px;">
					<div class="fc-extraction-h4">Email Extraction Data</div>
				</div>
				<div class="table-responsive" style="padding: 0 14px 14px 14px;">
					<table class="table table-striped table-hover" id="data_table">
					<thead>
						<tr>
							<th>Email Sender</th>
							<th>Email Subject</th>
							<th>Received Date</th>
							<th>Extracted Email</th>
							<th>Trip Request</th>
							<th>Trip Status</th>
							<th>City</th>
							<th>Vehicle Type</th>
							<th>Remarks</th>
						</tr>
					</thead>
					<tbody id="data_table_body">
						<!-- Data will be loaded here -->
					</tbody>
					</table>
				</div>
			</div>
		</div>
	`;

	// Pagination controls (Frappe-style markup from list/BaseList).
	// Server-side paging is done via dashboard_api using start/page_length.
	let paging_html = `
		<div class="list-paging-area level" id="dashboard_paging_area" style="margin-top: 10px; display: none;">
			<div class="level-left">
				<div class="btn-group">
					<button type="button" class="btn btn-default btn-sm btn-paging" data-value="20">20</button>
					<button type="button" class="btn btn-default btn-sm btn-paging" data-value="100">100</button>
					<button type="button" class="btn btn-default btn-sm btn-paging" data-value="500">500</button>
					<button type="button" class="btn btn-default btn-sm btn-paging" data-value="2500">2500</button>
				</div>
			</div>
			<div class="level-right">
				<button type="button" class="btn btn-default btn-more btn-sm" id="dashboard_btn_more">
					Load More
				</button>
			</div>
		</div>
	`;

	// Add all sections to the page
	page.main.html(
		page_shell_start +
			filters_html +
			number_cards_html +
			data_table_html +
			paging_html +
			page_shell_end
	);

	// Load initial data
	refresh_dashboard();

	// Wire up pagination events after render.
	setup_dashboard_pagination();
}

function setup_dashboard_pagination() {
	let $paging_area = $("#dashboard_paging_area");
	if (!$paging_area.length) return;

	let $more_btn = $("#dashboard_btn_more");
	if (!$more_btn.length) return;

	function set_active_paging_button() {
		$paging_area.find(".btn-paging").each(function () {
			const $btn = $(this);
			const value = parseInt($btn.data("value"), 10);
			const is_active = value === dashboardState.page_length;
			$btn.toggleClass("btn-info", is_active);
			$btn.prop("disabled", is_active);
		});
	}

	set_active_paging_button();

	$paging_area.off("click.dashboard_paging");

	$paging_area.on("click.dashboard_paging", ".btn-paging", function (e) {
		e.preventDefault();
		const value = parseInt($(e.currentTarget).data("value"), 10);
		if (!value || value < 1) return;
		dashboardState.selected_page_count = value;
		dashboardState.page_length = value;
		// Reset paging.
		dashboardState.start = 0;
		dashboardState.data = [];
		dashboardState.total_count = 0;
		set_active_paging_button();
		update_dashboard_pagination_ui();
		refresh_dashboard();
	});

	$more_btn.off("click.dashboard_paging").on("click.dashboard_paging", function (e) {
		e.preventDefault();
		if (dashboardState.data.length >= dashboardState.total_count) return;
		// Append next page.
		refresh_dashboard({ append: true });
	});
}

function update_dashboard_pagination_ui() {
	let $paging_area = $("#dashboard_paging_area");
	if (!$paging_area.length) return;
	let $more_btn = $("#dashboard_btn_more");
	if (!$more_btn.length) return;

	const total = dashboardState.total_count || 0;
	const loaded = dashboardState.data ? dashboardState.data.length : 0;

	// Show paging only when there's something to paginate.
	$paging_area.toggle(total > 0);

	// Disable load more unless there are more rows.
	const has_more = loaded < total;
	$more_btn.toggle(has_more);
	$more_btn.prop("disabled", !has_more);

	// Keep active button states in sync.
	$paging_area.find(".btn-paging").each(function () {
		const $btn = $(this);
		const value = parseInt($btn.data("value"), 10);
		const is_active = value === dashboardState.page_length;
		$btn.toggleClass("btn-info", is_active);
		$btn.prop("disabled", is_active);
	});
}

function refresh_dashboard(opts = {}) {
	const append = !!opts.append;

	// Get filter values
	let from_date = document.getElementById("from_date").value;
	let to_date = document.getElementById("to_date").value;
	let trip_status = document.getElementById("trip_status").value;

	// Reset data unless appending.
	if (!append) {
		dashboardState.start = 0;
		dashboardState.data = [];
	}

	const req_start = append ? dashboardState.data.length : 0;
	const req_page_length = dashboardState.page_length;

	// Show loading
	frappe.show_alert({ message: "Loading dashboard data...", indicator: "blue" });

	// Fetch data from server
	frappe.call({
		method: "fab_cars.fab_cars.api.dashboard_api.get_dashboard_data",
		args: {
			filters: {
				from_date: from_date,
				to_date: to_date,
				trip_request_status: trip_status,
				start: req_start,
				page_length: req_page_length,
			},
		},
		callback: function (r) {
			if (r.message && !r.message.error) {
				let data = r.message.data || [];
				let number_cards = r.message.number_cards || [];

				if (append) {
					dashboardState.data = dashboardState.data.concat(data);
				} else {
					dashboardState.data = data;
				}

				dashboardState.total_count = r.message.total_count || 0;

				// Update number cards on reset only.
				if (!append) {
					update_number_cards(number_cards);
				}

				update_data_table(dashboardState.data);
				update_dashboard_pagination_ui();
			} else if (r.message && r.message.error) {
				frappe.show_alert({
					message: "Error loading data: " + r.message.error,
					indicator: "red",
				});
			} else {
				frappe.show_alert({ message: "Error loading dashboard data", indicator: "red" });
			}
		},
	});
}

function update_number_cards(number_cards) {
	// Backend should return an array; guard against unexpected shapes.
	if (!Array.isArray(number_cards)) number_cards = [];

	let container = document.getElementById("number_cards_container");
	let html = "";

	number_cards.forEach(function (card) {
		const value = card && card.value !== undefined ? card.value : "";
		const label = card && card.label !== undefined ? card.label : "";

		html += `
			<div class="col-md-4">
				<div class="card" style="text-align: center; padding: 16px 10px; margin-bottom: 12px; border: 1px solid #eef1f5; border-radius: 12px; background: #fff;">
					<h3 style="color: #344054; margin: 0; font-size: 22px; font-weight: 800;">${value}</h3>
					<p style="margin: 6px 0 0 0; color: #667085; font-size: 12px;">${label}</p>
				</div>
			</div>
		`;
	});

	container.innerHTML = html;
}

function update_data_table(data) {
	let tbody = document.getElementById("data_table_body");
	let html = "";

	function escape_html(value) {
		if (value === null || value === undefined) return "";
		return String(value)
			.replaceAll("&", "&amp;")
			.replaceAll("<", "&lt;")
			.replaceAll(">", "&gt;")
			.replaceAll('"', "&quot;")
			.replaceAll("'", "&#039;");
	}

	if (data && data.length > 0) {
		data.forEach(function (row) {
			const sender = escape_html(row.sender || "");
			const subject = escape_html(row.subject || "");
			const extracted_email_raw = row.extracted_email || "";
			const trip_request_raw = row.trip_request || "";
			const extracted_email = escape_html(extracted_email_raw);
			const trip_request = escape_html(trip_request_raw);
			const received_date = escape_html(row.received_date || "");
			const city = escape_html(row.city || "");
			const vehicle_type = escape_html(row.vehicle_type || "");
			const remarks = escape_html(row.remarks || "");
			const trip_request_status = row.trip_request_status || "";

			html += `
				<tr>
					<td>
						<div class="fc-cell-ellipsis" title="${sender}">${sender}</div>
					</td>
					<td>
						<div class="fc-cell-clamp-2" title="${subject}">${subject}</div>
					</td>
					<td>
						<div class="fc-cell-ellipsis" title="${received_date}">${received_date}</div>
					</td>
					<td>
						${
							row.extracted_email
								? `<a class="fc-cell-ellipsis" style="display:inline-block; max-width: 100%;" href="/app/fc-raw-email-log/${encodeURIComponent(
										extracted_email_raw
								  )}" target="_blank" title="${extracted_email}">${extracted_email}</a>`
								: ""
						}
					</td>
					<td>
						${
							row.trip_request
								? `<a class="fc-cell-ellipsis" style="display:inline-block; max-width: 100%;" href="/app/fc-trip-request/${encodeURIComponent(
										trip_request_raw
								  )}" target="_blank" title="${trip_request}">${trip_request}</a>`
								: ""
						}
					</td>
					<td>
						<span class="badge badge-${get_status_badge_class(
							trip_request_status
						)} fc-extraction-badge" title="${escape_html(trip_request_status)}">
							${escape_html(trip_request_status)}
						</span>
					</td>
					<td>
						<div class="fc-cell-ellipsis" title="${city}">${city}</div>
					</td>
					<td>
						<div class="fc-cell-ellipsis" title="${vehicle_type}">${vehicle_type}</div>
					</td>
					<td>
						<div class="fc-cell-clamp-2" title="${remarks}">${remarks}</div>
					</td>
				</tr>
			`;
		});
	} else {
		html =
			'<tr><td colspan="9" style="text-align: center; color: #666;">No data found</td></tr>';
	}

	tbody.innerHTML = html;
}

function get_status_badge_class(status) {
	switch (status) {
		// case 'New': return 'primary';
		case "Pending":
			return "warning";
		case "Needs Info":
			return "secondary";
		case "Successful":
			return "success";
		case "Failed":
			return "danger";
		default:
			return "secondary";
	}
}
