#!/usr/bin/env bash
# Same steps as the deploy job in .github/workflows/ci.yml.
# Usage: AWS_PROFILE=homevision scripts/deploy.sh (alert_email from infra/terraform.tfvars or TF_VAR_alert_email)
set -euo pipefail
cd "$(dirname "$0")/.."

region=us-west-2
tag=$(git rev-parse HEAD)
[[ -z $(git status --porcelain) ]] || tag="$tag-dirty-$(date +%s)"
registry=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$region.amazonaws.com

aws ecr get-login-password --region $region | docker login --username AWS --password-stdin "$registry"
docker buildx build --platform linux/arm64 --provenance=false --push -t "$registry/homevision-checkboxes:$tag" backend

terraform -chdir=infra init -input=false
terraform -chdir=infra apply -input=false -var image_tag="$tag"

(cd frontend && npm ci && npm run build)
aws s3 sync frontend/dist "s3://$(terraform -chdir=infra output -raw site_bucket)" --delete
aws cloudfront create-invalidation --distribution-id "$(terraform -chdir=infra output -raw distribution_id)" --paths "/*" >/dev/null

url=$(terraform -chdir=infra output -raw url)
curl -fsS --retry 5 --retry-all-errors "$url/api/health" && echo
echo "$url"
