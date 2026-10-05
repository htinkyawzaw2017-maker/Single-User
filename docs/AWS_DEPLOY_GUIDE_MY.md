# ☁️ AWS တင်ဖို့ CMD Guide (မြန်မာ)

ဒီ guide က **Single-User Burmese/English Movie Dubbing Tool** ကို AWS ပေါ်
တင်ဖို့ command တစ်ခုချင်းစီ အသေးစိတ်ရှင်းပြတဲ့ လမ်းညွှန်ပါ။
Terminal / CMD မှာ အစဉ်လိုက် copy-paste လုပ်လို့ရအောင် ရေးထားပါတယ်။

---

## ပုံစံ (Architecture)

```
Browser (React SPA)
   ↓
ALB (Application Load Balancer) — http://xxx.elb.amazonaws.com
   ↓
ECS Fargate container — FastAPI (API + SPA + background worker + ffmpeg)
   ├─→ S3 input bucket   (upload တွေ — presigned URL)
   ├─→ S3 output bucket  (audio, video, subtitle တွေ — lifecycle rule ပါ)
   ├─→ RDS PostgreSQL    (project/segment/job metadata)
   └─→ Secrets Manager   (DB password, API keys)
CloudWatch — logs (/ecs/my-dubbing-tool, retention 30 ရက်)
```

တစ်ကယ့်စားရင် CloudFront နဲ့ HTTPS/WAF ထပ်တပ်နိုင်ပါတယ်
(အပိုင်း ၁၁ ကြည့်ပါ)။

---

## အရင်ဆုံး လိုအပ်တာတွေ

1. **AWS account** (Free Tier သို့မဟုတ် သင့်တော်တဲ့ plan)
2. ကွန်ပျူတာမှာ —
   - **AWS CLI v2** → https://aws.amazon.com/cli/
   - **Docker** → https://docs.docker.com/get-docker/
   - **openssl** (Windows ဆို Git Bash ထဲမှာ ပါပါတယ်)
3. Region ရွေးပါ — မြန်မာအနီးဆုံးက `ap-southeast-1` (Singapore)
   ဒါမှမဟုတ် `ap-southeast-7` (Thailand) သုံးလို့ရပါတယ်။

```bash
# စစ်ကြည့်ပါ
aws --version          # aws-cli/2.x ဖြစ်သင့်
docker --version
```

---

## အပိုင်း ၀ — AWS configure

```bash
aws configure
# AWS Access Key ID:      မင်းရဲ့ access key
# AWS Secret Access Key:  မင်းရဲ့ secret key
# Default region name:    ap-southeast-1
# Default output format:  json
```

Access key ကို AWS Console → IAM → Users → (မင်းရဲ့ user) →
Security credentials → **Create access key** ကနေ ယူနိုင်ပါတယ်။
(AdministratorAccess ရှိတဲ့ user နဲ့ စတင်တာ အလွယ်ဆုံးပါ။)

```bash
# အလုပ်လုပ်နေမှန်း စစ်ကြည့်ပါ
aws sts get-caller-identity
# Account နံပါတ်နဲ့ user နာမည် ပေါ်လာရင် အဆင်သင့်ပါ။
```

---

## အပိုင်း ၁ — အလိုအလျောက် deploy (အမြန်ဆုံးနည်း) ⭐

Repo root မှာ ဒီ script တစ်ကြိမ်တည်းနဲ့ အားလုံးတင်ပေးပါမယ် —
S3 buckets, ECR, Docker image, RDS, Secrets Manager, security groups,
ALB, ECS Fargate service အားလုံး —

```bash
cd Single-User
export AWS_REGION=ap-southeast-1
./infrastructure/deploy.sh
```

- RDS ဆောက်ဖို့ **၅-၁၀ မိနစ်** ခန့် ကြာပါမယ်။
- ပြီးရင် နောက်ဆုံးမှာ **App URL** နဲ့ **Access key** ပေါ်လာပါမယ်။
- Script က `.deploy-secrets` ဖိုင်ထဲ မင်းရဲ့ password/key တွေ သိမ်းထား
 ပါမယ် — ဒို့ကို တခြားသူ မမြင်စေနဲ့ (git ထဲလည်း မတင်ပါနဲ့)။

