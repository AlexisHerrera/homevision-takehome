variable "image_tag" {
  type        = string
  description = "Tag of the API image in ECR (the git commit SHA)"
}

variable "alert_email" {
  type        = string
  description = "Where budget alerts are sent"
}

variable "monthly_budget_usd" {
  type    = number
  default = 20
}

variable "domain_name" {
  type        = string
  default     = ""
  description = "Optional custom domain, e.g. app.example.com, whose parent (or itself, if it is an apex) is a Route 53 hosted zone in this account; the cloudfront.net URL keeps working"
}
