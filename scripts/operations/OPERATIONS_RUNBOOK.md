# Lighthouse Bridge Operations Runbook

## Overview

This runbook provides operational procedures for managing the Lighthouse Bridge containerized deployment in production environments.

## Quick Reference

### Emergency Contacts
- **DevOps Team**: devops@lighthouse.dev
- **On-Call Engineer**: oncall@lighthouse.dev
- **Escalation**: engineering@lighthouse.dev

### Critical URLs
- **Production Bridge**: https://bridge.lighthouse.prod
- **Staging Bridge**: https://bridge.lighthouse.staging
- **Monitoring Dashboard**: https://grafana.lighthouse.prod/d/lighthouse-bridge-overview
- **Log Aggregation**: https://logs.lighthouse.prod
- **Incident Management**: https://incidents.lighthouse.prod

## Service Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Load      │    │   Bridge    │    │   Storage   │
│   Balancer  │────│   Container │────│   Layer     │
│             │    │             │    │             │
│ - nginx     │    │ - Python    │    │ - Redis     │
│ - SSL term  │    │ - FastAPI   │    │ - PostgreSQL│
│ - Rate limit│    │ - FUSE      │    │ - Volumes   │
└─────────────┘    └─────────────┘    └─────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Monitoring  │    │   Expert    │    │   Backup    │
│             │    │   Agents    │    │   System    │
│ - Prometheus│    │             │    │             │
│ - Grafana   │    │ - Security  │    │ - S3/GCS    │
│ - Jaeger    │    │ - Perf      │    │ - Automated │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Standard Operating Procedures

### 1. Service Start/Stop/Restart

#### Starting the Service
```bash
# Production deployment
cd /opt/lighthouse
./scripts/deployment/deploy.sh production

# Or manually with Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# Verify startup
./scripts/operations/health-check.sh
```

#### Stopping the Service
```bash
# Graceful shutdown
docker-compose -f docker-compose.prod.yml down

# Force stop (emergency only)
docker-compose -f docker-compose.prod.yml down --timeout 30
```

#### Restarting the Service
```bash
# Rolling restart (zero downtime)
docker-compose -f docker-compose.prod.yml up -d --force-recreate lighthouse-bridge

# Full restart
docker-compose -f docker-compose.prod.yml restart
```

### 2. Health Monitoring

#### Manual Health Check
```bash
# Comprehensive check
./scripts/operations/health-check.sh --verbose

# JSON output for automation
./scripts/operations/health-check.sh --json

# Quick connectivity test
curl -f http://localhost:8765/health
```

#### Automated Monitoring
- **Prometheus**: Metrics collection every 15 seconds
- **Grafana**: Real-time dashboards and alerting
- **Health Checks**: Container-level health probes
- **Log Monitoring**: ELK stack for log analysis

### 3. Performance Monitoring

#### Key Metrics to Monitor
| Metric | Normal Range | Alert Threshold | Critical Threshold |
|--------|--------------|-----------------|-------------------|
| Memory Usage | < 70% | > 85% | > 95% |
| CPU Usage | < 60% | > 80% | > 95% |
| P95 Latency | < 100ms | > 500ms | > 1000ms |
| Error Rate | < 0.1% | > 1% | > 5% |
| Cache Hit Rate | > 80% | < 60% | < 40% |

#### Performance Tuning
```bash
# Check current resource usage
docker stats lighthouse-bridge

# Adjust memory limits
docker-compose -f docker-compose.prod.yml up -d --scale lighthouse-bridge=2

# Monitor performance impact
./scripts/operations/performance-monitor.sh
```

### 4. Log Management

#### Accessing Logs
```bash
# Real-time logs
docker-compose logs -f lighthouse-bridge

# Specific time range
docker-compose logs --since="2024-01-01T10:00:00" lighthouse-bridge

# Search for errors
docker-compose logs lighthouse-bridge | grep ERROR

# Export logs for analysis
docker-compose logs --no-color lighthouse-bridge > bridge-logs.txt
```

