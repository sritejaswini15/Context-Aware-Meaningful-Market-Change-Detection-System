terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # Recommended: remote state. Create the bucket once, then uncomment.
  # backend "s3" {
  #   bucket       = "your-terraform-state-bucket"
  #   key          = "knoww/terraform.tfstate"
  #   region       = "ap-south-1"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "knoww", Environment = var.environment, ManagedBy = "terraform" }
  }
}

locals {
  name = "knoww-${var.environment}"
}

module "network" {
  source = "./modules/network"
  name   = local.name
}

module "database" {
  source              = "./modules/database"
  name                = local.name
  subnet_ids          = module.network.private_subnet_ids
  security_group_id   = module.network.data_security_group_id
  instance_class      = var.db_instance_class
  multi_az            = var.db_multi_az
  deletion_protection = var.deletion_protection
}

module "redis" {
  source            = "./modules/redis"
  name              = local.name
  subnet_ids        = module.network.private_subnet_ids
  security_group_id = module.network.data_security_group_id
}

module "queue" {
  source                    = "./modules/queue"
  name                      = local.name
  market_refresh_expression = var.market_refresh_expression
}

module "cognito" {
  source = "./modules/cognito"
  name   = local.name
}

module "storage" {
  source = "./modules/storage"
  name   = local.name
}

# Application secrets. Terraform creates the container with a generated JWT
# secret and empty API keys; set real keys in the console or CLI afterwards.
# Values are never stored in Git.
resource "random_password" "jwt" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    jwt_secret      = random_password.jwt.result
    finnhub_api_key = ""
    ai_api_key      = ""
    sentry_dsn      = ""
  })
  lifecycle { ignore_changes = [secret_string] }
}

locals {
  app_url    = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.ecs.alb_dns_name}"
  app_secret = aws_secretsmanager_secret.app.arn
}

module "ecs" {
  source                = "./modules/ecs"
  name                  = local.name
  region                = var.region
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  app_security_group_id = module.network.app_security_group_id
  certificate_arn       = var.certificate_arn
  logs_bucket           = module.storage.logs_bucket
  image_tag             = var.image_tag
  queue_arn             = module.queue.queue_arn
  secret_arns           = [aws_secretsmanager_secret.app.arn, module.database.master_user_secret_arn]
  environment = {
    APP_ENV              = "production"
    LOG_JSON             = "true"
    AUTH_MODE            = "cognito"
    COGNITO_REGION       = var.region
    COGNITO_USER_POOL_ID = module.cognito.user_pool_id
    COGNITO_CLIENT_ID    = module.cognito.client_id
    COOKIE_SECURE        = var.certificate_arn != "" ? "true" : "false"
    # Same-origin behind the ALB, so no cross-origin access is granted by default.
    CORS_ORIGINS     = var.domain_name != "" ? "https://${var.domain_name}" : ""
    DB_HOST          = module.database.address
    DB_PORT          = tostring(module.database.port)
    DB_NAME          = "knoww"
    DB_USER          = "knoww"
    REDIS_URL        = module.redis.url
    QUEUE_BACKEND    = "sqs"
    SQS_QUEUE_URL    = module.queue.queue_url
    AWS_REGION       = var.region
    SCHEDULER_MODE   = "eventbridge"
    MARKET_PROVIDERS = var.market_providers
    AI_PROVIDER      = var.ai_provider
    AI_MODEL         = var.ai_model
    DEMO_MODE        = var.demo_mode ? "true" : "false"
    RUN_MIGRATIONS   = "false"
  }
  secrets = {
    DB_PASSWORD     = "${module.database.master_user_secret_arn}:password::"
    JWT_SECRET      = "${local.app_secret}:jwt_secret::"
    FINNHUB_API_KEY = "${local.app_secret}:finnhub_api_key::"
    AI_API_KEY      = "${local.app_secret}:ai_api_key::"
    SENTRY_DSN      = "${local.app_secret}:sentry_dsn::"
  }
}

module "monitoring" {
  source                      = "./modules/monitoring"
  name                        = local.name
  alarm_email                 = var.alarm_email
  alb_arn_suffix              = module.ecs.alb_arn_suffix
  api_target_group_arn_suffix = module.ecs.api_target_group_arn_suffix
  dlq_name                    = module.queue.dlq_name
  db_identifier               = module.database.identifier
  cluster_name                = module.ecs.cluster_name
  api_log_group               = module.ecs.log_groups["api"]
  worker_log_group            = module.ecs.log_groups["worker"]
}
