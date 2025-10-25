# Product Requirements Document (PRD)
## Robust Web Crawling System

---

## 1. Executive Summary

### 1.1 Project Overview
Build a production-grade, scalable web crawling system capable of handling 100+ websites with tens to hundreds of thousands of pages. The system must support diverse crawling methods (static HTML, JavaScript-heavy sites, REST APIs) with flexible configuration, efficient resource utilization, and comprehensive monitoring. The system supports both pre-configured scheduled crawls and ad-hoc seed URL submissions.

### 1.2 Key Objectives
- Crawl 100+ websites with varying complexity and protection levels
- Support one-time and recurring crawls (bi-weekly schedules)
- Handle static sites, dynamic JavaScript sites, and REST APIs
- Support seed URL submissions (with or without pre-configured templates)
- Implement efficient deduplication to prevent redundant storage
- Provide robust monitoring, logging, and alerting
- Enable job cancellation from frontend
- Real-time log streaming to frontend
- Maintain resource efficiency within 8GB RAM constraint
- Enable easy migration to microservices architecture in the future

### 1.3 Constraints
- **Budget**: Limited (no proxy initially, minimal infrastructure)
- **Team**: 3 developers
- **Server Resources**: Single server, 8GB RAM
- **Concurrent Browsers**: Maximum 5 Playwright browser instances
- **Deployment**: Dockerized monolithic application with modular design

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Out of Scope)                │
│                            ↓ JWT                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     API Service (FastAPI)                    │
│  - Job submission (scheduled & seed URL)                     │
│  - Job cancellation                                          │
│  - Website CRUD, status queries                              │
│  - Real-time log streaming (WebSocket)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Scheduler Service                         │
│  - Cron-based job scheduling                                 │
│  - Read website configs from PostgreSQL                      │
│  - Push jobs to NATS JetStream                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
                   ┌──────────────────┐
                   │ NATS JetStream   │
                   │   Job Queue      │
                   └──────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Worker Pool                             │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Browser Pool Manager (5 Playwright Browsers)          │  │
│  │  - Context pooling (10-15 contexts per browser)       │  │
│  │  - Lifecycle management                                │  │
│  │  - Cancellation signal handling                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ HTTP Workers (30+ concurrent async clients)           │  │
│  │  - httpx for static/API sites                          │  │
│  │  - Cancellation token support                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Step Executor                                          │  │
│  │  - Execute crawl steps (get URLs + metadata)           │  │
│  │  - Execute scrape steps (get main content)             │  │
│  │  - Check cancellation signal between steps            │  │
│  │  - Stream logs to PostgreSQL & WebSocket               │  │
│  │  - Variable substitution for seed URLs                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Result Processor                          │
│  - Content hash generation (95% similarity threshold)       │
│  - Deduplication check (Redis + PostgreSQL)                 │
│  - GCS upload (HTML, documents)                             │
│  - PostgreSQL insert (metadata + extracted content)         │
└─────────────────────────────────────────────────────────────┘
                              ↓
        ┌──────────────┬───────────────┬──────────────┐
        ↓              ↓               ↓              ↓
   ┌────────┐    ┌──────────┐    ┌───────┐    ┌──────────┐
   │  GCS   │    │PostgreSQL│    │ Redis │    │Prometheus│
   │Storage │    │ Database │    │ Cache │    │ Metrics  │
   └────────┘    └──────────┘    └───────┘    └──────────┘
```

### 2.2 Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Language** | Python 3.11+ | Rich ecosystem for web scraping, easier Cloudflare bypass |
| **Web Framework** | FastAPI | Modern, async, auto-generated docs, WebSocket support |
| **Browser Automation** | Playwright | Built-in stealth, context isolation, modern API |
| **Alternative Browser** | undetected-chromedriver | Fallback for heavy anti-bot (abstracted) |
| **HTTP Client** | httpx | Async support, modern API |
| **HTML Parsing** | selectolax | Fastest parser, BeautifulSoup4 as fallback |
| **Message Queue** | NATS JetStream | Already in use, reliable, persistent streams |
| **Database** | PostgreSQL | Structured data, JSONB support for flexible schemas |
| **Cache** | Redis | Deduplication checks, rate limiting, cancellation signals |
| **Object Storage** | Google Cloud Storage (GCS) | Raw HTML and document storage |
| **Monitoring** | Prometheus + Grafana | Metrics collection and visualization |
| **Logging** | Loki | Centralized log aggregation |
| **Alerting** | AlertManager | Alert routing and management |
| **Containerization** | Docker + Docker Compose | Isolated environments, easy deployment |

---

## 3. Core Features

### 3.1 Job Submission Modes

#### 3.1.1 Scheduled Jobs (Regular)

Pre-configured website crawls with cron schedules.

**Use Case**: Recurring crawls of known websites with stable structure.

**Flow**:
1. Admin creates website configuration with selectors and steps
2. Scheduler automatically creates jobs based on cron schedule
3. Jobs execute using pre-defined configuration
4. Results stored and deduplicated

#### 3.1.2 Seed URL Submission (Hybrid)

User submits a specific URL (search results, filtered lists) to crawl.

**Use Case**: Ad-hoc crawls with dynamic search parameters or one-time crawls.

**Two Modes**:

**Mode A: Reference Existing Config**
- User has pre-configured website template
- Submit seed URL with website_id
- Configuration loaded from database
- Variables substituted at runtime

**Mode B: Inline Configuration**
- No pre-existing configuration needed
- Submit seed URL with full inline config
- Configuration embedded in job record
- Truly ad-hoc, no setup required

**Supported Scenarios**:
- Search results with keywords (e.g., `?keywords=term`)
- Filtered lists (e.g., `?category=tech&date=2024`)
- Paginated listings starting from specific page
- Any URL that leads to list → detail page pattern

---

### 3.2 Seed URL Crawling

#### 3.2.1 Requirements
- Accept arbitrary starting URL
- Follow pagination from seed URL
- Extract detail page URLs from list pages
- Scrape content from detail pages
- Support variable substitution in configurations
- Support one-time or scheduled execution
- Handle both template-based and ad-hoc submissions

#### 3.2.2 Seed URL Algorithm

**Positive Cases**:
1. Seed URL with valid pagination → Crawl all pages → Extract all detail URLs → Scrape all
2. Seed URL is last page → No next page → Scrape current page only
3. Seed URL with URL pattern pagination → Auto-increment page number → Continue
4. Template config exists → Load config → Substitute seed URL → Execute
5. Inline config provided → Validate → Execute directly

**Negative Cases**:
1. Seed URL returns 404 → Log error → Fail job immediately
2. Pagination selector not found → Assume single page → Continue with current page
3. No detail URLs found → Log warning → Complete job with 0 results
4. Invalid configuration → Fail validation → Return error to user
5. Website structure changed → Selectors fail → Log extraction errors

**Edge Cases**:
1. Seed URL already on page 5 → Continue from page 5 → Crawl to end
2. Circular pagination (page N links back to page 1) → Detect visited URLs → Stop
3. Pagination with query parameters → Preserve other parameters → Only change page number
4. Seed URL redirects to different domain → Follow redirect → Use final URL
5. Multiple pagination patterns on same page → Use configured selector → Ignore others
6. Infinite pagination (load more buttons) → Respect max_pages config → Stop at limit

#### 3.2.3 Variable Substitution

Variables can be used in configuration and substituted at runtime.

**Variable Sources**:
1. `${variables.key}` - From job submission variables
2. `${ENV.KEY}` - From environment variables (stored in database)
3. `${input.field}` - From previous step output
4. `${pagination.current_page}` - Auto-incremented page counter
5. `${metadata.field}` - From job metadata

**Substitution Algorithm**:
1. Parse configuration for variable patterns
2. Resolve variables from appropriate source
3. Replace variable placeholders with actual values
4. If variable not found → Log warning → Use empty string or fail based on required flag
5. Type conversion if needed (string, integer, boolean)

**Example**:
```
Config: "url": "${variables.seed_url}"
Variables: {"seed_url": "https://example.com/search?q=test"}
Result: "url": "https://example.com/search?q=test"
```

---

### 3.3 Job Cancellation

#### 3.3.1 Requirements
- Frontend can cancel running jobs at any time
- Workers must detect cancellation within 5 seconds
- Graceful cleanup of resources (browser contexts, HTTP connections)
- Partial results are saved before cancellation
- Job status updated to "cancelled" with cancellation metadata

#### 3.3.2 Cancellation Algorithm

**Positive Cases**:
1. User clicks "Cancel" → Job marked as cancelled → Worker stops within 5 seconds
2. Job in queue (not started) → Removed from queue immediately
3. Job running crawl step → Current page finishes → Step cancelled → Cleanup
4. Job running scrape step → Current URL batch finishes → Step cancelled → Cleanup
5. Multiple parallel operations → All operations receive cancellation signal → All stop gracefully

**Negative Cases**:
1. Job already completed → Return error "Job already completed, cannot cancel"
2. Job already cancelled → Return error "Job already cancelled"
3. Job ID not found → Return 404 error
4. Unauthorized user → Return 403 error

**Edge Cases**:
1. Cancellation during browser navigation → Wait for navigation to abort (timeout 5s) → Force close context
2. Cancellation during GCS upload → Abort upload → Mark as incomplete → Save progress
3. Cancellation during database transaction → Rollback transaction → Clean state
4. Worker crashed before detecting cancellation → Scheduler marks as failed after timeout
5. Network partition during cancellation → Cancellation signal stored in Redis → Worker picks up on reconnect

#### 3.3.3 Cancellation Flow

```
Frontend Request → API validates → Update job status to "cancelling"
                                      ↓
                          Set Redis flag: cancel:job:{job_id} = true
                                      ↓
Worker checks cancellation signal (every 1-2 seconds)
                                      ↓
                    Signal detected → Stop current operation
                                      ↓
                          Cleanup resources (browser, HTTP)
                                      ↓
                    Save partial results to database
                                      ↓
              Update job status to "cancelled" with metadata
                                      ↓
                    Delete Redis cancellation flag
                                      ↓
                          Emit metrics and logs
