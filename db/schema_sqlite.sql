-- ---------------------------------------------------------------------------
-- SQLite mirror of db/schema.sql, for the Copilot extension's fallback backend
-- (DB_BACKEND=sqlite). Same 4 tables, same columns and relationships; only the
-- dialect-specific bits change (AUTOINCREMENT syntax, separate CREATE INDEX
-- statements, no inline MySQL INDEX clauses). The original db/schema.sql is
-- untouched -- this file is additive, used only by copilot/build_sqlite.py.
-- ---------------------------------------------------------------------------

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS policies;

CREATE TABLE policies (
    policy_number           INTEGER       NOT NULL PRIMARY KEY,
    months_as_customer      INTEGER       NOT NULL,
    age                     INTEGER       NOT NULL,
    policy_bind_date        TEXT          NOT NULL,
    policy_state             TEXT         NOT NULL,
    policy_csl               TEXT         NOT NULL,
    policy_deductable       INTEGER       NOT NULL,
    policy_annual_premium   REAL          NOT NULL,
    umbrella_limit          INTEGER       NULL,
    insured_zip              INTEGER      NOT NULL,
    insured_sex              TEXT         NOT NULL,
    insured_education_level  TEXT         NOT NULL,
    insured_occupation       TEXT         NOT NULL,
    insured_hobbies          TEXT         NOT NULL,
    insured_relationship     TEXT         NOT NULL,
    capital_gains            INTEGER      NOT NULL,
    capital_loss             INTEGER      NOT NULL
);
CREATE INDEX idx_policies_state ON policies (policy_state);
CREATE INDEX idx_policies_bind_date ON policies (policy_bind_date);

CREATE TABLE vehicles (
    vehicle_id      INTEGER     NOT NULL PRIMARY KEY AUTOINCREMENT,
    policy_number   INTEGER     NOT NULL,
    auto_make        TEXT       NOT NULL,
    auto_model       TEXT       NOT NULL,
    auto_year       INTEGER     NOT NULL,
    FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
);
CREATE UNIQUE INDEX uq_vehicles_policy ON vehicles (policy_number);
CREATE INDEX idx_vehicles_make_model ON vehicles (auto_make, auto_model);

CREATE TABLE incidents (
    incident_id                 INTEGER    NOT NULL PRIMARY KEY AUTOINCREMENT,
    policy_number               INTEGER    NOT NULL,
    incident_date                TEXT      NOT NULL,
    incident_type                TEXT      NOT NULL,
    collision_type                TEXT     NULL,
    incident_severity             TEXT     NOT NULL,
    authorities_contacted         TEXT     NULL,
    incident_state                TEXT     NOT NULL,
    incident_city                 TEXT     NOT NULL,
    incident_location              TEXT    NOT NULL,
    incident_hour_of_the_day    INTEGER    NOT NULL,
    number_of_vehicles_involved INTEGER    NOT NULL,
    property_damage                TEXT    NULL,
    bodily_injuries              INTEGER   NOT NULL,
    witnesses                    INTEGER   NOT NULL,
    police_report_available        TEXT    NULL,
    FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
);
CREATE INDEX idx_incidents_date ON incidents (incident_date);
CREATE INDEX idx_incidents_severity ON incidents (incident_severity);
CREATE INDEX idx_incidents_state ON incidents (incident_state);

CREATE TABLE claims (
    claim_id            INTEGER   NOT NULL PRIMARY KEY AUTOINCREMENT,
    policy_number       INTEGER   NOT NULL,
    incident_id         INTEGER   NOT NULL,
    total_claim_amount  INTEGER   NOT NULL,
    injury_claim        INTEGER   NOT NULL,
    property_claim      INTEGER   NOT NULL,
    vehicle_claim       INTEGER   NOT NULL,
    fraud_reported        TEXT    NOT NULL,
    FOREIGN KEY (policy_number) REFERENCES policies (policy_number),
    FOREIGN KEY (incident_id) REFERENCES incidents (incident_id)
);
CREATE UNIQUE INDEX uq_claims_incident ON claims (incident_id);
CREATE INDEX idx_claims_fraud ON claims (fraud_reported);
