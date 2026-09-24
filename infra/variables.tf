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
