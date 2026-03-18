# SQS

resource "aws_sqs_queue" "ingestion_dlq" {
  name                    = "${var.project}-ingestion-dlq"
  sqs_managed_sse_enabled = true
}

resource "aws_sqs_queue" "ingestion" {
  name = "${var.project}-ingestion"

  # AWS recommends >= 6x Lambda timeout. Lambda timeout = 600 s, so 3600 s here.
  visibility_timeout_seconds = 3600

  sqs_managed_sse_enabled = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq.arn
    maxReceiveCount     = 3
  })
}
