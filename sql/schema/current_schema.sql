--
-- Name: btree_gin; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;


--
-- Name: EXTENSION btree_gin; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gin IS 'support for indexing common datatypes in GIN';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: job_type_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE job_type_enum AS ENUM (
    'one_time',
    'scheduled',
    'recurring'
);


--
-- Name: log_level_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE log_level_enum AS ENUM (
    'DEBUG',
    'INFO',
    'WARNING',
    'ERROR',
    'CRITICAL'
);


--
-- Name: status_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE status_enum AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'cancelled',
    'active',
    'inactive'
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: content_hash; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE content_hash (
    content_hash character varying(64) NOT NULL,
    first_seen_page_id uuid,
    occurrence_count integer DEFAULT 1 NOT NULL,
    last_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_content_hash_valid_occurrence_count CHECK ((occurrence_count >= 1))
);


--
-- Name: TABLE content_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE content_hash IS 'Tracks content hash occurrences for duplicate detection';


--
-- Name: crawl_job; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_job (
    id uuid DEFAULT uuidv7() NOT NULL,
    website_id uuid,
    job_type job_type_enum DEFAULT 'one_time'::job_type_enum NOT NULL,
    seed_url character varying(2048) NOT NULL,
    inline_config jsonb,
    status status_enum DEFAULT 'pending'::status_enum NOT NULL,
    priority integer DEFAULT 5 NOT NULL,
    scheduled_at timestamp with time zone,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    cancelled_by character varying(255),
    cancellation_reason text,
    error_message text,
    retry_count integer DEFAULT 0 NOT NULL,
    max_retries integer DEFAULT 3 NOT NULL,
    metadata jsonb,
    variables jsonb,
    progress jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_crawl_job_config_source CHECK ((num_nonnulls(website_id, inline_config) = 1)),
    CONSTRAINT ck_crawl_job_valid_max_retries CHECK ((max_retries >= 0)),
    CONSTRAINT ck_crawl_job_valid_priority CHECK (((priority >= 1) AND (priority <= 10))),
    CONSTRAINT ck_crawl_job_valid_retry_count CHECK ((retry_count >= 0))
);


--
-- Name: TABLE crawl_job; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE crawl_job IS 'Stores crawl job definitions and execution state';


--
-- Name: COLUMN crawl_job.website_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN crawl_job.website_id IS 'Reference to website template (nullable for inline config jobs)';


--
-- Name: COLUMN crawl_job.inline_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN crawl_job.inline_config IS 'Inline configuration for jobs without website template';


--
-- Name: CONSTRAINT ck_crawl_job_config_source ON crawl_job; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT ck_crawl_job_config_source ON crawl_job IS 'Ensures exactly one of website_id or inline_config is set (mutually exclusive)';


--
-- Name: crawl_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log (
    id bigint CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
)
PARTITION BY RANGE (created_at);


--
-- Name: TABLE crawl_log; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE crawl_log IS 'Stores detailed crawl execution logs (partitioned by month)';


--
-- Name: crawl_log_id_seq1; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE crawl_log_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crawl_log_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE crawl_log_id_seq1 OWNED BY crawl_log.id;


--
-- Name: crawl_log_2025_08; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2025_08 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawl_log_2025_09; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2025_09 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawl_log_2025_10; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2025_10 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawl_log_2025_11; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2025_11 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawl_log_2025_12; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2025_12 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawl_log_2026_01; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2026_01 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawl_log_2026_02; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawl_log_2026_02 (
    id bigint DEFAULT nextval('crawl_log_id_seq1'::regclass) CONSTRAINT crawl_log_id_not_null1 NOT NULL,
    job_id uuid CONSTRAINT crawl_log_job_id_not_null1 NOT NULL,
    website_id uuid CONSTRAINT crawl_log_website_id_not_null1 NOT NULL,
    step_name character varying(255),
    log_level log_level_enum DEFAULT 'INFO'::log_level_enum CONSTRAINT crawl_log_log_level_not_null1 NOT NULL,
    message text CONSTRAINT crawl_log_message_not_null1 NOT NULL,
    context jsonb,
    trace_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP CONSTRAINT crawl_log_created_at_not_null1 NOT NULL
);


