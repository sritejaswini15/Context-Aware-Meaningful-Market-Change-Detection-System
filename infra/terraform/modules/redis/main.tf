variable "name" { type = string }
variable "subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "node_type" {
  type    = string
  default = "cache.t4g.micro"
}

resource "aws_elasticache_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

# Cache, rate limits and locks only: Postgres stays the source of truth,
# and the app degrades to in-process fallbacks if Redis is unavailable.
resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = var.name
  description                = "Knoww cache, rate limits and locks"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.node_type
  num_cache_clusters         = 1
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [var.security_group_id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = false
}

output "url" { value = "rediss://${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0" }
