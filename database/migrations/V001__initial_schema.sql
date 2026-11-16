-- V001: initial TableFlow Enterprise schema (generated from backend/app/models by
-- scripts/generate_schema_sql.py). PostgreSQL 14+.

-- api_clients
CREATE TABLE api_clients (
	id SERIAL NOT NULL, 
	client_id VARCHAR(80) NOT NULL, 
	client_secret_hash VARCHAR(255) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	scopes VARCHAR(500) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (client_id)
);

-- audit_logs
CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	actor VARCHAR(255) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	entity_type VARCHAR(40) NOT NULL, 
	entity_id VARCHAR(40), 
	details JSONB, 
	ip_address VARCHAR(45), 
	correlation_id VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_audit_created ON audit_logs (created_at);
CREATE INDEX ix_audit_entity ON audit_logs (entity_type, entity_id);

-- branches
CREATE TABLE branches (
	id SERIAL NOT NULL, 
	code VARCHAR(20) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	city VARCHAR(80) NOT NULL, 
	province VARCHAR(80) NOT NULL, 
	address VARCHAR(255) NOT NULL, 
	phone VARCHAR(30) NOT NULL, 
	pos_system VARCHAR(40) NOT NULL, 
	pos_location_ref VARCHAR(60) NOT NULL, 
	payment_provider VARCHAR(60) NOT NULL, 
	digital_channels JSONB NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	opened_on DATE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_branch_pos_system CHECK (pos_system IN ('micros_simphony','none')), 
	UNIQUE (code)
);

-- customers
CREATE TABLE customers (
	id SERIAL NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	email VARCHAR(255), 
	marketing_opt_in BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (phone)
);

-- integrations
CREATE TABLE integrations (
	id SERIAL NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	display_name VARCHAR(120) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	provider VARCHAR(80) NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	base_url VARCHAR(255) NOT NULL, 
	last_success_at TIMESTAMP WITH TIME ZONE, 
	last_failure_at TIMESTAMP WITH TIME ZONE, 
	consecutive_failures INTEGER NOT NULL, 
	total_requests INTEGER NOT NULL, 
	total_failures INTEGER NOT NULL, 
	avg_response_ms INTEGER NOT NULL, 
	last_error TEXT, 
	config JSONB NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_integration_kind CHECK (kind IN ('pos','payment','ordering','loyalty','finance','backoffice')), 
	CONSTRAINT ck_integration_mode CHECK (mode IN ('simulated','sandbox','live')), 
	CONSTRAINT ck_integration_status CHECK (status IN ('healthy','degraded','down','disabled')), 
	UNIQUE (name)
);

