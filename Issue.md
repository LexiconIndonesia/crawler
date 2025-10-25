# GitHub Issues for Lexicon Crawler

## 0. Foundational Infrastructure

### Issue #0: Implement database models and Redis data structures
**Description**: Create SQLAlchemy ORM models for PostgreSQL and Redis data structure implementations. This is the foundational infrastructure required for all other features.

**Acceptance Criteria**:

**PostgreSQL Models (SQLAlchemy ORM)**:
- [ ] Create `Website` model with fields: id (UUID), name, base_url, config (JSONB), status, created_at, updated_at, created_by
- [ ] Add indexes: status, config (GIN), unique constraint on name
- [ ] Create `CrawlJob` model with fields: id (UUID), website_id (FK), job_type, seed_url, embedded_config (JSONB), status, priority, scheduled_at, started_at, completed_at, cancelled_at, cancelled_by, cancellation_reason, error_message, retry_count, max_retries, metadata (JSONB), variables (JSONB), progress (JSONB), created_at, updated_at
- [ ] Add indexes on: website_id, job_type, status, scheduled_at, created_at, seed_url
- [ ] Create `CrawledPage` model with fields: id (UUID), website_id (FK), job_id (FK), url, url_hash, content_hash, title, extracted_content, metadata (JSONB), gcs_html_path, gcs_documents (JSONB), is_duplicate, duplicate_of (FK), similarity_score, crawled_at, created_at
- [ ] Add indexes on: website_id, job_id, url_hash, content_hash, crawled_at, is_duplicate
- [ ] Create `ContentHash` model with fields: content_hash (PK), first_seen_page_id (FK), occurrence_count, last_seen_at, created_at
- [ ] Add index on: last_seen_at
- [ ] Create `CrawlLog` model with fields: id (BIGSERIAL), job_id (FK), website_id (FK), step_name, log_level, message, context (JSONB), trace_id (UUID), created_at
- [ ] Add indexes on: job_id, website_id, log_level, created_at, trace_id
- [ ] All models include proper relationships (foreign keys, cascades)
- [ ] All models include __repr__ and __str__ methods
- [ ] All timestamp fields use UTC timezone

**Database Migrations (Alembic)**:
- [ ] Initialize Alembic configuration
- [ ] Create initial migration with all tables
- [ ] Migration includes all indexes and constraints
- [ ] Migration script is idempotent and reversible
- [ ] Migration tested on clean database

**Redis Data Structures**:
- [ ] Implement `URLDeduplicationCache` class with methods: set(url_hash, data, ttl), get(url_hash), exists(url_hash), delete(url_hash)
- [ ] Implement `JobCancellationFlag` class with methods: set_cancellation(job_id), is_cancelled(job_id), clear_cancellation(job_id)
- [ ] Implement `RateLimiter` class with methods: increment(website_id), is_rate_limited(website_id), get_count(website_id)
- [ ] Implement `BrowserPoolStatus` class with methods: update_status(active_browsers, active_contexts, available_contexts, memory_mb), get_status()
- [ ] Implement `JobProgressCache` class with methods: set_progress(job_id, progress), get_progress(job_id), delete_progress(job_id)
- [ ] All Redis operations include proper error handling (connection failures, timeouts)
- [ ] All Redis operations include TTL management where appropriate
- [ ] All Redis data structures support JSON serialization/deserialization

**Pydantic Schemas**:
- [ ] Create Pydantic schemas for all models (Base, Create, Update, Response)
- [ ] Include proper validation rules (URL validation, enum validation, etc.)
- [ ] Include example values in schema docstrings
- [ ] Schemas support nested objects where required (config, metadata, variables)

**Base Infrastructure**:
- [ ] Create base model class with common fields (id, created_at, updated_at)
- [ ] Database session management with proper connection pooling
- [ ] Redis connection manager with connection pooling
- [ ] Health check endpoints for both PostgreSQL and Redis
- [ ] Database and Redis connection utilities with retry logic