အောင်မြင်ပြီးသွားရင် အပိုင်း ၁၀ (စစ်ကြည့်ခြင်း) ကို ခုန်သွားလို့ရပါတယ်။
အောက်ပါ အပိုင်း ၂-၉ က တစ်ခုချင်း အသေးစိတ် manual နည်းပါ။

---

## အပိုင်း ၂ — S3 Buckets (input/output + lifecycle + CORS)

```bash
export AWS_REGION=ap-southeast-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME="my-dubbing-tool"
export IN_BUCKET="${APP_NAME}-input-${ACCOUNT}"
export OUT_BUCKET="${APP_NAME}-output-${ACCOUNT}"

# bucket နှစ်ခု ဖန်တီး
aws s3api create-bucket --bucket "$IN_BUCKET" --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"
aws s3api create-bucket --bucket "$OUT_BUCKET" --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"

# public မဖြစ်စေရန် ပိတ်ပါ
aws s3api put-public-access-block --bucket "$IN_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-public-access-block --bucket "$OUT_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# lifecycle rules (input: ၃၆၅ ရက်နောက် အလိုအလျောက်ဖျက် / output: storage class ပြောင်း)
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$IN_BUCKET" \
  --lifecycle-configuration file://infrastructure/s3/lifecycle-input.json
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$OUT_BUCKET" \
  --lifecycle-configuration file://infrastructure/s3/lifecycle-output.json

# CORS — browser က presigned PUT နဲ့ တိုက်ရိုက်တင်ဖို့ လိုပါတယ်
aws s3api put-bucket-cors --bucket "$IN_BUCKET" \
  --cors-configuration file://infrastructure/s3/cors-input.json

echo "buckets: $IN_BUCKET / $OUT_BUCKET"
```

---

## အပိုင်း ၃ — ECR + Docker Image

```bash
# ECR repo ဖန်တီး
aws ecr create-repository --repository-name "$APP_NAME" \
  --image-scanning-configuration scanOnPush=true

# login
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# image ဆောက် (linux/amd64 ဖြစ်စေရန် သတိ — Fargate x86)
docker build --platform linux/amd64 -t "$APP_NAME:latest" .

# push
docker tag "$APP_NAME:latest" \
  "${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}:latest"
docker push "${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}:latest"
```

> 💡 Apple Silicon (M1/M2) Mac မှာဆိုရင် `--platform linux/amd64` ကို
> မမေ့ပါနဲ့။ Dockerfile က frontend build (Node) + backend (Python+ffmpeg)
> နှစ်ခုလုံး ပါဝင်ပြီး container တစ်ခုတည်းနဲ့ API + web ကို
> တစ်ပြိုင်တည်း ဆာဗ်ပေးပါမယ်။

---

## အပိုင်း ၄ — RDS PostgreSQL

```bash
DB_PASSWORD=$(openssl rand -hex 16)
echo "DB_PASSWORD=$DB_PASSWORD"   # သိမ်းထားပါ!

VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ' ')

# subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name "${APP_NAME}-dbsubnet" \
  --db-subnet-group-description "dubbing tool" \
  --subnet-ids $SUBNETS

# database (၅-၁၀ မိနစ် ကြာပါမယ်)
aws rds create-db-instance \
  --db-instance-identifier "${APP_NAME}-db" \
  --db-name dubbing \
  --engine postgres --engine-version 16.3 \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp3 \
  --master-username dubbing --master-user-password "$DB_PASSWORD" \
  --db-subnet-group-name "${APP_NAME}-dbsubnet" \
  --no-publicly-accessible --no-multi-az \
  --backup-retention-period 7

aws rds wait db-instance-available --db-instance-identifier "${APP_NAME}-db"

DB_HOST=$(aws rds describe-db-instances --db-instance-identifier "${APP_NAME}-db" \
  --query 'DBInstances[0].Endpoint.Address' --output text)
echo "DB_HOST=$DB_HOST"
```

