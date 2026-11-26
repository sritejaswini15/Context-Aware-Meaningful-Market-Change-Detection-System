variable "name" { type = string }
variable "market_refresh_expression" {
  type        = string
  description = "EventBridge Scheduler expression for market ingestion"
  default     = "rate(1 minute)"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-jobs-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${var.name}-jobs"
  visibility_timeout_seconds = 180
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

# --- EventBridge Scheduler -> SQS (workers do the processing) -----------------
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.jobs.arn }]
  })
}

locals {
  schedules = {
    "market-refresh" = { expression = var.market_refresh_expression, timezone = "UTC", job = "market.refresh" }
    "health-check"   = { expression = "rate(2 minutes)", timezone = "UTC", job = "system.health_check" }
    "events-refresh" = { expression = "rate(30 minutes)", timezone = "UTC", job = "events.refresh" }
    "market-daily"   = { expression = "cron(30 16 ? * MON-FRI *)", timezone = "America/New_York", job = "market.daily" }
    "cleanup"        = { expression = "cron(0 3 * * ? *)", timezone = "UTC", job = "maintenance.cleanup" }
  }
}

resource "aws_scheduler_schedule" "this" {
  for_each                     = local.schedules
  name                         = "${var.name}-${each.key}"
  schedule_expression          = each.value.expression
  schedule_expression_timezone = each.value.timezone
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_sqs_queue.jobs.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ type = each.value.job, payload = {} })
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 300
    }
  }
}

output "queue_url" { value = aws_sqs_queue.jobs.url }
output "queue_arn" { value = aws_sqs_queue.jobs.arn }
output "dlq_name" { value = aws_sqs_queue.dlq.name }
output "dlq_arn" { value = aws_sqs_queue.dlq.arn }
