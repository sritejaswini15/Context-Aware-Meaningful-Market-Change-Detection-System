variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "domain_name" {
  description = "Public hostname (e.g. knoww.example.com). Leave empty to use the ALB DNS name."
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS. Strongly recommended; empty = HTTP only."
  type        = string
  default     = ""
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "market_providers" {
  description = "Comma-separated provider chain: finnhub | mock,mock-reference"
  type        = string
  default     = "finnhub"
}

variable "market_refresh_expression" {
  description = "EventBridge Scheduler expression for market refresh"
  type        = string
  default     = "rate(1 minute)"
}

variable "ai_provider" {
  description = "anthropic | none"
  type        = string
  default     = "anthropic"
}

variable "ai_model" {
  type    = string
  default = ""
}

variable "demo_mode" {
  description = "Expose the simulated-market controls (only effective with mock providers)"
  type        = bool
  default     = false
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "alarm_email" {
  description = "Email for CloudWatch alarm notifications (optional)"
  type        = string
  default     = ""
}