**Testing**:
- [ ] Unit tests for all model methods and properties
- [ ] Unit tests for all Redis operations
- [ ] Integration tests with test database (using pytest fixtures)
- [ ] Integration tests with test Redis instance
- [ ] Test data factories using Faker or factory_boy
- [ ] Tests for all model relationships and cascades
- [ ] Tests for JSONB field serialization/deserialization
- [ ] Tests for timezone handling
- [ ] Tests for migration up and down

**Documentation**:
- [ ] Docstrings for all models, fields, and methods
- [ ] README with database schema diagram
- [ ] Migration guide for running database setup
- [ ] Examples of common queries and operations

**Size**: Large | **Priority**: Critical (Blocking)

**Notes**: This issue must be completed before any other feature development can begin. All other issues depend on these foundational data models.

---

## 3.1 Job Submission Modes

### Issue #1: Create database schema for scheduled jobs
**Description**: Implement database models and migrations for scheduled jobs with cron schedules.

**Acceptance Criteria**:
- [ ] Website model includes cron_schedule field
- [ ] Migration creates required tables
- [ ] Indexes on website_id and next_run_time
- [ ] Schema includes is_active flag for pausing schedules

**Size**: Small | **Priority**: High

---

### Issue #2: Implement API endpoint for creating scheduled jobs
**Description**: Create POST /api/websites endpoint to configure recurring crawls.

**Acceptance Criteria**:
- [ ] Accept website configuration with selectors and steps
- [ ] Validate cron schedule expression
- [ ] Store configuration in PostgreSQL
- [ ] Return created website with ID and next run time
- [ ] Unit tests for validation logic

**Size**: Small | **Priority**: High

---

### Issue #3: Create database schema for seed URL submissions
**Description**: Extend job model to support seed URL submissions with template reference or inline config.

**Acceptance Criteria**:
- [ ] Job model includes seed_url field
- [ ] Job model includes website_id (nullable for inline config)
- [ ] Job model includes inline_config JSONB field
- [ ] Job model includes variables JSONB field
- [ ] Migration with proper indexes

**Size**: Small | **Priority**: High

---

### Issue #4: Implement seed URL submission API - Mode A (Template Reference)
**Description**: Create POST /api/jobs/seed endpoint for submitting URLs with existing website template.

**Acceptance Criteria**:
- [ ] Accept seed_url and website_id
- [ ] Accept optional variables for substitution
- [ ] Load configuration from database
- [ ] Create job with seed URL and template reference
- [ ] Return job ID and status
- [ ] Unit tests for template loading

**Size**: Small | **Priority**: High

---

### Issue #5: Implement seed URL submission API - Mode B (Inline Config)
**Description**: Create POST /api/jobs/seed endpoint variant for ad-hoc crawls with inline configuration.

**Acceptance Criteria**:
- [ ] Accept seed_url and full inline configuration
- [ ] Validate inline configuration against schema
- [ ] Create job with embedded configuration
- [ ] Support one-time execution without database template
- [ ] Return job ID and status
- [ ] Unit tests for inline config validation

**Size**: Small | **Priority**: Medium

---

## 3.2 Seed URL Crawling

### Issue #6: Implement URL normalization utility
**Description**: Create utility function to normalize URLs for deduplication and comparison.

**Acceptance Criteria**:
- [ ] Remove tracking parameters
- [ ] Sort query parameters consistently
- [ ] Handle URL redirects
- [ ] Convert to lowercase where appropriate
- [ ] Preserve semantic parameters (page, category, etc.)
- [ ] Unit tests with edge cases

**Size**: Small | **Priority**: High

---

### Issue #7: Implement pagination detection from seed URL
**Description**: Create logic to detect and follow pagination starting from arbitrary seed URL.

**Acceptance Criteria**:
- [ ] Extract current page number from seed URL
- [ ] Detect pagination pattern (next button, page links, URL pattern)
- [ ] Continue from seed URL page to end
- [ ] Handle last page detection (no next page)
- [ ] Detect circular pagination
- [ ] Unit tests for various pagination patterns

**Size**: Medium | **Priority**: High

---

### Issue #8: Implement detail URL extraction from list pages
**Description**: Extract detail page URLs from listing pages using configured selectors.

