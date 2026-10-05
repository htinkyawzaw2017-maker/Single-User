#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Single-User Burmese/English Movie Dubbing Tool — AWS deploy script
#  Idempotent-ish CLI deployment of the whole stack.
#
#  Usage:
#    cd Single-User
#    ./infrastructure/deploy.sh
#
#  Prereqs: aws CLI v2 (configured), docker, openssl
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."

# ── configuration ────────────────────────────────────────────────────
REGION="${AWS_REGION:-ap-southeast-1}"
APP_NAME="${APP_NAME:-my-dubbing-tool}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DB_CLASS="${DB_CLASS:-db.t4g.micro}"
TASK_CPU="${TASK_CPU:-1024}"
TASK_MEM="${TASK_MEM:-4096}"

IN_BUCKET="${APP_NAME}-input-${ACCOUNT}"
OUT_BUCKET="${APP_NAME}-output-${ACCOUNT}"
ECR_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${APP_NAME}"
LOG_GROUP="/ecs/${APP_NAME}"

echo "════════════════════════════════════════════════════════"
echo "  Deploying: $APP_NAME"
echo "  Region:    $REGION"
echo "  Account:   $ACCOUNT"
echo "════════════════════════════════════════════════════════"

# ── 0. sanity checks ─────────────────────────────────────────────────
command -v docker >/dev/null || { echo "✗ docker is required"; exit 1; }
command -v openssl >/dev/null || { echo "✗ openssl is required"; exit 1; }
aws sts get-caller-identity >/dev/null || { echo "✗ run 'aws configure' first"; exit 1; }

# secrets file so re-deploys reuse the same values
SECRET_FILE=".deploy-secrets"
if [ ! -f "$SECRET_FILE" ]; then
  cat > "$SECRET_FILE" <<EOF
DB_PASSWORD=$(openssl rand -hex 16)
ACCESS_KEY=$(openssl rand -hex 16)
EOF
  chmod 600 "$SECRET_FILE"
  echo "✓ generated $SECRET_FILE (keep it private!)"
fi
DB_PASSWORD="$(grep DB_PASSWORD "$SECRET_FILE" | cut -d= -f2)"
ACCESS_KEY="$(grep ACCESS_KEY "$SECRET_FILE" | cut -d= -f2)"

# ── 1. S3 buckets + lifecycle + CORS ─────────────────────────────────
for B in "$IN_BUCKET" "$OUT_BUCKET"; do
  if ! aws s3api head-bucket --bucket "$B" 2>/dev/null; then
    aws s3api create-bucket --bucket "$B" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
    echo "✓ created bucket $B"
  fi
  aws s3api put-public-access-block --bucket "$B" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
done
aws s3api put-bucket-lifecycle-configuration --bucket "$IN_BUCKET" \
  --lifecycle-configuration file://infrastructure/s3/lifecycle-input.json
aws s3api put-bucket-lifecycle-configuration --bucket "$OUT_BUCKET" \
  --lifecycle-configuration file://infrastructure/s3/lifecycle-output.json
# CORS so the browser can PUT presigned uploads straight to S3
aws s3api put-bucket-cors --bucket "$IN_BUCKET" \
  --cors-configuration file://infrastructure/s3/cors-input.json
echo "✓ S3 buckets + lifecycle + CORS configured"

# ── 2. ECR + docker image ────────────────────────────────────────────
if ! aws ecr describe-repositories --repository-names "$APP_NAME" 2>/dev/null; then
  aws ecr create-repository --repository-name "$APP_NAME" \
    --image-scanning-configuration scanOnPush=true >/dev/null
  echo "✓ created ECR repo $APP_NAME"
fi
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_URI" >/dev/null
echo "⏳ building image (linux/amd64)…"
docker build --platform linux/amd64 -t "$APP_NAME:$IMAGE_TAG" -f Dockerfile .
docker tag "$APP_NAME:$IMAGE_TAG" "$ECR_URI:$IMAGE_TAG"
docker push "$ECR_URI:$IMAGE_TAG" >/dev/null
echo "✓ image pushed → $ECR_URI:$IMAGE_TAG"

