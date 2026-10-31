CREATE SCHEMA IF NOT EXISTS smart_trash;

CREATE TABLE IF NOT EXISTS smart_trash.devices
(
    device_id          text                     PRIMARY KEY,
    area_id            text                     NOT NULL,
    description        text,
    firmware_version   text,
    registered_at      timestamp with time zone NOT NULL DEFAULT now(),
    last_seen_at       timestamp with time zone,
    status             text                     NOT NULL DEFAULT 'registered',

    CONSTRAINT ck_devices_status
        CHECK (status IN ('registered', 'online', 'offline', 'disabled'))
);

CREATE TABLE IF NOT EXISTS smart_trash.measurement_batches
(
    batch_id           text                     PRIMARY KEY,
    message_id         text                     NOT NULL UNIQUE,
    device_id          text                     NOT NULL,
    sequence_number    bigint                   NOT NULL,
    sent_at            timestamp with time zone NOT NULL,
    received_at        timestamp with time zone NOT NULL DEFAULT now(),
    sample_count       integer                  NOT NULL,
    processing_status  text                     NOT NULL DEFAULT 'received',
    payload_hash       text,

    CONSTRAINT fk_measurement_batches_device
        FOREIGN KEY (device_id)
        REFERENCES smart_trash.devices (device_id),

    CONSTRAINT ck_measurement_batches_sample_count
        CHECK (sample_count >= 0),

    CONSTRAINT ck_measurement_batches_status
        CHECK
        (
            processing_status IN
            (
                'received',
                'processing',
                'completed',
                'rejected'
            )
        )
);

CREATE TABLE IF NOT EXISTS smart_trash.measurements
(
    recorded_at         timestamp with time zone NOT NULL,
    device_id           text                     NOT NULL,
    batch_id            text                     NOT NULL,
    fulfilment_percent  double precision,
    weight_percent      double precision,
    battery_voltage     double precision,
    quality_code        integer                  NOT NULL DEFAULT 0,
    received_at         timestamp with time zone NOT NULL DEFAULT now(),

    CONSTRAINT fk_measurements_device
        FOREIGN KEY (device_id)
        REFERENCES smart_trash.devices (device_id),

    CONSTRAINT fk_measurements_batch
        FOREIGN KEY (batch_id)
        REFERENCES smart_trash.measurement_batches (batch_id),

    CONSTRAINT uq_measurements_device_time
        UNIQUE (device_id, recorded_at),

    CONSTRAINT ck_measurements_fulfilment
        CHECK
        (
            fulfilment_percent IS NULL
            OR fulfilment_percent BETWEEN 0 AND 100
        ),
		
	CONSTRAINT ck_measurements_weight
        CHECK
        (
            weight_percent IS NULL
            OR weight_percent BETWEEN 0 AND 100
        ),

    CONSTRAINT ck_measurements_battery
        CHECK
        (
            battery_voltage IS NULL
            OR battery_voltage >= 0
        )
);

CREATE TABLE IF NOT EXISTS smart_trash.ingestion_errors
(
    error_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at        timestamp with time zone NOT NULL DEFAULT now(),
    mqtt_topic         text                     NOT NULL,
    message_id         text,
    error_code         text                     NOT NULL,
    error_description  text                     NOT NULL,
    original_payload   jsonb
);