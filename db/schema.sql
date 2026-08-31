-- ---------------------------------------------------------------------------
-- Insurance Claims Analytics — relational schema
--
-- The raw Kaggle dataset (data/insurance_claims.csv) is one flat table of
-- 1,000 rows x 39 columns. Here it is normalized into four related tables:
--
--   policies (1) ---- (1) vehicles
--       |
--       | (1)
--       v
--   incidents (1) ---- (1) claims
--
-- In this particular dataset the relationships are 1:1 (one incident and one
-- claim per policy), but the model is built to allow 1:many so it reflects how
-- a real insurer's system would be structured.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS policies;

-- ---------------------------------------------------------------------------
-- policies: the insured party + policy terms. policy_number is a natural PK.
-- ---------------------------------------------------------------------------
CREATE TABLE policies (
    policy_number           INT           NOT NULL PRIMARY KEY,
    months_as_customer      INT           NOT NULL,
    age                     INT           NOT NULL,
    policy_bind_date        DATE          NOT NULL,
    policy_state            CHAR(2)       NOT NULL,
    policy_csl              VARCHAR(10)   NOT NULL,   -- combined single limits, e.g. 250/500
    policy_deductable       INT           NOT NULL,
    policy_annual_premium   DECIMAL(10,2) NOT NULL,
    umbrella_limit          BIGINT        NULL,       -- one raw row has a negative value -> stored as NULL
    insured_zip             INT           NOT NULL,
    insured_sex             VARCHAR(6)    NOT NULL,
    insured_education_level  VARCHAR(20)  NOT NULL,
    insured_occupation      VARCHAR(40)   NOT NULL,
    insured_hobbies         VARCHAR(40)   NOT NULL,
    insured_relationship    VARCHAR(20)   NOT NULL,
    capital_gains           INT           NOT NULL,
    capital_loss            INT           NOT NULL,
    INDEX idx_policies_state (policy_state),
    INDEX idx_policies_bind_date (policy_bind_date)
);

-- ---------------------------------------------------------------------------
-- vehicles: the insured vehicle. Surrogate PK (raw data has no vehicle id).
-- ---------------------------------------------------------------------------
CREATE TABLE vehicles (
    vehicle_id      INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    policy_number   INT         NOT NULL,
    auto_make       VARCHAR(30) NOT NULL,
    auto_model      VARCHAR(30) NOT NULL,
    auto_year       INT         NOT NULL,
    CONSTRAINT fk_vehicles_policy FOREIGN KEY (policy_number)
        REFERENCES policies (policy_number),
    UNIQUE KEY uq_vehicles_policy (policy_number),
    INDEX idx_vehicles_make_model (auto_make, auto_model)
);

-- ---------------------------------------------------------------------------
-- incidents: the reported event. Surrogate PK. "?" placeholders in the raw
-- data become NULL for collision_type / property_damage / police_report_available.
-- ---------------------------------------------------------------------------
CREATE TABLE incidents (
    incident_id                 INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    policy_number               INT         NOT NULL,
    incident_date               DATE        NOT NULL,
    incident_type               VARCHAR(30) NOT NULL,
    collision_type              VARCHAR(20) NULL,
    incident_severity           VARCHAR(20) NOT NULL,
    authorities_contacted       VARCHAR(20) NULL,
    incident_state              CHAR(2)     NOT NULL,
    incident_city               VARCHAR(30) NOT NULL,
    incident_location           VARCHAR(60) NOT NULL,
    incident_hour_of_the_day    INT         NOT NULL,
    number_of_vehicles_involved INT         NOT NULL,
    property_damage             VARCHAR(3)  NULL,
    bodily_injuries             INT         NOT NULL,
    witnesses                   INT         NOT NULL,
    police_report_available     VARCHAR(3)  NULL,
    CONSTRAINT fk_incidents_policy FOREIGN KEY (policy_number)
        REFERENCES policies (policy_number),
    INDEX idx_incidents_date (incident_date),
    INDEX idx_incidents_severity (incident_severity),
    INDEX idx_incidents_state (incident_state)
);

-- ---------------------------------------------------------------------------
-- claims: the money + the ground-truth fraud label.
-- total_claim_amount = injury_claim + property_claim + vehicle_claim (holds for
-- 100% of rows in the raw data).
-- ---------------------------------------------------------------------------
CREATE TABLE claims (
    claim_id            INT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    policy_number       INT      NOT NULL,
    incident_id         INT      NOT NULL,
    total_claim_amount  INT      NOT NULL,
    injury_claim        INT      NOT NULL,
    property_claim      INT      NOT NULL,
    vehicle_claim       INT      NOT NULL,
    fraud_reported      CHAR(1)  NOT NULL,   -- 'Y' / 'N'
    CONSTRAINT fk_claims_policy FOREIGN KEY (policy_number)
        REFERENCES policies (policy_number),
    CONSTRAINT fk_claims_incident FOREIGN KEY (incident_id)
        REFERENCES incidents (incident_id),
    UNIQUE KEY uq_claims_incident (incident_id),
    INDEX idx_claims_fraud (fraud_reported)
);
