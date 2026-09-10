# Corgi Infrastructure

AWS CDK (TypeScript) infrastructure for the Corgi Policy Administration System. Deploys a Django + Next.js application across 6 CloudFormation stacks.

## Architecture Overview

```
                         ┌─────────────────────────────────────────────┐
                         │              Internet / Users               │
                         └────────────────────┬────────────────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │     CloudFront Distribution    │
                              │        (CorgiFrontend)         │
                              │                               │
                              │  WAF ◄── CorgiEdge (us-east-1)│
                              └──┬───────────────┬────────────┘
                                 │               │
                    Static paths │               │ /api/* /admin/* /webhooks/*
                    (default, /) │               │ /health/* /static/*
                                 ▼               ▼
                         ┌──────────┐    ┌──────────────┐
                         │ S3 Bucket│    │     ALB      │
                         │ (frontend│    │  (public,    │
                         │  assets) │    │   HTTP:80)   │
                         └──────────┘    └──────┬───────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │    ECS Fargate Tasks   │
                                    │    (private subnets)   │
                                    │                        │
                                    │  Django + Gunicorn     │
                                    │  Port 8000             │
                                    └───────────┬───────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │      RDS Proxy         │
                                    │   (TLS required)       │
                                    └───────────┬───────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │   RDS PostgreSQL 16    │
                                    │  (isolated subnets)    │
                                    └───────────────────────┘
```

## Stack Breakdown

The infrastructure is split into 6 stacks to isolate concerns and manage dependencies:

```
┌────────────────────────────────────────────────────────────────────┐
│                        Deploy Order                                │
│                                                                    │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │
│  │ 1. Network   │   │ 2. Storage   │   │ 5a. Edge     │          │
│  │ (eu-west-2)  │   │ (eu-west-2)  │   │ (us-east-1)  │          │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘          │
│         │                  │                   │                   │
│         ▼                  │                   │                   │
│  ┌──────────────┐          │                   │                   │
│  │ 3. Database  │          │                   │                   │
│  │ (eu-west-2)  │          │                   │                   │
│  └──────┬───────┘          │                   │                   │
│         │                  │                   │                   │
│         ▼                  ▼                   │                   │
│  ┌─────────────────────────────┐               │                   │
│  │         4. ECS              │               │                   │
│  │       (eu-west-2)           │               │                   │
│  └──────────────┬──────────────┘               │                   │
│                 │                               │                   │
│                 ▼                               ▼                   │
│  ┌─────────────────────────────────────────────────┐               │
│  │              5b. Frontend                        │               │
│  │              (eu-west-2)                         │               │
│  │   consumes ALB from ECS + WAF ARN from Edge     │               │
│  └─────────────────────────────────────────────────┘               │
└────────────────────────────────────────────────────────────────────┘
```

### 1. CorgiNetwork (NetworkStack)

VPC foundation and security group definitions.

| Resource | Details |
|----------|---------|
| VPC | `10.0.0.0/16`, 2 AZs |
| Public subnets | ALB, NAT Gateway |
| Private subnets (egress) | ECS Fargate tasks |
| Isolated subnets | RDS, RDS Proxy |
| NAT Gateways | 1 (cost trade-off for staging) |
| ALB Security Group | Ingress on 80/443 from `allowedIps` |
| ECS Security Group | Ingress on 8000 from ALB SG only |

**VPC Endpoints** (private access to AWS services without NAT):

| Endpoint | Type |
|----------|------|
| S3 | Gateway |
| ECR API | Interface |
| ECR Docker | Interface |
| CloudWatch Logs | Interface |
| Secrets Manager | Interface |
| SSM | Interface |

### 2. CorgiStorage (StorageStack)

Stateful S3 storage for policy documents (PDFs).

| Resource | Details |
|----------|---------|
| Documents Bucket | Private, SSE-S3 encrypted, versioned |
| Removal Policy | RETAIN (survives stack deletion) |
| SSL | Enforced (deny non-HTTPS) |

Documents are stored at `policies/{policy_id}/{type}/{timestamp}.pdf` and served via presigned URLs.

### 3. CorgiDatabase (DatabaseStack)

PostgreSQL database with connection pooling.

