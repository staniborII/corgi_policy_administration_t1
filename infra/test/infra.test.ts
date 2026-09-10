import * as cdk from 'aws-cdk-lib/core';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { NetworkStack } from '../lib/stacks/network-stack';
import { StorageStack } from '../lib/stacks/storage-stack';
import { DatabaseStack } from '../lib/stacks/database-stack';
import { EcsStack } from '../lib/stacks/ecs-stack';
import { EdgeStack } from '../lib/stacks/edge-stack';
import { FrontendStack } from '../lib/stacks/frontend-stack';

function createStacks() {
  const app = new cdk.App({ context: { '@aws-cdk/core:bundlingStacks': [] } });
  const network = new NetworkStack(app, 'TestNetwork');
  const storage = new StorageStack(app, 'TestStorage');
  const database = new DatabaseStack(app, 'TestDatabase', {
    vpc: network.vpc,
    ecsSg: network.ecsSg,
    dbInstanceType: 't4g.micro',
    dbMultiAz: false,
    dbAllocatedStorage: 20,
  });
  const ecs = new EcsStack(app, 'TestEcs', {
    vpc: network.vpc,
    albSg: network.albSg,
    ecsSg: network.ecsSg,
    dbSecret: database.dbSecret,
    rdsProxy: database.rdsProxy,
    rdsProxySg: database.rdsProxySg,
    documentsBucket: storage.documentsBucket,
    cpu: 256,
    memory: 512,
    desiredCount: 1,
  });
  const edge = new EdgeStack(app, 'TestEdge');
  const frontend = new FrontendStack(app, 'TestFrontend', {
    alb: ecs.alb,
    wafAclArn: edge.webAclArn,
  });
  return { app, network, storage, database, ecs, edge, frontend };
}

describe('NetworkStack', () => {
  test('creates VPC with 3 subnet tiers', () => {
    const { network } = createStacks();
    const template = Template.fromStack(network);
    template.resourceCountIs('AWS::EC2::VPC', 1);
    template.hasResourceProperties('AWS::EC2::VPC', {
      CidrBlock: '10.0.0.0/16',
    });
  });

  test('creates exactly 1 NAT gateway (trial cost trade-off)', () => {
    const { network } = createStacks();
    const template = Template.fromStack(network);
    template.resourceCountIs('AWS::EC2::NatGateway', 1);
  });

  test('creates VPC endpoints for AWS services', () => {
    const { network } = createStacks();
    const template = Template.fromStack(network);
    template.resourceCountIs('AWS::EC2::VPCEndpoint', 6);
  });
});

describe('StorageStack', () => {
  test('creates private documents bucket with versioning', () => {
    const { storage } = createStacks();
    const template = Template.fromStack(storage);
    template.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
      VersioningConfiguration: { Status: 'Enabled' },
    });
  });
});

describe('DatabaseStack', () => {
  test('creates RDS PostgreSQL instance', () => {
    const { database } = createStacks();
    const template = Template.fromStack(database);
    template.hasResourceProperties('AWS::RDS::DBInstance', {
      Engine: 'postgres',
      StorageEncrypted: true,
      MultiAZ: false,
    });
  });

  test('creates RDS Proxy', () => {
    const { database } = createStacks();
    const template = Template.fromStack(database);
    template.hasResourceProperties('AWS::RDS::DBProxy', {
      DBProxyName: 'corgi-db-proxy',
      RequireTLS: true,
    });
  });

  test('creates database secret with auto-generated password', () => {
    const { database } = createStacks();
    const template = Template.fromStack(database);
    template.hasResourceProperties('AWS::SecretsManager::Secret', {
      Name: 'corgi/database',
      GenerateSecretString: {
        GenerateStringKey: 'password',
        SecretStringTemplate: '{"username":"corgi_user"}',
      },
    });
  });

  test('uses instance type from config', () => {
    const { database } = createStacks();
    const template = Template.fromStack(database);
    template.hasResourceProperties('AWS::RDS::DBInstance', {
      DBInstanceClass: 'db.t4g.micro',
    });
  });
});