**Acceptance Criteria**:
- [ ] Apply CSS/XPath selectors to list pages
- [ ] Extract URLs with metadata (title, preview)
- [ ] Deduplicate URLs within same crawl
- [ ] Handle relative URLs correctly
- [ ] Handle URLs in data attributes
- [ ] Unit tests with sample HTML

**Size**: Small | **Priority**: High

---

### Issue #9: Implement variable substitution engine
**Description**: Create variable substitution system supporting multiple variable sources.

**Acceptance Criteria**:
- [ ] Support `${variables.key}` from job submission
- [ ] Support `${ENV.KEY}` from environment variables
- [ ] Support `${input.field}` from previous step output
- [ ] Support `${pagination.current_page}` auto-increment
- [ ] Support `${metadata.field}` from job metadata
- [ ] Handle missing variables (warning vs error)
- [ ] Type conversion (string, integer, boolean)
- [ ] Unit tests for all variable types

**Size**: Medium | **Priority**: High

---

### Issue #10: Implement seed URL algorithm with error handling
**Description**: Main algorithm for seed URL crawling with comprehensive error handling.

**Acceptance Criteria**:
- [ ] Handle seed URL returns 404 (fail immediately)
- [ ] Handle pagination selector not found (single page mode)
- [ ] Handle no detail URLs found (log warning, complete)
- [ ] Handle invalid configuration (validation error)
- [ ] Handle circular pagination detection
- [ ] Handle max_pages limit
- [ ] Log all edge cases appropriately
- [ ] Integration tests for positive and negative cases

**Size**: Large | **Priority**: High

---

## 3.3 Job Cancellation

### Issue #11: Implement Redis cancellation flag system
**Description**: Create Redis-based signaling for job cancellation.

**Acceptance Criteria**:
- [ ] Set Redis flag: `cancel:job:{job_id} = true`
- [ ] TTL of 1 hour for cancellation flags
- [ ] Worker checks flag every 1-2 seconds
- [ ] Delete flag after successful cancellation
- [ ] Handle Redis connection failures gracefully

**Size**: Small | **Priority**: High

---

### Issue #12: Create cancellation API endpoint
**Description**: Implement POST /api/jobs/{job_id}/cancel endpoint.

**Acceptance Criteria**:
- [ ] Validate job exists
- [ ] Check job is not already completed/cancelled
- [ ] Update job status to "cancelling"
- [ ] Set Redis cancellation flag
- [ ] Return success response
- [ ] Authorization check
- [ ] Unit tests for all cases

**Size**: Small | **Priority**: High

---

### Issue #13: Implement worker cancellation detection
**Description**: Add cancellation signal checking in worker execution loop.

**Acceptance Criteria**:
- [ ] Check Redis flag every 1-2 seconds during execution
- [ ] Detect cancellation within 5 seconds
- [ ] Stop current operation gracefully
- [ ] Support cancellation during crawl step
- [ ] Support cancellation during scrape step
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #14: Implement graceful resource cleanup on cancellation
**Description**: Clean up browser contexts, HTTP connections, and other resources on cancellation.

**Acceptance Criteria**:
- [ ] Close browser contexts gracefully
- [ ] Abort ongoing HTTP requests
- [ ] Wait for current page to finish (timeout 5s)
- [ ] Force close if not responsive
- [ ] Save partial results before cleanup
- [ ] Update job status to "cancelled"
- [ ] Add cancellation metadata (timestamp, user)
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #15: Handle queue cancellation (jobs not started)
**Description**: Implement immediate cancellation for jobs in queue that haven't started.

**Acceptance Criteria**:
- [ ] Remove job from queue immediately
- [ ] Update status to "cancelled"
- [ ] No resource cleanup needed
- [ ] Add cancellation metadata
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

## 3.4 Real-Time Log Streaming

### Issue #16: Create log database schema
**Description**: Design and implement database schema for storing job logs.

**Acceptance Criteria**:
- [ ] Log table with fields: timestamp, job_id, website_id, step_name, log_level, message, context, trace_id
- [ ] Indexes on job_id, timestamp, log_level
- [ ] Migration script
- [ ] Partition by timestamp (monthly)
- [ ] Retention policy configuration