---

## အပိုင်း ၅ — Secrets Manager

```bash
ACCESS_KEY=$(openssl rand -hex 16)
echo "ACCESS_KEY=$ACCESS_KEY"      # app ဖွင့်တဲ့အခါ ထည့်ရမယ့် key!

aws secretsmanager create-secret \
  --name "${APP_NAME}/app" \
  --secret-string "{\"DB_PASSWORD\":\"$DB_PASSWORD\",\"ACCESS_KEY\":\"$ACCESS_KEY\"}"
```

> 🔑 **အရေးကြီး** — API keys (LLM/TTS) တွေကိုလည်း ဒီမှာတင် သိမ်းပါ
> (frontend code ထဲ မထည့်ပါနဲ့) —
>
> ```bash
> aws secretsmanager put-secret-value \
>   --secret-id "${APP_NAME}/app" \
>   --secret-string "{\"DB_PASSWORD\":\"$DB_PASSWORD\",\"ACCESS_KEY\":\"$ACCESS_KEY\",\"LLM_API_KEY\":\"sk-...\",\"TTS_HTTP_KEY\":\"...\"}"
> ```
> ပြီးရင် ECS task definition မှာ `SECRETS_MANAGER_SECRET_ID=${APP_NAME}/app`
> နဲ့ `TRANSLATION_PROVIDER=llm` / `TTS_PROVIDER=http` တွေ ထည့်ပေးရုံပါ။

---

## အပိုင်း ၆ — Security Groups

```bash
SG_ALB=$(aws ec2 create-security-group --group-name "${APP_NAME}-alb-sg" \
  --description "dubbing ALB" --vpc-id "$VPC_ID" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG_ALB" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG_ALB" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

SG_SVC=$(aws ec2 create-security-group --group-name "${APP_NAME}-svc-sg" \
  --description "dubbing service" --vpc-id "$VPC_ID" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG_SVC" \
  --protocol tcp --port 8000 --source-group "$SG_ALB"

SG_DB=$(aws ec2 create-security-group --group-name "${APP_NAME}-db-sg" \
  --description "dubbing DB" --vpc-id "$VPC_ID" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG_DB" \
  --protocol tcp --port 5432 --source-group "$SG_SVC"

# RDS ကို ကျွန်တော်တို့ SG နဲ့ ချိတ်ပါ
aws rds modify-db-instance --db-instance-identifier "${APP_NAME}-db" \
  --vpc-security-group-ids "$SG_DB" --apply-immediately
```

---

## အပိုင်း ၇ — ALB (Load Balancer)

```bash
ALB_ARN=$(aws elbv2 create-load-balancer --name "${APP_NAME}-alb" \
  --type application \
  --subnets $(echo $SUBNETS | tr ' ' '\n' | head -2 | tr '\n' ' ') \
  --security-groups "$SG_ALB" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

aws elbv2 wait load-balancer-available --load-balancer-arns "$ALB_ARN"

TG_ARN=$(aws elbv2 create-target-group --name "${APP_NAME}-tg" \
  --protocol HTTP --port 8000 --vpc-id "$VPC_ID" \
  --target-type ip --health-check-path /api/health \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

aws elbv2 create-listener --load-balancer-arn "$ALB_ARN" \
  --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn="$TG_ARN"

ALB_DNS=$(aws elbv2 describe-load-balancers --names "${APP_NAME}-alb" \
  --query 'LoadBalancers[0].DNSName' --output text)
echo "App URL: http://$ALB_DNS"
```

---

## အပိုင်း ၈ — ECS Fargate (Cluster + Roles + Task + Service)

### ၈.၁ Cluster + Logs

```bash
aws logs create-log-group --log-group-name "/ecs/${APP_NAME}" \
  --retention-in-days 30 2>/dev/null || true
aws ecs create-cluster --cluster-name "$APP_NAME"
```

