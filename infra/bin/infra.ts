#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { NetworkStack } from '../lib/stacks/network-stack';
import { StorageStack } from '../lib/stacks/storage-stack';
import { DatabaseStack } from '../lib/stacks/database-stack';
import { CacheStack } from '../lib/stacks/cache-stack';
import { EcsStack } from '../lib/stacks/ecs-stack';
import { EdgeStack } from '../lib/stacks/edge-stack';
import { FrontendStack } from '../lib/stacks/frontend-stack';
import { loadConfig } from '../lib/config';

const app = new cdk.App();

const stage = app.node.tryGetContext('stage') || 'staging';
const config = loadConfig(stage);

// Only set env when account is explicitly configured — keeps synth
// environment-agnostic until the user fills in config.yaml.
const account = config.account || undefined;
const region = config.region || 'us-east-1';
const env = account ? { account, region } : undefined;

// CLOUDFRONT-scoped WAF must be in us-east-1 regardless of main region
const edgeEnv = account ? { account, region: 'us-east-1' } : undefined;

// 1. Network foundation - VPC, subnets, SGs
const network = new NetworkStack(app, 'CorgiNetwork', {
  env,
  allowedIps: config.allowedIps,
});

// 2. Storage - S3 buckets for policy documents
const storage = new StorageStack(app, 'CorgiStorage', { env });

// 3. Database - RDS PostgreSQL + RDS Proxy in isolated subnets
const database = new DatabaseStack(app, 'CorgiDatabase', {
  env,
  vpc: network.vpc,
  ecsSg: network.ecsSg,
  dbInstanceType: config.dbInstanceType,
  dbMultiAz: config.dbMultiAz,
  dbAllocatedStorage: config.dbAllocatedStorage,
});

// 3b. Cache - ElastiCache Redis for Channels
const cache = new CacheStack(app, 'CorgiCache', {
  env,
  vpc: network.vpc,
  ecsSg: network.ecsSg,
});

// 4. ECS - Fargate service, ALB, ECR, Secrets Manager
const ecsStack = new EcsStack(app, 'CorgiEcs', {
  env,
  vpc: network.vpc,
  albSg: network.albSg,
  ecsSg: network.ecsSg,
  dbSecret: database.dbSecret,
  rdsProxy: database.rdsProxy,
  rdsProxySg: database.rdsProxySg,
  documentsBucket: storage.documentsBucket,
  redisUrl: cache.redisUrl,
  cpu: config.cpu,
  memory: config.memory,
  desiredCount: config.desiredCount,
  webDomainName: config.webDomainName || undefined,
  serverDomainName: config.serverDomainName || undefined,
  hostedZoneId: config.hostedZoneId || undefined,
  hostedZoneName: config.hostedZoneName || undefined,
  certificateArn: config.certificateArn || undefined,
});

// 5a. Edge - WAF (CLOUDFRONT scope, must be us-east-1)
const edge = new EdgeStack(app, 'CorgiEdge', { env: edgeEnv });

// 5b. Frontend - S3, CloudFront OAC (consumes WAF ARN cross-region)
new FrontendStack(app, 'CorgiFrontend', {
  env,
  crossRegionReferences: true,
  alb: ecsStack.alb,
  wafAclArn: edge.webAclArn,
  webDomainName: config.webDomainName || undefined,
  hostedZoneId: config.hostedZoneId || undefined,
  hostedZoneName: config.hostedZoneName || undefined,
  certificateArn: config.certificateArn || undefined,
});

app.synth();