**Size**: Small | **Priority**: High

---

### Issue #17: Implement WebSocket endpoint for log streaming
**Description**: Create WebSocket endpoint /ws/jobs/{job_id}/logs for real-time log streaming.

**Acceptance Criteria**:
- [ ] Accept job_id parameter
- [ ] Validate job exists and user authorized
- [ ] Establish WebSocket connection
- [ ] Handle connection errors (404, 403)
- [ ] Support multiple concurrent connections per job
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #18: Implement log broadcasting to WebSocket clients
**Description**: Broadcast new log entries to all connected WebSocket clients.

**Acceptance Criteria**:
- [ ] Worker writes logs to database
- [ ] Publish log event to Redis pub/sub
- [ ] WebSocket server subscribes to log events
- [ ] Broadcast to all clients watching specific job
- [ ] Handle high log volume (batch every 100ms)
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #19: Implement historical log retrieval API
**Description**: Create GET /api/jobs/{job_id}/logs endpoint for retrieving historical logs.

**Acceptance Criteria**:
- [ ] Return all logs for completed jobs
- [ ] Support pagination (limit, offset)
- [ ] Support filtering (log_level, timestamp range, search)
- [ ] Return logs in chronological order
- [ ] Authorization check
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

### Issue #20: Implement WebSocket reconnection with resume
**Description**: Support WebSocket reconnection and resume from last received log.

**Acceptance Criteria**:
- [ ] Client sends last_log_id on reconnect
- [ ] Server sends logs after last_log_id
- [ ] Buffer recent logs (max 1000) for reconnection
- [ ] Handle connection timeout gracefully
- [ ] Integration tests

**Size**: Medium | **Priority**: Low

---

## 3.5 Website Configuration Management

### Issue #21: Implement Create Website API
**Description**: Create POST /api/websites endpoint to create new website configurations.

**Acceptance Criteria**:
- [ ] Validate configuration schema
- [ ] Check for duplicate names or base URLs
- [ ] Store in PostgreSQL
- [ ] Return created website with ID
- [ ] Unit tests for validation

**Size**: Small | **Priority**: High

---

### Issue #22: Implement Read Website API
**Description**: Create GET endpoints for retrieving website configurations.

**Acceptance Criteria**:
- [ ] GET /api/websites/{id} - retrieve by ID
- [ ] GET /api/websites - list all with pagination
- [ ] Support filtering (active, paused)
- [ ] Include statistics (last crawl, success rate, page count)
- [ ] Authorization check
- [ ] Unit tests

**Size**: Small | **Priority**: High

---

### Issue #23: Implement Update Website API
**Description**: Create PUT /api/websites/{id} endpoint to update website configurations.

**Acceptance Criteria**:
- [ ] Validate configuration changes
- [ ] Preserve configuration history (versioning)
- [ ] Update schedule if changed
- [ ] Trigger re-crawl if requested
- [ ] Return updated website
- [ ] Unit tests

**Size**: Medium | **Priority**: High

---

### Issue #24: Implement Delete Website API
**Description**: Create DELETE /api/websites/{id} endpoint with soft delete.

**Acceptance Criteria**:
- [ ] Soft delete (mark as deleted)
- [ ] Cancel any running jobs for this website
- [ ] Option to delete all crawled data
- [ ] Archive configuration for audit
- [ ] Authorization check
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

### Issue #25: Implement website configuration versioning
**Description**: Track configuration changes over time for audit and rollback.

**Acceptance Criteria**:
- [ ] Create website_config_history table
- [ ] Store full config on each update
- [ ] Link to user who made change
- [ ] Timestamp each version
- [ ] API to retrieve version history
- [ ] API to rollback to previous version
- [ ] Unit tests

**Size**: Medium | **Priority**: Low

---

## 3.6 Multi-Step Crawling Workflow

### Issue #26: Create step execution engine
**Description**: Implement core engine for executing multi-step workflows sequentially.

**Acceptance Criteria**:
- [ ] Execute steps in configured order
- [ ] Pass output from one step as input to next
- [ ] Support step skipping based on conditions
- [ ] Handle step dependencies
- [ ] Detect dependency cycles during validation
- [ ] Unit tests for step execution