### ၈.၂ IAM Roles

```bash
cat > /tmp/trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF

aws iam create-role --role-name "${APP_NAME}-execution" \
  --assume-role-policy-document file:///tmp/trust.json
aws iam create-role --role-name "${APP_NAME}-task" \
  --assume-role-policy-document file:///tmp/trust.json

aws iam attach-role-policy --role-name "${APP_NAME}-execution" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# execution role → Secrets Manager ဖတ်ခွင့်
cat > /tmp/secpol.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Action":["secretsmanager:GetSecretValue"],
 "Resource":"arn:aws:secretsmanager:${AWS_REGION}:${ACCOUNT}:secret:${APP_NAME}/*"}]}
EOF
aws iam put-role-policy --role-name "${APP_NAME}-execution" \
  --policy-name read-app-secret --policy-document file:///tmp/secpol.json

# task role → S3 နှစ်ခု + Transcribe
cat > /tmp/taskpol.json <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"],
  "Resource":["arn:aws:s3:::${IN_BUCKET}","arn:aws:s3:::${IN_BUCKET}/*",
              "arn:aws:s3:::${OUT_BUCKET}","arn:aws:s3:::${OUT_BUCKET}/*"]},
 {"Effect":"Allow","Action":["transcribe:StartTranscriptionJob","transcribe:GetTranscriptionJob"],
  "Resource":"*"}]}
EOF
aws iam put-role-policy --role-name "${APP_NAME}-task" \
  --policy-name app-access --policy-document file:///tmp/taskpol.json
```

### ၈.၃ Task Definition

```bash
cat > /tmp/taskdef.json <<EOF
{
  "family": "$APP_NAME",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "1024",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT}:role/${APP_NAME}-execution",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT}:role/${APP_NAME}-task",
  "containerDefinitions": [{
    "name": "app",
    "image": "${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}:latest",
    "essential": true,
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name":"APP_ENV","value":"aws"},
      {"name":"AWS_REGION","value":"$AWS_REGION"},
      {"name":"STORAGE_BACKEND","value":"s3"},
      {"name":"S3_INPUT_BUCKET","value":"$IN_BUCKET"},
      {"name":"S3_OUTPUT_BUCKET","value":"$OUT_BUCKET"},
      {"name":"SINGLE_USER_ACCESS_KEY","value":"$ACCESS_KEY"},
      {"name":"TRANSCRIPTION_PROVIDER","value":"mock"},
      {"name":"TRANSLATION_PROVIDER","value":"mock"},
      {"name":"TTS_PROVIDER","value":"mock"},
      {"name":"LIPSYNC_PROVIDER","value":"mock"},
      {"name":"DATABASE_URL","value":"postgresql+psycopg2://dubbing:${DB_PASSWORD}@${DB_HOST}:5432/dubbing"},
      {"name":"DATA_DIR","value":"/app/data"}
    ],
    "logConfiguration": {
      "logDriver":"awslogs",
      "options": {"awslogs-group":"/ecs/$APP_NAME","awslogs-region":"$AWS_REGION","awslogs-stream-prefix":"app"}
    }
  }]
}
EOF

aws ecs register-task-definition --cli-input-json file:///tmp/taskdef.json
TASKDEF_ARN=$(aws ecs describe-task-definition --task-definition "$APP_NAME" \
  --query 'taskDefinition.taskDefinitionArn' --output text)
```

> 💡 **Real providers သုံးမယ်ဆိုရင်** environment ထဲမှာ ပြောင်းပါ —
> `TRANSLATION_PROVIDER: "llm"`, `LLM_BASE_URL: "https://api.openai.com/v1"`,
> `LLM_MODEL: "gpt-4o-mini"`, `TTS_PROVIDER: "http"`,
> `TTS_HTTP_URL: "https://..."` — API key တွေကိုတော့ Secrets Manager
> (အပိုင်း ၅) ထဲကနေ `secrets` section နဲ့ သွင်းပါ (plain environment ထဲ
> မထည့်သလို လုပ်နိုင်ပါတယ်)။