| Resource | Details |
|----------|---------|
| RDS Instance | PostgreSQL 16.4, encrypted at rest |
| RDS Proxy | Connection pooling, TLS required |
| Credentials | Auto-generated in Secrets Manager (`corgi/database`) |
| Subnets | Isolated (no internet access) |
| Backup | 7-day retention, snapshot on delete |

**Security group chain:**
```
ECS Tasks ──► RDS Proxy (port 5432) ──► RDS Instance (port 5432)
```

### 4. CorgiEcs (EcsStack)

Django backend compute, load balancing, secrets, and container registry.

| Resource | Details |
|----------|---------|
| ECS Cluster | Fargate, Container Insights enabled |
| Fargate Service | Private subnets, circuit breaker + rollback |
| ALB | Internet-facing, public subnets |
| ECR Repository | `corgi-backend`, scan on push |
| App Secrets | Secrets Manager (`corgi/app`) |
| Log Group | `/ecs/corgi-backend`, 2-week retention |
| Migration Task | Separate task definition for `manage.py migrate` |

**Secrets injected from Secrets Manager:**

| Secret | Source |
|--------|--------|
| `DB_USER`, `DB_PASSWORD` | `corgi/database` |
| `DJANGO_SECRET_KEY` | `corgi/app` |
| `DJANGO_SUPERUSER_*` | `corgi/app` |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` | `corgi/app` |
| `PERSONA_API_KEY`, `PERSONA_WEBHOOK_SECRET`, `PERSONA_TEMPLATE_ID` | `corgi/app` |

**Environment variables (non-sensitive):**

| Variable | Value |
|----------|-------|
| `DB_HOST` | RDS Proxy endpoint |
| `DB_SSLMODE` | `require` |
| `DOCUMENTS_BUCKET_NAME` | From StorageStack |
| `FRONTEND_URL_SSM_PARAM` | `/corgi/frontend-url` |
| `DJANGO_ALLOWED_HOSTS` | ALB DNS + optional custom domains |

**IAM permissions granted to task role:**
- Read `corgi/database` and `corgi/app` secrets
- Read/write documents S3 bucket
- Read SSM parameter `/corgi/frontend-url`

### 5a. CorgiEdge (EdgeStack)

WAF Web ACL for CloudFront. Deployed to **us-east-1** because AWS requires CLOUDFRONT-scoped WAF resources in that region.

| Resource | Details |
|----------|---------|
| WAF WebACL | CLOUDFRONT scope |
| Rule: CommonRuleSet | AWS managed, `SizeRestrictions_BODY` excluded |
| Rule: RateLimit | 2000 requests/5min per IP |

The WAF ARN is consumed cross-region by FrontendStack via CDK's `crossRegionReferences`.

### 5b. CorgiFrontend (FrontendStack)

Static frontend hosting and CDN with path-based routing.

| Resource | Details |
|----------|---------|
| S3 Bucket | Private, OAC access only, versioned |
| CloudFront | HTTPS redirect, OAC for S3 |
| SSM Parameter | `/corgi/frontend-url` (resolved CloudFront or custom domain URL) |

**CloudFront path routing:**

| Path | Origin | Cache | Methods |
|------|--------|-------|---------|
| `/*` (default) | S3 | Optimized | GET, HEAD |
| `/api/*` | ALB | Disabled | ALL |
| `/admin/*` | ALB | Disabled | ALL |
| `/webhooks/*` | ALB | Disabled | ALL |
| `/health/*` | ALB | Disabled | GET, HEAD |
| `/static/*` | ALB | Optimized | GET, HEAD |

**SPA routing:** 404 and 403 errors return `/index.html` (client-side routing).

**Custom domain (optional):** When `webDomainName`, `hostedZoneId`, `hostedZoneName`, and `certificateArn` are configured, CloudFront uses the custom domain with TLS and creates a Route 53 alias record.

## Network Diagram

```
┌─────────────────────────── VPC 10.0.0.0/16 ───────────────────────────┐
│                                                                        │
│  ┌─────────── Public Subnets ──────────┐                               │
│  │                                     │                               │
│  │  ┌─────────┐     ┌──────────────┐   │                               │
│  │  │   NAT   │     │     ALB      │   │                               │
│  │  │ Gateway │     │ (internet-   │   │                               │
│  │  │         │     │  facing)     │   │                               │
│  │  └────┬────┘     └──────┬───────┘   │                               │
│  └───────┼─────────────────┼───────────┘                               │
│          │                 │                                            │
│  ┌───────┼─── Private Subnets (egress) ┐                               │
│  │       │                 │            │   ┌────────────────────────┐  │
│  │       │    ┌────────────┴──────┐     │   │   VPC Endpoints       │  │
│  │       │    │  ECS Fargate      │     │   │                        │  │
│  │       │    │  Tasks            │─────┼──►│  S3 (Gateway)          │  │
│  │       │    │  (Django/Gunicorn)│     │   │  ECR, ECR Docker       │  │
│  │       │    └────────────┬──────┘     │   │  CloudWatch Logs       │  │
│  └───────┼─────────────────┼────────────┘   │  Secrets Manager       │  │
│          │                 │                 │  SSM                   │  │
│  ┌───────┼─── Isolated Subnets ─────────┐   └────────────────────────┘  │
│  │       │                 │            │                               │
│  │            ┌────────────┴──────┐     │                               │
│  │            │    RDS Proxy      │     │                               │
│  │            │    (TLS required) │     │                               │
│  │            └────────────┬──────┘     │                               │
│  │                         │            │                               │
│  │            ┌────────────┴──────┐     │                               │
│  │            │  RDS PostgreSQL   │     │                               │
│  │            │  (encrypted)      │     │                               │
│  │            └───────────────────┘     │                               │
│  └──────────────────────────────────────┘                               │
└────────────────────────────────────────────────────────────────────────┘
```

## Security Model

```
┌──────────┐    HTTPS     ┌────────────┐    HTTP     ┌─────────┐   TLS    ┌───────────┐   TLS   ┌─────┐
│  Browser ├─────────────►│ CloudFront ├────────────►│   ALB   ├────────►│ ECS Tasks ├───────►│ RDS │
│          │              │  + WAF     │             │         │  :8000  │ (Django)  │  :5432 │Proxy│
└──────────┘              └────────────┘             └─────────┘         └───────────┘        └──┬──┘
                               │                         ▲                     │                 │
                               │                    allowedIps            Secrets Mgr         ┌──┴──┐
                               │                    ingress only          SSM, S3             │ RDS │
                               ▼                                                              └─────┘
                          ┌─────────┐
                          │   S3    │
                          │(frontend│
                          │  + docs)│
                          └─────────┘
```

**Key security controls:**
- All traffic HTTPS (CloudFront redirects HTTP)
- WAF with AWS managed rules + rate limiting
- ALB ingress restricted to `allowedIps` (configurable)
- ECS tasks in private subnets (no public IP)
- RDS in isolated subnets (no internet route)
- RDS Proxy enforces TLS (`DB_SSLMODE=require`)
- Secrets in Secrets Manager (never in env vars or config files)
- S3 buckets private, encrypted, SSL-enforced
- VPC endpoints avoid traffic leaving VPC for AWS service calls

## SSM Parameter Bridge

CloudFront's URL isn't known until FrontendStack deploys, but EcsStack deploys first (FrontendStack depends on the ALB). This creates a circular dependency.

**Solution:** FrontendStack writes the resolved URL to SSM parameter `/corgi/frontend-url`. The Django container's `entrypoint.sh` reads it at boot time via boto3 and sets `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, and appends to `DJANGO_ALLOWED_HOSTS`.

```
Deploy time:
  EcsStack ──► FrontendStack ──► SSM: /corgi/frontend-url

Runtime (container boot):
  entrypoint.sh ──► SSM GetParameter ──► export FRONTEND_URL, CORS, CSRF
```

On first deploy, the SSM parameter doesn't exist yet (FrontendStack hasn't run). The entrypoint handles this gracefully — CORS/CSRF won't work until FrontendStack deploys and ECS tasks restart, but the container starts successfully.

## Configuration

### config.yaml

Per-environment settings in `infra/config.yaml`:

```yaml
environments:
  staging:
    project: corgi-demo
    owner: corgi-demo-app
    webDomainName: ""          # Optional custom domain
    serverDomainName: ""       # Optional API domain
    hostedZoneId: ""           # Route 53 hosted zone
    hostedZoneName: ""         # Zone name
    certificateArn: ""         # ACM cert (must be us-east-1 for CloudFront)
    allowedIps:
      - 0.0.0.0/0             # Restrict in production
    cpu: 256
    memory: 512
    desiredCount: 1
    dbInstanceType: t4g.micro
    dbMultiAz: false
    dbAllocatedStorage: 20
```

### Environment Variables

Set these before running `cdk deploy`:

| Variable | Purpose | Required |
|----------|---------|----------|
| `CDK_DEFAULT_ACCOUNT` or `AWS_ACCOUNT_ID` | AWS account ID | Yes |
| `CDK_DEFAULT_REGION` or `AWS_REGION` | Primary region (e.g. `eu-west-2`) | Yes |

The EdgeStack always deploys to us-east-1 regardless of the primary region.

### Stage Selection

```bash
cdk deploy --context stage=staging   # default
cdk deploy --context stage=production
```

## Deployment

### Prerequisites

- Node.js 18+
- AWS CDK CLI: `npm install -g aws-cdk`
- AWS credentials configured with sufficient permissions
- Docker (for building the backend image)

### First Deployment

```bash
# 1. Install dependencies
cd infra && npm install

# 2. Bootstrap CDK in both regions
cdk bootstrap aws://ACCOUNT_ID/eu-west-2
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# 3. Deploy all stacks
cdk deploy --all

# 4. Update secrets in AWS Console
#    Secrets Manager → corgi/app → edit DJANGO_SECRET_KEY, passwords, API keys

# 5. Build and push the backend image
aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.eu-west-2.amazonaws.com
docker build -t corgi-backend ./backend
docker tag corgi-backend:latest ACCOUNT_ID.dkr.ecr.eu-west-2.amazonaws.com/corgi-backend:latest
docker push ACCOUNT_ID.dkr.ecr.eu-west-2.amazonaws.com/corgi-backend:latest

# 6. Run database migrations
aws ecs run-task \
  --cluster corgi-cluster \
  --task-definition $(cdk output CorgiEcs.MigrationTaskDefArn) \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET_IDS],securityGroups=[SG_ID],assignPublicIp=DISABLED}"

# 7. Deploy frontend assets
cd frontend && npm run build
aws s3 sync out/ s3://$(cdk output CorgiFrontend.FrontendBucketName)/ --delete
aws cloudfront create-invalidation --distribution-id $(cdk output CorgiFrontend.DistributionId) --paths "/*"
```

### Running Migrations

The ECS stack outputs everything needed for `aws ecs run-task`:

| Output | Purpose |
|--------|---------|
| `MigrationTaskDefArn` | Task definition ARN |
| `PrivateSubnetIds` | Subnet IDs (comma-separated) |
| `EcsSecurityGroupId` | Security group for the task |

### Stack Outputs

| Stack | Output | Description |
|-------|--------|-------------|
| CorgiNetwork | `VpcId` | VPC identifier |
| CorgiStorage | `DocumentsBucketName`, `DocumentsBucketArn` | Policy documents bucket |
| CorgiDatabase | `RdsProxyEndpoint` | Database connection endpoint |
| CorgiEcs | `AlbDnsName` | ALB public DNS |
| CorgiEcs | `EcrRepoUri` | ECR repository URI for docker push |
| CorgiEcs | `ClusterName` | ECS cluster name |
| CorgiEcs | `MigrationTaskDefArn` | Migration task definition |
| CorgiEcs | `PrivateSubnetIds` | Subnets for run-task |
| CorgiEcs | `EcsSecurityGroupId` | SG for run-task |
| CorgiEdge | `WebAclArn` | WAF ACL ARN |
| CorgiFrontend | `CloudFrontUrl` | Distribution URL |
| CorgiFrontend | `FrontendBucketName` | S3 bucket for frontend assets |
| CorgiFrontend | `DistributionId` | CloudFront distribution ID |

## Development

```bash
cd infra

npm run build       # Compile TypeScript
npm run test        # Run Jest tests (18 tests)
npx tsc --noEmit    # Type-check without emitting
npx cdk synth       # Synthesize CloudFormation templates
npx cdk diff        # Compare with deployed state
```

### Tests

18 unit tests validate resource creation across all stacks:

- NetworkStack: VPC, NAT gateway, VPC endpoints
- StorageStack: Private bucket with versioning
- DatabaseStack: RDS instance, proxy, secrets, instance type
- EcsStack: Cluster, Fargate service, ECR, ALB, secrets, Route 53
- EdgeStack: CLOUDFRONT-scoped WAF
- FrontendStack: S3 bucket, CloudFront distribution, Route 53
