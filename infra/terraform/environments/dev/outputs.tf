output "health_url" {
  value = "${aws_api_gateway_stage.dev.invoke_url}/health"
}
