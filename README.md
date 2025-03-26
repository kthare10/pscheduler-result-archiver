# pScheduler Result Archiver

A lightweight Django + Redis application for storing, browsing, and viewing perfSONAR pScheduler test results via API and web interface.

## Features

- Receive and store JSON-formatted pScheduler test results via REST API
- Archive results using timestamp-based keys in Redis
- Simple web GUI to list and view entries
- Dockerized setup with Redis and Django app
- Optional auto-push client script to send results right after tests

## API

### POST `/api/save/`

Send a result:

```json
{
  "timestamp_utc": "20250326-143000Z",
  "category": "latency",
  "filename": "example.json",
  "content": {
    "rtt": "10ms",
    "loss": "0%"
  }
}

### GET `/`
List all entries

### GET `/view/<timestamp>/`
View a single entry


## Quick Start (Docker Compose)
```
git clone https://github.com/your-username/pscheduler-result-archiver.git
cd pscheduler-result-archiver
docker-compose up --build
```

Visit: http://localhost:8000

## License
MIT License