```

---

### 3.4 Real-Time Log Streaming

#### 3.4.1 Requirements
- Frontend can view logs for any job in real-time
- Logs available during job execution and after completion
- Support for log filtering (level, timestamp, search)
- Historical logs retrievable via API
- WebSocket connection for live updates
- Logs persisted in PostgreSQL for audit trail

#### 3.4.2 Log Streaming Algorithm

**Positive Cases**:
1. Frontend connects via WebSocket with job_id → Receive live logs as they happen
2. Job not started yet → WebSocket waits → Logs stream when job starts
3. Job already completed → Return all historical logs immediately
4. Multiple frontends watching same job → All receive same logs (broadcast)
5. Frontend reconnects after disconnect → Resume from last received log

**Negative Cases**:
1. Invalid job_id → Return error and close WebSocket
2. Unauthorized access → Return 403 and close WebSocket
3. Job ID not found → Return 404 and close WebSocket

**Edge Cases**:
1. High log volume (>1000 logs/sec) → Batch logs every 100ms → Send batch
2. WebSocket disconnection → Buffer logs (max 1000) → Resend on reconnect
3. Database write lag → Logs sent to client before DB confirm (eventual consistency)
4. WebSocket connection limit → Queue connection → Notify client
5. Worker crash mid-job → Logs up to crash point available → Mark incomplete

#### 3.4.3 Log Structure

Each log entry contains:
- **timestamp**: ISO8601 format
- **job_id**: UUID
- **website_id**: UUID
- **step_name**: Current step being executed
- **log_level**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **message**: Human-readable message
- **context**: JSON object with additional data
- **trace_id**: For distributed tracing

---

### 3.5 Website Configuration Management

#### 3.5.1 CRUD Operations

**Create Website**
- Validate configuration schema
- Check for duplicate names or base URLs
- Store in PostgreSQL
- Return created website with ID

**Read Website**
- Retrieve by ID
- List all with pagination and filtering
- Include statistics (last crawl, success rate, page count)

**Update Website**
- Validate changes
- Preserve configuration history (versioning)
- Update schedule if changed
- Trigger re-crawl if requested

**Delete Website**
- Soft delete (mark as deleted)
- Cancel any running jobs
- Optionally delete all crawled data
- Archive configuration for audit

---

### 3.6 Multi-Step Crawling Workflow

#### 3.6.1 Step Execution Algorithm

**Positive Cases**:
1. Sequential steps (crawl → scrape) → Execute in order → Pass data between steps
2. Crawl step finds 1000 URLs → Scrape step processes in batches of 100
3. Step output used as input → Variable substitution successful
4. All steps complete → Job marked as completed
5. Step with optional fields → Skip missing fields → Continue

**Negative Cases**:
1. Step configuration invalid → Fail validation → Reject job submission
2. Required input missing → Fail step → Mark job as failed
3. Step exceeds timeout → Cancel step → Retry or fail based on config
4. Output field not found → Log warning → Use null value

**Edge Cases**:
1. Crawl step finds 0 URLs → Skip scrape step → Log warning → Complete job
2. Partial step failure (500/1000 URLs fail) → Continue with successful ones → Log failures
3. Step dependency cycle → Detect during validation → Reject configuration
4. Step produces unexpected output format → Attempt to parse → Fail gracefully if impossible
5. Resource exhausted mid-step → Pause → Wait for resources → Resume

#### 3.6.2 Step Types

**Crawl Step**
- Purpose: Retrieve list of URLs and preview metadata
- Input: Seed URL or base URL, pagination config
- Output: Array of URLs with metadata
- Methods: API, Browser, HTTP

**Scrape Step**
- Purpose: Extract main content from detail pages
- Input: URLs from previous step or configuration
- Output: Extracted content and documents
- Methods: API, Browser, HTTP

---

### 3.7 Deduplication System

#### 3.7.1 Two-Phase Deduplication

**Phase 1: URL-Based (Redis)**
- Check if URL crawled recently (within TTL)
- Fast check (< 10ms)
- Prevents unnecessary re-crawls

**Phase 2: Content-Based (PostgreSQL)**
- Generate content hash using Simhash
- Check for similar content (95% threshold)
- Prevents duplicate content from different URLs

#### 3.7.2 Deduplication Algorithm

**Positive Cases**:
1. Exact same URL within TTL → Skip crawl → Return cached metadata
2. Same content different URL → Skip storage → Link to original
3. Content 96% similar → Mark as duplicate → Store reference only
4. Updated content (94% similar) → Store as new version → Link to previous
5. First time crawl → No duplicate → Store normally

**Negative Cases**:
1. URL outside TTL → Proceed with crawl
2. Content below 95% threshold → Store as new
3. Hash collision (rare) → Compare full text → Resolve correctly

**Edge Cases**:
1. Content with dynamic timestamps → Normalize before hashing → Accurate comparison
2. Content with ads/tracking → Extract main content only → Hash clean content
3. Pagination URLs with parameters → Normalize URL → Detect duplicates
4. URL redirects to different final URL → Use final URL for deduplication
5. Content in different languages but same structure → Not duplicate (hash differs)

#### 3.7.3 Simhash Algorithm for Fuzzy Matching

**Input**: Extracted text content
**Process**:
1. Tokenize text into words
2. Generate hash for each token
3. Combine token hashes into single fingerprint
4. Compare fingerprints using Hamming distance
5. Convert distance to similarity percentage

**Similarity Calculation**:
- Hamming distance / 64 = dissimilarity
- 1 - dissimilarity = similarity
- Threshold: 95%

---

### 3.8 Resource Management

#### 3.8.1 Browser Pool Management

**Algorithm: Browser Lifecycle**

**Positive Cases**:
1. Request browser context → Available in pool → Assign immediately
2. Pool full → Queue request → Assign when context freed
3. Browser healthy → Reuse contexts → Efficient resource usage
4. Context finished → Clean state → Return to pool
5. Graceful shutdown → Wait for jobs → Close all browsers

**Negative Cases**:
1. Browser crash → Detect → Restart browser → Retry job
2. Context timeout → Force close → Clean up → Log error
3. Memory leak detected → Restart browser proactively

**Edge Cases**:
1. All browsers busy → New job queued → Process when available
2. Memory >85% → Reduce active contexts → Scale down temporarily
3. Repeated crashes → Disable problematic website → Alert team
4. Context stuck (no response 60s) → Force kill → Recreate
5. Shutdown during active jobs → Wait max 5 minutes → Force close

#### 3.8.2 Memory Pressure Handling

**Monitoring**:
- Check memory usage every 30 seconds
- Track per-browser memory consumption
- Alert if approaching limit

**Thresholds**:
- **< 70%**: Normal operation
- **70-85%**: Warning, reduce new contexts
- **85-95%**: Critical, pause new jobs, close idle contexts
- **> 95%**: Emergency, force close lowest priority jobs

**Recovery Algorithm**:
1. Detect high memory → Pause job acceptance
2. Identify largest memory consumers
3. Close idle contexts first
4. If still high, close lowest priority active jobs
5. Restart browsers to reclaim memory
6. Resume normal operation when < 70%

---

### 3.9 Error Handling & Retry Logic

#### 3.9.1 Retry Strategy

**Positive Cases**:
1. Network timeout → Wait → Retry with backoff
2. 503 Service Unavailable → Retry with longer backoff
3. 429 Rate Limit → Respect Retry-After header → Retry
4. Temporary browser issue → Restart browser → Retry job
5. Third retry successful → Mark as completed

**Negative Cases**:
1. 404 Not Found → No retry → Mark URL as dead
2. 401 Unauthorized → No retry → Log auth error
3. Parser error → No retry → Mark as broken content
4. Max retries exceeded → Move to DLQ → Alert
5. Permanent failure → No retry → Mark as failed

**Edge Cases**:
1. Retry-After header malformed → Use default backoff
2. Exponential backoff exceeds max wait → Cap at max (300s)
3. Job cancelled during retry wait → Cancel immediately
4. Resource unavailable during retry → Extend wait
5. Different error on retry → Log both errors → Continue retry logic

#### 3.9.2 Backoff Calculation

**Exponential Backoff**:
- Attempt 1: 1 second
- Attempt 2: 2 seconds
- Attempt 3: 4 seconds
- Max: 300 seconds

**Formula**: `delay = min(initial_delay * (base ^ (attempt - 1)), max_delay)`

**Jitter**: Add random 0-20% to prevent thundering herd

---

### 3.10 Scheduling System

#### 3.10.1 Scheduler Algorithm

**Positive Cases**:
1. Cron schedule due → Create job → Push to queue
2. One-time job → Execute → Mark as completed schedule
3. Recurring job → Execute → Calculate next run time
4. Multiple websites due → Create jobs with priority → Queue in order
5. Manual trigger → Create high-priority job → Execute immediately

**Negative Cases**:
1. Website paused → Skip scheduled run
2. Previous job still running → Skip (don't stack)
3. Website deleted → Remove from schedule
4. Invalid cron expression → Log error → Alert

**Edge Cases**:
1. Scheduler restart → Recalculate missed schedules → Catch up if < 1 hour late
2. Time zone change → Adjust schedules → Log changes
3. Daylight saving time → Handle correctly → No duplicate/missed runs
4. Leap second → Ignore (no impact on daily/weekly schedules)
5. Server clock drift → Detect → Alert → Resync

#### 3.10.2 Priority System

**Priority Levels** (1-10, higher = more urgent):
- **10**: Manual trigger, critical
- **7-9**: High-priority websites
- **4-6**: Normal scheduled jobs
- **1-3**: Low-priority, bulk jobs
- **0**: Retry jobs

**Queue Ordering**: Priority → Scheduled time → Created time

---

## 4. Data Models

### 4.1 PostgreSQL Schema

#### 4.1.1 Table: websites

```sql
CREATE TABLE websites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    base_url TEXT NOT NULL,
    config JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID,
    CONSTRAINT websites_name_unique UNIQUE(name)
);

CREATE INDEX idx_websites_status ON websites(status);
CREATE INDEX idx_websites_config ON websites USING GIN(config);
```

#### 4.1.2 Table: crawl_jobs

```sql
CREATE TABLE crawl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL DEFAULT 'scheduled',
    seed_url TEXT,
    embedded_config JSONB,
    status VARCHAR(50) NOT NULL,
    priority INTEGER DEFAULT 5,
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancelled_by UUID,
    cancellation_reason TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    metadata JSONB,
    variables JSONB,
    progress JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_jobs_website ON crawl_jobs(website_id);
