# NATS JetStream Integration Guide

## Overview

NATS JetStream is fully integrated for distributed job queuing with immediate cancellation support for pending jobs.

## ✅ What Requires NATS

### **Production Features (NATS Required)**
- Job queue distribution to workers
- Immediate cancellation of pending jobs
- Worker job consumption
- Horizontal scaling (multiple workers)

### **Fallback Without NATS**
- ✅ API still works (job creation, cancellation)
- ✅ Jobs stored in database
- ⚠️ Workers cannot process jobs
- ⚠️ No immediate queue removal on cancellation

## 🚀 Setup

### **1. Start NATS with Docker**
```bash
# Start all services including NATS
make db-up

# Verify NATS is healthy
docker ps | grep nats
# Should show: (healthy)

# Check NATS logs
docker logs lexicon-nats

# Access NATS monitoring UI
open http://localhost:8222
```

### **2. Configuration**
Environment variables (`.env`):
```env
NATS_URL=nats://localhost:4222
NATS_STREAM_NAME=CRAWLER_TASKS
NATS_CONSUMER_NAME=crawler-worker
```

## 📊 Test Coverage

### **Unit Tests (No NATS Required)**
```bash
# All mocked - run without NATS
uv run pytest tests/unit/services/test_nats_queue.py -v
# ✅ 16 tests - connection, publishing, deletion, health checks
```

### **Integration Tests - Mocked (No NATS Required)**
```bash
# Mock NATS for API flow testing
uv run pytest tests/integration/test_nats_queue_cancellation.py -v
# ✅ 5 tests - job publishing, cancellation, message format
```

### **Integration Tests - Real NATS (NATS Required)**
```bash
# Requires NATS to be running
make db-up
uv run pytest tests/integration/test_nats_real_connection.py -v
# ✅ 6 tests - real connection, message publishing, queue operations
```

## 🔧 Components

### **1. NATS Service** (`crawler/services/nats_queue.py`)
- Stream management (auto-creation with proper config)
- Consumer setup (durable, ack-based)
- Job publishing with deduplication
- Job removal from queue (for cancellation)
- Health checks and monitoring

### **2. Job Service** (`crawler/api/v1/services/jobs.py`)
- **Job Creation**: Publishes to NATS queue
- **Job Cancellation**:
  - Pending jobs → Removed from NATS queue immediately
  - Running jobs → Redis cancellation flag set

### **3. Worker** (`crawler/worker.py`)
- Pull-based consumer
- Processes jobs from NATS queue
- Checks cancellation before starting
- Updates job status in database
- Graceful shutdown handling

### **4. Lifecycle Management** (`main.py`)
- Startup: Connects to NATS
- Shutdown: Disconnects gracefully
- Graceful error handling if NATS unavailable

## 🔄 Data Flow

### **Job Creation**
```
API Request → JobService.create_seed_job()
             ↓
         Database (job record created)
             ↓
         NATS Queue (message published)
             ↓
         Worker picks up job
```

### **Job Cancellation - Pending**
```
API Request → JobService.cancel_job()
             ↓
         Check job status
             ↓
         IF PENDING:
             Remove from NATS queue
             Set Redis flag
             Update DB status
             ↓
         Job will NOT start
```

### **Job Cancellation - Running**
```
API Request → JobService.cancel_job()
             ↓
         Check job status
             ↓
         IF RUNNING:
             Set Redis flag (no queue removal)
             Update DB status
             ↓
         Worker detects flag during execution
```

## 🏃 Running Workers

### **Start a Worker**
```bash
# Requires NATS to be running
make db-up
uv run python -m crawler.worker
```

### **Multiple Workers (Horizontal Scaling)**
```bash
# Terminal 1
uv run python -m crawler.worker

# Terminal 2
uv run python -m crawler.worker

# Jobs will be distributed across workers automatically
```

## 🐛 Troubleshooting

### **NATS Shows as "Unhealthy"**
```bash
# Check if HTTP monitoring port is configured
docker logs lexicon-nats | grep "http monitor"
# Should see: Starting http monitor on 0.0.0.0:8222

# If not, docker-compose.yml should have:
command: "--jetstream --store_dir /data --http_port 8222"

# Restart NATS
docker-compose down nats && docker-compose up -d nats
```

### **Worker Can't Connect**
```bash
# Verify NATS is running
docker ps | grep nats

# Check connection
curl http://localhost:8222/varz

# Check worker logs for connection errors
uv run python -m crawler.worker
# Look for: "nats_connection_failed"
```

### **Jobs Not Being Processed**
```bash
# Check queue depth
curl http://localhost:8222/jsz | jq '.streams[0].state.messages'

# Check if workers are running
ps aux | grep "crawler.worker"

# Check if stream exists
curl http://localhost:8222/jsz | jq '.streams[].config.name'
# Should include: CRAWLER_TASKS
```

## 🎯 Key Features

### **Work Queue Pattern**
- Messages deleted after acknowledgment
- No redelivery to same consumer
- Max 3 delivery attempts on failure
- Dead letter handling for repeated failures

### **Deduplication**
- 5-minute window
- Based on job_id
- Prevents duplicate job messages

### **Reliability**
- Durable consumers survive restarts
- Ack-wait timeout (5 minutes)
- Automatic redelivery on worker crash
- Max 10 unacked messages per consumer

### **Immediate Cancellation**
- Pending jobs removed from queue
- Workers never see cancelled pending jobs
- Running jobs detect flag during execution
- Zero resource waste for cancelled jobs

## 📈 Monitoring

### **NATS Metrics**
```bash
# Stream status
curl http://localhost:8222/jsz

# Consumer stats
curl http://localhost:8222/jsz?consumers=true

# Server stats
curl http://localhost:8222/varz
```

### **Application Logs**
```json
// Job published
{"event": "job_published_to_queue", "job_id": "...", "sequence": 123}

// Job removed on cancellation
{"event": "job_removed_from_queue", "job_id": "...", "status": "pending"}

// Job not in queue (already picked up)
{"event": "job_not_in_queue_on_cancel", "job_id": "...", "reason": "may_have_been_picked_up"}
```

## ⚙️ Configuration Options

### **Stream Config** (in `nats_queue.py`)
```python
retention=RetentionPolicy.WORK_QUEUE  # Delete after ack
max_age=86400                          # 24 hours max
max_msgs=100000                        # Max 100k pending
duplicate_window=300                   # 5 min dedup
```

### **Consumer Config**
```python
deliver_policy=DeliverPolicy.ALL      # Process all messages
ack_wait=300                          # 5 min timeout
max_deliver=3                         # 3 attempts max
max_ack_pending=10                    # 10 unacked per consumer
```

## 🔐 Production Checklist

- [ ] NATS running with `--http_port 8222`
- [ ] Docker health checks passing
- [ ] Environment variables configured
- [ ] Workers started and consuming
- [ ] Monitoring endpoints accessible
- [ ] Test job creation and cancellation
- [ ] Verify immediate queue removal works
- [ ] Check logs for errors

## 🚨 Known Limitations

1. **Queue removal is best-effort**: If a job is being picked up by a worker at the exact moment of cancellation, the Redis flag will handle it
2. **Worker must implement crawl logic**: Current worker has placeholder for actual crawling
3. **No priority queue yet**: Jobs processed in order received (can be added)
4. **Single stream**: All jobs in one stream (can be split by website/priority)

## 📚 References

- [NATS JetStream Documentation](https://docs.nats.io/jetstream)
- [Python NATS Client](https://github.com/nats-io/nats.py)
- Project README: `README.md`
- Database Schema: `docs/DATABASE_SCHEMA.md`