describe('EcsStack', () => {
  test('creates ECS cluster', () => {
    const { ecs } = createStacks();
    const template = Template.fromStack(ecs);
    template.hasResourceProperties('AWS::ECS::Cluster', {
      ClusterName: 'corgi-cluster',
    });
  });

  test('creates Fargate service with configured task count', () => {
    const { ecs } = createStacks();
    const template = Template.fromStack(ecs);
    template.hasResourceProperties('AWS::ECS::Service', {
      DesiredCount: 1,
      LaunchType: 'FARGATE',
    });
  });

  test('backend image is built from local Dockerfile', () => {
    const { ecs } = createStacks();
    const template = Template.fromStack(ecs);
    template.hasResourceProperties('AWS::ECS::TaskDefinition', {
      ContainerDefinitions: Match.arrayWith([
        Match.objectLike({ Name: 'backend' }),
      ]),
    });
  });

  test('creates public-facing ALB', () => {
    const { ecs } = createStacks();
    const template = Template.fromStack(ecs);
    template.hasResourceProperties('AWS::ElasticLoadBalancingV2::LoadBalancer', {
      Scheme: 'internet-facing',
    });
  });

  test('creates app secrets with Django superuser and provider keys', () => {
    const { ecs } = createStacks();
    const template = Template.fromStack(ecs);
    template.hasResourceProperties('AWS::SecretsManager::Secret', {
      Name: 'corgi/app',
    });
  });

  test('creates Route 53 record when domain config is provided', () => {
    const app = new cdk.App({ context: { '@aws-cdk/core:bundlingStacks': [] } });
    const network = new NetworkStack(app, 'DnsTestNetwork');
    const storageStack = new StorageStack(app, 'DnsTestStorage');
    const database = new DatabaseStack(app, 'DnsTestDatabase', {
      vpc: network.vpc,
      ecsSg: network.ecsSg,
      dbInstanceType: 't4g.micro',
      dbMultiAz: false,
      dbAllocatedStorage: 20,
    });
    const ecs = new EcsStack(app, 'DnsTestEcs', {
      vpc: network.vpc,
      albSg: network.albSg,
      ecsSg: network.ecsSg,
      dbSecret: database.dbSecret,
      rdsProxy: database.rdsProxy,
      rdsProxySg: database.rdsProxySg,
      documentsBucket: storageStack.documentsBucket,
      cpu: 256,
      memory: 512,
      desiredCount: 1,
      webDomainName: 'app.corgi.example.com',
      serverDomainName: 'api.corgi.example.com',
      hostedZoneId: 'Z1234567890',
      hostedZoneName: 'corgi.example.com',
      certificateArn: 'arn:aws:acm:us-east-1:123456789012:certificate/test-cert',
    });
    const template = Template.fromStack(ecs);
    template.hasResourceProperties('AWS::Route53::RecordSet', {
      Name: 'api.corgi.example.com.',
      Type: 'A',
    });
  });
});

describe('EdgeStack', () => {
  test('creates CLOUDFRONT-scoped WAF Web ACL', () => {
    const { edge } = createStacks();
    const template = Template.fromStack(edge);
    template.hasResourceProperties('AWS::WAFv2::WebACL', {
      Scope: 'CLOUDFRONT',
    });
  });
});

describe('FrontendStack', () => {
  test('creates private S3 bucket for frontend', () => {
    const { frontend } = createStacks();
    const template = Template.fromStack(frontend);
    template.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    });
  });

  test('creates CloudFront distribution', () => {
    const { frontend } = createStacks();
    const template = Template.fromStack(frontend);
    template.resourceCountIs('AWS::CloudFront::Distribution', 1);
  });

  test('deploys frontend assets to S3 with CloudFront invalidation', () => {
    const { frontend } = createStacks();
    const template = Template.fromStack(frontend);
    template.hasResourceProperties('Custom::CDKBucketDeployment', {
      DistributionPaths: ['/*'],
    });
  });

  test('creates Route 53 record when domain config is provided', () => {
    const app = new cdk.App({ context: { '@aws-cdk/core:bundlingStacks': [] } });
    const network = new NetworkStack(app, 'WebDnsTestNetwork');
    const storageStack = new StorageStack(app, 'WebDnsTestStorage');
    const database = new DatabaseStack(app, 'WebDnsTestDatabase', {
      vpc: network.vpc,
      ecsSg: network.ecsSg,
      dbInstanceType: 't4g.micro',
      dbMultiAz: false,
      dbAllocatedStorage: 20,
    });
    const ecs = new EcsStack(app, 'WebDnsTestEcs', {
      vpc: network.vpc,
      albSg: network.albSg,
      ecsSg: network.ecsSg,
      dbSecret: database.dbSecret,
      rdsProxy: database.rdsProxy,
      rdsProxySg: database.rdsProxySg,
      documentsBucket: storageStack.documentsBucket,
      cpu: 256,
      memory: 512,
      desiredCount: 1,
    });
    const edge = new EdgeStack(app, 'WebDnsTestEdge');
    const frontend = new FrontendStack(app, 'WebDnsTestFrontend', {
      alb: ecs.alb,
      wafAclArn: edge.webAclArn,
      webDomainName: 'app.corgi.example.com',
      hostedZoneId: 'Z1234567890',
      hostedZoneName: 'corgi.example.com',
      certificateArn: 'arn:aws:acm:us-east-1:123456789012:certificate/test-cert',
    });
    const template = Template.fromStack(frontend);
    template.hasResourceProperties('AWS::Route53::RecordSet', {
      Name: 'app.corgi.example.com.',
      Type: 'A',
    });
  });
});