CREATE INDEX idx_jobs_type ON crawl_jobs(job_type);
CREATE INDEX idx_jobs_status ON crawl_jobs(status);
CREATE INDEX idx_jobs_scheduled ON crawl_jobs(scheduled_at);
CREATE INDEX idx_jobs_created ON crawl_jobs(created_at DESC);
CREATE INDEX idx_jobs_seed_url ON crawl_jobs(seed_url);
```

**Job Types**:
- `scheduled`: Regular scheduled job using website config
- `seed_template`: Seed URL submission using existing website config
- `seed_adhoc`: Seed URL submission with inline config

**Status Values**:
- `pending`: Job queued, not started
- `running`: Job actively executing
- `cancelling`: Cancellation requested, cleanup in progress
- `cancelled`: Job cancelled by user
- `completed`: Job finished successfully
- `failed`: Job failed after retries
- `paused`: Job paused (future feature)

**Progress JSONB Structure**:
```json
{
  "current_step": "scrape_detail",
  "step_progress": {
    "total_urls": 1000,
    "processed_urls": 450,
    "failed_urls": 12,
    "skipped_urls": 3,
    "discovered_urls": 1000
  },
  "start_time": "2024-01-01T10:00:00Z",
  "estimated_completion": "2024-01-01T12:30:00Z"
}
```

**Variables JSONB Structure**:
```json
{
  "seed_url": "https://example.com/search?q=test",
  "search_keyword": "test",
  "custom_param": "value"
}
```

**Embedded Config**: Used for seed_adhoc jobs, contains full configuration inline.

#### 4.1.3 Table: crawled_pages

```sql
CREATE TABLE crawled_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
    job_id UUID REFERENCES crawl_jobs(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    url_hash VARCHAR(64) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    title TEXT,
    extracted_content TEXT,
    metadata JSONB,
    gcs_html_path TEXT,
    gcs_documents JSONB,
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of UUID REFERENCES crawled_pages(id),
    similarity_score FLOAT,
    crawled_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pages_website ON crawled_pages(website_id);
CREATE INDEX idx_pages_job ON crawled_pages(job_id);
CREATE INDEX idx_pages_url_hash ON crawled_pages(url_hash);
CREATE INDEX idx_pages_content_hash ON crawled_pages(content_hash);
CREATE INDEX idx_pages_crawled ON crawled_pages(crawled_at DESC);
CREATE INDEX idx_pages_duplicate ON crawled_pages(is_duplicate);
```

#### 4.1.4 Table: content_hashes

```sql
CREATE TABLE content_hashes (
    content_hash VARCHAR(64) PRIMARY KEY,
    first_seen_page_id UUID REFERENCES crawled_pages(id),
    occurrence_count INTEGER DEFAULT 1,
    last_seen_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_hashes_last_seen ON content_hashes(last_seen_at DESC);
```

#### 4.1.5 Table: crawl_logs

```sql
CREATE TABLE crawl_logs (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
    step_name VARCHAR(100),
    log_level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    trace_id UUID,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_logs_job ON crawl_logs(job_id);
CREATE INDEX idx_logs_website ON crawl_logs(website_id);
CREATE INDEX idx_logs_level ON crawl_logs(log_level);
CREATE INDEX idx_logs_created ON crawl_logs(created_at DESC);
CREATE INDEX idx_logs_trace ON crawl_logs(trace_id);
```

#### 4.1.6 Table: proxy_pool (Future)

```sql
CREATE TABLE proxy_pool (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proxy_url TEXT NOT NULL,
    proxy_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'active',
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    last_checked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 Redis Data Structures

#### 4.2.1 URL Deduplication Cache

```
Key Pattern: crawled:{url_hash}
Type: String (JSON)
Value: {
  "crawled_at": "2024-01-01T12:00:00Z",
  "job_id": "uuid",
  "content_hash": "abc123",
  "page_id": "uuid"
}
TTL: Website-specific (e.g., 14 days for bi-weekly)
```

#### 4.2.2 Job Cancellation Flags

```
Key Pattern: cancel:job:{job_id}
Type: String (boolean)
Value: "true"
TTL: 3600 seconds (1 hour)
```

#### 4.2.3 Rate Limiting

```
Key Pattern: ratelimit:{website_id}:{window_start}
Type: String (counter)
Value: request_count
TTL: 1 second
```

#### 4.2.4 Browser Pool Status

```
Key: browser:pool:status
Type: Hash
Fields:
  active_browsers: 5
  active_contexts: 42
  available_contexts: 33
  memory_usage_mb: 4200
```

#### 4.2.5 Job Progress Cache

```
Key Pattern: progress:job:{job_id}
Type: String (JSON)
Value: {progress_object}
TTL: 86400 (24 hours)
```

---

## 5. API Specifications

### 5.1 Authentication Endpoints

```
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
```

**Note**: JWT with RBAC out of scope for initial implementation. Fields provided for future integration.

### 5.2 Website Management Endpoints

#### 5.2.1 Create Website

```
POST /api/v1/websites
Content-Type: application/json

Request Body: {
  "name": "string",
  "base_url": "string",
  "config": {website_config_object}
}

Response 201: {
  "success": true,
  "data": {
    "id": "uuid",
    "name": "string",
    "base_url": "string",
    "config": {config},
    "status": "active",
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
}

Response 400: {
  "success": false,
  "error": {
    "code": "INVALID_CONFIG",
    "message": "Configuration validation failed",
    "details": {validation_errors}
  }
}
```

#### 5.2.2 List Websites

```
GET /api/v1/websites?page=1&limit=20&status=active&search=keyword

Response 200: {
  "success": true,
  "data": {
    "items": [website_objects],
    "total": 100,
    "page": 1,
    "limit": 20,
    "pages": 5
  }
}
```

#### 5.2.3 Get Website Details

```
GET /api/v1/websites/{id}

Response 200: {
  "success": true,
  "data": {
    "id": "uuid",
    "name": "string",
    "base_url": "string",
    "config": {config},
    "status": "active",
    "statistics": {
      "total_crawls": 45,
      "last_crawl_at": "ISO8601",
      "success_rate": 0.96,
      "total_pages": 12450,
      "avg_duration_seconds": 320
    },
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
}
```

#### 5.2.4 Update Website

```
PUT /api/v1/websites/{id}
Content-Type: application/json

Request Body: {
  "name": "string (optional)",
  "config": {config_object (optional)},
  "status": "active|paused (optional)"
}

Response 200: {
  "success": true,
  "data": {updated_website}
}
```

#### 5.2.5 Delete Website

```
DELETE /api/v1/websites/{id}?delete_data=false

Response 200: {
  "success": true,
  "message": "Website deleted successfully"
}
```

### 5.3 Job Management Endpoints

#### 5.3.1 Submit Scheduled Job (Batch)

```
POST /api/v1/jobs/submit
Content-Type: application/json

Request Body: {
  "website_ids": ["uuid1", "uuid2"],
  "priority": 5,
  "scheduled_at": "ISO8601 (optional)"
}

Response 201: {
  "success": true,
  "data": {
    "jobs": [
      {
        "id": "uuid",
        "website_id": "uuid",
        "job_type": "scheduled",
        "status": "pending",
        "priority": 5,
        "scheduled_at": "ISO8601",
        "created_at": "ISO8601"
      }
    ]
  }
}
```

#### 5.3.2 Submit Seed URL Job

```
POST /api/v1/jobs/submit-seed
Content-Type: application/json

Request Body (Mode A - Reference Config): {
  "website_id": "uuid",
  "seed_url": "https://example.com/search?q=test",
  "schedule": {
    "type": "once",
    "cron": "0 0 * * *",
    "timezone": "Asia/Jakarta"
  },
  "priority": 7,
  "variables": {
    "search_keyword": "test",
    "custom_param": "value"
  },
  "metadata": {
    "description": "Search results for 'test'",
    "tags": ["search", "test"]
  }
}

Request Body (Mode B - Inline Config): {
  "seed_url": "https://example.com/search?q=test",
  "schedule": {
    "type": "once"
  },
  "priority": 5,
  "config": {
    "name": "Ad-hoc Search Crawl",
    "steps": [
      {
        "name": "crawl_list",
        "type": "crawl",
        "method": "browser",
        "config": {
          "url": "${variables.seed_url}",
          "pagination": {
            "enabled": true,
            "type": "next_button",
            "selector": "a.next-page",
            "max_pages": 50
          },
          "extraction": {
            "item_selector": "div.result-item",
            "fields": {
              "detail_url": {
                "selector": "a.title-link",
                "attribute": "href"
              }
            }
          }
        }
      },
      {
        "name": "scrape_detail",
        "type": "scrape",
        "method": "browser",
        "input_from": "crawl_list.detail_urls",
        "selectors": {
          "title": "h1.title",
          "content": "div.content"
        }
      }
    ],
    "global_config": {
      "rate_limit": {
        "requests_per_second": 2
      }
    }
  },
  "variables": {
    "seed_url": "https://example.com/search?q=test"
  },
  "metadata": {
    "description": "One-time ad-hoc crawl"
  }
}

Response 201: {
  "success": true,
  "data": {
    "id": "uuid",
    "job_type": "seed_template | seed_adhoc",
    "website_id": "uuid (if Mode A)",
    "seed_url": "string",
    "status": "pending",
    "priority": 5,
    "scheduled_at": "ISO8601 (if scheduled)",
    "created_at": "ISO8601"
  }
}

Response 400: {
  "success": false,
  "error": {
    "code": "INVALID_CONFIG | WEBSITE_NOT_FOUND",
    "message": "Error description",
    "details": {}
  }
}
```

#### 5.3.3 Manual Trigger (Website Config)

```
POST /api/v1/jobs/trigger/{website_id}
Content-Type: application/json

Request Body: {
  "priority": 10,
  "variables": {
    "optional_override": "value"
  }
}

Response 201: {
  "success": true,
  "data": {
    "id": "uuid",
    "website_id": "uuid",
    "job_type": "scheduled",
    "status": "pending",
    "priority": 10,
    "created_at": "ISO8601"
  }
}
```

#### 5.3.4 Cancel Job

```
POST /api/v1/jobs/{job_id}/cancel
Content-Type: application/json

Request Body: {
  "reason": "string (optional)"
}

Response 200: {
  "success": true,
  "message": "Job cancellation initiated",
  "data": {
    "id": "uuid",
    "status": "cancelling",
    "cancelled_at": "ISO8601"
  }
}

Response 400: {
  "success": false,
  "error": {
    "code": "INVALID_STATUS | ALREADY_CANCELLED",
    "message": "Job already completed, cannot cancel"
  }
}
```

#### 5.3.5 List Jobs

```
GET /api/v1/jobs?website_id=uuid&job_type=seed_template&status=running&page=1&limit=20&sort=created_at:desc

Response 200: {
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "website_id": "uuid",
        "website_name": "string",
        "job_type": "scheduled | seed_template | seed_adhoc",
        "seed_url": "string (if seed job)",
        "status": "running",
        "priority": 5,
        "progress": {progress_object},
        "scheduled_at": "ISO8601",
        "started_at": "ISO8601",
        "metadata": {metadata_object},
        "created_at": "ISO8601"
      }
    ],
    "total": 250,
    "page": 1,
    "limit": 20
  }
}
```

#### 5.3.6 Get Job Status

```
GET /api/v1/jobs/{job_id}

Response 200: {
  "success": true,
  "data": {
    "id": "uuid",
    "website_id": "uuid",
    "website_name": "string",
    "job_type": "seed_template",
    "seed_url": "https://example.com/search?q=test",
    "status": "running",
    "priority": 5,
    "progress": {
      "current_step": "scrape_detail",
      "step_progress": {
        "total_urls": 1000,
        "processed_urls": 450,
        "failed_urls": 12,
        "skipped_urls": 3,
        "discovered_urls": 1000
      },
      "percentage": 45.0,
      "estimated_completion": "ISO8601"
    },
    "variables": {
      "seed_url": "...",
      "search_keyword": "test"
    },
    "metadata": {
      "description": "Search results crawl"
    },
    "scheduled_at": "ISO8601",
    "started_at": "ISO8601",
    "completed_at": null,
    "duration_seconds": 1234,
    "retry_count": 0,
    "error_message": null,
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
}
```

#### 5.3.7 Get Job Logs (HTTP)

```
GET /api/v1/jobs/{job_id}/logs?level=INFO,WARNING,ERROR&since=ISO8601&limit=1000&offset=0&search=keyword

Response 200: {
  "success": true,
  "data": {
    "logs": [
      {
        "id": 12345,
        "job_id": "uuid",
        "step_name": "scrape_detail",
        "log_level": "INFO",
        "message": "Processing URL batch 5/10",
        "context": {
          "urls_count": 100,
          "batch_number": 5
        },
        "created_at": "ISO8601"
      }
    ],
    "total": 5432,
    "limit": 1000,
    "offset": 0
  }
}
```

#### 5.3.8 Stream Job Logs (WebSocket)

```
WS /api/v1/jobs/{job_id}/logs/stream

Client → Server (after connection):
{
  "action": "subscribe",
  "job_id": "uuid",
  "filters": {
    "levels": ["INFO", "WARNING", "ERROR"],
    "since": "ISO8601 (optional)"
  }
}

Server → Client (real-time logs):
{
  "type": "log",
  "data": {
    "id": 12345,
    "job_id": "uuid",
    "step_name": "scrape_detail",
    "log_level": "INFO",
    "message": "Page crawled successfully",
    "context": {details},
    "created_at": "ISO8601"
  }
}

Server → Client (job status change):
{
  "type": "status_change",
  "data": {
    "job_id": "uuid",
    "old_status": "running",
    "new_status": "completed",
    "timestamp": "ISO8601"
  }
}

Server → Client (progress update):
{
  "type": "progress",
  "data": {
    "job_id": "uuid",
    "progress": {progress_object}
  }
}

Server → Client (connection ack):
{
  "type": "connected",
  "message": "Subscribed to job logs",
  "job_id": "uuid"
}

Server → Client (error):
{
  "type": "error",
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Job not found"
  }
}

Client → Server (unsubscribe):
{
  "action": "unsubscribe"
}

Client → Server (ping):
{
  "action": "ping"
}

Server → Client (pong):
{
  "type": "pong"
}
```

### 5.4 Statistics & Monitoring Endpoints

#### 5.4.1 Website Statistics

```
GET /api/v1/websites/{id}/stats?from=ISO8601&to=ISO8601

Response 200: {
  "success": true,
  "data": {
    "website_id": "uuid",
    "time_range": {
      "from": "ISO8601",
      "to": "ISO8601"
    },
    "total_crawls": 45,
    "successful_crawls": 43,
    "failed_crawls": 2,
    "success_rate": 0.956,
    "total_pages": 12450,
    "duplicate_pages": 342,
    "avg_duration_seconds": 320,
    "total_data_size_mb": 1250,
    "crawl_history": [
      {
        "date": "2024-01-01",
        "crawls": 2,
        "pages": 450,
        "success_rate": 1.0
      }
    ]
  }
}
```

#### 5.4.2 List Crawled Pages

```
GET /api/v1/websites/{id}/pages?page=1&limit=50&sort=crawled_at:desc&is_duplicate=false

Response 200: {
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "url": "string",
        "title": "string",
        "is_duplicate": false,
        "similarity_score": null,
        "crawled_at": "ISO8601"
      }
    ],
    "total": 12450,
    "page": 1,
    "limit": 50
  }
}
```

#### 5.4.3 Get Page Details

```
GET /api/v1/pages/{page_id}

Response 200: {
  "success": true,
  "data": {
    "id": "uuid",
    "website_id": "uuid",
    "website_name": "string",
    "job_id": "uuid",
    "url": "string",
    "title": "string",
    "extracted_content": "text...",
    "metadata": {extracted_metadata},
    "gcs_html_path": "gs://bucket/path/file.html",
    "gcs_documents": [
      {
        "filename": "doc.pdf",
        "path": "gs://bucket/path/doc.pdf",
        "size_bytes": 12345
      }
    ],
    "is_duplicate": false,
    "duplicate_of": null,
    "similarity_score": null,
    "crawled_at": "ISO8601",
    "created_at": "ISO8601"
  }
}
```

#### 5.4.4 System Health

```
GET /api/v1/health

Response 200: {
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "ISO8601",
    "services": {
      "database": "healthy",
      "redis": "healthy",
      "nats": "healthy",
      "gcs": "healthy"
    },
    "resources": {
      "memory_usage_percent": 72.5,
      "cpu_usage_percent": 45.2,
      "disk_usage_percent": 58.3
    },
    "workers": {
      "active_browsers": 5,
      "active_contexts": 42,
      "active_jobs": 12
    }
  }
}
```

#### 5.4.5 Prometheus Metrics

```
GET /api/v1/metrics

Response 200 (Prometheus format):
# HELP crawl_jobs_total Total number of crawl jobs
# TYPE crawl_jobs_total counter
crawl_jobs_total{website_id="uuid",status="completed",job_type="scheduled"} 145
crawl_jobs_total{website_id="uuid",status="failed",job_type="seed_template"} 5
```

---

## 6. Website Configuration Schema

### 6.1 Full Configuration Structure

```json
{
  "id": "uuid",
  "name": "Website Name",
  "base_url": "https://example.com",
  "description": "Optional description of the website",
  "schedule": {
    "type": "recurring",
    "cron": "0 0 */14 * *",
    "timezone": "Asia/Jakarta"
  },
  "steps": [
    {
      "name": "crawl_list",
      "type": "crawl",
      "description": "Retrieve list of detail URLs",
      "method": "api",
      "browser_type": null,
      "config": {},
      "output": {}
    },
    {
      "name": "scrape_detail",
      "type": "scrape",
      "description": "Extract main content",
      "method": "browser",
      "browser_type": "playwright",
      "input_from": "crawl_list.detail_urls",
      "config": {},
      "selectors": {},
      "output": {}
    }
  ],
  "global_config": {
    "rate_limit": {},
    "timeout": {},
    "retry": {},
    "proxy": {},
    "headers": {},
    "cookies": {},
    "authentication": {}
  },
  "variables": {}
}
```

### 6.2 Schedule Configuration

```json
{
  "schedule": {
    "type": "once | recurring",
    "cron": "0 0 */14 * *",
    "timezone": "Asia/Jakarta",
    "enabled": true
  }
}
```

**Cron Format**: `minute hour day month weekday`

**Examples**:
- `0 0 */14 * *`: Every 14 days at midnight
- `0 2 * * 1`: Every Monday at 2 AM
- `*/30 * * * *`: Every 30 minutes
- `0 0 1 * *`: First day of every month

### 6.3 API Method Configuration

```json
{
  "name": "fetch_items",
  "type": "crawl",
  "method": "api",
  "config": {
    "url": "https://api.example.com/v1/items",
    "http_method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer ${variables.api_token}",
      "User-Agent": "CrawlerBot/1.0"
    },
    "query_params": {
      "page": "${pagination.current_page}",
      "limit": "100",
      "filter": "${variables.category_id}"
    },
    "body": {
      "type": "json",
      "data": {
        "filters": {
          "status": "active",
          "date_from": "${variables.start_date}"
        },
        "sort": "created_at:desc"
      }
    },
    "authentication": {
      "type": "bearer",
      "token_field": "${variables.api_token}",
      "refresh_endpoint": null,
      "session_config": null
    },
    "pagination": {
      "enabled": true,
      "type": "page_based",
      "page_param": "page",
      "start_page": 1,
      "max_pages": 100,
      "has_next_indicator": "response.pagination.has_more",
      "next_page_indicator": "response.pagination.next_page"
    },
    "response": {
      "format": "json",
      "encoding": "utf-8",
      "data_path": "data.items",
      "url_field": "detail_url",
      "metadata_fields": {
        "id": "id",
        "title": "title",
        "preview": "summary",
        "date": "created_at"
      }
    },
    "error_handling": {
      "retry_on_status": [429, 500, 502, 503, 504],
      "retry_after_header": "Retry-After",
      "max_retries": 3,
      "timeout": 30
    }
  },
  "output": {
    "urls_field": "detail_urls",
    "metadata_fields": ["id", "title", "preview", "date"]
  }
}
```

**Variable Substitution**:
- `${variables.key}`: From config.variables or job variables
- `${ENV.KEY}`: From environment variables (stored in database)
- `${pagination.current_page}`: Auto-incremented during pagination
- `${response.path}`: From previous API response (JSONPath)

**JSONPath Examples**:
- `$.data.items[*]`: All items in array
- `$.pagination.has_more`: Boolean field
- `$..detail_url`: All detail_url fields recursively

**Authentication Types**:
- `bearer`: Bearer token in Authorization header
- `session`: Session-based (cookies)
- `basic`: HTTP Basic Auth (future)
- `oauth2`: OAuth2 flow (future)

**Pagination Types**:
- `page_based`: Traditional page numbers (1, 2, 3, ...)
- `offset_based`: Offset and limit (0, 100, 200, ...)
- `cursor_based`: Cursor tokens (next/previous)

### 6.4 Browser Method Configuration

```json
{
  "name": "scrape_page",
  "type": "scrape",
  "method": "browser",
  "browser_type": "playwright",
  "input_from": "crawl_list.detail_urls",
  "config": {
    "url": "${input.url}",
    "wait_until": "networkidle",
    "viewport": {
      "width": 1920,
      "height": 1080
    },
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "extra_headers": {
      "Accept-Language": "en-US,en;q=0.9"
    },
    "cookies": [],
    "javascript_enabled": true,
    "images_enabled": false,
    "actions": [
      {
        "type": "wait",
        "selector": "div.content",
        "timeout": 10000
      },
      {
        "type": "click",
        "selector": "button.load-more",
        "optional": true
      },
      {
        "type": "scroll",
        "direction": "bottom",
        "count": 3,
        "delay": 1000
      }
    ],
    "infinite_scroll": {
      "enabled": false,
      "max_scrolls": 10,
      "scroll_delay": 1000,
      "no_change_limit": 3
    },
    "pagination": {
      "enabled": false,
      "type": "next_button",
      "selector": "a.next-page",
      "max_pages": 50,
      "wait_after_click": 2000
    },
    "screenshot": {
      "enabled": false,
      "full_page": true,
      "path_template": "screenshots/{job_id}/{url_hash}.png"
    }
  },
  "selectors": {
    "title": "h1.article-title",
    "content": "div.article-body",
    "author": "span.author-name",
    "date": "time[datetime]",
    "tags": {
      "selector": "span.tag",
      "attribute": "text",
      "type": "array"
    },
    "documents": {
      "selector": "a.download-link",
      "attribute": "href",
      "type": "array"
    },
    "metadata": {
      "selector": "meta[property='og:description']",
      "attribute": "content"
    }
  },
  "output": {
    "main_content_field": "content",
    "metadata_fields": ["title", "author", "date", "tags", "documents"]
  }
}
```

**Wait Until Options**:
- `load`: Wait for page load event
- `domcontentloaded`: Wait for DOM ready
- `networkidle`: Wait for network idle (recommended)

**Action Types**:
- `wait`: Wait for selector or duration
- `click`: Click element
- `fill`: Fill input field
- `scroll`: Scroll page
- `execute_script`: Run custom JavaScript
- `hover`: Hover over element

**Selector Attribute Types**:
- `text`: Element text content
- `html`: Element HTML
- `href`: Link URL
- `src`: Image/script source
- `content`: Meta tag content
- Any custom attribute name

**Selector Types**:
- Single value (default)
- `array`: Multiple elements as array

### 6.5 HTTP Method Configuration

```json
{
  "name": "fetch_page",
  "type": "scrape",
  "method": "http",
  "input_from": "crawl_list.detail_urls",
  "config": {
    "url": "${input.url}",
    "http_method": "GET",
    "headers": {
      "User-Agent": "Mozilla/5.0...",
      "Accept": "text/html"
    },
    "query_params": {},
    "follow_redirects": true,
    "timeout": 30,
    "encoding": "utf-8",
    "pagination": {
      "enabled": false,
      "type": "url_pattern",
      "url_template": "https://example.com/page?page={page}",
      "start_page": 1,
      "max_pages": 100
    },
    "extraction": {
      "parser": "selectolax",
      "item_selector": null,
      "fields": {}
    }
  },
  "selectors": {
    "title": "h1.title",
    "content": "div.article",
    "author": "span.author"
  },
  "output": {
    "main_content_field": "content",
    "metadata_fields": ["title", "author"]
  }
}
```

**Parser Options**:
- `selectolax`: Fast CSS selector parser (recommended)
- `beautifulsoup4`: Full-featured parser (fallback)

### 6.6 Global Configuration

```json
{
  "global_config": {
    "rate_limit": {
      "requests_per_second": 2,
      "concurrent_pages": 5,
      "burst": 10
    },
    "timeout": {
      "page_load": 30,
      "selector_wait": 10,
      "http_request": 30
    },
    "retry": {
      "max_attempts": 3,
      "backoff_strategy": "exponential",
      "backoff_base": 2,
      "initial_delay": 1,
      "max_delay": 300
    },
    "proxy": {
      "enabled": false,
      "type": null,
      "config": {}
    },
    "headers": {
      "User-Agent": "Mozilla/5.0...",
      "Accept-Language": "en-US,en;q=0.9"
    },
    "cookies": {},
    "authentication": {
      "type": null,
      "config": {}
    }
  }
}
```

**Backoff Strategies**:
- `exponential`: delay = initial × (base ^ attempt)
- `linear`: delay = initial × attempt
- `fixed`: delay = initial (constant)

### 6.7 Variables Configuration

```json
{
  "variables": {
    "seed_url": "${ENV.DEFAULT_SEED_URL}",
    "api_token": "${ENV.WEBSITE_API_TOKEN}",
    "start_date": "2024-01-01",
    "category_id": "123",
    "custom_header_value": "secret_value"
  }
}
```

Variables can be referenced in any configuration field using `${variables.key}` syntax. When submitting seed URL jobs, additional variables can be provided and will override config variables.

---

## 7. Processing Algorithms

### 7.1 Job Execution Flow

**Algorithm: Execute Job**

**Input**: Job object with website configuration or embedded config
**Output**: Job completion status and results

**Steps**:
1. Load job from queue
2. Validate job status (must be "pending")
3. Update status to "running"
4. Determine config source:
   - If job_type = "scheduled" or "seed_template": Load from websites table
   - If job_type = "seed_adhoc": Use embedded_config from job
5. Merge job variables with config variables (job variables take precedence)
6. Initialize cancellation signal listener
7. Initialize logging context
8. For each step in configuration:
   - Resolve all variable substitutions
   - Check cancellation signal
   - If cancelled: Jump to cleanup
   - Execute step based on method (API/Browser/HTTP)
   - Store step output
   - Update progress
   - Log step completion
9. Mark job as completed
10. Emit metrics
11. Cleanup resources

**Positive Cases**:
1. All steps execute successfully → Job marked as "completed"
2. Step produces 0 results → Log warning → Continue to next step
3. Optional step fails → Log error → Continue to next step
4. Cancellation requested → Graceful stop → Status "cancelled"
5. Partial results before cancellation → Saved to database
6. Seed URL job with template → Variables substituted → Normal execution
7. Seed URL job adhoc → Inline config used → Normal execution

**Negative Cases**:
1. Required step fails → Retry logic → If max retries exceeded → Job "failed"
2. Invalid configuration → Fail immediately → Log error → Job "failed"
3. Resource unavailable → Pause → Wait → Retry
4. Worker crash → Job marked "failed" by scheduler after timeout
5. Variable not found and required → Fail step → Job "failed"
6. Website config deleted mid-job → Use cached config → Complete normally

**Edge Cases**:
1. Cancellation during critical operation → Wait for operation → Then cancel
2. Configuration changed mid-job → Use original config → Log warning
3. Database connection lost → Buffer results → Reconnect → Flush buffer
4. Memory limit reached → Pause job → Free memory → Resume
5. Network partition → Retry with backoff → If persistent → Fail job
6. Seed URL redirects → Follow redirect → Use final URL → Continue
7. Variable circular reference → Detect → Fail validation
8. Job variables override config variables → Use job variables

### 7.2 Seed URL Job Execution

**Algorithm: Execute Seed URL Job**

**Input**: Job with seed_url and config (from database or embedded)
**Output**: Crawled and scraped pages

**Steps**:
1. Validate seed URL format
2. Load configuration:
   - If website_id present: Load from database
   - Else: Use embedded_config from job
3. Merge variables:
   - Start with config.variables
   - Override with job.variables
   - Add seed_url to variables
4. Substitute ${variables.seed_url} in step configs
5. Execute first step (usually crawl) starting from seed URL:
   - Navigate to seed URL
   - Extract detail URLs from page
   - Follow pagination if configured
   - Store discovered URLs
6. Execute subsequent steps (usually scrape):
   - Use URLs from previous step
   - Extract content from each URL
   - Apply deduplication
   - Store results
7. Mark job as completed

**Positive Cases**:
1. Seed URL with pagination → Discover all pages → Extract all URLs → Scrape all
2. Seed URL single page → Extract URLs from single page → Scrape all
3. Template config with variables → Substitute seed_url → Execute normally
4. Adhoc config inline → Validate → Execute directly
5. Seed URL with filters/parameters → Preserved in pagination → Correct results

**Negative Cases**:
1. Seed URL 404 → Log error → Fail job immediately
2. Seed URL blocked → Retry → If persistent → Fail
3. No pagination selector found → Treat as single page → Continue
4. Variable substitution fails → Log error → Fail step
5. Config validation fails → Return error to user → Don't create job

**Edge Cases**:
1. Seed URL is page 5 of results → Start from page 5 → Continue to end
2. Pagination loops (page 10 → page 1) → Track visited URLs → Detect cycle → Stop
3. Seed URL query parameters conflict with pagination → Preserve user params → Append pagination
4. Multiple pagination mechanisms detected → Use configured one → Ignore others
5. Seed URL redirects to login page → Detect redirect → Fail with auth error
6. Base URL different from seed URL domain → Allow cross-domain → Log warning
7. Discovered URLs exceed max_pages limit → Stop discovery → Process discovered so far
8. Same seed URL submitted multiple times → Separate jobs → Independent execution

### 7.3 Variable Substitution Algorithm

**Algorithm: Resolve Variables**

**Input**: Configuration string with variable placeholders, variable sources
**Output**: String with variables replaced by values

**Steps**:
1. Scan string for variable patterns: `${source.key}`
2. For each variable found:
   - Parse source (variables, ENV, input, pagination, metadata)
   - Parse key
   - Look up value in appropriate source
   - If found: Replace placeholder with value
   - If not found:
     - Check if variable is required (context-dependent)
     - If required: Throw error → Fail validation/execution
     - If optional: Use empty string or null → Log warning
3. Perform type conversion if needed
4. Return resolved string

**Variable Sources Priority**:
1. Job variables (highest priority)
2. Config variables
3. Environment variables
4. Runtime variables (input, pagination)
5. Metadata variables

**Positive Cases**:
1. Simple variable → `${variables.name}` → "value"
2. Nested variable → `${variables.api.token}` → "token123"
3. Environment variable → `${ENV.API_KEY}` → Value from database env storage
4. Runtime variable → `${pagination.current_page}` → "5"
5. Multiple variables in one string → All substituted correctly
6. Variable value is number → Convert to string → Substitute

**Negative Cases**:
1. Variable not found → Return empty string (if optional) or fail (if required)
2. Invalid syntax → Log error → Fail validation
3. Circular reference → Detect → Fail validation

**Edge Cases**:
1. Variable value contains `${...}` → No recursive substitution → Use literal value
2. Escaped placeholder `\${...}` → Treat as literal → Don't substitute
3. Variable value is JSON object → Serialize to JSON string → Substitute
4. Multiple sources have same key → Use highest priority source
5. Variable is boolean/number → Convert to string representation

### 7.4 Step Execution

**Algorithm: Execute Step**

**Input**: Step configuration, previous step output (if any), job variables
**Output**: Step results (URLs, metadata, content)

**Steps**:
1. Parse step configuration
2. Resolve all variables in configuration
3. Initialize appropriate worker (API/Browser/HTTP)
4. If crawl step:
   - Execute method to get list
   - Extract URLs and metadata
   - Store in temporary results
   - Update progress (discovered URLs)
5. If scrape step:
   - Get URLs from input_from or config
   - For each URL (with rate limiting):
     - Check cancellation signal
     - Check deduplication (skip if duplicate)
     - Execute method to get content
     - Extract using selectors
     - Store content and metadata
     - Update progress (processed URLs)
6. Return results

**Positive Cases**:
1. Crawl step finds URLs → Pass to scrape step
2. Scrape step extracts all fields → Store successfully
3. Pagination works correctly → All pages processed
4. Rate limiting respected → No blocks
5. Variables substituted correctly → URLs accessed

**Negative Cases**:
1. No URLs found in crawl step → Log warning → Skip scrape step
2. Selector not found → Use null value → Log warning
3. Required selector not found → Mark as extraction error
4. Pagination fails → Stop at current page → Log error
5. Variable resolution fails → Fail step

**Edge Cases**:
1. Infinite pagination detected → Stop at max_pages → Log warning
2. URL redirects to different domain → Follow if allowed → Skip if not
3. Content in unexpected format → Attempt flexible parsing → Log if fails
4. Rate limit hit → Wait for Retry-After → Continue
5. Partial batch failure → Continue with successful items → Log failures
6. Input URLs from previous step empty → Skip step → Log warning
7. Step timeout exceeded → Cancel step → Partial results saved

### 7.5 Deduplication Check

**Algorithm: Check Duplicate**

**Input**: URL, extracted content, website_id
**Output**: (is_duplicate: bool, reason: string, original_page_id: uuid or null)

**Steps**:
1. Generate URL hash (SHA256)
2. Check Redis: `crawled:{url_hash}`
   - If exists and fresh (within TTL):
     - Return (True, "URL recently crawled", cached_page_id)
3. Clean and normalize content
4. Generate content hash (Simhash)
5. Query PostgreSQL: SELECT FROM content_hashes WHERE content_hash = ?
6. If found:
   - Calculate similarity score
   - If similarity >= 95%:
     - Return (True, "Content duplicate", original_page_id)
7. Return (False, "Not duplicate", None)

**Positive Cases**:
1. Exact same URL within TTL → Duplicate, skip crawl
2. Same content different URL → Duplicate, skip storage
3. 96% similar content → Duplicate, link to original
4. First time seeing URL and content → Not duplicate, proceed

**Negative Cases**:
1. URL outside TTL → Proceed with crawl
2. Content similarity 94% → Not duplicate (below threshold)
3. Content hash collision (rare) → Compare full text → Resolve

**Edge Cases**:
1. Content with dynamic ads → Extract main content only → Hash clean content
2. Minor formatting differences → Normalize → Hash normalized version
3. URL with tracking parameters → Normalize URL → Generate consistent hash
4. Redirected URL → Use final URL for deduplication
5. Updated content (93% similar) → Not duplicate → Store as new
6. Seed URL job vs scheduled job → Same deduplication logic
7. Multiple concurrent jobs crawling same URL → First wins → Others skip

**Content Normalization**:
- Remove extra whitespace
- Convert to lowercase
- Remove HTML tags if present
- Remove common stop words (optional)
- Remove timestamps and dynamic elements

### 7.6 Cancellation Handling

**Algorithm: Handle Cancellation**

**Input**: Job ID
**Output**: Cancellation status

**Steps**:
1. Validate job exists and is cancellable
2. Update job status to "cancelling"
3. Set Redis flag: `cancel:job:{job_id} = true`
4. Notify worker via Redis Pub/Sub (if available)
5. Wait for worker acknowledgment (max 30 seconds)
6. If worker acknowledges:
   - Wait for cleanup completion (max 5 minutes)
   - Update status to "cancelled"
7. If timeout:
   - Force kill worker process
   - Mark as "cancelled with errors"
8. Delete Redis flag
9. Log cancellation

**Worker Cancellation Check**:
- Check Redis flag every 1-2 seconds during execution
- Check before starting new page/URL
- Check between major steps

**Cleanup Steps**:
1. Stop current operation gracefully
2. Close browser context/tab
3. Close HTTP connections
4. Flush pending logs to database
5. Save progress and partial results
6. Update job metadata
7. Release resources

**Positive Cases**:
1. Cancellation during crawl → Stop after current page → Save URLs found
2. Cancellation during scrape → Complete current URL → Stop → Save pages
3. Quick response (<5s) → Clean cancellation
4. All resources freed → Successful cleanup
5. Seed URL job cancelled → Same handling as regular job

**Negative Cases**:
1. Worker not responding → Force kill after timeout
2. Database transaction in progress → Rollback → Retry
3. Browser frozen → Force close context → Log error

**Edge Cases**:
1. Cancellation during GCS upload → Abort upload → Delete partial file
2. Multiple cancellation requests → Idempotent (same result)
3. Cancellation of already completed job → Return error
4. Cancellation during critical database write → Wait for write → Then cancel
5. Worker crash during cleanup → Scheduler handles orphaned job

### 7.7 Log Streaming

**Algorithm: Stream Logs to Frontend**

**Input**: Job ID, WebSocket connection
**Output**: Real-time log stream

**Steps**:
1. Validate WebSocket connection and job_id
2. Query historical logs from database
3. Send historical logs to client
4. Subscribe to new logs for this job_id
5. While connection open:
   - When new log created:
     - Write to database
     - Broadcast to all connected clients
   - Handle client messages (unsubscribe, ping)
   - Send heartbeat every 30 seconds
6. On disconnect:
   - Unsubscribe from updates
   - Close connection

**Positive Cases**:
1. Client connects → Receives all historical logs → Receives real-time updates
2. Log created during execution → Sent to client within 100ms
3. Job completes → Final logs sent → Connection closed gracefully
4. Multiple clients connected → All receive same logs
5. Seed URL job logs → Same streaming mechanism

**Negative Cases**:
1. Invalid job_id → Error sent → Connection closed
2. Unauthorized → 403 error → Connection closed
3. Job not found → 404 error → Connection closed

**Edge Cases**:
1. High log volume → Batch logs every 100ms → Send batch
2. Client disconnect → Buffer last 1000 logs → Resend on reconnect
3. Database write lag → Logs sent to client before DB confirm
4. WebSocket connection limit → Queue connection → Notify client
5. Worker crash → Logs up to crash available → Mark incomplete

### 7.8 Browser Pool Management

**Algorithm: Manage Browser Pool**

**Input**: Browser pool configuration
**Output**: Available browser contexts

**Steps**:
1. Initialize browser pool:
   - Start N browsers (default 5)
   - Create M contexts per browser (default 10-15)
2. Request handling:
   - When job requests browser context:
     - Check available contexts
     - If available: Assign immediately
     - If none: Queue request
3. Context lifecycle:
   - Assign to job
   - Job uses context
   - Job completes/cancels
   - Clean context (clear cookies, cache, storage)
   - Return to pool
4. Health monitoring:
   - Check memory usage every 30s
   - Check browser responsiveness every 60s
   - Restart unhealthy browsers
5. Graceful shutdown:
   - Stop accepting new requests
   - Wait for active jobs (max 5 minutes)
   - Close all contexts
   - Close all browsers

**Positive Cases**:
1. Context available → Immediate assignment
2. Context returned after use → Cleaned → Available for reuse
3. Browser healthy → Long uptime → Efficient resource use
4. Memory within limits → Normal operation

**Negative Cases**:
1. All contexts busy → Queue request → Wait
2. Browser crash → Detect → Restart → Recreate contexts
3. Context timeout → Force close → Create new

**Edge Cases**:
1. Memory >85% → Reduce active contexts → Scale down
2. Repeated browser crashes → Disable → Alert
3. Context stuck → Force kill → Log error
4. Zero contexts available for 10 minutes → Alert
5. Shutdown during active jobs → Force close after timeout

---

## 8. Monitoring & Alerting

### 8.1 Prometheus Metrics

**Counters**:
```
crawl_jobs_total{website_id, status, job_type}
crawl_pages_total{website_id}
crawl_errors_total{website_id, error_type}
duplicate_urls_skipped{website_id}
duplicate_content_found{website_id}
job_cancellations_total{website_id, reason}
seed_url_jobs_total{website_id, mode}
http_requests_total{method, status_code}
browser_crashes_total
websocket_connections_total
variable_substitution_errors_total
```

**Gauges**:
```
browser_pool_active_count
browser_pool_available_contexts
browser_pool_memory_mb
queue_depth{status, job_type}
workers_active_count
active_websocket_connections
```

**Histograms**:
```
crawl_duration_seconds{website_id, step_name, job_type}
page_load_duration_seconds{website_id}
content_size_bytes{website_id}
deduplication_check_duration_seconds
log_streaming_latency_seconds
variable_resolution_duration_seconds
```

**Summary**:
```
crawl_success_rate{website_id, job_type}
```

### 8.2 Alert Definitions

**Critical Alerts**:

```yaml
- alert: SystemDown
  expr: up == 0
  for: 1m
  severity: critical

- alert: HighMemoryUsage
  expr: browser_pool_memory_mb > 6500
  for: 5m
  severity: critical

- alert: BrowserCrashSpike
  expr: rate(browser_crashes_total[5m]) > 0.1
  for: 5m
  severity: critical

- alert: DatabaseConnectionFailed
  expr: database_connection_errors_total > 5
  for: 2m
  severity: critical

- alert: QueueStuck
  expr: queue_depth{status="pending"} > 0 AND rate(crawl_jobs_total[5m]) == 0
  for: 10m
  severity: critical
```

**Warning Alerts**:

```yaml
- alert: LowSuccessRate
  expr: sum(rate(crawl_jobs_total{status="completed"}[6h])) / sum(rate(crawl_jobs_total[6h])) < 0.8
  for: 30m
  severity: warning

- alert: WebsiteFailures
  expr: sum(increase(crawl_errors_total[1h])) BY (website_id) >= 5
  severity: warning

- alert: QueueBacklog
  expr: queue_depth{status="pending"} > 1000
  for: 30m
  severity: warning

- alert: SlowCrawls
  expr: histogram_quantile(0.95, rate(crawl_duration_seconds_bucket[10m])) > 300
  for: 30m
  severity: warning

- alert: HighCancellationRate
  expr: rate(job_cancellations_total[1h]) / rate(crawl_jobs_total[1h]) > 0.2
  for: 30m
  severity: warning

- alert: HighVariableSubstitutionErrors
  expr: rate(variable_substitution_errors_total[10m]) > 1
  for: 5m
  severity: warning
```

### 8.3 Grafana Dashboards

**Dashboard 1: System Overview**
- Current status
- Active jobs by type (scheduled, seed_template, seed_adhoc)
- Queue depth
- Success rate (24h)
- Memory, CPU usage
- Error rate chart

**Dashboard 2: Job Monitoring**
- Running jobs table
- Job duration histogram by type
- Success/failure rates per website
- Cancellation statistics
- Seed URL job statistics

**Dashboard 3: Resource Utilization**
- Browser pool status
- HTTP worker stats
- Database connection pool
- Redis operations/sec

**Dashboard 4: Website Performance**
- Table: All websites
- Drill-down to website details
- Historical performance chart
- Seed URL vs scheduled job comparison

**Dashboard 5: Error Analysis**
- Error types breakdown
- Top failing websites
- Error trends over time
- Recent error logs

**Dashboard 6: Seed URL Jobs**
- Active seed URL jobs
- Success rate by mode (template vs adhoc)
- Variable substitution statistics
- Popular seed URLs

---

## 9. Deployment

### 9.1 Docker Compose Structure

**Services**:
- `api`: FastAPI application
- `scheduler`: Cron scheduler service
- `worker`: Job worker service (scalable)
- `postgres`: PostgreSQL database
- `redis`: Redis cache
- `nats`: NATS JetStream
- `prometheus`: Metrics collection
- `grafana`: Visualization
- `loki`: Log aggregation
- `promtail`: Log shipping

### 9.2 Environment Variables

**Database**:
```
DATABASE_URL=postgresql://user:pass@postgres:5432/crawler
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

**Redis**:
```
REDIS_URL=redis://redis:6379/0
REDIS_MAX_CONNECTIONS=50
```

**NATS**:
```
NATS_URL=nats://nats:4222
NATS_STREAM_NAME=crawl_jobs
NATS_CONSUMER_NAME=crawler_workers
```

**Google Cloud Storage**:
```
GCS_BUCKET=crawler-storage
GCS_CREDENTIALS_PATH=/secrets/gcs-key.json
GCS_PROJECT_ID=project-id
```

**Browser Pool**:
```
MAX_BROWSERS=5
CONTEXTS_PER_BROWSER=15
BROWSER_TIMEOUT=30
BROWSER_HEADLESS=true
```

**Worker Configuration**:
```
MAX_HTTP_WORKERS=30
MAX_CONCURRENT_JOBS=100
WORKER_HEARTBEAT_INTERVAL=30
```

**Logging**:
```
LOG_LEVEL=INFO
LOG_FORMAT=json
LOKI_URL=http://loki:3100
```

**Monitoring**:
```
PROMETHEUS_PORT=9090
METRICS_ENABLED=true
METRICS_PUSH_INTERVAL=15
```

**Security** (Future):
```
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
API_KEY_HEADER=X-API-Key
```

### 9.3 Resource Allocation (8GB RAM)

```
- Browsers (5 × 800MB):     4.0 GB
- PostgreSQL:                1.0 GB
- Redis:                     0.5 GB
- Python workers:            1.0 GB
- NATS:                      0.3 GB
- Monitoring:                0.7 GB
- OS + Buffer:               0.5 GB
                           --------
Total:                       8.0 GB
```

### 9.4 Startup Sequence

1. Start infrastructure (postgres, redis, nats)
2. Wait for health checks
3. Run database migrations
4. Start API service
5. Start scheduler service
6. Start worker service(s)
7. Start monitoring stack

### 9.5 Graceful Shutdown

**Shutdown Procedure**:
1. API: Stop accepting new requests → Wait for in-flight requests (30s timeout)
2. Scheduler: Stop creating new jobs → Wait for current cycle
3. Workers: Stop accepting new jobs → Wait for active jobs (5 min timeout) → Force stop
4. Browsers: Close all contexts → Close all browsers
5. Connections: Close database, Redis, NATS connections
6. Monitoring: Flush metrics and logs

---

## 10. Success Criteria

### 10.1 Functional Requirements

- [ ] Successfully crawl 100+ websites with different configurations
- [ ] Support static, dynamic (JavaScript), and API-based crawling
- [ ] Support seed URL submission (template and ad-hoc modes)
- [ ] Accurate deduplication (95% similarity threshold)
- [ ] Reliable scheduling (one-time and recurring)
- [ ] Complete API for frontend integration
- [ ] Real-time log streaming via WebSocket
- [ ] Job cancellation from frontend
- [ ] Variable substitution in configurations
- [ ] Comprehensive monitoring and alerting

### 10.2 Performance Requirements

- [ ] Handle 100+ concurrent crawls
- [ ] Crawl speed: 5-10 pages/second per website (average)
- [ ] Memory usage: ≤7.5GB (93% of 8GB)
- [ ] Success rate: ≥90% for well-behaved websites
- [ ] API response time: <200ms (P95)
- [ ] Log streaming latency: <200ms
- [ ] Cancellation response time: <5 seconds
- [ ] Queue processing lag: <5 minutes under normal load
- [ ] Variable resolution: <10ms

### 10.3 Reliability Requirements

- [ ] System uptime: ≥99% (excluding planned maintenance)
- [ ] Job failure rate: ≤10%
- [ ] Automatic recovery from browser crashes
- [ ] Data integrity: No data loss during failures
- [ ] Graceful degradation under resource pressure
- [ ] Complete audit trail via logs
- [ ] Seed URL jobs execute reliably

### 10.4 Operational Requirements

- [ ] Clear, structured logs for debugging
- [ ] Alerts for critical issues (<5 minute detection)
- [ ] Easy configuration updates (no code changes)
- [ ] Database backups (automated daily)
- [ ] Rollback capability for deployments
- [ ] Real-time system health monitoring
- [ ] Seed URL job monitoring and statistics

---

## 11. Future Enhancements (Out of Scope)

### 11.1 Advanced Features
- Proxy rotation (residential/datacenter)
- CAPTCHA solving integration
- Advanced authentication (OAuth2, 2FA)
- Distributed crawling (multi-server)
- Real-time crawling (WebSocket)
- Content change detection
- Email/Webhook notifications
- Recursive site crawling (follow all internal links)
- Link graph analysis

### 11.2 Scale & Performance
- Microservices architecture
- Kubernetes deployment
- Horizontal auto-scaling
- CDN integration
- Elasticsearch for search
- Message queue sharding
- Multi-region deployment

### 11.3 Business Features
- Multi-tenancy
- RBAC implementation
- Billing & usage tracking
- API rate limiting per user
- Custom alerting rules
- Scheduled reports
- Data export/import

---

## 12. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Memory overflow from browsers | High | Medium | Memory monitoring, auto-restart, dynamic scaling down |
| Cloudflare/anti-bot blocking | Medium | High | Abstract browser layer, prepare undetected-chrome, future proxy |
| Website structure changes | Medium | Medium | Configuration versioning, change detection, alerts |
| Database growth | Medium | High | Data retention policy, archival, partitioning |
| Queue backup | Medium | Low | Dead letter queue, alerts, priority system |
| Single point of failure | High | Medium | Regular backups, disaster recovery plan, prepare distributed |
| WebSocket connection limits | Low | Low | Connection pooling, load balancing |
| Log storage growth | Medium | Medium | Log retention policy, compression, Loki limits |
| Variable resolution errors | Low | Medium | Validation at config creation, comprehensive testing |
| Seed URL abuse | Low | Low | Rate limiting, monitoring, user quotas (future) |

---

## 13. Appendix

### 13.1 Example Configurations

#### Example 1: BPK Peraturan - Template Config for Seed URLs

**Website Configuration (stored in database)**:

```json
{
  "name": "BPK Peraturan",
  "base_url": "https://peraturan.bpk.go.id",
  "description": "Template for crawling BPK regulation search results",
  "schedule": {
    "type": "once",
    "enabled": false
  },
  "steps": [
    {
      "name": "crawl_search_results",
      "type": "crawl",
      "description": "Extract regulation links from search results",
      "method": "browser",
      "browser_type": "playwright",
      "config": {
        "url": "${variables.seed_url}",
        "wait_until": "networkidle",
        "actions": [
          {
            "type": "wait",
            "selector": "div.search-results",
            "timeout": 10000
          }
        ],
        "pagination": {
          "enabled": true,
          "type": "next_button",
          "selector": "a.pagination-next",
          "max_pages": 100,
          "wait_after_click": 2000
        },
        "extraction": {
          "item_selector": "div.result-item",
          "fields": {
            "detail_url": {
              "selector": "a.regulation-link",
              "attribute": "href",
              "required": true
            },
            "title": {
              "selector": "h3.regulation-title",
              "attribute": "text"
            },
            "nomor": {
              "selector": "span.nomor",
              "attribute": "text"
            },
            "tahun": {
              "selector": "span.tahun",
              "attribute": "text"
            }
          }
        }
      },
      "output": {
        "urls_field": "detail_urls",
        "metadata_fields": ["title", "nomor", "tahun"]
      }
    },
    {
      "name": "scrape_regulation_detail",
      "type": "scrape",
      "description": "Extract full regulation content",
      "method": "browser",
      "browser_type": "playwright",
      "input_from": "crawl_search_results.detail_urls",
      "config": {
        "url": "${input.url}",
        "wait_until": "networkidle",
        "actions": [
          {
            "type": "wait",
            "selector": "div.regulation-content",
            "timeout": 10000
          }
        ]
      },
      "selectors": {
        "title": "h1.regulation-title",
        "nomor_lengkap": "div.regulation-number",
        "tentang": "div.regulation-about",
        "content": "div.regulation-content",
        "tanggal_ditetapkan": "span.tanggal-penetapan",
        "tanggal_diundangkan": "span.tanggal-pengundangan",
        "sumber": "span.sumber",
        "status": "span.status",
        "documents": {
          "selector": "a.download-pdf",
          "attribute": "href",
          "type": "array"
        }
      },
      "output": {
        "main_content_field": "content",
        "metadata_fields": ["title", "nomor_lengkap", "tentang", "tanggal_ditetapkan", "status", "documents"]
      }
    }
  ],
  "global_config": {
    "rate_limit": {
      "requests_per_second": 2,
      "concurrent_pages": 5
    },
    "timeout": {
      "page_load": 30,
      "selector_wait": 10
    },
    "retry": {
      "max_attempts": 3,
      "backoff_strategy": "exponential"
    }
  },
  "variables": {
    "seed_url": "${ENV.BPK_DEFAULT_SEARCH_URL}"
  }
}
```

**Seed URL Job Submission (using template)**:

```json
POST /api/v1/jobs/submit-seed

{
  "website_id": "uuid-of-bpk-peraturan-config",
  "seed_url": "https://peraturan.bpk.go.id/Search?keywords=%22penuntut+umum%22",
  "schedule": {
    "type": "once"
  },
  "priority": 7,
  "variables": {
    "search_keyword": "penuntut umum"
  },
  "metadata": {
    "description": "Crawl regulations about 'penuntut umum'",
    "tags": ["hukum", "penuntut-umum"],
    "requested_by": "legal_team"
  }
}
```

#### Example 2: SPSE Tender - Mixed API and Browser

**Website Configuration**:

```json
{
  "name": "SPSE Government Tenders",
  "base_url": "https://spse.go.id",
  "description": "Crawl government tender listings",
  "schedule": {
    "type": "recurring",
    "cron": "0 0 */14 * *",
    "timezone": "Asia/Jakarta"
  },
  "steps": [
    {
      "name": "fetch_tender_list_api",
      "type": "crawl",
      "description": "Get tender list from API",
      "method": "api",
      "config": {
        "url": "https://api.spse.go.id/v1/tenders",
        "http_method": "POST",
        "headers": {
          "Content-Type": "application/json",
          "Authorization": "Bearer ${variables.api_token}"
        },
        "body": {
          "type": "json",
          "data": {
            "status": "active",
            "year": 2024
          }
        },
        "pagination": {
          "enabled": true,
          "type": "page_based",
          "page_param": "page",
          "start_page": 1,
          "max_pages": 50,
          "has_next_indicator": "meta.has_next"
        },
        "response": {
          "format": "json",
          "data_path": "data",
          "url_field": "detail_url",
          "metadata_fields": {
            "tender_id": "id",
            "title": "title",
            "agency": "agency_name",
            "budget": "budget_amount"
          }
        }
      },
      "output": {
        "urls_field": "detail_urls",
        "metadata_fields": ["tender_id", "title", "agency", "budget"]
      }
    },
    {
      "name": "scrape_tender_detail_browser",
      "type": "scrape",
      "description": "Get detailed tender info (requires JS)",
      "method": "browser",
      "browser_type": "playwright",
      "input_from": "fetch_tender_list_api.detail_urls",
      "config": {
        "url": "${input.url}",
        "wait_until": "networkidle",
        "actions": [
          {
            "type": "wait",
            "selector": "div.tender-detail",
            "timeout": 15000
          }
        ]
      },
      "selectors": {
        "title": "h1.tender-title",
        "description": "div.tender-description",
        "specifications": "div.tender-specifications",
        "requirements": "div.tender-requirements",
        "deadline_registration": "span.deadline-registration",
        "deadline_submission": "span.deadline-submission",
        "contact_person": "div.contact-info",
        "documents": {
          "selector": "a.document-download",
          "attribute": "href",
          "type": "array"
        }
      },
      "output": {
        "main_content_field": "description",
        "metadata_fields": ["title", "specifications", "deadline_submission", "documents"]
      }
    }
  ],
  "global_config": {
    "rate_limit": {
      "requests_per_second": 1,
      "concurrent_pages": 3
    },
    "timeout": {
      "page_load": 30,
      "http_request": 20
    },
    "retry": {
      "max_attempts": 3,
      "backoff_strategy": "exponential"
    }
  },
  "variables": {
    "api_token": "${ENV.SPSE_API_TOKEN}"
  }
}
```

#### Example 3: E-commerce - Ad-hoc Seed URL (No Template)

**Seed URL Job Submission (inline config)**:

```json
POST /api/v1/jobs/submit-seed

{
  "seed_url": "https://shop.example.com/search?q=laptop&category=electronics",
  "schedule": {
    "type": "once"
  },
  "priority": 5,
  "config": {
    "name": "E-commerce Product Search",
    "steps": [
      {
        "name": "crawl_product_list",
        "type": "crawl",
        "method": "browser",
        "browser_type": "playwright",
        "config": {
          "url": "${variables.seed_url}",
          "wait_until": "networkidle",
          "infinite_scroll": {
            "enabled": true,
            "max_scrolls": 10,
            "scroll_delay": 2000,
            "no_change_limit": 3
          },
          "extraction": {
            "item_selector": "div.product-card",
            "fields": {
              "detail_url": {
                "selector": "a.product-link",
                "attribute": "href"
              },
              "name": {
                "selector": "h3.product-name",
                "attribute": "text"
              },
              "price": {
                "selector": "span.price",
                "attribute": "text"
              },
              "rating": {
                "selector": "span.rating",
                "attribute": "text"
              }
            }
          }
        },
        "output": {
          "urls_field": "product_urls",
          "metadata_fields": ["name", "price", "rating"]
        }
      },
      {
        "name": "scrape_product_detail",
        "type": "scrape",
        "method": "browser",
        "browser_type": "playwright",
        "input_from": "crawl_product_list.product_urls",
        "config": {
          "url": "${input.url}",
          "wait_until": "networkidle"
        },
        "selectors": {
          "name": "h1.product-name",
          "description": "div.product-description",
          "price": "span.current-price",
          "original_price": "span.original-price",
          "discount": "span.discount-percentage",
          "specifications": "div.specifications",
          "seller": "span.seller-name",
          "stock": "span.stock-count",
          "images": {
            "selector": "img.product-image",
            "attribute": "src",
            "type": "array"
          }
        },
        "output": {
          "main_content_field": "description",
          "metadata_fields": ["name", "price", "discount", "seller", "stock"]
        }
      }
    ],
    "global_config": {
      "rate_limit": {
        "requests_per_second": 2,
        "concurrent_pages": 5
      },
      "timeout": {
        "page_load": 30
      },
      "retry": {
        "max_attempts": 3,
        "backoff_strategy": "exponential"
      }
    }
  },
  "variables": {
    "seed_url": "https://shop.example.com/search?q=laptop&category=electronics",
    "search_query": "laptop",
    "category": "electronics"
  },
  "metadata": {
    "description": "Ad-hoc crawl for laptop products",
    "tags": ["e-commerce", "laptop", "electronics"],
    "requested_by": "marketing_team"
  }
}
```

#### Example 4: News Archive - Scheduled Seed URL

**Seed URL Job Submission (scheduled, using template)**:

```json
POST /api/v1/jobs/submit-seed

{
  "website_id": "uuid-of-news-portal-config",
  "seed_url": "https://news.example.com/archive/2024/10",
  "schedule": {
    "type": "recurring",
    "cron": "0 0 1 * *",
    "timezone": "Asia/Jakarta"
  },
  "priority": 5,
  "variables": {
    "archive_month": "October 2024"
  },
  "metadata": {
    "description": "Monthly archive crawl for October 2024",
    "tags": ["news", "archive", "monthly"]
  }
}
```

---

## 14. Glossary

**Terms**:
- **Crawl**: Process of discovering URLs and collecting preview metadata
- **Scrape**: Process of extracting detailed content from individual pages
- **Step**: Single unit of work in a multi-step workflow
- **Context**: Isolated browser session with separate cookies/storage
- **Deduplication**: Process of identifying and skipping duplicate content
- **Simhash**: Fuzzy hashing algorithm for near-duplicate detection
- **TTL**: Time To Live - duration before cache entry expires
- **DLQ**: Dead Letter Queue - storage for failed jobs requiring manual review
- **Backoff**: Delay strategy for retrying failed operations
- **Jitter**: Random variance added to delays to prevent synchronization
- **Seed URL**: Starting URL for crawling, typically a search result or filtered list page
- **Template Config**: Pre-configured website settings that can be reused with different seed URLs
- **Ad-hoc Job**: One-time job with inline configuration, not stored as website config
- **Variable Substitution**: Process of replacing placeholders with actual values at runtime
- **Job Type**: Category of job (scheduled, seed_template, seed_adhoc)

---

**Document Version**: 3.0
**Last Updated**: 2025-10-26
**Status**: Ready for Implementation

---