# ── 3. RDS PostgreSQL ────────────────────────────────────────────────
if ! aws rds describe-db-instances --db-instance-identifier "${APP_NAME}-db" 2>/dev/null | grep -q "${APP_NAME}-db"; then
  echo "⏳ creating RDS PostgreSQL (${DB_CLASS}) — takes 5–10 minutes…"
  aws rds create-db-instance \
    --db-instance-identifier "${APP_NAME}-db" \
    --db-name dubbing --engine postgres --engine-version 16.3 \
    --db-instance-class "$DB_CLASS" --allocated-storage 20 --storage-type gp3 \
    --master-username dubbing --master-user-password "$DB_PASSWORD" \
    --backup-retention-period 7 --no-multi-az --no-publicly-accessible \
    --db-subnet-group-name "${APP_NAME}-dbsubnet" >/dev/null || true
  # subnet group may not exist yet — create if needed (default VPC subnets)
  if ! aws rds describe-db-subnet-groups --db-subnet-group-name "${APP_NAME}-dbsubnet" 2>/dev/null | grep -q "${APP_NAME}-dbsubnet"; then
    VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
    SUBNET_CSV="$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" --query 'Subnets[].SubnetId' --output text | tr '\t' ',')"
    aws rds create-db-subnet-group --db-subnet-group-name "${APP_NAME}-dbsubnet" \
      --db-subnet-group-description "dubbing tool" --subnet-ids $(echo "$SUBNET_CSV" | tr ',' ' ') >/dev/null
  fi
  aws rds wait db-instance-available --db-instance-identifier "${APP_NAME}-db"
  echo "✓ RDS ready"
fi
DB_HOST="$(aws rds describe-db-instances --db-instance-identifier "${APP_NAME}-db" \
  --query 'DBInstances[0].Endpoint.Address' --output text)"
echo "✓ database host: $DB_HOST"

# ── 4. Secrets Manager ───────────────────────────────────────────────
SECRET_NAME="${APP_NAME}/app"
if ! aws secretsmanager describe-secret --secret-id "$SECRET_NAME" 2>/dev/null; then
  aws secretsmanager create-secret --name "$SECRET_NAME" \
    --secret-string "{\"DB_PASSWORD\":\"$DB_PASSWORD\",\"ACCESS_KEY\":\"$ACCESS_KEY\"}" >/dev/null
  echo "✓ created secret $SECRET_NAME"
fi

# ── 5. VPC / security groups ─────────────────────────────────────────
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
SUBNETS_JSON="$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" --query 'Subnets[].SubnetId' --output json)"
SUBNET_ARGS="$(echo "$SUBNETS_JSON" | tr -d '[]" ' | tr ',' ' ')"

SG_ALB_NAME="${APP_NAME}-alb-sg"
SG_SVC_NAME="${APP_NAME}-svc-sg"
SG_DB_NAME="${APP_NAME}-db-sg"

