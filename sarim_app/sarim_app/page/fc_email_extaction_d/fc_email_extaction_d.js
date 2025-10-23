frappe.pages['fc-email-extaction-d'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'FC Email Extraction Dashboard',
		single_column: true
	});

	// Create the dashboard layout
	create_dashboard(page);
}

function create_dashboard(page) {
	// Create filters section
	let filters_html = `
		<div class="dashboard-filters" style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px;">
			<div class="row">
				<div class="col-md-3">
					<label>From Date</label>
					<input type="date" class="form-control" id="from_date" value="${frappe.datetime.add_months(frappe.datetime.get_today(), -1)}">
				</div>
				<div class="col-md-3">
					<label>To Date</label>
					<input type="date" class="form-control" id="to_date" value="${frappe.datetime.get_today()}">
				</div>
				<div class="col-md-3">
					<label>Trip Status</label>
					<select class="form-control" id="trip_status">
						<option value="">All Status</option>
						<option value="New">New</option>
						<option value="In Progress">In Progress</option>
						<option value="Completed">Completed</option>
						<option value="Cancelled">Cancelled</option>
					</select>
				</div>
				<div class="col-md-3">
					<label>&nbsp;</label><br>
					<button class="btn btn-primary" onclick="refresh_dashboard()">Refresh</button>
				</div>
			</div>
		</div>
	`;

	// Create number cards section
	let number_cards_html = `
		<div class="number-cards" style="margin-bottom: 20px;">
			<div class="row" id="number_cards_container">
				<!-- Number cards will be loaded here -->
			</div>
		</div>
	`;

	// Create data table section
	let data_table_html = `
		<div class="data-table-section">
			<h4>Email Extraction Data</h4>
			<div class="table-responsive">
				<table class="table table-bordered table-striped" id="data_table">
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
	`;

	// Add all sections to the page
	page.main.html(filters_html + number_cards_html + data_table_html);

	// Load initial data
	refresh_dashboard();
}

function refresh_dashboard() {
	// Get filter values
	let from_date = document.getElementById('from_date').value;
	let to_date = document.getElementById('to_date').value;
	let trip_status = document.getElementById('trip_status').value;

	// Show loading
	frappe.show_alert({message: 'Loading dashboard data...', indicator: 'blue'});

	// Fetch data from server
	frappe.call({
		method: 'sarim_app.sarim_app.api.dashboard_api.get_dashboard_data',
		args: {
			filters: {
				from_date: from_date,
				to_date: to_date,
				trip_request_status: trip_status
			}
		},
		callback: function(r) {
			if (r.message && !r.message.error) {
				let columns = r.message.columns;
				let data = r.message.data;
				let number_cards = r.message.number_cards;

				// Update number cards
				update_number_cards(number_cards);

				// Update data table
				update_data_table(data);
			} else if (r.message && r.message.error) {
				frappe.show_alert({message: 'Error loading data: ' + r.message.error, indicator: 'red'});
			} else {
				frappe.show_alert({message: 'Error loading dashboard data', indicator: 'red'});
			}
		}
	});
}

function update_number_cards(number_cards) {
	let container = document.getElementById('number_cards_container');
	let html = '';

	number_cards.forEach(function(card) {
		html += `
			<div class="col-md-4">
				<div class="card" style="text-align: center; padding: 20px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 5px;">
					<h3 style="color: #007bff; margin: 0;">${card.value}</h3>
					<p style="margin: 5px 0 0 0; color: #666;">${card.label}</p>
				</div>
			</div>
		`;
	});

	container.innerHTML = html;
}

function update_data_table(data) {
	let tbody = document.getElementById('data_table_body');
	let html = '';

	if (data && data.length > 0) {
		data.forEach(function(row) {
			html += `
				<tr>
					<td>${row.sender || ''}</td>
					<td>${row.subject || ''}</td>
					<td>${row.received_date || ''}</td>
					<td>
						${row.extracted_email ? 
							`<a href="/app/fc-btw-extracted-emails/${row.extracted_email}" target="_blank">${row.extracted_email}</a>` : 
							''
						}
					</td>
					<td>
						${row.trip_request ? 
							`<a href="/app/fc-btw-trip-requests/${row.trip_request}" target="_blank">${row.trip_request}</a>` : 
							''
						}
					</td>
					<td>
						<span class="badge badge-${get_status_badge_class(row.trip_request_status)}">
							${row.trip_request_status || ''}
						</span>
					</td>
					<td>${row.city || ''}</td>
					<td>${row.vehicle_type || ''}</td>
					<td>${row.remarks || ''}</td>
				</tr>
			`;
		});
	} else {
		html = '<tr><td colspan="9" style="text-align: center; color: #666;">No data found</td></tr>';
	}

	tbody.innerHTML = html;
}

function get_status_badge_class(status) {
	switch(status) {
		case 'New': return 'primary';
		case 'In Progress': return 'warning';
		case 'Completed': return 'success';
		case 'Cancelled': return 'danger';
		default: return 'secondary';
	}
}