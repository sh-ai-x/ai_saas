# Infrastructure boundary

This step contains local Docker packaging plus a declarative
`aws/fargate-spot-runtask.json` contract. It does not provision Terraform,
ECS/Fargate, ALB, NAT, Redis, managed secrets, or an always-on service. The
AWS contract is for an interruptible worker task only and makes no commercial
SLA or multi-AZ availability claim.