get_sg() { aws ec2 describe-security-groups --filters "Name=group-name,Values=$1" "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text; }

SG_ALB="$(get_sg "$SG_ALB_NAME")"
if [ "$SG_ALB" = "None" ]; then
  SG_ALB="$(aws ec2 create-security-group --group-name "$SG_ALB_NAME" --description "dubbing ALB" --vpc-id "$VPC_ID" --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ALB" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null
  aws ec2 authorize-security-group-ingress --group-id "$SG_ALB" --protocol tcp --port 443 --cidr 0.0.0.0/0 >/dev/null
fi
SG_SVC="$(get_sg "$SG_SVC_NAME")"
if [ "$SG_SVC" = "None" ]; then
  SG_SVC="$(aws ec2 create-security-group --group-name "$SG_SVC_NAME" --description "dubbing service" --vpc-id "$VPC_ID" --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$SG_SVC" --protocol tcp --port 8000 --source-group "$SG_ALB" >/dev/null
fi
SG_DB="$(get_sg "$SG_DB_NAME")"
if [ "$SG_DB" = "None" ]; then
  SG_DB="$(aws ec2 create-security-group --group-name "$SG_DB_NAME" --description "dubbing DB" --vpc-id "$VPC_ID" --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$SG_DB" --protocol tcp --port 5432 --source-group "$SG_SVC" >/dev/null
fi
# make sure RDS uses our DB security group
aws rds modify-db-instance --db-instance-identifier "${APP_NAME}-db" \
  --vpc-security-group-ids "$SG_DB" --apply-immediately >/dev/null 2>&1 || true
echo "✓ security groups ready"

# ── 6. ALB ───────────────────────────────────────────────────────────
ALB_NAME="${APP_NAME}-alb"
ALB_ARN="$(aws elbv2 describe-load-balancers --names "$ALB_NAME" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || echo None)"
if [ "$ALB_ARN" = "None" ]; then
  ALB_ARN="$(aws elbv2 create-load-balancer --name "$ALB_NAME" --type application \
    --subnets $SUBNET_ARGS --security-groups "$SG_ALB" \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)"
  aws elbv2 wait load-balancer-available --load-balancer-arns "$ALB_ARN"
  TG_ARN="$(aws elbv2 create-target-group --name "${APP_NAME}-tg" --protocol HTTP --port 8000 \
    --vpc-id "$VPC_ID" --target-type ip --health-check-path /api/health \
    --query 'TargetGroups[0].TargetGroupArn' --output text)"
  aws elbv2 create-listener --load-balancer-arn "$ALB_ARN" --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" >/dev/null
  echo "✓ ALB created"
else
  TG_ARN="$(aws elbv2 describe-target-groups --load-balancer-arn "$ALB_ARN" --names "${APP_NAME}-tg" --query 'TargetGroups[0].TargetGroupArn' --output text)"
fi

# ── 7. CloudWatch logs ───────────────────────────────────────────────
aws logs create-log-group --log-group-name "$LOG_GROUP" --retention-in-days 30 2>/dev/null || true

# ── 8. ECS cluster + roles ───────────────────────────────────────────
if ! aws ecs describe-clusters --clusters "$APP_NAME" --query 'clusters[0].status' --output text 2>/dev/null | grep -q ACTIVE; then
  aws ecs create-cluster --cluster-name "$APP_NAME" >/dev/null
  echo "✓ ECS cluster created"
fi

EXEC_ROLE_NAME="${APP_NAME}-execution"
TASK_ROLE_NAME="${APP_NAME}-task"
for ROLE in "$EXEC_ROLE_NAME" "$TASK_ROLE_NAME"; do
  if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
    cat > /tmp/trust-$ROLE.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
EOF
    aws iam create-role --role-name "$ROLE" --assume-role-policy-document file:///tmp/trust-$ROLE.json >/dev/null
  fi
done
aws iam attach-role-policy --role-name "$EXEC_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy 2>/dev/null || true
# execution role may read the app secret
cat > /tmp/secpol.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"], "Resource": "arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:${APP_NAME}/*"}]}
EOF
aws iam put-role-policy --role-name "$EXEC_ROLE_NAME" --policy-name read-app-secret --policy-document file:///tmp/secpol.json
# task role: S3 + Transcribe access
cat > /tmp/taskpol.json <<EOF
{"Version": "2012-10-17", "Statement": [
 {"Effect": "Allow", "Action": ["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"], "Resource": ["arn:aws:s3:::${IN_BUCKET}","arn:aws:s3:::${IN_BUCKET}/*","arn:aws:s3:::${OUT_BUCKET}","arn:aws:s3:::${OUT_BUCKET}/*"]},
 {"Effect": "Allow", "Action": ["transcribe:StartTranscriptionJob","transcribe:GetTranscriptionJob"], "Resource": "*"}
]}
EOF
aws iam put-role-policy --role-name "$TASK_ROLE_NAME" --policy-name app-access --policy-document file:///tmp/taskpol.json
echo "✓ IAM roles ready"

# ── 9. Task definition ───────────────────────────────────────────────
cat > /tmp/taskdef.json <<EOF
{
  "family": "$APP_NAME",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "$TASK_CPU",
  "memory": "$TASK_MEM",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT}:role/${EXEC_ROLE_NAME}",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT}:role/${TASK_ROLE_NAME}",
  "containerDefinitions": [{
    "name": "app",
    "image": "${ECR_URI}:${IMAGE_TAG}",
    "essential": true,
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name": "APP_ENV", "value": "aws"},
      {"name": "AWS_REGION", "value": "$REGION"},
      {"name": "STORAGE_BACKEND", "value": "s3"},
      {"name": "S3_INPUT_BUCKET", "value": "$IN_BUCKET"},
      {"name": "S3_OUTPUT_BUCKET", "value": "$OUT_BUCKET"},
      {"name": "SINGLE_USER_ACCESS_KEY", "value": "$ACCESS_KEY"},
      {"name": "TRANSCRIPTION_PROVIDER", "value": "mock"},
      {"name": "TRANSLATION_PROVIDER", "value": "mock"},
      {"name": "TTS_PROVIDER", "value": "mock"},
      {"name": "LIPSYNC_PROVIDER", "value": "mock"},
      {"name": "DATABASE_URL", "value": "postgresql+psycopg2://dubbing:${DB_PASSWORD}@${DB_HOST}:5432/dubbing"},
      {"name": "DATA_DIR", "value": "/app/data"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {"awslogs-group": "$LOG_GROUP", "awslogs-region": "$REGION", "awslogs-stream-prefix": "app"}
    }
  }]
}
EOF
aws ecs register-task-definition --cli-input-json file:///tmp/taskdef.json >/dev/null
TASKDEF_ARN="$(aws ecs describe-task-definition --task-definition "$APP_NAME" --query 'taskDefinition.taskDefinitionArn' --output text)"
echo "✓ task definition registered"

# ── 10. ECS service ──────────────────────────────────────────────────
SERVICE_STATUS="$(aws ecs describe-services --cluster "$APP_NAME" --services "$APP_NAME" --query 'services[0].status' --output text 2>/dev/null || echo None)"
if [ "$SERVICE_STATUS" = "None" ] || [ "$SERVICE_STATUS" = "INACTIVE" ]; then
  aws ecs create-service --cluster "$APP_NAME" --service-name "$APP_NAME" \
    --task-definition "$TASKDEF_ARN" --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$(echo $SUBNET_ARGS | tr ' ' ',')],securityGroups=[$SG_SVC],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_ARN,containerName=app,containerPort=8000" \
    --health-check-grace-period-seconds 60 >/dev/null
  echo "✓ ECS service created — waiting for it to stabilise…"
else
  aws ecs update-service --cluster "$APP_NAME" --service "$APP_NAME" \
    --task-definition "$TASKDEF_ARN" --force-new-deployment >/dev/null
  echo "✓ ECS service updated — waiting…"
fi
aws ecs wait services-stable --cluster "$APP_NAME" --services "$APP_NAME" || true

ALB_DNS="$(aws elbv2 describe-load-balancers --names "$ALB_NAME" --query 'LoadBalancers[0].DNSName' --output text)"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  🎬 Deployment complete!"
echo ""
echo "  App URL:     http://$ALB_DNS"
echo "  Access key:  $ACCESS_KEY   (also saved in $SECRET_FILE & Secrets Manager)"
echo "  Buckets:     $IN_BUCKET / $OUT_BUCKET"
echo "  Database:    ${APP_NAME}-db ($DB_HOST)"
echo "  Logs:        aws logs tail $LOG_GROUP --follow"
echo ""
echo "  Next steps:"
echo "   • switch providers: set TRANSLATION_PROVIDER=llm / TTS_PROVIDER=http"
echo "     in section 9 of this script (or the task definition) and re-run"
echo "   • add HTTPS via CloudFront — see infrastructure/cloudfront/README.md"
echo "════════════════════════════════════════════════════════"
