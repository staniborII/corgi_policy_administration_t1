#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { NetworkStack } from '../lib/stacks/network-stack';
import { DatabaseStack } from '../lib/stacks/database-stack';
import { EcsStack } from '../lib/stacks/ecs-stack';
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

// 1. Network foundation - VPC, subnets, SGs
const network = new NetworkStack(app, 'CorgiNetwork', { env });

// 2. Database - RDS PostgreSQL + RDS Proxy in isolated subnets
const database = new DatabaseStack(app, 'CorgiDatabase', {
  env,
  vpc: network.vpc,
  ecsSg: network.ecsSg,
  dbInstanceType: config.dbInstanceType,
  dbMultiAz: config.dbMultiAz,
  dbAllocatedStorage: config.dbAllocatedStorage,
});

// 3. ECS - Fargate service, ALB, ECR, Secrets Manager
const ecsStack = new EcsStack(app, 'CorgiEcs', {
  env,
  vpc: network.vpc,
  albSg: network.albSg,
  ecsSg: network.ecsSg,
  dbSecret: database.dbSecret,
  rdsProxy: database.rdsProxy,
  rdsProxySg: database.rdsProxySg,
  cpu: config.cpu,
  memory: config.memory,
  desiredCount: config.desiredCount,
  serverDomainName: config.serverDomainName || undefined,
  hostedZoneId: config.hostedZoneId || undefined,
  hostedZoneName: config.hostedZoneName || undefined,
  certificateArn: config.certificateArn || undefined,
});

// 4. Frontend + Edge - S3, CloudFront OAC, WAF
new FrontendStack(app, 'CorgiFrontend', {
  env,
  alb: ecsStack.alb,
  webDomainName: config.webDomainName || undefined,
  hostedZoneId: config.hostedZoneId || undefined,
  hostedZoneName: config.hostedZoneName || undefined,
  certificateArn: config.certificateArn || undefined,
});

app.synth();
