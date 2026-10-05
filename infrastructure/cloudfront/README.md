# CloudFront (optional hardening for the single-user deployment)

The simplest deployment serves everything through the ALB DNS name and
protects the app with `SINGLE_USER_ACCESS_KEY`. When you want HTTPS at
your own domain + hiding the ALB, put CloudFront in front:

1. Create a distribution with the ALB as a custom origin (HTTP, port 80).
2. Attach an ACM certificate (us-east-1 for the default CloudFront cert)
   and set your domain as an alternate domain name.
3. Restrict the ALB security group to the CloudFront managed prefix list
   so the origin is not directly reachable.
4. Optional: attach AWS WAF with an IP allow-list rule — for a private
   single-user tool this is the cheapest strong protection.

Commands (quick start):

```bash
DOMAIN=dubbing.example.com
CERT_ARN=$(aws acm request-certificate \
  --domain-name "$DOMAIN" --validation-method DNS \
  --region us-east-1 --query CertificateArn --output text)

# create the distribution with the ALB DNS name as origin
ALB_DNS=$(aws elbv2 describe-load-balancers --names my-dubbing-tool-alb \
  --query 'LoadBalancers[0].DNSName' --output text)
# (or use the AWS console once, then keep the distribution in code)
```

CloudFront + S3 for the frontend (alternative split):

```bash
aws s3 sync frontend/dist s3://YOUR-STATIC-BUCKET \
  --cache-control "public,max-age=300"
aws cloudfront create-invalidation --distribution-id XXXX --paths "/*"
```

The backend can serve the built SPA itself (default Dockerfile setup),
so this split is optional.
