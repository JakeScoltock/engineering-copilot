output "api_url" {
  description = "REST API base URL — append /health, /repos, etc."
  value       = aws_api_gateway_stage.dev.invoke_url
}

output "streaming_query_url" {
  description = "Lambda Function URL for streaming POST /repos/{repo_id}/query"
  value       = aws_lambda_function_url.query_streaming.function_url
}

output "api_key" {
  description = "API key value — pass as x-api-key header on all non-health requests"
  value       = aws_api_gateway_api_key.default.value
  sensitive   = true
}
