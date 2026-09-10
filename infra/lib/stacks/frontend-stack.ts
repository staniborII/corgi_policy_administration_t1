import * as cdk from 'aws-cdk-lib/core';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as path from 'path';
import { Construct } from 'constructs';

export interface FrontendStackProps extends cdk.StackProps {
  alb: elbv2.ApplicationLoadBalancer;
  wafAclArn: string;

  webDomainName?: string;
  hostedZoneId?: string;
  hostedZoneName?: string;
  certificateArn?: string;
}

export class FrontendStack extends cdk.Stack {
  public readonly distribution: cloudfront.Distribution;
  public readonly frontendBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: FrontendStackProps) {
    super(scope, id, props);

    const { alb } = props;

    const hasCert = !!props.certificateArn;
    const hasHostedZone = !!props.hostedZoneId && !!props.hostedZoneName;
    const hasWebDomain = !!props.webDomainName && hasCert;

    // Private S3 bucket for static frontend
    this.frontendBucket = new s3.Bucket(this, 'FrontendBucket', {
      bucketName: `corgi-frontend-${this.account}-${this.region}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // CloudFront OAC for S3
    const oac = new cloudfront.S3OriginAccessControl(this, 'FrontendOac', {
      signing: cloudfront.Signing.SIGV4_NO_OVERRIDE,
    });

    const s3Origin = origins.S3BucketOrigin.withOriginAccessControl(this.frontendBucket, {
      originAccessControl: oac,
    });

    const albOrigin = new origins.HttpOrigin(alb.loadBalancerDnsName, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      httpPort: 80,
    });

    // Optional custom domain + TLS certificate for CloudFront
    const certificate = hasWebDomain
      ? acm.Certificate.fromCertificateArn(this, 'CloudFrontCert', props.certificateArn!)
      : undefined;

    this.distribution = new cloudfront.Distribution(this, 'CorgiDistribution', {
      defaultBehavior: {
        origin: s3Origin,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      additionalBehaviors: {
        '/api/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        },
        '/health/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        },
        '/admin/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        },
        '/webhooks/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        },
        '/ws/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        },
        '/static/*': {
          origin: albOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        },
      },
      defaultRootObject: 'index.html',
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
          ttl: cdk.Duration.seconds(0),
        },
        {
          httpStatus: 403,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
          ttl: cdk.Duration.seconds(0),
        },
      ],
      webAclId: props.wafAclArn,
      ...(hasWebDomain ? {
        domainNames: [props.webDomainName!],
        certificate,
      } : {}),
    });

    // Route 53 alias for custom web domain
    if (hasWebDomain && hasHostedZone) {
      const zone = route53.HostedZone.fromHostedZoneAttributes(this, 'WebZone', {
        hostedZoneId: props.hostedZoneId!,
        zoneName: props.hostedZoneName!,
      });
      new route53.ARecord(this, 'WebDns', {
        zone,
        recordName: props.webDomainName,
        target: route53.RecordTarget.fromAlias(new targets.CloudFrontTarget(this.distribution)),
      });
    }

    // Build and deploy frontend to S3, invalidate CloudFront
    // The `build` command in cdk.json runs `npm run build` before synth.
    // Local bundling reuses existing out/ if available, or builds fresh.
    const frontendPath = path.join(__dirname, '..', '..', '..', 'frontend');

    new s3deploy.BucketDeployment(this, 'DeployFrontend', {
      sources: [
        s3deploy.Source.asset(frontendPath, {
          exclude: ['node_modules', '.next'],
          bundling: {
            image: cdk.DockerImage.fromRegistry('node:20-slim'),
            command: [
              'bash', '-c',
              'cd /asset-input && npm install && npm run build && cp -r out/* /asset-output/',
            ],
            environment: { NEXT_PUBLIC_API_URL: '' },
            local: {
              tryBundle(outputDir: string): boolean {
                const fs = require('fs');
                const outDir = path.join(frontendPath, 'out');

                if (fs.existsSync(path.join(outDir, 'index.html'))) {
                  fs.cpSync(outDir, outputDir, { recursive: true });
                  return true;
                }

                try {
                  const { execSync } = require('child_process');
                  execSync('npm install', { cwd: frontendPath, stdio: 'inherit' });
                  execSync('npm run build', { cwd: frontendPath, stdio: 'inherit' });
                  fs.cpSync(outDir, outputDir, { recursive: true });
                  return true;
                } catch {
                  return false;
                }
              },
            },
          },
        }),
      ],
      destinationBucket: this.frontendBucket,
      distribution: this.distribution,
      distributionPaths: ['/*'],
    });

    const frontendUrl = hasWebDomain
      ? `https://${props.webDomainName}`
      : `https://${this.distribution.distributionDomainName}`;

    new ssm.StringParameter(this, 'FrontendUrlParam', {
      parameterName: '/corgi/frontend-url',
      stringValue: frontendUrl,
      description: 'Resolved frontend URL (custom domain or CloudFront distribution)',
    });

    new cdk.CfnOutput(this, 'CloudFrontUrl', { value: frontendUrl });
    new cdk.CfnOutput(this, 'FrontendBucketName', {
      value: this.frontendBucket.bucketName,
    });
    new cdk.CfnOutput(this, 'DistributionId', {
      value: this.distribution.distributionId,
    });
  }
}
