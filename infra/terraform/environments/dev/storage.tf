# S3

resource "aws_s3_bucket" "repo_data" {
  bucket = "${var.project}-repo-data"
}

resource "aws_s3_bucket_public_access_block" "repo_data" {
  bucket = aws_s3_bucket.repo_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "repo_data" {
  bucket = aws_s3_bucket.repo_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# DynamoDB

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.project}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "repo_id"

  attribute {
    name = "repo_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