--
-- Name: crawled_page; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE crawled_page (
    id uuid DEFAULT uuidv7() NOT NULL,
    website_id uuid NOT NULL,
    job_id uuid NOT NULL,
    url character varying(2048) NOT NULL,
    url_hash character varying(64) NOT NULL,
    content_hash character varying(64) NOT NULL,
    title character varying(500),
    extracted_content text,
    metadata jsonb,
    gcs_html_path character varying(1024),
    gcs_documents jsonb,
    is_duplicate boolean DEFAULT false NOT NULL,
    duplicate_of uuid,
    similarity_score integer,
    crawled_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_crawled_page_valid_similarity_score CHECK (((similarity_score IS NULL) OR ((similarity_score >= 0) AND (similarity_score <= 100))))
);


--
-- Name: TABLE crawled_page; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE crawled_page IS 'Stores crawled page data and content';


--
-- Name: scheduled_job; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE scheduled_job (
    id uuid DEFAULT uuidv7() NOT NULL,
    website_id uuid NOT NULL,
    cron_schedule character varying(255) NOT NULL,
    next_run_time timestamp with time zone NOT NULL,
    last_run_time timestamp with time zone,
    is_active boolean DEFAULT true NOT NULL,
    job_config jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_scheduled_job_valid_cron CHECK (((cron_schedule)::text ~ '^(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+|[A-Z]{3})\s+(\*|[0-9,\-/]+|[A-Z]{3})(\s+(\*|[0-9,\-/]+))?$'::text))
);


--
-- Name: TABLE scheduled_job; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE scheduled_job IS 'Stores scheduled crawl job configurations with cron schedules';


--
-- Name: COLUMN scheduled_job.cron_schedule; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN scheduled_job.cron_schedule IS 'Cron expression defining when the job should run';


--
-- Name: COLUMN scheduled_job.next_run_time; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN scheduled_job.next_run_time IS 'Next scheduled execution time';


--
-- Name: COLUMN scheduled_job.last_run_time; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN scheduled_job.last_run_time IS 'Most recent execution time';


--
-- Name: COLUMN scheduled_job.is_active; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN scheduled_job.is_active IS 'Flag to pause/resume schedule without deleting';


--
-- Name: COLUMN scheduled_job.job_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN scheduled_job.job_config IS 'Job-specific configuration overrides';


--
-- Name: website; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE website (
    id uuid DEFAULT uuidv7() NOT NULL,
    name character varying(255) NOT NULL,
    base_url character varying(2048) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    status status_enum DEFAULT 'active'::status_enum NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by character varying(255),
    cron_schedule character varying(255) DEFAULT '0 0 1,15 * *'::character varying
);


--
-- Name: TABLE website; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE website IS 'Stores website configurations and metadata';


--
-- Name: COLUMN website.cron_schedule; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN website.cron_schedule IS 'Default cron schedule expression for this website (default: "0 0 1,15 * *" runs on 1st and 15th at midnight, approximately every 2 weeks)';


--
-- Name: website_config_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE website_config_history (
    id uuid DEFAULT uuidv7() NOT NULL,
    website_id uuid NOT NULL,
    version integer NOT NULL,
    config jsonb NOT NULL,
    changed_by character varying(255),
    change_reason text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_website_config_history_valid_version CHECK ((version >= 1))
);


--
-- Name: TABLE website_config_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE website_config_history IS 'Stores configuration history for websites to track changes over time';


--
-- Name: COLUMN website_config_history.version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN website_config_history.version IS 'Version number, incremented with each change (starts at 1)';


--
-- Name: COLUMN website_config_history.config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN website_config_history.config IS 'Full configuration snapshot at this version';


--
-- Name: COLUMN website_config_history.changed_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN website_config_history.changed_by IS 'User or system that made the change';


--
-- Name: COLUMN website_config_history.change_reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN website_config_history.change_reason IS 'Optional description of why the change was made';


--
-- Name: crawl_log_2025_08; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2025_08 FOR VALUES FROM ('2025-08-01 00:00:00+00') TO ('2025-09-01 00:00:00+00');


--
-- Name: crawl_log_2025_09; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2025_09 FOR VALUES FROM ('2025-09-01 00:00:00+00') TO ('2025-10-01 00:00:00+00');


--
-- Name: crawl_log_2025_10; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2025_10 FOR VALUES FROM ('2025-10-01 00:00:00+00') TO ('2025-11-01 00:00:00+00');


--
-- Name: crawl_log_2025_11; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2025_11 FOR VALUES FROM ('2025-11-01 00:00:00+00') TO ('2025-12-01 00:00:00+00');