**Size**: Medium | **Priority**: High

---

### Issue #27: Implement Crawl Step executor
**Description**: Create executor for crawl steps (retrieve list of URLs).

**Acceptance Criteria**:
- [ ] Accept seed URL or base URL
- [ ] Support pagination configuration
- [ ] Output array of URLs with metadata
- [ ] Support API, Browser, and HTTP methods
- [ ] Handle 0 URLs found (skip scrape step)
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #28: Implement Scrape Step executor
**Description**: Create executor for scrape steps (extract content from detail pages).

**Acceptance Criteria**:
- [ ] Accept URLs from previous step
- [ ] Process in batches of 100
- [ ] Extract content using configured selectors
- [ ] Output extracted content and documents
- [ ] Support API, Browser, and HTTP methods
- [ ] Handle partial failures (continue with successful)
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #29: Implement step timeout handling
**Description**: Add timeout configuration and enforcement for each step.

**Acceptance Criteria**:
- [ ] Step timeout configuration per step type
- [ ] Cancel step execution after timeout
- [ ] Retry or fail based on configuration
- [ ] Log timeout events
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

### Issue #30: Implement step input/output validation
**Description**: Validate step inputs and outputs against expected schema.

**Acceptance Criteria**:
- [ ] Define schema for each step type
- [ ] Validate input before execution
- [ ] Validate output after execution
- [ ] Handle missing required fields
- [ ] Handle unexpected output format
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

## 3.7 Deduplication System

### Issue #31: Implement Redis URL-based deduplication (Phase 1)
**Description**: Create fast URL deduplication check using Redis with TTL.

**Acceptance Criteria**:
- [ ] Store normalized URL with TTL (configurable, default 24h)
- [ ] Check existence in Redis before crawling
- [ ] Return cached metadata if found within TTL
- [ ] Response time < 10ms
- [ ] Unit tests

**Size**: Small | **Priority**: High

---

### Issue #32: Implement Simhash algorithm for content fingerprinting
**Description**: Create Simhash implementation for fuzzy content matching.

**Acceptance Criteria**:
- [ ] Tokenize text content into words
- [ ] Generate hash for each token
- [ ] Combine into 64-bit fingerprint
- [ ] Calculate Hamming distance between fingerprints
- [ ] Convert distance to similarity percentage
- [ ] Unit tests with known examples

**Size**: Medium | **Priority**: High

---

### Issue #33: Implement PostgreSQL content-based deduplication (Phase 2)
**Description**: Store content hashes and detect similar content across different URLs.

**Acceptance Criteria**:
- [ ] Store Simhash fingerprint with content
- [ ] Index on fingerprint for fast lookups
- [ ] Query for similar content (95% threshold)
- [ ] Link duplicates to original content
- [ ] Handle hash collisions correctly
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #34: Implement content normalization before hashing
**Description**: Normalize content to remove dynamic elements before generating hash.

**Acceptance Criteria**:
- [ ] Remove timestamps and dates
- [ ] Remove ads and tracking elements
- [ ] Extract main content only
- [ ] Normalize whitespace
- [ ] Remove navigation and footers
- [ ] Unit tests with sample content

**Size**: Medium | **Priority**: Medium

---

### Issue #35: Implement duplicate detection and linking
**Description**: Detect duplicates and create relationships between original and duplicate content.

**Acceptance Criteria**:
- [ ] Create duplicates table linking URLs
- [ ] Store similarity percentage
- [ ] API to retrieve original content for duplicate URLs
- [ ] Handle content updates (new version vs duplicate)
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

## 3.8 Resource Management

### Issue #36: Implement browser pool initialization
**Description**: Create browser pool manager with configurable pool size.

**Acceptance Criteria**:
- [ ] Initialize N browser instances on startup (configurable)
- [ ] Create browser contexts from pool
- [ ] Configuration for max browsers and contexts per browser
- [ ] Health check for browser instances
- [ ] Graceful shutdown

**Size**: Medium | **Priority**: High

---

### Issue #37: Implement browser context assignment and queuing
**Description**: Assign browser contexts to jobs with queuing when pool is full.

