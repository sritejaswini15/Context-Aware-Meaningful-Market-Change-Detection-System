# Deployment (AWS)

Everything is defined in `infra/terraform`. You provide AWS credentials, a few
variables and API keys. No application code changes are needed.

## What gets created

| Module | Resources |
|---|---|
| `network` | VPC (2 AZs), public and private subnets, NAT gateway, security groups (ALB → app → data) |
| `database` | RDS PostgreSQL 17 (encrypted, private, 7-day backups, master password managed in Secrets Manager) |
| `redis` | ElastiCache Redis 7 (TLS, private) |
| `queue` | SQS `jobs` + DLQ (5 receives), EventBridge Scheduler schedules → SQS |
| `cognito` | User pool (email sign-in, verified email) + public app client (USER_PASSWORD_AUTH, refresh) |
| `storage` | S3 bucket for ALB access logs (encrypted, private, 90-day expiry) |
| root | Secrets Manager secret `<name>/app` (JWT secret, Finnhub/AI keys, Sentry DSN) |
| `ecs` | ECR repos, ECS cluster (Container Insights), Fargate services `api`, `worker`, `web`, ALB (`/api/*` → API), CPU autoscaling, circuit-breaker rollback, CloudWatch log groups |
| `monitoring` | SNS alarm topic (+ email), alarms: API 5xx, p95 latency, DLQ, RDS CPU and storage, market-data outage, AI failures |

## First deployment

1. **Prerequisites**: Terraform ≥ 1.6, AWS CLI, Docker. An ACM certificate for your domain in the same region (recommended).
2. **Configure**
   ```bash
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars
   # edit: region, domain_name, certificate_arn, market_providers, ai_provider, alarm_email
   ```
   For remote state, create an S3 bucket and uncomment the `backend "s3"` block in `main.tf`.
3. **Provision**
   ```bash
   terraform init
   terraform apply
   ```
4. **Add secrets.** Set the real values in the `knoww-<env>/app` secret:
   ```bash
   aws secretsmanager put-secret-value --secret-id knoww-prod/app --secret-string \
     '{"jwt_secret":"<keep the generated one>","finnhub_api_key":"…","ai_api_key":"…","sentry_dsn":""}'
   ```
5. **Build and ship.** Either run the GitHub Actions **Deploy** workflow (below), or by hand:
   ```bash
   REG=$(terraform output -raw ecr_api_repository | cut -d/ -f1)
   aws ecr get-login-password | docker login --username AWS --password-stdin $REG
   docker build -t $(terraform output -raw ecr_api_repository):latest ../../backend && docker push $(terraform output -raw ecr_api_repository):latest
   docker build -t $(terraform output -raw ecr_web_repository):latest ../../frontend && docker push $(terraform output -raw ecr_web_repository):latest
   ```
6. **Migrate**: run a one-off task with the API task definition and command `["migrate"]` (the Deploy workflow does this).
7. **Roll out**: `aws ecs update-service --cluster knoww-prod --service <api|worker|web> --force-new-deployment`.
8. Point your DNS (`domain_name`) at the ALB (`terraform output alb_dns_name`).

## GitHub Actions

- `ci.yml` (every push and PR): backend tests, Alembic up/down/up on PostgreSQL, frontend typecheck and build, docker-compose E2E with Playwright, `terraform fmt` and `validate`.
- `deploy.yml` (manual, `production` environment for approvals): GitHub OIDC → assume `AWS_DEPLOY_ROLE_ARN` → build and push both images (`:sha` and `:latest`) → migration task → force new deployments → wait for stable services.

The deploy role needs `ecr:*` push actions on the two repositories, `ecs:RunTask`, `ecs:DescribeTasks`,
`ecs:UpdateService`, `ecs:DescribeServices`, `ec2:Describe*`, and `iam:PassRole` on the two ECS task roles.

## Configuration in AWS

ECS injects plain configuration (Cognito IDs, DB host, Redis URL, queue URL, provider
chain) as environment variables, and secrets from Secrets Manager: the DB password
from the RDS-managed secret, and the API keys from `<name>/app`. `AUTH_MODE=cognito`,
`QUEUE_BACKEND=sqs`, `SCHEDULER_MODE=eventbridge`.

**Demo on AWS:** set `market_providers = "mock,mock-reference"` and `demo_mode = true`, and
`market_refresh_expression` stays `rate(1 minute)`. With Finnhub you may prefer to refresh
only around US trading hours, for example `cron(* 13-21 ? * MON-FRI *)` (UTC), because the free plan allows 60 calls per minute.

## Rough monthly cost (ap-south-1, smallest sizes)

NAT gateway ≈ $35, ALB ≈ $20, RDS t4g.micro ≈ $15, ElastiCache t4g.micro ≈ $12,
Fargate (2 API + 1 worker + 2 web, small tasks) ≈ $45, plus CloudWatch, SQS, Secrets
Manager and Cognito (low at small scale). About **$130/month**. Scale out with
`db_multi_az`, larger instance classes and higher autoscaling limits.

## Operations

- **Logs**: CloudWatch `/knoww/<name>/{api,worker,web}`, structured JSON. Example Logs Insights query: `fields @timestamp, event, symbol, error | filter event like /market\./ | sort @timestamp desc`.
- **Alarms** go to the SNS topic (confirm the email subscription).
- **Dead letters**: inspect the `-jobs-dlq` queue; jobs are idempotent and safe to redrive.
- **Rollback**: ECS circuit breaker rolls back failed deployments automatically. For a manual rollback, redeploy a previous `:sha` image.