### ၈.၄ Service တင်ခြင်း

```bash
SUBNET_CSV=$(echo $SUBNETS | tr ' ' ',')

aws ecs create-service --cluster "$APP_NAME" --service-name "$APP_NAME" \
  --task-definition "$TASKDEF_ARN" \
  --desired-count 1 --launch-type FARGATE \
  --network-configuration \
    "awsvpcConfiguration={subnets=[$SUBNET_CSV],securityGroups=[$SG_SVC],assignPublicIp=ENABLED}" \
  --load-balancers \
    "targetGroupArn=$TG_ARN,containerName=app,containerPort=8000" \
  --health-check-grace-period-seconds 60

aws ecs wait services-stable --cluster "$APP_NAME" --services "$APP_NAME"
echo "✅ Service တက်သွားပါပြီ!"
```

---

## အပိုင်း ၉ — CloudWatch Logs

```bash
# live logs ကြည့်ခြင်း
aws logs tail "/ecs/${APP_NAME}" --follow

# error တွေပဲရှာချင်ရင်
aws logs filter-log-events \
  --log-group-name "/ecs/${APP_NAME}" \
  --filter-pattern "ERROR"
```

Log retention ၃၀ ရက် ထားပြီးသား (အပိုင်း ၈.၁) — ပြောင်းချင်ရင် —

```bash
aws logs put-retention-policy --log-group-name "/ecs/${APP_NAME}" \
  --retention-in-days 90
```

---

## အပိုင်း ၁၀ — စစ်ကြည့်ခြင်း + အသုံးပြုခြင်း

```bash
# health check
curl "http://$ALB_DNS/api/health"
# → {"status":"ok","ffmpeg":true,...}

# browser မှာ ဖွင့်ပါ
echo "http://$ALB_DNS"
```

1. Browser မှာ URL ဖွင့်ပါ → **Access key** ထည့်ပါ (အပိုင်း ၅ က key)။
2. **New project** → video တင် (သို့) demo clip နှိပ် → pipeline
   အလိုအလျောက် လည်ပါမယ်။
3. Editor မှာ စာပြင် → voice ထုတ် → timing ညှိ → export။
4. Upload လုပ်တဲ့ file တွေ အားလုံးက S3 input bucket ထဲ၊
   ရလဒ်တွေက output bucket ထဲ —

```bash
aws s3 ls "s3://$IN_BUCKET/" --recursive | head
aws s3 ls "s3://$OUT_BUCKET/" --recursive | head
```

---

## အပိုင်း ၁၁ — (မဖြစ်မနေ) CloudFront + HTTPS + WAF

ALB URL က http (ဒဏ်ငွေမကုန်) ပါ။ Domain ရှိရင် HTTPS တပ်လို့ရပါတယ် —

1. **ACM certificate** (us-east-1) — `aws acm request-certificate
   --domain-name dubbing.example.com --validation-method DNS
   --region us-east-1` → DNS validation record ထည့်ပါ။
2. **CloudFront distribution** ဆောက်ပါ — origin = ALB DNS name
   (HTTP port 80)၊ alternate domain = မင်းရဲ့ domain၊ certificate = ACM။
3. **ALB security group** ကို CloudFront prefix list ချည်း ချုပ်ပါ —
   ALB ကိုတိုက်ရိုက် မဝင်နိုင်တော့ပါဘူး။
4. (Option) **AWS WAF** — IP allow-list rule တပ်ပါ။ Private single-user
   tool အတွက် အားကောင်းဆုံးကာကွယ်မှုပါ။

အသေးစိတ် — `infrastructure/cloudfront/README.md`

---

## အပိုင်း ၁၂ — Update တင်ခြင်း (code ပြောင်းပြီးနောက်)