**Acceptance Criteria**:
- [ ] Request context returns available context immediately
- [ ] Queue request if pool full
- [ ] FIFO queue for pending requests
- [ ] Assign context when freed
- [ ] Timeout for queue wait (fail if exceeded)
- [ ] Unit tests

**Size**: Medium | **Priority**: High

---

### Issue #38: Implement browser context cleanup and reuse
**Description**: Clean browser context state after use and return to pool.

**Acceptance Criteria**:
- [ ] Clear cookies and storage
- [ ] Close all pages except about:blank
- [ ] Reset context state
- [ ] Return to available pool
- [ ] Handle cleanup errors
- [ ] Unit tests

**Size**: Small | **Priority**: High

---

### Issue #39: Implement browser crash detection and recovery
**Description**: Detect browser crashes and restart with job retry.

**Acceptance Criteria**:
- [ ] Monitor browser process health
- [ ] Detect crashed browsers
- [ ] Remove crashed browser from pool
- [ ] Start new browser instance
- [ ] Retry affected job
- [ ] Log crash events
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #40: Implement memory pressure monitoring
**Description**: Monitor system memory usage and alert on high usage.

**Acceptance Criteria**:
- [ ] Check memory every 30 seconds
- [ ] Track per-browser memory consumption
- [ ] Define thresholds (<70%, 70-85%, 85-95%, >95%)
- [ ] Emit metrics to monitoring system
- [ ] Alert on high memory
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

### Issue #41: Implement memory pressure response
**Description**: Respond to memory pressure by reducing resource usage.

**Acceptance Criteria**:
- [ ] Pause new job acceptance at 85% memory
- [ ] Close idle browser contexts
- [ ] Close lowest priority active jobs at 95%
- [ ] Restart browsers to reclaim memory
- [ ] Resume normal operation when < 70%
- [ ] Log all actions
- [ ] Integration tests

**Size**: Medium | **Priority**: Medium

---

## 3.9 Error Handling & Retry Logic

### Issue #42: Implement retry strategy configuration
**Description**: Define retry policies for different error types.

**Acceptance Criteria**:
- [ ] Configuration for retryable vs non-retryable errors
- [ ] Max retry attempts per error type
- [ ] Retry delays and backoff strategy
- [ ] Store retry configuration in database
- [ ] Unit tests

**Size**: Small | **Priority**: High

---

### Issue #43: Implement exponential backoff with jitter
**Description**: Create backoff calculation for retry delays.

**Acceptance Criteria**:
- [ ] Formula: `delay = min(initial_delay * (base ^ (attempt - 1)), max_delay)`
- [ ] Add random jitter (0-20%)
- [ ] Cap at max delay (300s)
- [ ] Handle Retry-After header from responses
- [ ] Unit tests with various scenarios

**Size**: Small | **Priority**: High

---

### Issue #44: Implement retry logic for transient errors
**Description**: Automatically retry jobs on transient failures.

**Acceptance Criteria**:
- [ ] Retry on network timeout
- [ ] Retry on 503 Service Unavailable
- [ ] Retry on 429 Rate Limit (respect Retry-After)
- [ ] Retry on temporary browser issues
- [ ] Track retry attempts in job metadata
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #45: Implement Dead Letter Queue (DLQ) for failed jobs
**Description**: Move permanently failed jobs to DLQ for manual review.

**Acceptance Criteria**:
- [ ] Create DLQ table
- [ ] Move jobs after max retries exceeded
- [ ] Store all error information
- [ ] API to list DLQ jobs
- [ ] API to retry DLQ job manually
- [ ] Alert on DLQ additions
- [ ] Unit tests

**Size**: Medium | **Priority**: Medium

---

### Issue #46: Implement error classification
**Description**: Classify errors into retryable, permanent, and unknown categories.

**Acceptance Criteria**:
- [ ] Classify by HTTP status code (404 = permanent, 503 = retryable)
- [ ] Classify by exception type
- [ ] Custom classification rules
- [ ] Log classification decisions
- [ ] Unit tests for all error types

**Size**: Small | **Priority**: Medium

