provider "aws" {
  alias               = "us_east_1"
  region              = "us-east-1"
  allowed_account_ids = ["630773215521"]
  default_tags { tags = { Project = "homevision-checkboxes" } }
}

locals {
  domain = var.domain_name == "" ? [] : [var.domain_name]
}

data "aws_route53_zone" "site" {
  for_each = toset(local.domain)
  name     = each.value
}

resource "aws_acm_certificate" "site" {
  for_each          = toset(local.domain)
  provider          = aws.us_east_1
  domain_name       = each.value
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for o in flatten([for c in aws_acm_certificate.site : c.domain_validation_options]) : o.domain_name => o
  }
  zone_id         = data.aws_route53_zone.site[var.domain_name].zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  for_each                = aws_acm_certificate.site
  provider                = aws.us_east_1
  certificate_arn         = each.value.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

resource "aws_route53_record" "site" {
  for_each = { for pair in setproduct(local.domain, ["A", "AAAA"]) : "${pair[0]}-${pair[1]}" => pair }
  zone_id  = data.aws_route53_zone.site[each.value[0]].zone_id
  name     = each.value[0]
  type     = each.value[1]
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
