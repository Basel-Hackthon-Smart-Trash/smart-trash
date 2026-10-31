SELECT create_hypertable(
    'smart_trash.measurements',
    by_range('recorded_at'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS ix_measurements_device_recorded_at
    ON smart_trash.measurements
    (device_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS ix_measurement_batches_device_sent_at
    ON smart_trash.measurement_batches
    (device_id, sent_at DESC);

CREATE INDEX IF NOT EXISTS ix_measurement_batches_received_at
    ON smart_trash.measurement_batches
    (received_at DESC);