output "health_url" {
  value = "${aws_api_gateway_stage.dev.invoke_url}/health"
}

output "repos_url" {
  value = "${aws_api_gateway_stage.dev.invoke_url}/repos"
}

output "api_key" {
  description = "API key value — pass as x-api-key header on all non-health requests"
  value       = aws_api_gateway_api_key.default.value
  sensitive   = true
}