#### Log Locations
- **Container Logs**: `/app/logs/bridge.log`
- **System Logs**: `/var/log/lighthouse/`
- **Audit Logs**: `/app/data/events/audit.log`
- **Performance Logs**: `/app/logs/performance.log`

### 5. Database Operations

#### PostgreSQL Management
```bash
# Connect to database
docker-compose exec postgres psql -U lighthouse -d lighthouse

# Backup database
docker-compose exec postgres pg_dump -U lighthouse lighthouse > backup.sql

# Restore database
docker-compose exec -T postgres psql -U lighthouse lighthouse < backup.sql

# Check database status
docker-compose exec postgres pg_isready -U lighthouse
```

#### Redis Management
```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Check Redis status
docker-compose exec redis redis-cli ping

# Monitor Redis
docker-compose exec redis redis-cli monitor

# Flush cache (emergency only)
docker-compose exec redis redis-cli flushall
```

## Incident Response Procedures

### 1. Service Unavailable (HTTP 503)

#### Immediate Actions
1. Check service status: `docker-compose ps`
2. Review recent logs: `docker-compose logs --tail=100 lighthouse-bridge`
3. Check resource usage: `docker stats lighthouse-bridge`
4. Verify dependencies: `./scripts/operations/health-check.sh`

#### Escalation Criteria
- Service down > 5 minutes
- Memory usage > 95%
- Error rate > 10%
- Dependencies unavailable

#### Recovery Steps
```bash
# 1. Quick restart
docker-compose restart lighthouse-bridge

# 2. If restart fails, check dependencies
docker-compose ps redis postgres

# 3. Full service restart
docker-compose down && docker-compose up -d

# 4. If still failing, rollback to previous version
./scripts/deployment/rollback.sh
```

### 2. High Memory Usage

#### Investigation
```bash
# Check memory metrics
curl -s http://localhost:9090/metrics | grep lighthouse_bridge_memory

# Analyze heap dump (if enabled)
docker-compose exec lighthouse-bridge python -m memory_profiler

# Check for memory leaks
docker-compose exec lighthouse-bridge ps aux | grep python
```

#### Mitigation
```bash
# Temporary: Restart service
docker-compose restart lighthouse-bridge

# Permanent: Increase memory limits
# Edit docker-compose.yml memory limits
docker-compose up -d --force-recreate lighthouse-bridge
```

### 3. FUSE Mount Failures

#### Symptoms
- Error: "FUSE filesystem not available"
- Degraded performance
- Expert agents cannot access shadow filesystem

#### Recovery
```bash
# Check FUSE status
docker-compose exec lighthouse-bridge mount | grep fuse

# Restart with FUSE debugging
docker-compose exec lighthouse-bridge \
  fusermount -u /mnt/lighthouse/project || true
docker-compose restart lighthouse-bridge

# If persistent, check container capabilities
docker inspect lighthouse-bridge | grep -A 10 CapAdd
```

### 4. Database Connection Issues

#### PostgreSQL Issues
```bash
# Check connection
docker-compose exec lighthouse-bridge \
  python -c "import psycopg2; psycopg2.connect('$POSTGRES_URL')"

# Check PostgreSQL logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

#### Redis Issues
```bash
# Check Redis connectivity
docker-compose exec lighthouse-bridge \
  python -c "import redis; redis.from_url('$REDIS_URL').ping()"

# Clear Redis if corrupted
docker-compose exec redis redis-cli flushall

# Restart Redis
docker-compose restart redis
```

## Maintenance Procedures

### 1. Routine Maintenance

#### Daily Tasks
- [ ] Check health dashboard
- [ ] Review error rates in logs
- [ ] Monitor resource usage trends
- [ ] Verify backup completion

#### Weekly Tasks
- [ ] Update container images
- [ ] Clean up old logs and data
- [ ] Review performance metrics
- [ ] Test disaster recovery procedures

#### Monthly Tasks
- [ ] Security vulnerability scans
- [ ] Performance optimization review
- [ ] Capacity planning assessment
- [ ] Documentation updates

### 2. Updates and Deployments

#### Pre-Deployment Checklist
- [ ] Review change log
- [ ] Backup current configuration
- [ ] Test in staging environment
- [ ] Schedule maintenance window
- [ ] Notify stakeholders

#### Deployment Process
```bash
# 1. Deploy to staging
./scripts/deployment/deploy.sh staging v1.2.3

