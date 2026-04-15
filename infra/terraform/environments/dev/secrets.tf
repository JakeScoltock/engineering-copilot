# Secrets Manager

resource "aws_secretsmanager_secret" "github_token" {
  name        = "${var.project}/github-token"
  description = "GitHub personal access token for repo ingestion. Set the value manually in the AWS console after first deploy."
}

resource "aws_secretsmanager_secret" "streaming_api_key" {
  name        = "${var.project}/streaming-api-key"
  description = "API key for the streaming query Lambda Function URL. Set the value manually in the AWS console after first deploy."
}