```bash
# image အသစ် build + push
docker build --platform linux/amd64 -t "$APP_NAME:latest" .
docker tag "$APP_NAME:latest" \
  "${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}:latest"
docker push "${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}:latest"

# task definition အသစ် register (ပြင်ထားရင် /tmp/taskdef.json ပြင်ပြီးမှ)
aws ecs register-task-definition --cli-input-json file:///tmp/taskdef.json

# service ကို လေးစားစွာ restart
aws ecs update-service --cluster "$APP_NAME" --service "$APP_NAME" \
  --task-definition "$APP_NAME" --force-new-deployment
aws ecs wait services-stable --cluster "$APP_NAME" --services "$APP_NAME"
```

---

## အပိုင်း ၁၃ — (Option) Step Functions + GPU Lip-sync

MVP မှာ backend ကိုယ်တိုင်ရဲ့ background worker နဲ့ လုံလောက်ပါတယ်။
ကြီးလာရင် —

- **Step Functions** — `infrastructure/step-functions/pipeline.asl.json`
  က production orchestration definition (user review တွေက callback
  pattern နဲ့ စောင့်တာပါ)။
- **GPU lip-sync** — `infrastructure/sagemaker/lipsync-endpoint.yaml`
  နဲ့ SageMaker async endpoint ထောင်ပြီး task definition မှာ
  `LIPSYNC_PROVIDER=sagemaker` + `LIPSYNC_ENDPOINT_NAME=...` ထည့်ပါ။

---

## အပိုင်း ၁၄ — ကုန်ကျစရိတ် (သတိမှတ်ချက်)

| Service | Tier/Size | ခန့်မှန်းကုန်ကျ/လ (US East တွင်) |
|---|---|---|
| ECS Fargate | 1 vCPU / 4GB, 24/7 | ~$30–45 |
| ALB | အသုံးနည်း | ~$16–20 |
| RDS PostgreSQL | db.t4g.micro, 20GB | ~$12–15 |
| S3 | အသုံးအတွက် အလိုက် | အနည်းငယ် |
| **စုစုပေါင်း** | | **~$60–80/လ** |

သုံးပြီးသား အချိန်များရင် ဖြတ်တာ — `aws ecs update-service
--cluster $APP_NAME --service $APP_NAME --desired-count 0` (ပြန်ဖွင့်ရင်
`--desired-count 1`)၊ RDS ကိုလည်း temporarily stop လုပ်နိုင်ပါတယ်။

### အားလုံးဖျက်ချင်ရင် (cleanup)

```bash
aws ecs update-service --cluster "$APP_NAME" --service "$APP_NAME" \
  --desired-count 0
aws ecs delete-service --cluster "$APP_NAME" --service "$APP_NAME" --force
aws ecs delete-cluster --cluster "$APP_NAME"
aws elbv2 delete-load-balancer --load-balancer-arn "$ALB_ARN"
aws elbv2 delete-target-group --target-group-arn "$TG_ARN"
aws rds delete-db-instance --db-instance-identifier "${APP_NAME}-db" \
  --skip-final-snapshot
aws s3 rb "s3://$IN_BUCKET" --force
aws s3 rb "s3://$OUT_BUCKET" --force
aws secretsmanager delete-secret --secret-id "${APP_NAME}/app" \
  --force-delete-without-recovery
aws logs delete-log-group --log-group-name "/ecs/${APP_NAME}"
```

---

## အမြန်ညွှန်း (cheat sheet)

```bash
export AWS_REGION=ap-southeast-1
export APP_NAME="my-dubbing-tool"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

aws logs tail "/ecs/$APP_NAME" --follow              # logs
aws ecs update-service --cluster $APP_NAME \
  --service $APP_NAME --force-new-deployment          # restart
aws ecs describe-services --cluster $APP_NAME \
  --services $APP_NAME \
  --query 'services[0].{status:status,running:runningCount}'  # status
```

ကောင်းပါပြီ — မေးချင်တာရှိရင် project ရဲ့
`docs/GUIDE_MY.md` (အသုံးပြုပုံ) နဲ့ `docs/ARCHITECTURE.md` (system design)
တွေကိုလည်း ဖတ်ကြည့်ပါ။ 🎬
