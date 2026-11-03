#!/usr/bin/env bash
# Same steps as the deploy job in .github/workflows/ci.yml.
# Usage: AWS_PROFILE=homevision scripts/deploy.sh
# alert_email and domain_name come from infra/terraform.tfvars or TF_VAR_*, like the ALERT_EMAIL GitHub secret and DOMAIN_NAME GitHub variable.
# AWS_ACCOUNT_ID (like the GitHub secret) comes from the environment or a .env file at the repo root (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] && source .env
region=us-west-2
account=${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID, e.g. in .env}
[[ $(aws sts get-caller-identity --query Account --output text) == "$account" ]] || {
  echo "The AWS session is not for account $account." >&2
  exit 1
}
export TF_VAR_account_id=$account
tag=$(git rev-parse HEAD)
[[ -z $(git status --porcelain) ]] || tag="$tag-dirty-$(date +%s)"
registry=$account.dkr.ecr.$region.amazonaws.com

aws ecr get-login-password --region $region | docker login --username AWS --password-stdin "$registry"
docker buildx build --platform linux/arm64 --provenance=false --push -t "$registry/homevision-checkboxes:$tag" backend

terraform -chdir=infra init -input=false -backend-config="bucket=homevision-checkboxes-tfstate-$account"
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