-- notifications
CREATE TABLE notifications (
	id SERIAL NOT NULL, 
	event_type VARCHAR(60) NOT NULL, 
	workflow VARCHAR(80) NOT NULL, 
	payload JSONB NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	target_url VARCHAR(500) NOT NULL, 
	error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_notifications_created ON notifications (created_at);

-- products
CREATE TABLE products (
	id SERIAL NOT NULL, 
	sku VARCHAR(40) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	category VARCHAR(60) NOT NULL, 
	price NUMERIC(12, 2) NOT NULL, 
	pos_item_ref VARCHAR(40) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_product_price_positive CHECK (price >= 0), 
	UNIQUE (sku)
);

-- roles
CREATE TABLE roles (
	id SERIAL NOT NULL, 
	name VARCHAR(40) NOT NULL, 
	description VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

-- settlement_records
CREATE TABLE settlement_records (
	id SERIAL NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	provider_reference VARCHAR(80) NOT NULL, 
	branch_code VARCHAR(20) NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	fee NUMERIC(12, 2) NOT NULL, 
	business_date DATE NOT NULL, 
	imported_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_settlement_provider_ref UNIQUE (provider, provider_reference)
);
CREATE INDEX ix_settlement_business_date ON settlement_records (business_date);

-- webhook_events
CREATE TABLE webhook_events (
	id SERIAL NOT NULL, 
	source VARCHAR(40) NOT NULL, 
	event_id VARCHAR(100) NOT NULL, 
	event_type VARCHAR(80) NOT NULL, 
	payload JSONB NOT NULL, 
	signature_valid BOOLEAN NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	attempts INTEGER NOT NULL, 
	error TEXT, 
	received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	processed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_webhook_source_event UNIQUE (source, event_id), 
	CONSTRAINT ck_webhook_status CHECK (status IN ('received','processed','failed','duplicate','rejected'))
);
CREATE INDEX ix_webhook_events_received ON webhook_events (received_at);
CREATE INDEX ix_webhook_events_status ON webhook_events (status);

-- webhook_subscriptions
CREATE TABLE webhook_subscriptions (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	target_url VARCHAR(500) NOT NULL, 
	event_types JSONB NOT NULL, 
	secret_env_var VARCHAR(80) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- integration_logs
CREATE TABLE integration_logs (
	id SERIAL NOT NULL, 
	integration_id INTEGER NOT NULL, 
	branch_id INTEGER, 
	operation VARCHAR(60) NOT NULL, 
	direction VARCHAR(10) NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	http_status INTEGER, 
	response_ms INTEGER NOT NULL, 
	attempt INTEGER NOT NULL, 
	correlation_id VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(40), 
	entity_id INTEGER, 
	request_payload JSONB, 
	response_payload JSONB, 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_integration_log_status CHECK (status IN ('success','failed','retrying','retried_ok')), 
	FOREIGN KEY(integration_id) REFERENCES integrations (id) ON DELETE CASCADE, 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE SET NULL
);
CREATE INDEX ix_integration_logs_entity ON integration_logs (entity_type, entity_id);
CREATE INDEX ix_integration_logs_integration_created ON integration_logs (integration_id, created_at);
CREATE INDEX ix_integration_logs_status ON integration_logs (status);

-- inventory_items
CREATE TABLE inventory_items (
	id SERIAL NOT NULL, 
	branch_id INTEGER NOT NULL, 
	item_name VARCHAR(120) NOT NULL, 
	unit VARCHAR(20) NOT NULL, 
	quantity_on_hand NUMERIC(12, 2) NOT NULL, 
	reorder_level NUMERIC(12, 2) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_inventory_branch_item UNIQUE (branch_id, item_name), 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE CASCADE
);

-- loyalty_accounts
CREATE TABLE loyalty_accounts (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	member_number VARCHAR(30) NOT NULL, 
	points_balance INTEGER NOT NULL, 
	lifetime_points INTEGER NOT NULL, 
	tier VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_loyalty_balance_non_negative CHECK (points_balance >= 0), 
	UNIQUE (customer_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	UNIQUE (member_number)
);

-- orders
CREATE TABLE orders (
	id SERIAL NOT NULL, 
	order_number VARCHAR(30) NOT NULL, 
	branch_id INTEGER NOT NULL, 
	customer_id INTEGER, 
	channel VARCHAR(20) NOT NULL, 
	external_ref VARCHAR(80), 
	status VARCHAR(20) NOT NULL, 
	subtotal NUMERIC(12, 2) NOT NULL, 
	vat NUMERIC(12, 2) NOT NULL, 
	total NUMERIC(12, 2) NOT NULL, 
	pos_check_ref VARCHAR(40), 
	notes TEXT NOT NULL, 
	cancel_reason VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_order_channel_external_ref UNIQUE (channel, external_ref), 
	CONSTRAINT ck_order_total_positive CHECK (total >= 0), 
	CONSTRAINT ck_order_status CHECK (status IN ('received', 'sent_to_pos', 'accepted', 'preparing', 'ready', 'completed', 'cancelled', 'failed')), 
	CONSTRAINT ck_order_channel CHECK (channel IN ('in_store', 'uber_eats', 'mr_d', 'web')), 
	UNIQUE (order_number), 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE RESTRICT, 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL
);
CREATE INDEX ix_orders_branch_created ON orders (branch_id, created_at);
CREATE INDEX ix_orders_created_at ON orders (created_at);
CREATE INDEX ix_orders_status ON orders (status);

-- reconciliation_runs
CREATE TABLE reconciliation_runs (
	id SERIAL NOT NULL, 
	business_date DATE NOT NULL, 
	branch_id INTEGER, 
	status VARCHAR(15) NOT NULL, 
	total_orders INTEGER NOT NULL, 
	matched INTEGER NOT NULL, 
	discrepancies INTEGER NOT NULL, 
	discrepancy_value NUMERIC(12, 2) NOT NULL, 
	run_by VARCHAR(255) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE SET NULL
);
CREATE INDEX ix_reconciliation_runs_business_date ON reconciliation_runs (business_date);

-- users
CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role_id INTEGER NOT NULL, 
	branch_id INTEGER, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT, 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX ix_users_email ON users (email);

-- incidents
CREATE TABLE incidents (
	id SERIAL NOT NULL, 
	reference VARCHAR(20) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	severity VARCHAR(5) NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	category VARCHAR(40) NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	branch_id INTEGER, 
	integration_id INTEGER, 
	assigned_to_id INTEGER, 
	escalation_level INTEGER NOT NULL, 
	root_cause TEXT, 
	resolution_notes TEXT, 
	opened_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_incident_severity CHECK (severity IN ('SEV1', 'SEV2', 'SEV3', 'SEV4')), 
	CONSTRAINT ck_incident_status CHECK (status IN ('open', 'investigating', 'mitigated', 'resolved', 'closed')), 
	UNIQUE (reference), 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE SET NULL, 
	FOREIGN KEY(integration_id) REFERENCES integrations (id) ON DELETE SET NULL, 
	FOREIGN KEY(assigned_to_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_incidents_status_severity ON incidents (status, severity);

-- loyalty_transactions
CREATE TABLE loyalty_transactions (
	id SERIAL NOT NULL, 
	account_id INTEGER NOT NULL, 
	order_id INTEGER, 
	type VARCHAR(10) NOT NULL, 
	points INTEGER NOT NULL, 
	sync_status VARCHAR(10) NOT NULL, 
	external_ref VARCHAR(80), 
	error VARCHAR(255), 
	attempts INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_loyalty_txn_type CHECK (type IN ('earn','redeem','adjust')), 
	CONSTRAINT ck_loyalty_sync_status CHECK (sync_status IN ('pending','synced','failed')), 
	CONSTRAINT uq_loyalty_once_per_order UNIQUE (account_id, order_id, type), 
	FOREIGN KEY(account_id) REFERENCES loyalty_accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL
);
CREATE INDEX ix_loyalty_transactions_account_id ON loyalty_transactions (account_id);

-- order_items
CREATE TABLE order_items (
	id SERIAL NOT NULL, 
	order_id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	unit_price NUMERIC(12, 2) NOT NULL, 
	line_total NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_item_qty CHECK (quantity > 0), 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT
);
CREATE INDEX ix_order_items_order_id ON order_items (order_id);

-- payments
CREATE TABLE payments (
	id SERIAL NOT NULL, 
	order_id INTEGER NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	provider_reference VARCHAR(80), 
	idempotency_key VARCHAR(80), 
	amount NUMERIC(12, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	method VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	failure_reason VARCHAR(255), 
	refunded_amount NUMERIC(12, 2) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_payment_amount_positive CHECK (amount > 0), 
	CONSTRAINT ck_payment_status CHECK (status IN ('initiated', 'authorised', 'captured', 'failed', 'refunded', 'partially_refunded')), 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT, 
	UNIQUE (provider_reference), 
	UNIQUE (idempotency_key)
);
CREATE INDEX ix_payments_order_id ON payments (order_id);
CREATE INDEX ix_payments_status_created ON payments (status, created_at);

-- pos_transactions
CREATE TABLE pos_transactions (
	id SERIAL NOT NULL, 
	branch_id INTEGER NOT NULL, 
	check_number VARCHAR(40) NOT NULL, 
	order_id INTEGER, 
	total NUMERIC(12, 2) NOT NULL, 
	tender_type VARCHAR(20) NOT NULL, 
	business_date DATE NOT NULL, 
	synced_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_pos_branch_check UNIQUE (branch_id, check_number), 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE RESTRICT, 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL
);
CREATE INDEX ix_pos_tx_business_date ON pos_transactions (business_date);

-- incident_events
CREATE TABLE incident_events (
	id SERIAL NOT NULL, 
	incident_id INTEGER NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	message TEXT NOT NULL, 
	actor VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE
);
CREATE INDEX ix_incident_events_incident_id ON incident_events (incident_id);

-- reconciliation_records
CREATE TABLE reconciliation_records (
	id SERIAL NOT NULL, 
	run_id INTEGER NOT NULL, 
	branch_id INTEGER, 
	order_id INTEGER, 
	payment_id INTEGER, 
	issue_type VARCHAR(30) NOT NULL, 
	expected_amount NUMERIC(12, 2), 
	actual_amount NUMERIC(12, 2), 
	difference NUMERIC(12, 2), 
	details TEXT NOT NULL, 
	resolved BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_recon_issue_type CHECK (issue_type IN ('matched', 'missing_payment', 'failed_payment', 'duplicate_payment', 'amount_mismatch', 'missing_pos_record', 'pos_amount_mismatch', 'missing_settlement', 'settlement_mismatch', 'unknown_settlement')), 
	FOREIGN KEY(run_id) REFERENCES reconciliation_runs (id) ON DELETE CASCADE, 
	FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE SET NULL, 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL, 
	FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL
);
CREATE INDEX ix_recon_records_run_issue ON reconciliation_records (run_id, issue_type);

-- refunds
CREATE TABLE refunds (
	id SERIAL NOT NULL, 
	payment_id INTEGER NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	reason VARCHAR(255) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	provider_reference VARCHAR(80), 
	requested_by VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_refund_amount_positive CHECK (amount > 0), 
	FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE RESTRICT
);
CREATE INDEX ix_refunds_payment_id ON refunds (payment_id);