---

## 3.10 Scheduling System

### Issue #47: Implement cron schedule parser and validator
**Description**: Parse and validate cron expressions for scheduled jobs.

**Acceptance Criteria**:
- [ ] Parse standard cron format
- [ ] Validate cron expressions
- [ ] Calculate next run time from cron
- [ ] Support extended cron syntax (e.g., @daily, @weekly)
- [ ] Handle timezone conversions
- [ ] Unit tests with various expressions

**Size**: Small | **Priority**: High

---

### Issue #48: Implement scheduler daemon
**Description**: Create background scheduler that checks and creates due jobs.

**Acceptance Criteria**:
- [ ] Run scheduler loop every minute
- [ ] Query websites with due schedules
- [ ] Create jobs for due schedules
- [ ] Update next_run_time after scheduling
- [ ] Skip if previous job still running
- [ ] Handle scheduler restarts gracefully
- [ ] Integration tests

**Size**: Medium | **Priority**: High

---

### Issue #49: Implement priority queue system
**Description**: Create priority-based job queue with proper ordering.

**Acceptance Criteria**:
- [ ] Priority levels 0-10 (10 = highest)
- [ ] Queue ordering: priority → scheduled_time → created_time
- [ ] Manual trigger jobs get priority 10
- [ ] Scheduled jobs get priority 4-6
- [ ] Retry jobs get priority 0
- [ ] Redis-based queue implementation
- [ ] Unit tests

**Size**: Medium | **Priority**: High

---

### Issue #50: Implement manual job trigger
**Description**: API endpoint to manually trigger immediate job execution.

**Acceptance Criteria**:
- [ ] POST /api/websites/{id}/trigger
- [ ] Create high-priority job (priority 10)
- [ ] Push to front of queue
- [ ] Return job ID
- [ ] Authorization check
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

### Issue #51: Implement schedule pause/resume functionality
**Description**: Allow pausing and resuming scheduled crawls for websites.

**Acceptance Criteria**:
- [ ] POST /api/websites/{id}/pause
- [ ] POST /api/websites/{id}/resume
- [ ] Update is_active flag
- [ ] Scheduler skips paused websites
- [ ] Return updated status
- [ ] Unit tests

**Size**: Small | **Priority**: Medium

---

### Issue #52: Implement missed schedule catch-up logic
**Description**: Handle missed schedules when scheduler restarts.

**Acceptance Criteria**:
- [ ] Detect schedules missed during downtime
- [ ] Catch up if < 1 hour late
- [ ] Skip if > 1 hour late (log warning)
- [ ] Recalculate next run times
- [ ] Log catch-up actions
- [ ] Unit tests

**Size**: Small | **Priority**: Low

---

### Issue #53: Implement daylight saving time handling
**Description**: Correctly handle DST transitions in scheduled jobs.

**Acceptance Criteria**:
- [ ] Adjust schedules for DST changes
- [ ] No duplicate runs during "fall back"
- [ ] No missed runs during "spring forward"
- [ ] Log DST adjustments
- [ ] Unit tests with DST transitions

**Size**: Small | **Priority**: Low

---

## Summary

**Total Issues**: 54
**Priority Breakdown**:
- Critical (Blocking): 1 issue
- High: 31 issues
- Medium: 18 issues
- Low: 4 issues

**Size Breakdown**:
- Small: 30 issues
- Medium: 22 issues
- Large: 2 issues

**Recommended Implementation Order**:
1. **MUST START HERE** - Foundational infrastructure: #0 (Database Models & Redis)
2. Job submission modes: #1-5 (Job Submission)
3. Core crawling: #6-10 (Seed URL Crawling)
4. Configuration management: #21-24 (Website CRUD)
5. Step execution: #26-28 (Multi-Step Workflow)
6. Resource management: #36-39 (Browser Pool)
7. Error handling: #42-46 (Retry Logic)
8. Scheduling: #47-50 (Scheduler)
9. Advanced features: Deduplication, Cancellation, Log Streaming

**Critical Path**: Issue #0 is a blocking dependency for ALL other issues. No feature development can begin without completing the database models and Redis data structures.
