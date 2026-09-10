import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as path from 'path';
import { Construct } from 'constructs';

export interface EcsStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  albSg: ec2.SecurityGroup;
  ecsSg: ec2.SecurityGroup;
  dbSecret: secretsmanager.ISecret;
  rdsProxy: rds.DatabaseProxy;
  rdsProxySg: ec2.SecurityGroup;
  documentsBucket: s3.Bucket;

  cpu: number;
  memory: number;
  desiredCount: number;
  redisUrl?: string;

  webDomainName?: string;
  serverDomainName?: string;
  hostedZoneId?: string;
  hostedZoneName?: string;
  certificateArn?: string;
}

export class EcsStack extends cdk.Stack {
  public readonly alb: elbv2.ApplicationLoadBalancer;

  constructor(scope: Construct, id: string, props: EcsStackProps) {
    super(scope, id, props);

    const { vpc, albSg, ecsSg, dbSecret, rdsProxy, documentsBucket } = props;

    const hasCert = !!props.certificateArn;
    const hasHostedZone = !!props.hostedZoneId && !!props.hostedZoneName;
    const hasServerDomain = !!props.serverDomainName && hasCert && hasHostedZone;

    // Backend Docker image — built and pushed automatically during cdk deploy
    const backendImage = ecs.ContainerImage.fromAsset(
      path.join(__dirname, '..', '..', '..', 'backend'),
    );

    // Application secrets: Django, superuser, Stripe, Persona
    // Update values in AWS Console after initial deployment
    const appSecrets = new secretsmanager.Secret(this, 'AppSecrets', {
      secretName: 'corgi/app',
      secretStringValue: cdk.SecretValue.unsafePlainText(JSON.stringify({
        DJANGO_SECRET_KEY: 'CHANGE-ME-IN-CONSOLE',
        DJANGO_SUPERUSER_USERNAME: 'admin',
        DJANGO_SUPERUSER_EMAIL: 'admin@corgi.local',
        DJANGO_SUPERUSER_PASSWORD: 'CHANGE-ME-IN-CONSOLE',
        STRIPE_SECRET_KEY: '',
        STRIPE_WEBHOOK_SECRET: '',
        STRIPE_PUBLISHABLE_KEY: '',
        PERSONA_API_KEY: '',
        PERSONA_WEBHOOK_SECRET: '',
        PERSONA_TEMPLATE_ID: '',
      })),
    });

    // Public-facing ALB so it's reachable via default DNS or custom domain
    this.alb = new elbv2.ApplicationLoadBalancer(this, 'CorgiAlb', {
      vpc,
      internetFacing: true,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroup: albSg,
    });

    // ECS cluster
    const cluster = new ecs.Cluster(this, 'CorgiCluster', {
      vpc,
      clusterName: 'corgi-cluster',
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
    });

    // Log group
    const logGroup = new logs.LogGroup(this, 'CorgiBackendLogs', {
      logGroupName: '/ecs/corgi-backend',
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Task definition with all secrets injected from Secrets Manager
    const taskDef = new ecs.FargateTaskDefinition(this, 'CorgiTaskDef', {
      memoryLimitMiB: props.memory,
      cpu: props.cpu,
    });

    dbSecret.grantRead(taskDef.taskRole);
    appSecrets.grantRead(taskDef.taskRole);
    documentsBucket.grantReadWrite(taskDef.taskRole);

    const ssmParamName = '/corgi/frontend-url';
    taskDef.taskRole.addToPrincipalPolicy(new iam.PolicyStatement({
      actions: ['ssm:GetParameter'],
      resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter${ssmParamName}`],
    }));

    const rdsProxyEndpoint = rdsProxy.endpoint;

    const albDns = this.alb.loadBalancerDnsName;
    const hostParts = [albDns];
    if (props.serverDomainName) hostParts.push(props.serverDomainName);
    if (props.webDomainName) hostParts.push(props.webDomainName);

    const environment: Record<string, string> = {
      DJANGO_ALLOWED_HOSTS: hostParts.join(','),
      DJANGO_DEBUG: 'false',
      WEB_CONCURRENCY: '2',
      PORT: '8000',
      DB_HOST: rdsProxyEndpoint,
      DB_PORT: '5432',
      DB_NAME: 'corgi',
      DB_TYPE: 'postgres',
      DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
      AWS_REGION: props.env?.region || 'us-east-1',
      FRONTEND_URL_SSM_PARAM: ssmParamName,
      DB_SSLMODE: 'require',
      ...(props.redisUrl ? { REDIS_URL: props.redisUrl } : {}),
    };

    if (props.webDomainName) {
      const frontendOrigin = `https://${props.webDomainName}`;
      environment.FRONTEND_URL = frontendOrigin;
      environment.CORS_ALLOWED_ORIGINS = frontendOrigin;
      environment.CSRF_TRUSTED_ORIGINS = frontendOrigin;
    }

    taskDef.addContainer('backend', {
      image: backendImage,
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'backend',
        logGroup,
      }),
      environment,
      secrets: {
        DB_USER: ecs.Secret.fromSecretsManager(dbSecret, 'username'),
        DB_PASSWORD: ecs.Secret.fromSecretsManager(dbSecret, 'password'),
        DJANGO_SECRET_KEY: ecs.Secret.fromSecretsManager(appSecrets, 'DJANGO_SECRET_KEY'),
        DJANGO_SUPERUSER_USERNAME: ecs.Secret.fromSecretsManager(appSecrets, 'DJANGO_SUPERUSER_USERNAME'),
        DJANGO_SUPERUSER_EMAIL: ecs.Secret.fromSecretsManager(appSecrets, 'DJANGO_SUPERUSER_EMAIL'),
        DJANGO_SUPERUSER_PASSWORD: ecs.Secret.fromSecretsManager(appSecrets, 'DJANGO_SUPERUSER_PASSWORD'),
        STRIPE_SECRET_KEY: ecs.Secret.fromSecretsManager(appSecrets, 'STRIPE_SECRET_KEY'),
        STRIPE_WEBHOOK_SECRET: ecs.Secret.fromSecretsManager(appSecrets, 'STRIPE_WEBHOOK_SECRET'),
        STRIPE_PUBLISHABLE_KEY: ecs.Secret.fromSecretsManager(appSecrets, 'STRIPE_PUBLISHABLE_KEY'),
        PERSONA_API_KEY: ecs.Secret.fromSecretsManager(appSecrets, 'PERSONA_API_KEY'),
        PERSONA_WEBHOOK_SECRET: ecs.Secret.fromSecretsManager(appSecrets, 'PERSONA_WEBHOOK_SECRET'),
        PERSONA_TEMPLATE_ID: ecs.Secret.fromSecretsManager(appSecrets, 'PERSONA_TEMPLATE_ID'),
      },
      portMappings: [{ containerPort: 8000 }],
      healthCheck: {
        command: ['CMD-SHELL', 'python -c "import urllib.request; urllib.request.urlopen(\'http://localhost:8000/health/\')" || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // Optional TLS certificate for HTTPS
    const certificate = hasCert
      ? acm.Certificate.fromCertificateArn(this, 'AlbCert', props.certificateArn!)
      : undefined;

    const fargateService = new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'CorgiService', {
      cluster,
      taskDefinition: taskDef,
      loadBalancer: this.alb,
      securityGroups: [ecsSg],
      assignPublicIp: false,
      desiredCount: props.desiredCount,
      circuitBreaker: { enable: true, rollback: true },
      minHealthyPercent: 100,
      healthCheckGracePeriod: cdk.Duration.seconds(300),
      ...(certificate
        ? { certificate, redirectHTTP: true }
        : { listenerPort: 80 }),
    });

    fargateService.targetGroup.configureHealthCheck({
      path: '/health/',
      interval: cdk.Duration.seconds(30),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    // Route 53 alias for custom API domain
    if (hasServerDomain) {
      const zone = route53.HostedZone.fromHostedZoneAttributes(this, 'ApiZone', {
        hostedZoneId: props.hostedZoneId!,
        zoneName: props.hostedZoneName!,
      });
      new route53.ARecord(this, 'ApiDns', {
        zone,
        recordName: props.serverDomainName,
        target: route53.RecordTarget.fromAlias(new targets.LoadBalancerTarget(this.alb)),
      });
    }

    new cdk.CfnOutput(this, 'AlbDnsName', { value: this.alb.loadBalancerDnsName });
    new cdk.CfnOutput(this, 'ClusterName', { value: cluster.clusterName });
    if (props.serverDomainName) {
      new cdk.CfnOutput(this, 'ApiUrl', {
        value: `https://${props.serverDomainName}`,
      });
    }
  }
}