--
-- Name: crawl_log_2025_12; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2025_12 FOR VALUES FROM ('2025-12-01 00:00:00+00') TO ('2026-01-01 00:00:00+00');


--
-- Name: crawl_log_2026_01; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2026_01 FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2026-02-01 00:00:00+00');


--
-- Name: crawl_log_2026_02; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ATTACH PARTITION crawl_log_2026_02 FOR VALUES FROM ('2026-02-01 00:00:00+00') TO ('2026-03-01 00:00:00+00');


--
-- Name: crawl_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log ALTER COLUMN id SET DEFAULT nextval('crawl_log_id_seq1'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: content_hash content_hash_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY content_hash
    ADD CONSTRAINT content_hash_pkey PRIMARY KEY (content_hash);


--
-- Name: crawl_job crawl_job_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_job
    ADD CONSTRAINT crawl_job_pkey PRIMARY KEY (id);


--
-- Name: crawl_log crawl_log_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log
    ADD CONSTRAINT crawl_log_pkey1 PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2025_08 crawl_log_2025_08_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2025_08
    ADD CONSTRAINT crawl_log_2025_08_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2025_09 crawl_log_2025_09_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2025_09
    ADD CONSTRAINT crawl_log_2025_09_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2025_10 crawl_log_2025_10_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2025_10
    ADD CONSTRAINT crawl_log_2025_10_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2025_11 crawl_log_2025_11_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2025_11
    ADD CONSTRAINT crawl_log_2025_11_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2025_12 crawl_log_2025_12_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2025_12
    ADD CONSTRAINT crawl_log_2025_12_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2026_01 crawl_log_2026_01_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2026_01
    ADD CONSTRAINT crawl_log_2026_01_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawl_log_2026_02 crawl_log_2026_02_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_log_2026_02
    ADD CONSTRAINT crawl_log_2026_02_pkey PRIMARY KEY (id, created_at);


--
-- Name: crawled_page crawled_page_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawled_page
    ADD CONSTRAINT crawled_page_pkey PRIMARY KEY (id);


--
-- Name: scheduled_job scheduled_job_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY scheduled_job
    ADD CONSTRAINT scheduled_job_pkey PRIMARY KEY (id);


--
-- Name: website_config_history website_config_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY website_config_history
    ADD CONSTRAINT website_config_history_pkey PRIMARY KEY (id);


--
-- Name: website website_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY website
    ADD CONSTRAINT website_name_key UNIQUE (name);


--
-- Name: website website_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY website
    ADD CONSTRAINT website_pkey PRIMARY KEY (id);


--
-- Name: crawl_log_2025_08_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_08_job_created_idx ON crawl_log_2025_08 USING btree (job_id, created_at);


--
-- Name: crawl_log_2025_08_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_08_job_id_idx ON crawl_log_2025_08 USING btree (job_id);


--
-- Name: crawl_log_2025_08_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_08_log_level_idx ON crawl_log_2025_08 USING btree (log_level);


--
-- Name: crawl_log_2025_08_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_08_trace_id_idx ON crawl_log_2025_08 USING btree (trace_id);


--
-- Name: crawl_log_2025_08_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_08_website_id_idx ON crawl_log_2025_08 USING btree (website_id);


--
-- Name: crawl_log_2025_09_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_09_job_created_idx ON crawl_log_2025_09 USING btree (job_id, created_at);


--
-- Name: crawl_log_2025_09_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_09_job_id_idx ON crawl_log_2025_09 USING btree (job_id);


--
-- Name: crawl_log_2025_09_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_09_log_level_idx ON crawl_log_2025_09 USING btree (log_level);


--
-- Name: crawl_log_2025_09_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_09_trace_id_idx ON crawl_log_2025_09 USING btree (trace_id);


--
-- Name: crawl_log_2025_09_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_09_website_id_idx ON crawl_log_2025_09 USING btree (website_id);


--
-- Name: crawl_log_2025_10_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_10_job_created_idx ON crawl_log_2025_10 USING btree (job_id, created_at);


--
-- Name: crawl_log_2025_10_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_10_job_id_idx ON crawl_log_2025_10 USING btree (job_id);


--
-- Name: crawl_log_2025_10_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_10_log_level_idx ON crawl_log_2025_10 USING btree (log_level);


--
-- Name: crawl_log_2025_10_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_10_trace_id_idx ON crawl_log_2025_10 USING btree (trace_id);


--
-- Name: crawl_log_2025_10_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_10_website_id_idx ON crawl_log_2025_10 USING btree (website_id);


--
-- Name: crawl_log_2025_11_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_11_job_created_idx ON crawl_log_2025_11 USING btree (job_id, created_at);


--
-- Name: crawl_log_2025_11_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_11_job_id_idx ON crawl_log_2025_11 USING btree (job_id);


--
-- Name: crawl_log_2025_11_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_11_log_level_idx ON crawl_log_2025_11 USING btree (log_level);


--
-- Name: crawl_log_2025_11_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_11_trace_id_idx ON crawl_log_2025_11 USING btree (trace_id);


--
-- Name: crawl_log_2025_11_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_11_website_id_idx ON crawl_log_2025_11 USING btree (website_id);


--
-- Name: crawl_log_2025_12_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_12_job_created_idx ON crawl_log_2025_12 USING btree (job_id, created_at);


--
-- Name: crawl_log_2025_12_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_12_job_id_idx ON crawl_log_2025_12 USING btree (job_id);


--
-- Name: crawl_log_2025_12_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_12_log_level_idx ON crawl_log_2025_12 USING btree (log_level);


--
-- Name: crawl_log_2025_12_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_12_trace_id_idx ON crawl_log_2025_12 USING btree (trace_id);


--
-- Name: crawl_log_2025_12_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2025_12_website_id_idx ON crawl_log_2025_12 USING btree (website_id);


--
-- Name: crawl_log_2026_01_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_01_job_created_idx ON crawl_log_2026_01 USING btree (job_id, created_at);


--
-- Name: crawl_log_2026_01_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_01_job_id_idx ON crawl_log_2026_01 USING btree (job_id);


--
-- Name: crawl_log_2026_01_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_01_log_level_idx ON crawl_log_2026_01 USING btree (log_level);


--
-- Name: crawl_log_2026_01_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_01_trace_id_idx ON crawl_log_2026_01 USING btree (trace_id);


--
-- Name: crawl_log_2026_01_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_01_website_id_idx ON crawl_log_2026_01 USING btree (website_id);


--
-- Name: crawl_log_2026_02_job_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_02_job_created_idx ON crawl_log_2026_02 USING btree (job_id, created_at);


--
-- Name: crawl_log_2026_02_job_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_02_job_id_idx ON crawl_log_2026_02 USING btree (job_id);


--
-- Name: crawl_log_2026_02_log_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_02_log_level_idx ON crawl_log_2026_02 USING btree (log_level);


--
-- Name: crawl_log_2026_02_trace_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_02_trace_id_idx ON crawl_log_2026_02 USING btree (trace_id);


--
-- Name: crawl_log_2026_02_website_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crawl_log_2026_02_website_id_idx ON crawl_log_2026_02 USING btree (website_id);


--
-- Name: ix_content_hash_last_seen_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_hash_last_seen_at ON content_hash USING btree (last_seen_at);


--
-- Name: ix_content_hash_occurrence_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_hash_occurrence_count ON content_hash USING btree (occurrence_count);


--
-- Name: ix_crawl_job_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_created_at ON crawl_job USING btree (created_at);


--
-- Name: ix_crawl_job_inline_config; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_inline_config ON crawl_job USING gin (inline_config) WHERE (inline_config IS NOT NULL);


--
-- Name: ix_crawl_job_inline_config_jobs; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_inline_config_jobs ON crawl_job USING btree (created_at DESC) WHERE ((website_id IS NULL) AND (inline_config IS NOT NULL));


--
-- Name: ix_crawl_job_job_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_job_type ON crawl_job USING btree (job_type);


--
-- Name: ix_crawl_job_priority_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_priority_status ON crawl_job USING btree (priority, status);


--
-- Name: ix_crawl_job_scheduled_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_scheduled_at ON crawl_job USING btree (scheduled_at);


--
-- Name: ix_crawl_job_seed_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_seed_url ON crawl_job USING btree (seed_url);


--
-- Name: ix_crawl_job_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_status ON crawl_job USING btree (status);


--
-- Name: ix_crawl_job_website_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawl_job_website_id ON crawl_job USING btree (website_id);


--
-- Name: ix_crawled_page_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_content_hash ON crawled_page USING btree (content_hash);


--
-- Name: ix_crawled_page_crawled_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_crawled_at ON crawled_page USING btree (crawled_at);


--
-- Name: ix_crawled_page_duplicate_of; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_duplicate_of ON crawled_page USING btree (duplicate_of);


--
-- Name: ix_crawled_page_is_duplicate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_is_duplicate ON crawled_page USING btree (is_duplicate);


--
-- Name: ix_crawled_page_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_job_id ON crawled_page USING btree (job_id);


--
-- Name: ix_crawled_page_url_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_url_hash ON crawled_page USING btree (url_hash);


--
-- Name: ix_crawled_page_website_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crawled_page_website_id ON crawled_page USING btree (website_id);


--
-- Name: ix_crawled_page_website_url_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_crawled_page_website_url_hash ON crawled_page USING btree (website_id, url_hash);


--
-- Name: ix_scheduled_job_active_next_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_job_active_next_run ON scheduled_job USING btree (is_active, next_run_time) WHERE (is_active = true);


--
-- Name: INDEX ix_scheduled_job_active_next_run; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX ix_scheduled_job_active_next_run IS 'Optimized index for finding next jobs to execute';


--
-- Name: ix_scheduled_job_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_job_is_active ON scheduled_job USING btree (is_active);


--
-- Name: ix_scheduled_job_next_run_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_job_next_run_time ON scheduled_job USING btree (next_run_time);


--
-- Name: ix_scheduled_job_website_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_job_website_id ON scheduled_job USING btree (website_id);


--
-- Name: ix_website_config; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_website_config ON website USING gin (config);


--
-- Name: ix_website_config_history_website_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_website_config_history_website_id ON website_config_history USING btree (website_id);


--
-- Name: ix_website_config_history_website_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_website_config_history_website_version ON website_config_history USING btree (website_id, version DESC);


--
-- Name: ix_website_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_website_created_at ON website USING btree (created_at);


--
-- Name: ix_website_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_website_status ON website USING btree (status);


--
-- Name: uq_website_config_history_website_version; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_website_config_history_website_version ON website_config_history USING btree (website_id, version);


--
-- Name: crawl_log_2025_08_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2025_08_pkey;


--
-- Name: crawl_log_2025_09_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2025_09_pkey;


--
-- Name: crawl_log_2025_10_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2025_10_pkey;


--
-- Name: crawl_log_2025_11_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2025_11_pkey;


--
-- Name: crawl_log_2025_12_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2025_12_pkey;


--
-- Name: crawl_log_2026_01_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2026_01_pkey;


--
-- Name: crawl_log_2026_02_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX crawl_log_pkey1 ATTACH PARTITION crawl_log_2026_02_pkey;


--
-- Name: content_hash content_hash_first_seen_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY content_hash
    ADD CONSTRAINT content_hash_first_seen_page_id_fkey FOREIGN KEY (first_seen_page_id) REFERENCES crawled_page(id) ON DELETE SET NULL;


--
-- Name: crawl_job crawl_job_website_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawl_job
    ADD CONSTRAINT crawl_job_website_id_fkey FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE;


--
-- Name: crawled_page crawled_page_duplicate_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawled_page
    ADD CONSTRAINT crawled_page_duplicate_of_fkey FOREIGN KEY (duplicate_of) REFERENCES crawled_page(id) ON DELETE SET NULL;


--
-- Name: crawled_page crawled_page_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawled_page
    ADD CONSTRAINT crawled_page_job_id_fkey FOREIGN KEY (job_id) REFERENCES crawl_job(id) ON DELETE CASCADE;


--
-- Name: crawled_page crawled_page_website_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY crawled_page
    ADD CONSTRAINT crawled_page_website_id_fkey FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE;


--
-- Name: crawl_log fk_crawl_log_job; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE crawl_log
    ADD CONSTRAINT fk_crawl_log_job FOREIGN KEY (job_id) REFERENCES crawl_job(id) ON DELETE CASCADE;


--
-- Name: crawl_log fk_crawl_log_website; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE crawl_log
    ADD CONSTRAINT fk_crawl_log_website FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE;


--
-- Name: scheduled_job scheduled_job_website_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY scheduled_job
    ADD CONSTRAINT scheduled_job_website_id_fkey FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE;


--
-- Name: website_config_history website_config_history_website_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY website_config_history
    ADD CONSTRAINT website_config_history_website_id_fkey FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