# 2. Run smoke tests
./scripts/testing/smoke-tests.sh staging

# 3. Deploy to production
./scripts/deployment/deploy.sh production v1.2.3

# 4. Monitor for issues
watch ./scripts/operations/health-check.sh
```

#### Rollback Process
```bash
# Quick rollback to previous version
./scripts/deployment/rollback.sh

# Manual rollback
docker tag lighthouse-bridge:previous lighthouse-bridge:latest
docker-compose up -d --force-recreate lighthouse-bridge
```

### 3. Backup and Recovery

#### Backup Procedures
```bash
# Full system backup
./scripts/operations/backup.sh full

# Configuration backup
./scripts/operations/backup.sh config

# Data-only backup
./scripts/operations/backup.sh data
```

#### Recovery Procedures
```bash
# Restore from backup
./scripts/operations/restore.sh /path/to/backup.tar.gz

# Verify restoration
./scripts/operations/health-check.sh --verbose
```

## Troubleshooting Guide

### Common Issues

#### Issue: Container Won't Start
**Symptoms**: Docker container exits immediately
**Cause**: Configuration error, missing dependencies
**Solution**:
```bash
# Check container logs
docker-compose logs lighthouse-bridge

# Validate configuration
docker-compose config

# Start in debug mode
docker-compose up lighthouse-bridge
```

#### Issue: High CPU Usage
**Symptoms**: CPU consistently above 80%
**Cause**: Infinite loops, inefficient algorithms, high load
**Solution**:
```bash
# Profile CPU usage
docker-compose exec lighthouse-bridge py-spy top -p 1

# Check for busy loops
docker-compose exec lighthouse-bridge strace -p 1

# Scale horizontally if needed
docker-compose up -d --scale lighthouse-bridge=3
```

#### Issue: Slow Response Times
**Symptoms**: P95 latency > 1 second
**Cause**: Database bottlenecks, cache misses, network issues
**Solution**:
```bash
# Check database performance
docker-compose exec postgres pg_stat_activity

# Analyze slow queries
docker-compose logs postgres | grep "slow query"

# Check cache hit rates
curl -s http://localhost:9090/metrics | grep cache_hit_rate
```

### Performance Optimization

#### Memory Optimization
```bash
# Tune garbage collection
export PYTHONOPTIMIZE=1
export PYTHONDONTWRITEBYTECODE=1

# Adjust Python memory settings
export PYTHONMALLOC=malloc
export MALLOC_ARENA_MAX=2
```

#### Database Optimization
```sql
-- PostgreSQL tuning
ANALYZE;
VACUUM;
REINDEX SCHEMA public;

-- Check for unused indexes
SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch 
FROM pg_stat_user_indexes 
WHERE idx_tup_read = 0;
```

## Security Procedures

### 1. Security Monitoring
- Monitor failed authentication attempts
- Check for suspicious API usage patterns
- Review security audit logs
- Scan for vulnerabilities in dependencies

### 2. Incident Response
```bash
# Security incident detected
# 1. Isolate affected systems
docker-compose stop lighthouse-bridge

# 2. Preserve evidence
docker-compose logs --no-color lighthouse-bridge > incident-logs.txt

# 3. Notify security team
./scripts/operations/security-alert.sh "Security incident detected"

# 4. Follow security playbook
./scripts/security/incident-response.sh
```

## Contact Information

### Escalation Matrix
1. **Level 1**: DevOps Engineer (Response: 15 minutes)
2. **Level 2**: Senior DevOps Engineer (Response: 30 minutes)
3. **Level 3**: Engineering Manager (Response: 1 hour)
4. **Level 4**: CTO (Response: 2 hours)

### External Vendors
- **Cloud Provider**: AWS Support
- **Monitoring**: DataDog Support
- **Security**: Security vendor support

---

**Document Version**: 1.0  
**Last Updated**: 2025-08-26  
**Next Review**: 2025-09-26  
**Owner**: DevOps Team