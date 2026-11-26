variable "name" { type = string }
variable "alarm_email" {
  type    = string
  default = ""
}
variable "alb_arn_suffix" { type = string }
variable "api_target_group_arn_suffix" { type = string }
variable "dlq_name" { type = string }
variable "db_identifier" { type = string }
variable "cluster_name" { type = string }
variable "api_log_group" { type = string }
variable "worker_log_group" { type = string }

resource "aws_sns_topic" "alarms" { name = "${var.name}-alarms" }

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarms = {
    "api-5xx" = {
      namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", stat = "Sum", threshold = 10, period = 300, op = "GreaterThanThreshold"
      dims      = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.api_target_group_arn_suffix }
      desc      = "API is returning server errors"
    }
    "api-latency-p95" = {
      namespace = "AWS/ApplicationELB", metric = "TargetResponseTime", stat = "p95", threshold = 2, period = 300, op = "GreaterThanThreshold"
      dims      = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.api_target_group_arn_suffix }
      desc      = "API p95 latency above 2s"
    }
    "jobs-dead-lettered" = {
      namespace = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", stat = "Maximum", threshold = 0, period = 300, op = "GreaterThanThreshold"
      dims      = { QueueName = var.dlq_name }
      desc      = "Background jobs failed repeatedly and were dead-lettered"
    }
    "db-cpu" = {
      namespace = "AWS/RDS", metric = "CPUUtilization", stat = "Average", threshold = 80, period = 300, op = "GreaterThanThreshold"
      dims      = { DBInstanceIdentifier = var.db_identifier }
      desc      = "Database CPU above 80%"
    }
    "db-storage" = {
      namespace = "AWS/RDS", metric = "FreeStorageSpace", stat = "Minimum", threshold = 2147483648, period = 300, op = "LessThanThreshold"
      dims      = { DBInstanceIdentifier = var.db_identifier }
      desc      = "Database free storage below 2 GB"
    }
    "market-data-outage" = {
      namespace = "Knoww", metric = "MarketAllProvidersFailed", stat = "Sum", threshold = 3, period = 300, op = "GreaterThanThreshold"
      dims      = {}
      desc      = "All market data providers are failing; users see last-known prices"
    }
    "ai-failures" = {
      namespace = "Knoww", metric = "AIFailures", stat = "Sum", threshold = 20, period = 900, op = "GreaterThanThreshold"
      dims      = {}
      desc      = "AI explanations are failing; deterministic fallbacks are in use"
    }
  }
}

# Structured log events become metrics (no extra code or agents needed).
resource "aws_cloudwatch_log_metric_filter" "all_providers_failed" {
  name           = "${var.name}-market-all-providers-failed"
  log_group_name = var.worker_log_group
  pattern        = "{ $.event = \"market.all_providers_failed\" }"
  metric_transformation {
    name      = "MarketAllProvidersFailed"
    namespace = "Knoww"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "ai_failures" {
  name           = "${var.name}-ai-failures"
  log_group_name = var.worker_log_group
  pattern        = "{ $.event = \"ai.failure\" }"
  metric_transformation {
    name      = "AIFailures"
    namespace = "Knoww"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each            = local.alarms
  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.desc
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = each.value.stat == "p95" ? null : each.value.stat
  extended_statistic  = each.value.stat == "p95" ? "p95" : null
  dimensions          = length(each.value.dims) > 0 ? each.value.dims : null
  period              = each.value.period
  evaluation_periods  = 1
  threshold           = each.value.threshold
  comparison_operator = each.value.op
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

output "alarm_topic_arn" { value = aws_sns_topic.alarms.arn }
