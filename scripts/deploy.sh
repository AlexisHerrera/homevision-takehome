#!/usr/bin/env bash
# Same steps as the deploy job in .github/workflows/ci.yml.
# Usage: AWS_PROFILE=homevision scripts/deploy.sh
# alert_email and domain_name come from infra/terraform.tfvars or TF_VAR_*, like the ALERT_EMAIL and DOMAIN_NAME GitHub variables.
set -euo pipefail
cd "$(dirname "$0")/.."

region=us-west-2
tag=$(git rev-parse HEAD)
[[ -z $(git status --porcelain) ]] || tag="$tag-dirty-$(date +%s)"
registry=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$region.amazonaws.com

aws ecr get-login-password --region $region | docker login --username AWS --password-stdin "$registry"
docker buildx build --platform linux/arm64 --provenance=false --push -t "$registry/homevision-checkboxes:$tag" backend

terraform -chdir=infra init -input=false
if [[ -z ${TF_VAR_domain_name+set} ]] && ! grep -q '^domain_name' infra/terraform.tfvars 2>/dev/null; then
  echo "domain_name is not set: this apply would remove the custom domain. Set it in infra/terraform.tfvars or TF_VAR_domain_name ('' for no domain)." >&2
  exit 1
fi
terraform -chdir=infra apply -input=false -var image_tag="$tag"

(cd frontend && npm ci && npm run build)
bucket=s3://$(terraform -chdir=infra output -raw site_bucket)
distribution=$(terraform -chdir=infra output -raw distribution_id)
aws s3 sync frontend/dist "$bucket"
invalidation=$(aws cloudfront create-invalidation --distribution-id "$distribution" --paths "/*" --query Invalidation.Id --output text)
aws cloudfront wait invalidation-completed --distribution-id "$distribution" --id "$invalidation"
aws s3 sync frontend/dist "$bucket" --delete

url=$(terraform -chdir=infra output -raw url)
curl -fsS --retry 5 --retry-all-errors "$url/api/health" && echo
echo "$url"
